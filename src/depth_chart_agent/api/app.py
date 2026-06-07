from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import boto3
from fastapi import Depends, FastAPI, HTTPException

from depth_chart_agent.api.auth import require_api_key
from depth_chart_agent.api.models import (
    DepthChartHistoryResponse,
    DepthChartResponse,
    DepthChartSnapshot,
    RefreshInfo,
    RefreshStatusResponse,
)
from depth_chart_agent.api.refresh import RefreshManager
from depth_chart_agent.logging_config import configure_logging
from depth_chart_agent.mlb_client import MLBApiError, get_team_id
from depth_chart_agent.storage import list_charts, read_chart, read_chart_at

logger = logging.getLogger(__name__)

_CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "86400"))

_refresh: RefreshManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    global _refresh
    _refresh = RefreshManager()
    logger.info("API started cache_ttl=%ss", _CACHE_TTL)
    yield
    await _refresh.close()
    logger.info("API shutdown")


app = FastAPI(title="DepthChartAgent API", lifespan=lifespan)


# --- helpers ---

def _is_fresh(chart: dict) -> bool:
    generated_at = datetime.fromisoformat(chart["generated_at"])
    age = (datetime.now(timezone.utc) - generated_at).total_seconds()
    return age < _CACHE_TTL


def _refresh_info(job: dict) -> RefreshInfo:
    return RefreshInfo(
        refresh_id=job["refresh_id"],
        status=job["status"],
        triggered_at=datetime.fromisoformat(job["triggered_at"]),
        completed_at=datetime.fromisoformat(job["completed_at"]) if job.get("completed_at") else None,
        error=job.get("error"),
    )


def _chart_response(chart: dict, cache_status: str, refresh: RefreshInfo | None) -> DepthChartResponse:
    return DepthChartResponse(
        team_id=chart["team_id"],
        team_name=chart["team_name"],
        generated_at=datetime.fromisoformat(chart["generated_at"]),
        cache_status=cache_status,
        refresh=refresh,
        positions=chart["positions"],
        rotation=chart["rotation"],
        bullpen=chart["bullpen"],
    )


