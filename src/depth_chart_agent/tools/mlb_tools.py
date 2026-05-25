from __future__ import annotations

from agents import function_tool

from depth_chart_agent.mlb_client import (
    STAT_GROUP_HITTING,
    STAT_GROUP_PITCHING,
    STAT_TYPE_BY_DATE_RANGE,
    STAT_TYPE_LAST_X_GAMES,
    STAT_TYPE_SEASON,
    get_active_roster as _get_active_roster,
    get_player_stats as _get_player_stats,
    get_recent_lineups as _get_recent_lineups,
    get_roster as _get_roster,
    get_team_id as _get_team_id,
    get_transactions as _get_transactions,
)


def get_team_id(query: str) -> int:
    """
    Resolve a team name, city, or abbreviation to an MLB team ID by querying
    the MLB Stats API. MUST be called first — every other tool requires a
    team_id and this is the only way to obtain one from a user-provided name.

    Matching is case-insensitive. Tries exact match on name, nickname,
    city, and abbreviation first; falls back to substring match on the full
    team name. Raises an error if the query is ambiguous or unrecognized.

    Args:
        query: Any recognizable team identifier — full name ("New York
            Yankees"), nickname ("Yankees"), city ("Boston"), or abbreviation
            ("NYY"). Avoid bare city names for cities with two teams (e.g.
            "New York") as these will be flagged as ambiguous.
    """
    return _get_team_id(query)


def get_active_roster(team_id: int) -> list[dict]:
    """
    Return the active 26-man roster — the players eligible to play in
    today's game. This is the ground truth for who may appear in the depth
    chart. Every player_id in this list MUST appear somewhere in the chart;
    no player absent from this list MAY appear.

    Each entry contains: player_id, name, position, status.

    Args:
        team_id: MLB team ID obtained from get_team_id.
    """
    return _get_active_roster(team_id)


def get_roster(team_id: int) -> list[dict]:
    """
    Return the full 40-man roster including players on the IL, optioned to
    the minors, and other non-active designations. Use this as the injury
    report — any player whose status contains "Injured" is on the IL and
    MUST NOT be charted. The il_note field contains the specific injury.

    Each entry contains: player_id, name, position, status, il_note.

    Args:
        team_id: MLB team ID obtained from get_team_id.
    """
    return _get_roster(team_id)


def get_transactions(team_id: int, days: int = 14) -> list[dict]:
    """
    Return recent transactions for a team: IL placements, recalls from the
    minors, options, DFA's, and trades. Use this to identify roster changes
    that may not yet be reflected in an existing depth chart.

    Each entry contains: date, player, type, description.

    Args:
        team_id: MLB team ID obtained from get_team_id.
        days: How many days back to search (default: 14).
    """
    return _get_transactions(team_id, days=days)


def get_recent_lineups(team_id: int, days: int = 14) -> list[dict]:
    """
    Return batting orders and full pitching staff usage for each completed
    game in the last `days` days. Use batting order frequency to determine
    positional depth strings. Use pitching appearance order, saves, holds,
    blown saves, and innings pitched to infer bullpen roles.

    Each game entry contains: date, game_id, batting_order, pitching_staff.
    batting_order entries: player_id, name, position.
    pitching_staff entries: player_id, name, appearance_order,
        innings_pitched, saves, holds, blown_saves, games_finished,
        inherited_runners.

    Args:
        team_id: MLB team ID obtained from get_team_id.
        days: How many days back to search (default: 14).
    """
    return _get_recent_lineups(team_id, days=days)


def get_player_stats(
    player_id: int,
    group: str,
    stat_type: str = STAT_TYPE_SEASON,
    last_x_games: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict | None:
    """
    Fetch stats for a single player. Returns None if no stats are available
    (e.g. a player who hasn't appeared yet this season). Call this when
    lineup frequency alone is insufficient to rank two players at a position.

    Prefer stat_type="lastXGames" with last_x_games=14 over season totals
    when recent form is the deciding factor.

    Returns a dict with: player_id, group, stat_type, stats (dict of
    stat key/value pairs). Hitting stats include avg, homeRuns, ops,
    obp, slg. Pitching stats include era, whip, strikeOuts, inningsPitched.

    Args:
        player_id: MLB player ID from get_active_roster or get_roster.
        group: Stat group. Use "hitting" for position players, "pitching"
            for pitchers.
        stat_type: One of "season" (default), "lastXGames", "byDateRange".
        last_x_games: Number of games to look back. Required when
            stat_type is "lastXGames" (recommended value: 14).
        start_date: ISO date string (YYYY-MM-DD). Required when stat_type
            is "byDateRange".
        end_date: ISO date string (YYYY-MM-DD). Required when stat_type
            is "byDateRange".
    """
    return _get_player_stats(
        player_id,
        group,
        stat_type=stat_type,
        last_x_games=last_x_games,
        start_date=start_date,
        end_date=end_date,
    )


MLB_CLIENT_TOOLS = [
    function_tool(get_team_id),
    function_tool(get_active_roster),
    function_tool(get_roster),
    function_tool(get_transactions),
    function_tool(get_recent_lineups),
    function_tool(get_player_stats),
]
