from __future__ import annotations

import time
from typing import Any

from agents import AgentHookContext, AgentHooks, RunContextWrapper
from agents.items import ModelResponse

# GPT-4o-mini pricing (per 1M tokens)
_INPUT_COST_PER_M = 0.150
_OUTPUT_COST_PER_M = 0.600


class DepthChartAgentHooks(AgentHooks):
    def __init__(self) -> None:
        self._start: float = 0.0
        self._llm_calls: int = 0

    async def on_start(self, context: AgentHookContext, agent: Any) -> None:
        self._start = time.monotonic()
        self._llm_calls = 0
        print(f"[agent] starting — {agent.name}")

    async def on_llm_end(self, context: RunContextWrapper, agent: Any, response: ModelResponse) -> None:
        self._llm_calls += 1
        u = response.usage
        cost = (u.input_tokens * _INPUT_COST_PER_M + u.output_tokens * _OUTPUT_COST_PER_M) / 1_000_000
        print(
            f"[llm]   call {self._llm_calls} — "
            f"in={u.input_tokens} out={u.output_tokens} "
            f"(${cost:.5f})"
        )

    async def on_tool_start(self, context: RunContextWrapper, agent: Any, tool: Any) -> None:
        print(f"[tool]  → {tool.name}")

    async def on_tool_end(self, context: RunContextWrapper, agent: Any, tool: Any, result: str) -> None:
        preview = result[:120].replace("\n", " ")
        print(f"[tool]  ← {tool.name}: {preview}")

    async def on_end(self, context: AgentHookContext, agent: Any, output: Any) -> None:
        elapsed = time.monotonic() - self._start
        print(f"[agent] done — {self._llm_calls} LLM call(s), {elapsed:.1f}s")
