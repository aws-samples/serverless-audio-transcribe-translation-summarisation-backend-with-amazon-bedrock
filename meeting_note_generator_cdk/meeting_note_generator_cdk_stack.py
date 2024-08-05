import os
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    aws_lambda as _lambda,
    aws_lambda_python_alpha as _lambda_python,
    aws_iam as _iam,
    aws_apigateway as _apigateway,
    aws_cognito as _cognito,
    aws_dynamodb as _dynamodb,
    aws_ses as _ses,
    aws_iam as _iam,
    custom_resources as _cr,
    aws_wafv2 as _wafv2,
    Tags,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class MeetingNoteGeneratorCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bedrock_model_id = "anthropic.claude-3-haiku-20240307-v1:0"
        self.origins = ['http://localhost:3000']
        self.ses_default_from_email = "email@address"
        self.setup_ses_email_identity = False
        self.send_email = "false"

        #create logging bucket
        self.logging_bucket = s3.Bucket(self, 'notes_application_logs_bucket',
            enforce_ssl=True,
            versioned=True,
            access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        #application bucket
        self.application_bucket = s3.Bucket(self, 'notes_application_bucket',
            enforce_ssl=True,
            versioned=True,
            access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            cors=[s3.CorsRule(
                allowed_headers=["*"],
                allowed_methods=[s3.HttpMethods.PUT],
                allowed_origins=self.origins)
            ]
        )

        #add ses email address (good if in sandbox)
        if(self.setup_ses_email_identity is True):
            self.ses_email_confirmation = _ses.CfnEmailIdentity(self, 'notes_application_ses_identity',
                email_identity=self.ses_default_from_email
            )
        
        #email sending policy for Lambda etc
        self.allow_ses_sending = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW, 
            actions=['ses:SendEmail', 'SES:SendTemplatedEmail', 'SES:SendRawEmail'],
            resources=['*']          
        )

        #create a cognito user pool and identity pool with client
        self.cognito_user_pool = _cognito.UserPool(self, 'cognito_user_pool',
            self_sign_up_enabled=True,
            auto_verify=_cognito.AutoVerifiedAttrs(email=True),
            sign_in_aliases=_cognito.SignInAliases(email=True),
            standard_attributes=_cognito.StandardAttributes(
                email=_cognito.StandardAttribute(required=True),
                phone_number=_cognito.StandardAttribute(required=False)
            ),
            mfa=_cognito.Mfa.REQUIRED,
            mfa_second_factor=_cognito.MfaSecondFactor(
                sms=False,
                otp=True
            ),
            password_policy=_cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(3)
            ),
            account_recovery=_cognito.AccountRecovery.EMAIL_ONLY,
            user_pool_name='MeetingNotesBedrockUserPool',
        )

        self.cognito_user_pool_client = _cognito.UserPoolClient(self, 'cognito_user_pool_client',
            user_pool=self.cognito_user_pool,
            generate_secret=False,
            auth_flows=_cognito.AuthFlow(
                user_password=True,
                user_srp=True
            )
        )

        #dynamodb table
        self.upload_storage_table = _dynamodb.Table(self, 'notes_application_upload_storage',
            partition_key=_dynamodb.Attribute(name='file_name', type=_dynamodb.AttributeType.STRING),
            billing_mode=_dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            encryption=_dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True
        )

        self.lambda_generate_transcription = _lambda.Function(self, 'lambda_generate_transcription',
            code=_lambda.Code.from_asset('lambda/generate_transcription'),
            handler='index.lambda_handler',
            runtime=_lambda.Runtime.PYTHON_3_11,
            timeout=Duration.seconds(60),
            memory_size=256,
            environment={
                'LOG_BUCKET': self.logging_bucket.bucket_name,
                'APPLICATION_BUCKET': self.application_bucket.bucket_name,
                'SOURCE_PREFIX': 'recordings',
                'DESTINATION_PREFIX': 'transcripts'
            }
        )
        #add event notification from S3 upload to trigger Lambda
        self.application_bucket.add_event_notification(s3.EventType.OBJECT_CREATED,
            s3_notifications.LambdaDestination(self.lambda_generate_transcription),
            s3.NotificationKeyFilter(prefix='recordings')
        )

        #permissions for Lambda to access Transcribe, S3 and Logs
        self.lambda_generate_transcription.role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name('AmazonTranscribeFullAccess')
        )
        self.lambda_generate_transcription_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=['s3:GetObject','s3:PutObject','logs:CreateLogGroup','logs:CreateLogStream','logs:PutLogEvents'],
            resources=['*']
        )
        self.lambda_generate_transcription.add_to_role_policy(self.lambda_generate_transcription_policy)
        #allow S3 to call Lambda
        self.lambda_generate_transcription.add_permission(
            's3-service-principal', 
            principal=_iam.ServicePrincipal('s3.amazonaws.com'),
            source_account=os.getenv('CDK_DEFAULT_ACCOUNT'),
            source_arn=self.application_bucket.bucket_arn
        )

        #function to create the combined file and email...
        self.lambda_generate_compiled = _lambda_python.PythonFunction(self, 'lambda_generate_compiled',
            entry='lambda/generate_compiled',
            index='index.py',
            runtime=_lambda.Runtime.PYTHON_3_11,
            timeout=Duration.seconds(300),
            memory_size=2048,
            handler='lambda_handler',
            environment={
                'LOG_BUCKET': self.logging_bucket.bucket_name,
                'APPLICATION_BUCKET': self.application_bucket.bucket_name,
                'SOURCE_PREFIX': 'transcripts',
                'NOTES_PREFIX': 'notes',
                'COMPILED_PREFIX': 'compiled',
                'TRANSLATIONS_PREFIX': 'translations',
                'BEDROCK_MODEL_ID': self.bedrock_model_id,
                'SES_SENDER_FROM': self.ses_default_from_email,
                'SES_SEND_EMAIL': self.send_email,
                'DYNAMODB_TABLE_NAME': self.upload_storage_table.table_name,
            }
        )
        #add event notification from S3 upload to trigger Lambda only if .txt file
        self.application_bucket.add_event_notification(s3.EventType.OBJECT_CREATED,
            s3_notifications.LambdaDestination(self.lambda_generate_compiled),
            s3.NotificationKeyFilter(prefix='transcripts',suffix='.txt')
        )
        #allow S3 to call Lambda
        self.lambda_generate_compiled.add_permission(
            's3-service-principal', 
            principal=_iam.ServicePrincipal('s3.amazonaws.com'),
            source_account=os.getenv('CDK_DEFAULT_ACCOUNT'),
            source_arn=self.application_bucket.bucket_arn
        )
        self.lambda_generate_compiled_policy = _iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=['s3:GetObject','s3:PutObject','dynamodb:GetItem',
                     'logs:CreateLogGroup','logs:CreateLogStream','logs:PutLogEvents',
                     'comprehend:DetectSentiment',
                     'translate:TranslateText',
                     'bedrock:InvokeModel','dynamodb:UpdateItem'],
            resources=['*'],
        )
        self.lambda_generate_compiled.add_to_role_policy(self.lambda_generate_compiled_policy)
        self.lambda_generate_compiled.add_to_role_policy(self.allow_ses_sending)

        self.api_gateway = _apigateway.RestApi(self, 'meeting_notes_api',
            rest_api_name='MeetingNotesApi',
            description='Meeting Notes API',
            deploy_options=_apigateway.StageOptions(
                stage_name='dev',
                tracing_enabled=True,
                throttling_rate_limit=10,
                throttling_burst_limit=20
            ),
            default_cors_preflight_options=_apigateway.CorsOptions(
                allow_origins=self.origins,
                allow_methods=_apigateway.Cors.ALL_METHODS,
                allow_credentials=True
            )
        )

        self.api_gateway_auth = _apigateway.CognitoUserPoolsAuthorizer(self, 'api_gateway_auth',
            cognito_user_pools=[self.cognito_user_pool]
        )

        #add WAF to API Gateway
        self.api_gw_waf = _wafv2.CfnWebACL(self, 'api_gw_waf_bedrock',
            scope="REGIONAL",
            default_action=_wafv2.CfnWebACL.DefaultActionProperty(allow=_wafv2.CfnWebACL.AllowActionProperty()),
            visibility_config=_wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name='api_gw_waf_bedrock',
                sampled_requests_enabled=True
            ),
            name='api_gw_waf_bedrock',
            rules=[
                _wafv2.CfnWebACL.RuleProperty(
                    name="AWS-AWSManagedRulesCommonRuleSet",
                    priority=0,
                    statement=_wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=_wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name="AWSManagedRulesCommonRuleSet"
                        )
                    ),
                    override_action=_wafv2.CfnWebACL.OverrideActionProperty(none={}),
                    visibility_config=_wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="AWS-AWSManagedRulesCommonRuleSet",
                        sampled_requests_enabled=True,
                    ),
                )
            ]
        )

        #setup ARN for API Gateway Stage
        region = os.getenv('CDK_DEFAULT_REGION')
        self.api_arn = f"arn:aws:apigateway:{region}::/restapis/{self.api_gateway.rest_api_id}/stages/{self.api_gateway.deployment_stage.stage_name}"

        #associate WAF to API Gateway
        self.waf_to_api_gateway = _wafv2.CfnWebACLAssociation(self, 'waf_to_api_gateway',
            resource_arn=self.api_arn,
            web_acl_arn=self.api_gw_waf.attr_arn
        )

        #pre singed URL Lambda
        self.generate_pre_signed_url_lambda = _lambda.Function(self, 'generate_pre_signed_url_lambda',
            code=_lambda.Code.from_asset('lambda/pre_signed_url'),
            handler='index.lambda_handler',
            runtime=_lambda.Runtime.PYTHON_3_11,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                'APPLICATION_BUCKET': self.application_bucket.bucket_name,
                'SOURCE_PREFIX': 'recordings',
                'DYNAMODB_TABLE_NAME': self.upload_storage_table.table_name,
                'SES_SENDER_FROM': self.ses_default_from_email,
                'SES_SEND_EMAIL': self.send_email
            }
        )
        self.application_bucket.grant_read_write(self.generate_pre_signed_url_lambda)
        self.upload_storage_table.grant_read_write_data(self.generate_pre_signed_url_lambda)
        self.generate_pre_signed_url_lambda.add_to_role_policy(self.allow_ses_sending)

        #list dynamodb objects by user lambda
        self.list_uploads_lambda = _lambda.Function(self, 'list_uploads_lambda',
            code=_lambda.Code.from_asset('lambda/list_uploads'),
            handler='index.lambda_handler',
            runtime=_lambda.Runtime.PYTHON_3_11,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                'LOG_BUCKET': self.logging_bucket.bucket_name,
                'APPLICATION_BUCKET': self.application_bucket.bucket_name,
                'SOURCE_PREFIX': 'transcripts',
                'NOTES_PREFIX': 'notes',
                'COMPILED_PREFIX': 'compiled',
                'TRANSLATIONS_PREFIX': 'translations',
                'DYNAMODB_TABLE_NAME': self.upload_storage_table.table_name,
            }
        )
        self.application_bucket.grant_read_write(self.list_uploads_lambda)
        self.upload_storage_table.grant_read_write_data(self.list_uploads_lambda)

        #get file from S3
        self.get_file_from_s3_lambda = _lambda.Function(self, 'get_file_from_s3_lambda',
            code=_lambda.Code.from_asset('lambda/get_file_from_s3'),
            handler='index.lambda_handler',
            runtime=_lambda.Runtime.PYTHON_3_11,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                'LOG_BUCKET': self.logging_bucket.bucket_name,
                'APPLICATION_BUCKET': self.application_bucket.bucket_name,
                'SOURCE_PREFIX': 'transcripts',
                'NOTES_PREFIX': 'notes',
                'COMPILED_PREFIX': 'compiled',
                'TRANSLATIONS_PREFIX': 'translations',
                'DYNAMODB_TABLE_NAME': self.upload_storage_table.table_name,
            }
        )
        self.application_bucket.grant_read_write(self.get_file_from_s3_lambda)
        self.upload_storage_table.grant_read_write_data(self.get_file_from_s3_lambda)

        #ensure api call for pre signed URL needs cognito auth
        self.api_pre_signed = self.api_gateway.root.add_resource('pre_signed_url')
        self.api_pre_signed_post_method = self.api_pre_signed.add_method(
            http_method='GET',
            integration=_apigateway.LambdaIntegration(
                handler=self.generate_pre_signed_url_lambda
            ),
            authorizer=self.api_gateway_auth,
            authorization_type=_apigateway.AuthorizationType.COGNITO
        )
        #ensure api call for pre signed URL needs cognito auth
        self.api_uploads = self.api_gateway.root.add_resource('list_uploads')
        self.api_uploads_get = self.api_uploads.add_method(
            http_method='GET',
            integration=_apigateway.LambdaIntegration(
                handler=self.list_uploads_lambda
            ),
            authorizer=self.api_gateway_auth,
            authorization_type=_apigateway.AuthorizationType.COGNITO
        )
        #get file
        self.api_uploads = self.api_gateway.root.add_resource('get_file')
        self.api_uploads_get = self.api_uploads.add_method(
            http_method='GET',
            integration=_apigateway.LambdaIntegration(
                handler=self.get_file_from_s3_lambda
            ),
            authorizer=self.api_gateway_auth,
            authorization_type=_apigateway.AuthorizationType.COGNITO
        )

        CfnOutput(self, 'UserPoolID', value=self.cognito_user_pool.user_pool_id)
        CfnOutput(self, 'UserPoolClientID', value=self.cognito_user_pool_client.user_pool_client_id)
        
        Tags.of(self).add('Application','MeetingNotesApp')
