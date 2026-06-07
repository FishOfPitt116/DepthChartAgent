from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from depth_chart_agent.api.app import app
from depth_chart_agent.api.refresh import RefreshManager
from depth_chart_agent.mlb_client import MLBApiError

TEAM_ID = 147
TEAM_NAME = "New York Yankees"
REFRESH_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

_POSITIONS = {pos: [] for pos in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH")}

FRESH_CHART = {
    "team_id": TEAM_ID,
    "team_name": TEAM_NAME,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "positions": _POSITIONS,
    "rotation": [],
    "bullpen": [],
}

STALE_CHART = {**FRESH_CHART, "generated_at": "2020-01-01T00:00:00+00:00"}

SAMPLE_JOB = {
    "refresh_id": REFRESH_ID,
    "team_id": TEAM_ID,
    "team_name": TEAM_NAME,
    "status": "pending",
    "triggered_at": datetime.now(timezone.utc).isoformat(),
    "completed_at": None,
    "error": None,
}


@pytest.fixture
def mock_rm():
    rm = AsyncMock(spec=RefreshManager)
    rm.get_lock.return_value = None
    rm.create_job.return_value = REFRESH_ID
    rm.get_job.return_value = SAMPLE_JOB
    return rm


@pytest.fixture
def client(mock_rm):
    with (
        patch("depth_chart_agent.api.app.RefreshManager", return_value=mock_rm),
        patch("depth_chart_agent.api.app._invoke_agent_runner", new_callable=MagicMock),
    ):
        with TestClient(app) as c:
            yield c


# --- GET /depth-chart/{team} ---

def test_get_depth_chart_team_not_found(client):
    with patch("depth_chart_agent.api.app.get_team_id", side_effect=MLBApiError("No team found")):
        resp = client.get("/depth-chart/faketeam")
    assert resp.status_code == 404


def test_get_depth_chart_initializing_no_lock(client, mock_rm):
    mock_rm.get_lock.return_value = None
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=None),
    ):
        resp = client.get("/depth-chart/yankees")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache_status"] == "initializing"
    assert data["refresh"]["refresh_id"] == REFRESH_ID
    mock_rm.create_job.assert_awaited_once_with(TEAM_ID, "yankees")


def test_get_depth_chart_initializing_lock_exists(client, mock_rm):
    mock_rm.get_lock.return_value = REFRESH_ID
    mock_rm.get_job.return_value = {**SAMPLE_JOB, "status": "running"}
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=None),
    ):
        resp = client.get("/depth-chart/yankees")
    data = resp.json()
    assert data["cache_status"] == "initializing"
    assert data["refresh"]["status"] == "running"
    mock_rm.create_job.assert_not_awaited()


def test_get_depth_chart_fresh(client, mock_rm):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=FRESH_CHART),
    ):
        resp = client.get("/depth-chart/yankees")
    data = resp.json()
    assert data["cache_status"] == "fresh"
    assert data["refresh"] is None
    assert data["team_id"] == TEAM_ID
    mock_rm.create_job.assert_not_awaited()


def test_get_depth_chart_stale_no_lock(client, mock_rm):
    mock_rm.get_lock.return_value = None
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=STALE_CHART),
    ):
        resp = client.get("/depth-chart/yankees")
    data = resp.json()
    assert data["cache_status"] == "stale"
    assert data["refresh"]["refresh_id"] == REFRESH_ID
    mock_rm.create_job.assert_awaited_once()


def test_get_depth_chart_stale_lock_exists(client, mock_rm):
    mock_rm.get_lock.return_value = REFRESH_ID
    mock_rm.get_job.return_value = {**SAMPLE_JOB, "status": "running"}
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=STALE_CHART),
    ):
        resp = client.get("/depth-chart/yankees")
    data = resp.json()
    assert data["cache_status"] == "refreshing"
    assert data["refresh"]["status"] == "running"
    mock_rm.create_job.assert_not_awaited()


# --- GET /refresh/{refresh_id} ---

def test_get_refresh_status_not_found(client, mock_rm):
    mock_rm.get_job.return_value = None
    resp = client.get("/refresh/nonexistent")
    assert resp.status_code == 404


