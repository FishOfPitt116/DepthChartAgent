from __future__ import annotations

import logging
import time
from typing import Any

from agents import AgentHookContext, AgentHooks, RunContextWrapper
from agents.items import ModelResponse

# gpt-5-mini pricing (per 1M tokens)
_INPUT_COST_PER_M = 0.250
_OUTPUT_COST_PER_M = 2.000


class _RunLogger(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        return f"[{self.extra['run_id']}] {msg}", kwargs


class DepthChartAgentHooks(AgentHooks):
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._start: float = 0.0
        self._llm_calls: int = 0
        self._log = _RunLogger(logging.getLogger(__name__), {"run_id": run_id})

    async def on_start(self, context: AgentHookContext, agent: Any) -> None:
        self._start = time.monotonic()
        self._llm_calls = 0
        self._log.info("agent started name=%s", agent.name)

    async def on_llm_end(self, context: RunContextWrapper, agent: Any, response: ModelResponse) -> None:
        self._llm_calls += 1
        u = response.usage
        cost = (u.input_tokens * _INPUT_COST_PER_M + u.output_tokens * _OUTPUT_COST_PER_M) / 1_000_000
        self._log.info("llm call=%d in=%d out=%d cost=$%.5f", self._llm_calls, u.input_tokens, u.output_tokens, cost)

        for item in response.output:
            if hasattr(item, "arguments"):
                self._log.debug("tool input name=%s args=%s", item.name, item.arguments)
            if hasattr(item, "content") and item.content:
                for block in item.content:
                    if hasattr(block, "text") and block.text.strip():
                        self._log.debug("reasoning %s", block.text.strip())

    async def on_tool_start(self, context: RunContextWrapper, agent: Any, tool: Any) -> None:
        self._log.info("tool → %s", tool.name)

    async def on_tool_end(self, context: RunContextWrapper, agent: Any, tool: Any, result: str) -> None:
        preview = str(result)[:200].replace("\n", " ")
        self._log.info("tool ← %s: %s", tool.name, preview)
        self._log.debug("tool ← %s full result: %s", tool.name, result)

    async def on_end(self, context: AgentHookContext, agent: Any, output: Any) -> None:
        elapsed = time.monotonic() - self._start
        self._log.info("agent done llm_calls=%d elapsed=%.1fs", self._llm_calls, elapsed)
