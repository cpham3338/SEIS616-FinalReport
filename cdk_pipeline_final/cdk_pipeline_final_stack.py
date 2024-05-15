# Chinh Pham SEIS616 Final
# Link to HW5 template - https://github.com/cpham3338/SEIS616Homework5.git

import os.path
import aws_cdk as cdk

from aws_cdk import(
    Duration,
    Stack,
    aws_autoscaling as autoscaling,
    aws_codebuild as codebuild,
    aws_codecommit as codecommit,
    aws_codedeploy as codedeploy,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_s3 as s3,
    CfnParameter
)

from constructs import Construct

class CdkPipelineFinalStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #PARAMETER
        YourIP = CfnParameter(
            self, "YourIP", 
            type="String",
            description="Enter your IP address in CIDR notation. Example: \"100.22.33.250/32\"",
            default="76.17.205.87/32"
        )        

        # RESOURCES
        
        # Create Codecommit Repo
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_codecommit/CfnRepository.html
        # https://constructs.dev/packages/aws-cdk-lib/v/2.122.0/api/CfnRepository?lang=typescript&submodule=aws_codecommit
        javaProjectRepo = codecommit.CfnRepository(
            self, 'JavaProjectRepo',
            repository_name = 'java-project',
            repository_description = 'Java-project source code',
            
            code = {
                's3': {
                    'bucket': 'seis665-public',
                    'key': 'java-project.zip',
                },
            },
        )
        
        # Create s3 Bucket
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/CfnBucket.html
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/CfnBucket.html#aws_cdk.aws_s3.CfnBucket.BucketEncryptionProperty
        artifactBucket = s3.CfnBucket(
            self, 'ArtifactBucket',
            bucket_name="seis616bucket",
            bucket_encryption = {
                'serverSideEncryptionConfiguration': [{
                    'serverSideEncryptionByDefault': {
                        'sseAlgorithm': 'AES256',
                        
                        # the properties below are optional
                        # kms_master_key_id="kmsMasterKeyId"
                    }
                }]
            }
        )
        
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_s3/CfnBucketPolicy.html
        artifactBucketPolicy = s3.CfnBucketPolicy(
            self, 'ArtifactBucketPolicy',
            bucket = "seis616bucket",
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "DenyUnEncryptedObjectUploads",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:PutObject",
                        "Resource": {
                            "Fn::Join": [
                                "",
                                [
                                    {
                                        "Fn::GetAtt": [
                                            "ArtifactBucket",
                                            "Arn"
                                        ]
                                    },
                                    "/*"
                                ]
                            ]
                        },
                        "Condition": {
                            "StringNotEquals": {
                                "s3:x-amz-server-side-encryption": "aws:kms"
                            }
                        }
                    }
                ]
            }
        )  
        
        #Create VPC
        vpc = ec2.Vpc(
            self, "myVPC",
            vpc_name = "myVpc",
            availability_zones=["us-east-1a", "us-east-1b"],
            #max_azs=1,
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            subnet_configuration=[ 
                          ec2.SubnetConfiguration(name="PublicSubnet1", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                          ec2.SubnetConfiguration(name="PublicSubnet2", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24)     
            ]
        )  
        
        # Create Security Group
        WebserverSG = ec2.SecurityGroup(
            self, "WebserverSG", 
            security_group_name="WebserverSG",
            vpc=vpc,
            allow_all_outbound=True
        )
        
        # Create Security Group Ingress Rule
        WebserverSG.add_ingress_rule(
            ec2.Peer.ipv4(YourIP.value_as_string), 
            ec2.Port.tcp(22), "allow SSH access"
        )
            
        WebserverSG.add_ingress_rule(
            ec2.Peer.ipv4("0.0.0.0/0"), 
            ec2.Port.tcp(80), 
            "Allow incoming requests on port 80"
        )
        
        #Create Load Balancer
        lb = elbv2.ApplicationLoadBalancer(
            self, "ELB",
            load_balancer_name="ELB",
            vpc=vpc,
            internet_facing=True,
            security_group=WebserverSG,
            vpc_subnets=ec2.SubnetSelection(one_per_az=True)
        )
        
        # Add Listener
        listener = lb.add_listener(
            "Listener", 
            port=80, 
            open=True
        )
        
        #Create Target Group
        target_groups= elbv2.ApplicationTargetGroup(
            self, "ELBTargetGroup",
            target_group_name="ELBTargetGroup",
            protocol=elbv2.ApplicationProtocol.HTTP,
            port=80,
            vpc=vpc,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(
                path="/ping",
                interval=Duration.minutes(1)
            )
        )
        
        listener.add_target_groups(
            "http", 
            target_groups=[target_groups]
        )
        
        #Create Roles
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_iam/CfnRole.html
        appBuildRole = iam.CfnRole(
            self, 'AppBuildRole',
            assume_role_policy_document = {
                "Version" : "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {
                        "Service": [ "codebuild.amazonaws.com" ]
                    },
                    "Action": [ "sts:AssumeRole" ]
                }]
            },
            path = '/',
            policies = [{
                "policyName": "CodeBuildAccess",
                'policyDocument': {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Resource": [{ "Fn::Sub": "arn:aws:s3:::codepipeline-${AWS::Region}-*"}],
                        "Action": [
                            "s3:PutObject",
                            "s3:GetObject",
                            "s3:GetObjectVersion",
                            "s3:GetBucketAcl",
                            "s3:GetBucketLocation"
                        ]
                    },{
                        "Effect": "Allow",
                        "Resource": [{
                            "Fn::GetAtt": [
                                "ArtifactBucket", "Arn"
                            ]},{
                                "Fn::Join": [ "", [{
                                    "Fn::GetAtt": [
                                        "ArtifactBucket", "Arn"
                                    ]}, "/*" 
                                ]]}
                            ],
                            "Action": [
                                "s3:GetObject",
                                "s3:PutObject",
                                "s3:GetBucketAcl",
                                "s3:GetBucketLocation"
                            ]
                    },{
                        "Sid": "CodeCommitPolicy",
                        "Effect": "Allow",
                        "Action": ["codecommit:GitPull"],
                        "Resource": ["*"]
                    }]
                }
            }]
        )

        # Create the Project
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_codebuild/CfnProject.html
        appBuildProject = codebuild.CfnProject(
            self, "AppBuildProject",
            artifacts = {
                "type": "CODEPIPELINE",
            },
            description = "app build project",
            environment = {
                "computeType": "BUILD_GENERAL1_SMALL",
                "image": "aws/codebuild/standard:1.0",
                "imagePullCredentialsType": "CODEBUILD",
                "type": "LINUX_CONTAINER"                
            },
            #TypeError: type of argument service_role must be str; got dict instead
            #https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_iam/CfnRole.html
            service_role = appBuildRole.attr_arn,
            source = {"type": "CODEPIPELINE"}
        )        

        # Create Service Role
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_iam/CfnRole.html
        codePipelineServiceRole = iam.CfnRole(
            self, 'CodePipelineServiceRole',
            assume_role_policy_document = {
                "Statement": [{ 
                    "Action": [ "sts:AssumeRole" ], 
                    "Effect": "Allow", 
                    "Principal": { 
                        "Service": [ "codepipeline.amazonaws.com" ] 
                    } 
                }] 
            }, 
            path = '/service-role/',
            policies = [{
                "policyName": "ec2codedeploy",
                "policyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Resource": [{ "Fn::GetAtt": ["ArtifactBucket","Arn"]},{
                            "Fn::Join": [ "", [{
                                "Fn::GetAtt": ["ArtifactBucket","Arn"]
                                }, "/*" 
                            ]]
                        }],
                        "Action": [
                            "s3:PutObject",
                            "s3:GetObject",
                            "s3:GetBucketAcl",
                            "s3:GetBucketLocation"
                        ]
                    },{
                        "Action": [
                            "codecommit:CancelUploadArchive",
                            "codecommit:GetBranch",
                            "codecommit:GetCommit",
                            "codecommit:GetUploadArchiveStatus",
                            "codecommit:UploadArchive"
                        ],
                        "Resource": [{
                            "Fn::GetAtt": ["JavaProjectRepo","Arn"]
                        }],
                        "Effect": "Allow"
                        },{
                            "Action": [
                                "codebuild:BatchGetBuilds",
                                "codebuild:StartBuild"
                            ],
                            "Resource": [{
                                "Fn::GetAtt": ["AppBuildProject","Arn"]
                            }],
                            "Effect": "Allow"
                            }
                    ],}
                }]
        )
        
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_iam/CfnPolicy.html
        buildLogPolicy = iam.CfnPolicy(
            self, "BuildLogPolicy",
            policy_name = "BuildLogAccess",
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Resource": [{
                        "Fn::Sub": [
                            "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/codebuild/${project}",
                            {
                                "project": { "Ref": "AppBuildProject" }
                            }
                        ]
                    },{
                        "Fn::Sub": [
                            "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/codebuild/${project}:*",
                            {
                                "project": { "Ref": "AppBuildProject" }
                            }
                        ]
                            }
                        ],
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ]
                }]
          },
          roles = [appBuildRole.ref]
        )
        
        
        # Create Pipeline and add stages
        # For this assignement we don't need to implement the Deploy stage
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_codepipeline/CfnPipeline.html
        appCodePipeline = codepipeline.CfnPipeline(
            self, 'AppCodePipeline',
            role_arn = codePipelineServiceRole.attr_arn,
            #https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_codepipeline/CfnPipeline.html#aws_cdk.aws_codepipeline.CfnPipeline.ArtifactStoreProperty
            artifact_store = {
                'location': artifactBucket.ref,
                'type': 'S3',
            },
            stages = [{
                'name': 'Source',
                'actions': [{
                    'name': 'GetSource',
                    'actionTypeId': {
                        'category': 'Source',
                        'owner': 'AWS',
                        'provider': 'CodeCommit',
                        'version': '1',
                    },
                    'configuration': {
                        'RepositoryName': javaProjectRepo.attr_name,
                        'BranchName': 'main',
                        'PollForSourceChanges': 'false',
                    },
                    'outputArtifacts': [{
                        'name': 'SourceCode',
                    },],
                }]
            },{
                'name': 'Build',
                'actions': [{
                    'name': 'BuildSource',
                    'inputArtifacts': [{
                        'name': 'SourceCode',
                    },],
                    'actionTypeId': {
                        'category': 'Build',
                        'owner': 'AWS',
                        'provider': 'CodeBuild',
                        'version': '1',
                    },
                    'configuration': { 
                        'ProjectName': appBuildProject.ref,
                    },
                    'outputArtifacts': [{
                        'name': 'CodeArtifact',
                    },],
                }]
            }]
        )

            
            
        

