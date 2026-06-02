import aws_cdk as cdk
from constructs import Construct

from depth_chart_stack import DepthChartStack


class DepthChartStage(cdk.Stage):
    def __init__(self, scope: Construct, id: str, *, stage: str, retention_days: int, **kwargs):
        super().__init__(scope, id, **kwargs)
        DepthChartStack(self, "DepthChartStack", stage=stage, retention_days=retention_days)
