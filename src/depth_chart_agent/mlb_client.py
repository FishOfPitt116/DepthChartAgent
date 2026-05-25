from __future__ import annotations

from datetime import date, timedelta

import httpx

# Valid values for the group parameter in get_player_stats
STAT_GROUP_HITTING = "hitting"
STAT_GROUP_PITCHING = "pitching"

# Valid values for the stat_type parameter in get_player_stats
STAT_TYPE_SEASON = "season"
STAT_TYPE_LAST_X_GAMES = "lastXGames"
STAT_TYPE_BY_DATE_RANGE = "byDateRange"
STAT_TYPE_GAME_LOG = "gameLog"
STAT_TYPE_BY_MONTH = "byMonth"

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


def _fetch_roster(team_id: int, roster_type: str) -> list[dict]:
    data = _get(f"/teams/{team_id}/roster", rosterType=roster_type)
    if not data.get("roster"):
        raise MLBApiError(f"Empty roster returned for team_id={team_id} (rosterType={roster_type})")
    return _parse_roster(data)


def get_roster(team_id: int) -> list[dict]:
    """Return the 40-man roster with position and IL status for each player."""
    return _fetch_roster(team_id, "40Man")


def get_active_roster(team_id: int) -> list[dict]:
    """Return the active (26-man) roster — players available to play today."""
    return _fetch_roster(team_id, "active")


def get_player_stats(
    player_id: int,
    group: str,
    stat_type: str = STAT_TYPE_SEASON,
    season: int | None = None,
    last_x_games: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict | None:
    """
    Fetch stats for a player. Returns None if no stats are found (e.g. player
    hasn't appeared yet this season).

    Args:
        player_id:    MLB player ID.
        group:        STAT_GROUP_HITTING or STAT_GROUP_PITCHING.
        stat_type:    One of the STAT_TYPE_* constants (default: season totals).
        season:       Year to query — defaults to the current year.
        last_x_games: Number of games for STAT_TYPE_LAST_X_GAMES.
        start_date:   ISO date string (YYYY-MM-DD) for STAT_TYPE_BY_DATE_RANGE.
        end_date:     ISO date string (YYYY-MM-DD) for STAT_TYPE_BY_DATE_RANGE.
    """
    params: dict = {
        "stats": stat_type,
        "group": group,
        "season": season or date.today().year,
    }
    if last_x_games is not None:
        params["limit"] = last_x_games
    if start_date is not None:
        params["startDate"] = start_date
    if end_date is not None:
        params["endDate"] = end_date

    data = _get(f"/people/{player_id}/stats", **params)

    entries = data.get("stats", [])
    if not entries or not entries[0].get("splits"):
        return None

    return {
        "player_id": player_id,
        "group": group,
        "stat_type": stat_type,
        "stats": entries[0]["splits"][0]["stat"],
    }


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
