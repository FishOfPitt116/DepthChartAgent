from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

_PROJECT_ROOT = str(Path(__file__).parent.parent)

_BUNDLING = cdk.BundlingOptions(
    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
    command=["bash", "-c", "pip install /asset-input -t /asset-output --no-cache-dir"],
)


class DepthChartStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: str, retention_days: int, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.stage = stage
        self.retention_days = retention_days

        is_prod = stage == "prod"

        # --- S3 ---

        self.bucket = s3.Bucket(
            self, "DepthChartBucket",
            lifecycle_rules=[
                s3.LifecycleRule(expiration=cdk.Duration.days(retention_days))
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=not is_prod,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        cdk.CfnOutput(self, "BucketName", value=self.bucket.bucket_name)

        # --- DynamoDB ---

        self.table = dynamodb.Table(
            self, "RefreshTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
        )

        cdk.CfnOutput(self, "TableName", value=self.table.table_name)

        # --- CloudWatch log groups ---

        retention = logs.RetentionDays.TWO_WEEKS if not is_prod else logs.RetentionDays.ONE_MONTH

        self.api_log_group = logs.LogGroup(
            self, "ApiLogGroup",
            log_group_name=f"/aws/lambda/depth-chart-api-{stage}",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.agent_runner_log_group = logs.LogGroup(
            self, "AgentRunnerLogGroup",
            log_group_name=f"/aws/lambda/depth-chart-agent-runner-{stage}",
            retention=retention,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # --- Lambda ---

        code = lambda_.Code.from_asset(_PROJECT_ROOT, bundling=_BUNDLING)

        common_env = {
            "S3_BUCKET": self.bucket.bucket_name,
            "DYNAMODB_TABLE": self.table.table_name,
            "OPENAI_API_KEY": self.node.try_get_context("openai_api_key") or "",
            "LOG_LEVEL": "INFO",
        }

        agent_runner_fn = lambda_.Function(
            self, "AgentRunnerFunction",
            function_name=f"depth-chart-agent-runner-{stage}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=code,
            handler="depth_chart_agent.lambda_agent_runner.handler",
            log_group=self.agent_runner_log_group,
            timeout=cdk.Duration.minutes(15),
            memory_size=1024,
            environment=common_env,
        )

        api_fn = lambda_.Function(
            self, "ApiFunction",
            function_name=f"depth-chart-api-{stage}",
            runtime=lambda_.Runtime.PYTHON_3_11,
            code=code,
            handler="depth_chart_agent.lambda_api.handler",
            log_group=self.api_log_group,
            timeout=cdk.Duration.seconds(30),
            memory_size=512,
            environment={
                **common_env,
                "AGENT_RUNNER_FUNCTION_NAME": agent_runner_fn.function_name,
                "DEPTH_CHART_API_KEY": self.node.try_get_context("depth_chart_api_key") or "",
            },
        )

        # --- IAM grants ---

        self.bucket.grant_read_write(api_fn)
        self.bucket.grant_read_write(agent_runner_fn)
        self.table.grant_read_write(api_fn)
        self.table.grant_read_write(agent_runner_fn)
        agent_runner_fn.grant_invoke(api_fn)

        # --- API Gateway ---

        api = apigw.LambdaRestApi(
            self, "RestApi",
            handler=api_fn,
            deploy_options=apigw.StageOptions(stage_name=stage),
        )

        cdk.CfnOutput(self, "ApiUrl", value=api.url)
