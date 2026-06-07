from mangum import Mangum

from depth_chart_agent.api.app import app

handler = Mangum(app)
