from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import AgentHookContext, AgentHooks, RunContextWrapper
from agents.items import ModelResponse

# GPT-5-mini pricing (per 1M tokens)
_INPUT_COST_PER_M = 0.250
_OUTPUT_COST_PER_M = 2.000

_LOG_DIR = Path(__file__).parent.parent.parent.parent / "logs"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(entry: dict) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_LOG_DIR / "audit.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


class DepthChartAgentHooks(AgentHooks):
    def __init__(self) -> None:
        self._start: float = 0.0
        self._llm_calls: int = 0
        self._session_id: str = ""

    async def on_start(self, context: AgentHookContext, agent: Any) -> None:
        self._start = time.monotonic()
        self._llm_calls = 0
        self._session_id = _now()
        print(f"[agent] starting — {agent.name}")
        _audit({"session": self._session_id, "event": "agent_start", "agent": agent.name})

    async def on_llm_end(self, context: RunContextWrapper, agent: Any, response: ModelResponse) -> None:
        self._llm_calls += 1
        u = response.usage
        cost = (u.input_tokens * _INPUT_COST_PER_M + u.output_tokens * _OUTPUT_COST_PER_M) / 1_000_000
        print(
            f"[llm]   call {self._llm_calls} — "
            f"in={u.input_tokens} out={u.output_tokens} "
            f"(${cost:.5f})"
        )
        for item in response.output:
            if hasattr(item, "arguments"):
                try:
                    args = json.loads(item.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = item.arguments
                _audit({
                    "session": self._session_id,
                    "event": "tool_input",
                    "ts": _now(),
                    "tool": item.name,
                    "arguments": args,
                })
            if hasattr(item, "content") and item.content:
                for block in item.content:
                    if hasattr(block, "text") and block.text.strip():
                        print(f"[reasoning] {block.text.strip()}")
                        _audit({
                            "session": self._session_id,
                            "event": "reasoning",
                            "ts": _now(),
                            "text": block.text.strip(),
                        })

    async def on_tool_start(self, context: RunContextWrapper, agent: Any, tool: Any) -> None:
        print(f"[tool]  → {tool.name}")

    async def on_tool_end(self, context: RunContextWrapper, agent: Any, tool: Any, result: str) -> None:
        preview = str(result)[:120].replace("\n", " ")
        print(f"[tool]  ← {tool.name}: {preview}")
        _audit({
            "session": self._session_id,
            "event": "tool_output",
            "ts": _now(),
            "tool": tool.name,
            "result": result,
        })

    async def on_end(self, context: AgentHookContext, agent: Any, output: Any) -> None:
        elapsed = time.monotonic() - self._start
        print(f"[agent] done — {self._llm_calls} LLM call(s), {elapsed:.1f}s")
        _audit({"session": self._session_id, "event": "agent_end", "elapsed_s": round(elapsed, 2)})