def test_get_refresh_status_running(client, mock_rm):
    mock_rm.get_job.return_value = {**SAMPLE_JOB, "status": "running"}
    resp = client.get(f"/refresh/{REFRESH_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["depth_chart"] is None


def test_get_refresh_status_complete_includes_chart(client, mock_rm):
    mock_rm.get_job.return_value = {
        **SAMPLE_JOB,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with patch("depth_chart_agent.api.app.read_chart", return_value=FRESH_CHART):
        resp = client.get(f"/refresh/{REFRESH_ID}")
    data = resp.json()
    assert data["status"] == "complete"
    assert data["depth_chart"]["team_id"] == TEAM_ID
    assert data["depth_chart"]["cache_status"] == "fresh"


SNAPSHOT_OLD = {"snapshot_id": "2026-05-28T10-00-00Z", "generated_at": "2026-05-28T10:00:00+00:00"}
SNAPSHOT_NEW = {"snapshot_id": "2026-05-29T10-00-00Z", "generated_at": "2026-05-29T10:00:00+00:00"}


# --- GET /depth-chart/{team}/history ---

def test_get_history_team_not_found(client):
    with patch("depth_chart_agent.api.app.get_team_id", side_effect=MLBApiError("No team found")):
        resp = client.get("/depth-chart/faketeam/history")
    assert resp.status_code == 404


def test_get_history_returns_snapshots(client):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.list_charts", return_value=[SNAPSHOT_NEW, SNAPSHOT_OLD]),
        patch("depth_chart_agent.api.app.read_chart", return_value=FRESH_CHART),
    ):
        resp = client.get("/depth-chart/yankees/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == TEAM_ID
    assert data["team_name"] == TEAM_NAME
    assert len(data["snapshots"]) == 2
    assert data["snapshots"][0]["snapshot_id"] == SNAPSHOT_NEW["snapshot_id"]


def test_get_history_empty(client):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.list_charts", return_value=[]),
        patch("depth_chart_agent.api.app.read_chart", return_value=None),
    ):
        resp = client.get("/depth-chart/yankees/history")
    assert resp.status_code == 200
    assert resp.json()["snapshots"] == []


# --- GET /depth-chart/{team}/history/{snapshot_id} ---

def test_get_snapshot_team_not_found(client):
    with patch("depth_chart_agent.api.app.get_team_id", side_effect=MLBApiError("No team found")):
        resp = client.get("/depth-chart/faketeam/history/2026-05-28T10-00-00Z")
    assert resp.status_code == 404


def test_get_snapshot_not_found(client):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart_at", return_value=None),
    ):
        resp = client.get("/depth-chart/yankees/history/2020-01-01T00-00-00Z")
    assert resp.status_code == 404


def test_get_snapshot_returns_chart(client):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart_at", return_value=FRESH_CHART),
    ):
        resp = client.get(f"/depth-chart/yankees/history/{SNAPSHOT_OLD['snapshot_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == TEAM_ID
    assert data["cache_status"] == "fresh"


# --- POST /depth-chart/{team}/refresh ---

def test_force_refresh_no_api_key(client):
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch.dict(os.environ, {"DEPTH_CHART_API_KEY": "secret"}),
    ):
        resp = client.post("/depth-chart/yankees/refresh")
    assert resp.status_code == 403


def test_force_refresh_valid_key_triggers_refresh(client, mock_rm):
    mock_rm.get_lock.return_value = None
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch("depth_chart_agent.api.app.read_chart", return_value=FRESH_CHART),
        patch.dict(os.environ, {"DEPTH_CHART_API_KEY": "secret"}),
    ):
        resp = client.post("/depth-chart/yankees/refresh", headers={"X-API-Key": "secret"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refresh_id"] == REFRESH_ID
    mock_rm.create_job.assert_awaited_once()


def test_force_refresh_already_running_returns_existing_job(client, mock_rm):
    mock_rm.get_lock.return_value = REFRESH_ID
    mock_rm.get_job.return_value = {**SAMPLE_JOB, "status": "running"}
    with (
        patch("depth_chart_agent.api.app.get_team_id", return_value=TEAM_ID),
        patch.dict(os.environ, {"DEPTH_CHART_API_KEY": "secret"}),
    ):
        resp = client.post("/depth-chart/yankees/refresh", headers={"X-API-Key": "secret"})
    data = resp.json()
    assert data["refresh_id"] == REFRESH_ID
    assert data["status"] == "running"
    mock_rm.create_job.assert_not_awaited()
