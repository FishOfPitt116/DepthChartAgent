import aws_cdk as cdk
from constructs import Construct


class DepthChartStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: str, retention_days: int, **kwargs):
        super().__init__(scope, id, **kwargs)
        self.stage = stage
        self.retention_days = retention_days
