from __future__ import annotations

import asyncio
import logging

from agents import Runner

from depth_chart_agent.agent.orchestrator import make_agent
from depth_chart_agent.api.refresh import RefreshManager
from depth_chart_agent.logging_config import configure_logging

configure_logging()

logger = logging.getLogger(__name__)

_refresh = RefreshManager()


def handler(event: dict, context) -> None:
    asyncio.run(_run(
        team_id=event["team_id"],
        team_name=event["team_name"],
        refresh_id=event["refresh_id"],
    ))


async def _run(team_id: int, team_name: str, refresh_id: str) -> None:
    await _refresh.update_status(refresh_id, "running")
    logger.info("agent run started refresh_id=%s team_id=%s team=%s", refresh_id, team_id, team_name)
    try:
        messages = [{"role": "user", "content": team_name}]
        await Runner.run(make_agent(run_id=refresh_id), messages, max_turns=50)
        await _refresh.update_status(refresh_id, "complete")
        logger.info("agent run complete refresh_id=%s team_id=%s", refresh_id, team_id)
    except Exception as e:
        await _refresh.update_status(refresh_id, "failed", error=str(e))
        logger.error("agent run failed refresh_id=%s team_id=%s error=%s", refresh_id, team_id, e)
    finally:
        await _refresh.release_lock(team_id)
