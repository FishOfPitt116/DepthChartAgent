from __future__ import annotations

import os
import secrets

from agents import Agent

from depth_chart_agent.agent.hooks import DepthChartAgentHooks
from depth_chart_agent.agent.prompt import SYSTEM_PROMPT
from depth_chart_agent.tools.depth_chart_tools import DEPTH_CHART_TOOLS
from depth_chart_agent.tools.mlb_tools import MLB_CLIENT_TOOLS


def make_agent(run_id: str | None = None) -> Agent:
    return Agent(
        name="DepthChartAgent",
        instructions=SYSTEM_PROMPT,
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        tools=MLB_CLIENT_TOOLS + DEPTH_CHART_TOOLS,
        hooks=DepthChartAgentHooks(run_id=run_id or secrets.token_hex(8)),
    )