def _invoke_agent_runner(team_id: int, team_name: str, refresh_id: str) -> None:
    boto3.client("lambda").invoke(
        FunctionName=os.environ["AGENT_RUNNER_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"team_id": team_id, "team_name": team_name, "refresh_id": refresh_id}),
    )


async def _trigger_refresh(team_id: int, team_name: str) -> RefreshInfo:
    """Create a job + lock and invoke the agent runner Lambda."""
    refresh_id = await _refresh.create_job(team_id, team_name)
    await asyncio.to_thread(_invoke_agent_runner, team_id, team_name, refresh_id)
    job = await _refresh.get_job(refresh_id)
    return _refresh_info(job)


# --- routes ---

@app.get("/depth-chart/{team}", response_model=DepthChartResponse)
async def get_depth_chart(team: str):
    try:
        team_id = await asyncio.to_thread(get_team_id, team)
    except MLBApiError as e:
        logger.warning("team not found query=%s error=%s", team, e)
        raise HTTPException(status_code=404, detail=str(e))

    chart = read_chart(team_id)

    if chart is None:
        lock_id = await _refresh.get_lock(team_id)
        if lock_id:
            job = await _refresh.get_job(lock_id)
            info = _refresh_info(job) if job else None
        else:
            info = await _trigger_refresh(team_id, team)
        logger.info("GET /depth-chart/%s team_id=%s cache_status=initializing refresh_id=%s",
                    team, team_id, info.refresh_id if info else None)
        return DepthChartResponse(
            team_id=team_id,
            team_name=team,
            generated_at=datetime.now(timezone.utc),
            cache_status="initializing",
            refresh=info,
        )

    if _is_fresh(chart):
        logger.info("GET /depth-chart/%s team_id=%s cache_status=fresh", team, team_id)
        return _chart_response(chart, "fresh", None)

    lock_id = await _refresh.get_lock(team_id)
    if lock_id:
        job = await _refresh.get_job(lock_id)
        info = _refresh_info(job) if job else None
        logger.info("GET /depth-chart/%s team_id=%s cache_status=refreshing refresh_id=%s",
                    team, team_id, lock_id)
        return _chart_response(chart, "refreshing", info)

    info = await _trigger_refresh(team_id, chart["team_name"])
    logger.info("GET /depth-chart/%s team_id=%s cache_status=stale refresh_id=%s",
                team, team_id, info.refresh_id)
    return _chart_response(chart, "stale", info)


@app.get("/refresh/{refresh_id}", response_model=RefreshStatusResponse)
async def get_refresh_status(refresh_id: str):
    job = await _refresh.get_job(refresh_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Refresh job '{refresh_id}' not found or expired")

    depth_chart = None
    if job["status"] == "complete":
        chart = read_chart(job["team_id"])
        if chart:
            depth_chart = _chart_response(chart, "fresh", None)

    return RefreshStatusResponse(
        refresh_id=job["refresh_id"],
        team_id=job["team_id"],
        status=job["status"],
        triggered_at=datetime.fromisoformat(job["triggered_at"]),
        completed_at=datetime.fromisoformat(job["completed_at"]) if job.get("completed_at") else None,
        error=job.get("error"),
        depth_chart=depth_chart,
    )


@app.get("/depth-chart/{team}/history", response_model=DepthChartHistoryResponse)
async def get_depth_chart_history(team: str):
    try:
        team_id = await asyncio.to_thread(get_team_id, team)
    except MLBApiError as e:
        logger.warning("history team not found query=%s error=%s", team, e)
        raise HTTPException(status_code=404, detail=str(e))

    snapshots = list_charts(team_id)
    latest = read_chart(team_id)
    team_name = latest["team_name"] if latest else team
    logger.info("GET /depth-chart/%s/history team_id=%s count=%d", team, team_id, len(snapshots))
    return DepthChartHistoryResponse(
        team_id=team_id,
        team_name=team_name,
        snapshots=[DepthChartSnapshot(**s) for s in snapshots],
    )


@app.get("/depth-chart/{team}/history/{snapshot_id}", response_model=DepthChartResponse)
async def get_depth_chart_snapshot(team: str, snapshot_id: str):
    try:
        team_id = await asyncio.to_thread(get_team_id, team)
    except MLBApiError as e:
        logger.warning("snapshot team not found query=%s error=%s", team, e)
        raise HTTPException(status_code=404, detail=str(e))

    chart = read_chart_at(team_id, snapshot_id)
    if chart is None:
        raise HTTPException(status_code=404, detail=f"Snapshot '{snapshot_id}' not found for {team}")
    logger.info("GET /depth-chart/%s/history/%s team_id=%s", team, snapshot_id, team_id)
    return _chart_response(chart, "fresh", None)


@app.post("/depth-chart/{team}/refresh", response_model=RefreshInfo)
async def force_refresh(
    team: str,
    _: None = Depends(require_api_key),
):
    try:
        team_id = await asyncio.to_thread(get_team_id, team)
    except MLBApiError as e:
        logger.warning("force refresh team not found query=%s error=%s", team, e)
        raise HTTPException(status_code=404, detail=str(e))

    lock_id = await _refresh.get_lock(team_id)
    if lock_id:
        job = await _refresh.get_job(lock_id)
        if job:
            logger.info("force refresh already running team_id=%s refresh_id=%s", team_id, lock_id)
            return _refresh_info(job)

    chart = read_chart(team_id)
    team_name = chart["team_name"] if chart else team
    info = await _trigger_refresh(team_id, team_name)
    logger.info("force refresh triggered team_id=%s refresh_id=%s", team_id, info.refresh_id)
    return info
