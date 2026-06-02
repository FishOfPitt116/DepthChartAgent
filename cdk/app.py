import os

import aws_cdk as cdk

from depth_chart_stage import DepthChartStage

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region="us-east-1",
)

DepthChartStage(app, "DepthChartGamma", stage="gamma", retention_days=14, env=env)
DepthChartStage(app, "DepthChartProd", stage="prod", retention_days=28, env=env)

app.synth()
