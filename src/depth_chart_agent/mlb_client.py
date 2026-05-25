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


def get_team_id(query: str) -> int:
    """
    Resolve a team name, city, or abbreviation to an MLB team ID.

    Matching is case-insensitive and runs in two passes:
      1. Exact match against name, teamName, locationName, abbreviation,
         franchiseName, or clubName.
      2. Query is a substring of the full team name.

    Raises MLBApiError if no match is found or the query is ambiguous.
    """
    data = _get("/teams", sportId=1)
    teams = [t for t in data.get("teams", []) if t.get("active")]

    q = query.strip().lower()

    exact = [
        t for t in teams
        if q in {
            t.get("name", "").lower(),
            t.get("teamName", "").lower(),
            t.get("locationName", "").lower(),
            t.get("abbreviation", "").lower(),
            t.get("franchiseName", "").lower(),
            t.get("clubName", "").lower(),
        }
    ]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(exact) > 1:
        names = [t["name"] for t in exact]
        raise MLBApiError(f"Ambiguous team identifier '{query}' — matched: {names}")

    partial = [t for t in teams if q in t.get("name", "").lower()]
    if len(partial) == 1:
        return partial[0]["id"]
    if len(partial) > 1:
        names = [t["name"] for t in partial]
        raise MLBApiError(f"Ambiguous team identifier '{query}' — matched: {names}")

    raise MLBApiError(f"No MLB team found matching '{query}'")


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


def _parse_boxscore_lineup(boxscore: dict, team_id: int) -> dict | None:
    """Extract batting order and full pitching staff for team_id from a boxscore."""
    teams = boxscore.get("teams", {})

    side = None
    for s in ("home", "away"):
        if teams.get(s, {}).get("team", {}).get("id") == team_id:
            side = s
            break
    if side is None:
        return None

    team_data = teams[side]
    players = team_data.get("players", {})
    batting_order = team_data.get("battingOrder", [])
    pitcher_ids = team_data.get("pitchers", [])

    if not batting_order:
        return None

    lineup = []
    for pid in batting_order:
        player = players.get(f"ID{pid}", {})
        lineup.append({
            "player_id": pid,
            "name": player.get("person", {}).get("fullName", "Unknown"),
            "position": player.get("position", {}).get("abbreviation", ""),
        })

    pitching_staff = []
    for order, pid in enumerate(pitcher_ids, start=1):
        player = players.get(f"ID{pid}", {})
        stats = player.get("stats", {}).get("pitching", {})
        pitching_staff.append({
            "player_id": pid,
            "name": player.get("person", {}).get("fullName", "Unknown"),
            "appearance_order": order,
            "innings_pitched": stats.get("inningsPitched", "0.0"),
            "saves": stats.get("saves", 0),
            "save_opportunities": stats.get("saveOpportunities", 0),
            "holds": stats.get("holds", 0),
            "blown_saves": stats.get("blownSaves", 0),
            "games_finished": stats.get("gamesFinished", 0),
            "inherited_runners": stats.get("inheritedRunners", 0),
            "inherited_runners_scored": stats.get("inheritedRunnersScored", 0),
            "note": stats.get("note"),
        })

    return {"batting_order": lineup, "pitching_staff": pitching_staff}


def get_recent_lineups(team_id: int, days: int = 14) -> list[dict]:
    """
    Return batting orders and starting pitchers for completed games in the
    last `days` days. Each entry covers one game.
    """
    end = date.today()
    start = end - timedelta(days=days)
    schedule = _get(
        "/schedule",
        teamId=team_id,
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        sportId=1,
    )

    lineups = []
    for date_entry in schedule.get("dates", []):
        for game in date_entry.get("games", []):
            if game.get("status", {}).get("abstractGameState") != "Final":
                continue

            game_pk = game["gamePk"]
            game_date = game["officialDate"]

            boxscore = _get(f"/game/{game_pk}/boxscore")
            lineup = _parse_boxscore_lineup(boxscore, team_id)
            if lineup:
                lineups.append({"date": game_date, "game_id": game_pk, **lineup})

    return lineups


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
