from __future__ import annotations

from agents import function_tool

from depth_chart_agent.mlb_client import get_team_id as _get_team_id


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


MLB_CLIENT_TOOLS = [
    function_tool(get_team_id),
]
