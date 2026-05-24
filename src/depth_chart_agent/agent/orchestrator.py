"""
Agent definition. The OpenAI Agents SDK handles the execution loop,
tool calls, and result handling via Runner — nothing to manage here.

To add a tool later: define it with @function_tool and add it to the
tools list on the Agent.
"""

from __future__ import annotations

import os

from agents import Agent

from depth_chart_agent.agent.prompt import SYSTEM_PROMPT

depth_chart_agent = Agent(
    name="DepthChartAgent",
    instructions=SYSTEM_PROMPT,
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
)
