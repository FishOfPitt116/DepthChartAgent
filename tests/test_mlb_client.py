from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from depth_chart_agent.mlb_client import MLBApiError, get_active_roster, get_roster, get_transactions


# --- fixtures ---

ROSTER_RESPONSE = {
    "roster": [
        {
            "person": {"id": 592450, "fullName": "Aaron Judge"},
            "position": {"abbreviation": "RF"},
            "status": {"code": "A", "description": "Active"},
        },
        {
            "person": {"id": 123456, "fullName": "John Doe"},
            "position": {"abbreviation": "SP"},
            "status": {"code": "D15", "description": "Injured 15-Day"},
            "note": "Right elbow inflammation.",
        },
    ]
}

TRANSACTIONS_RESPONSE = {
    "transactions": [
        {
            "person": {"fullName": "Aaron Judge"},
            "date": "2026-05-20",
            "typeDesc": "Placed on Injured List",
            "description": "RF Aaron Judge placed on the 10-day IL.",
        },
        {
            "person": {"fullName": "John Doe"},
            "date": "2026-05-21",
            "typeDesc": "Recalled From Minors",
            "description": "RHP John Doe recalled from Triple-A.",
        },
    ]
}


def _mock_response(json_data: dict) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


# --- get_roster ---

def test_get_roster_returns_normalized_players():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(ROSTER_RESPONSE)):
        result = get_roster(147)

    assert len(result) == 2
    assert result[0] == {
        "player_id": 592450,
        "name": "Aaron Judge",
        "position": "RF",
        "status": "Active",
        "il_note": None,
    }


def test_get_roster_includes_il_note():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(ROSTER_RESPONSE)):
        result = get_roster(147)

    assert result[1]["il_note"] == "Right elbow inflammation."
    assert result[1]["status"] == "Injured 15-Day"


def test_get_roster_empty_roster_raises():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response({"roster": []})):
        with pytest.raises(MLBApiError, match="Empty roster"):
            get_roster(147)


def test_get_roster_http_error():
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = 404
    mock.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock
    )
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=mock):
        with pytest.raises(MLBApiError, match="HTTP 404"):
            get_roster(99999)


def test_get_roster_network_error():
    with patch("depth_chart_agent.mlb_client.httpx.get", side_effect=httpx.ConnectError("timeout")):
        with pytest.raises(MLBApiError, match="Request failed"):
            get_roster(147)


# --- get_active_roster ---

ACTIVE_ROSTER_RESPONSE = {
    "roster": [
        {
            "person": {"id": 592450, "fullName": "Aaron Judge"},
            "position": {"abbreviation": "RF"},
            "status": {"code": "A", "description": "Active"},
        },
        {
            "person": {"id": 683011, "fullName": "Anthony Volpe"},
            "position": {"abbreviation": "SS"},
            "status": {"code": "A", "description": "Active"},
        },
    ]
}


def test_get_active_roster_returns_normalized_players():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(ACTIVE_ROSTER_RESPONSE)):
        result = get_active_roster(147)

    assert len(result) == 2
    assert result[0] == {
        "player_id": 592450,
        "name": "Aaron Judge",
        "position": "RF",
        "status": "Active",
        "il_note": None,
    }


def test_get_active_roster_requests_correct_roster_type():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(ACTIVE_ROSTER_RESPONSE)) as mock_get:
        get_active_roster(147)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["rosterType"] == "active"


def test_get_roster_requests_correct_roster_type():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(ROSTER_RESPONSE)) as mock_get:
        get_roster(147)

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["rosterType"] == "40Man"


def test_get_active_roster_empty_raises():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response({"roster": []})):
        with pytest.raises(MLBApiError, match="Empty roster"):
            get_active_roster(147)


# --- get_transactions ---

def test_get_transactions_returns_normalized_entries():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(TRANSACTIONS_RESPONSE)):
        result = get_transactions(147)

    assert len(result) == 2
    assert result[0] == {
        "date": "2026-05-20",
        "player": "Aaron Judge",
        "type": "Placed on Injured List",
        "description": "RF Aaron Judge placed on the 10-day IL.",
    }


def test_get_transactions_empty():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response({"transactions": []})):
        result = get_transactions(147)

    assert result == []


def test_get_transactions_passes_date_range():
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=_mock_response(TRANSACTIONS_RESPONSE)) as mock_get:
        get_transactions(147, days=7)

    _, kwargs = mock_get.call_args
    params = kwargs["params"]
    assert "startDate" in params
    assert "endDate" in params
    assert params["teamId"] == 147


def test_get_transactions_http_error():
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = 500
    mock.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock
    )
    with patch("depth_chart_agent.mlb_client.httpx.get", return_value=mock):
        with pytest.raises(MLBApiError, match="HTTP 500"):
            get_transactions(147)
