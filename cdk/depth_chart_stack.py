import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class DepthChartStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: str, retention_days: int, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.stage = stage
        self.retention_days = retention_days

        is_prod = stage == "prod"

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

        self.table = dynamodb.Table(
            self, "RefreshTable",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=cdk.RemovalPolicy.RETAIN if is_prod else cdk.RemovalPolicy.DESTROY,
        )

        cdk.CfnOutput(self, "TableName", value=self.table.table_name)
