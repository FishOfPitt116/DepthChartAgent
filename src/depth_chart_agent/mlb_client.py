from __future__ import annotations

from datetime import date, timedelta

import httpx

BASE_URL = "https://statsapi.mlb.com/api/v1"


class MLBApiError(Exception):
    pass


def _get(path: str, **params) -> dict:
    url = f"{BASE_URL}{path}"
    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise MLBApiError(f"HTTP {e.response.status_code} from {url}") from e
    except httpx.RequestError as e:
        raise MLBApiError(f"Request failed: {e}") from e


def _parse_roster(data: dict) -> list[dict]:
    return [
        {
            "player_id": entry["person"]["id"],
            "name": entry["person"]["fullName"],
            "position": entry["position"]["abbreviation"],
            "status": entry["status"]["description"],
            "il_note": entry.get("note"),
        }
        for entry in data.get("roster", [])
    ]


def get_roster(team_id: int) -> list[dict]:
    """Return the 40-man roster with position and IL status for each player."""
    return _parse_roster(_get(f"/teams/{team_id}/roster", rosterType="40Man"))


def get_active_roster(team_id: int) -> list[dict]:
    """Return the active (26-man) roster — players available to play today."""
    return _parse_roster(_get(f"/teams/{team_id}/roster", rosterType="active"))


def get_transactions(team_id: int, days: int = 14) -> list[dict]:
    """Return recent transactions (IL moves, recalls, signings) for a team."""
    end = date.today()
    start = end - timedelta(days=days)
    data = _get(
        "/transactions",
        teamId=team_id,
        startDate=start.isoformat(),
        endDate=end.isoformat(),
    )
    transactions = []
    for entry in data.get("transactions", []):
        transactions.append({
            "date": entry["date"],
            "player": entry["person"]["fullName"],
            "type": entry["typeDesc"],
            "description": entry["description"],
        })
    return transactions
