from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RefreshInfo(BaseModel):
    refresh_id: str
    status: Literal["pending", "running", "complete", "failed"]
    triggered_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class DepthChartResponse(BaseModel):
    team_id: int
    team_name: str
    generated_at: datetime
    cache_status: Literal["fresh", "stale", "refreshing", "initializing"]
    refresh: RefreshInfo | None = None
    positions: dict | None = None
    rotation: list | None = None
    bullpen: list | None = None


class RefreshStatusResponse(BaseModel):
    refresh_id: str
    team_id: int
    status: Literal["pending", "running", "complete", "failed"]
    triggered_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    depth_chart: DepthChartResponse | None = None
