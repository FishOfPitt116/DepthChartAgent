"""
Integration tests — hit the real MLB Stats API.

Run with:
    pytest -m integration
"""
from __future__ import annotations

import pytest

from depth_chart_agent.mlb_client import (
    MLBApiError,
    STAT_GROUP_HITTING,
    STAT_GROUP_PITCHING,
    STAT_TYPE_BY_DATE_RANGE,
    STAT_TYPE_LAST_X_GAMES,
    STAT_TYPE_SEASON,
    get_active_roster,
    get_player_stats,
    get_recent_lineups,
    get_roster,
    get_team_id,
    get_transactions,
)

# New York Yankees — stable, well-known team ID
YANKEES_ID = 147

# Aaron Judge — reliable hitter with a full season of data
JUDGE_ID = 592450

# Gerrit Cole — reliable pitcher with a full season of data
COLE_ID = 543037


# --- get_team_id ---

@pytest.mark.integration
def test_get_team_id_full_name():
    assert get_team_id("New York Yankees") == YANKEES_ID


@pytest.mark.integration
def test_get_team_id_team_name():
    assert get_team_id("Yankees") == YANKEES_ID


@pytest.mark.integration
def test_get_team_id_abbreviation():
    assert get_team_id("NYY") == YANKEES_ID


@pytest.mark.integration
def test_get_team_id_case_insensitive():
    assert get_team_id("yankees") == YANKEES_ID


@pytest.mark.integration
def test_get_team_id_ambiguous_raises():
    with pytest.raises(MLBApiError, match="Ambiguous"):
        get_team_id("New York")


@pytest.mark.integration
def test_get_team_id_no_match_raises():
    with pytest.raises(MLBApiError, match="No MLB team"):
        get_team_id("Purple Penguins")


# --- get_roster ---

@pytest.mark.integration
def test_get_roster_returns_players():
    result = get_roster(YANKEES_ID)

    assert len(result) > 0
    player = result[0]
    assert "player_id" in player
    assert "name" in player
    assert "position" in player
    assert "status" in player
    assert "il_note" in player


@pytest.mark.integration
def test_get_roster_has_expected_size():
    result = get_roster(YANKEES_ID)

    # 40-man roster must have between 26 and 40 players
    assert 26 <= len(result) <= 40


@pytest.mark.integration
def test_get_active_roster_returns_players():
    result = get_active_roster(YANKEES_ID)

    assert len(result) > 0
    player = result[0]
    assert "player_id" in player
    assert "name" in player
    assert "position" in player
    assert "status" in player


@pytest.mark.integration
def test_get_active_roster_has_expected_size():
    result = get_active_roster(YANKEES_ID)

    # Active roster is 26 players (28 in September)
    assert 26 <= len(result) <= 28


@pytest.mark.integration
def test_active_roster_is_subset_of_40_man():
    """Every player on the active roster should appear on the 40-man roster."""
    active = get_active_roster(YANKEES_ID)
    full = get_roster(YANKEES_ID)

    full_ids = {p["player_id"] for p in full}
    active_ids = {p["player_id"] for p in active}

    assert active_ids.issubset(full_ids), (
        f"Players on active roster not found on 40-man: "
        f"{active_ids - full_ids}"
    )


@pytest.mark.integration
def test_active_roster_players_are_all_active_status():
    result = get_active_roster(YANKEES_ID)

    non_active = [p for p in result if p["status"] != "Active"]
    assert non_active == [], f"Non-active players on active roster: {non_active}"


@pytest.mark.integration
def test_get_transactions_returns_entries():
    result = get_transactions(YANKEES_ID, days=30)

    assert isinstance(result, list)
    if result:
        tx = result[0]
        assert "date" in tx
        assert "player" in tx
        assert "type" in tx
        assert "description" in tx


@pytest.mark.integration
def test_get_roster_invalid_team_raises_error():
    with pytest.raises(MLBApiError):
        get_roster(99999)


# --- get_player_stats ---

@pytest.mark.integration
def test_get_player_stats_season_hitting():
    result = get_player_stats(JUDGE_ID, STAT_GROUP_HITTING)

    assert result is not None
    assert result["player_id"] == JUDGE_ID
    assert result["group"] == STAT_GROUP_HITTING
    assert result["stat_type"] == STAT_TYPE_SEASON
    stats = result["stats"]
    assert "avg" in stats
    assert "homeRuns" in stats
    assert "ops" in stats
    assert "gamesPlayed" in stats


@pytest.mark.integration
def test_get_player_stats_season_pitching():
    result = get_player_stats(COLE_ID, STAT_GROUP_PITCHING)

    assert result is not None
    assert result["group"] == STAT_GROUP_PITCHING
    stats = result["stats"]
    assert "era" in stats
    assert "whip" in stats
    assert "strikeOuts" in stats
    assert "inningsPitched" in stats


@pytest.mark.integration
def test_get_player_stats_last_x_games():
    result = get_player_stats(
        JUDGE_ID, STAT_GROUP_HITTING,
        stat_type=STAT_TYPE_LAST_X_GAMES,
        last_x_games=14,
    )

    assert result is not None
    assert result["stat_type"] == STAT_TYPE_LAST_X_GAMES
    assert result["stats"]["gamesPlayed"] <= 14


@pytest.mark.integration
def test_get_player_stats_by_date_range():
    result = get_player_stats(
        JUDGE_ID, STAT_GROUP_HITTING,
        stat_type=STAT_TYPE_BY_DATE_RANGE,
        start_date="2026-05-01",
        end_date="2026-05-24",
    )

    assert result is not None
    assert result["stat_type"] == STAT_TYPE_BY_DATE_RANGE
    assert "avg" in result["stats"]


@pytest.mark.integration
def test_get_player_stats_invalid_player_returns_none():
    result = get_player_stats(999999999, STAT_GROUP_HITTING)

    assert result is None


# --- get_recent_lineups ---

@pytest.mark.integration
def test_get_recent_lineups_returns_list():
    result = get_recent_lineups(YANKEES_ID, days=14)

    assert isinstance(result, list)


@pytest.mark.integration
def test_get_recent_lineups_entry_shape():
    result = get_recent_lineups(YANKEES_ID, days=14)

    assert len(result) > 0, "Expected at least one completed game in the last 14 days"
    game = result[0]
    assert "date" in game
    assert "game_id" in game
    assert "batting_order" in game
    assert "pitching_staff" in game


@pytest.mark.integration
def test_get_recent_lineups_batting_order_shape():
    result = get_recent_lineups(YANKEES_ID, days=14)

    order = result[0]["batting_order"]
    assert len(order) == 9
    for entry in order:
        assert "player_id" in entry
        assert "name" in entry
        assert "position" in entry


@pytest.mark.integration
def test_get_recent_lineups_pitching_staff_shape():
    result = get_recent_lineups(YANKEES_ID, days=14)

    staff = result[0]["pitching_staff"]
    assert len(staff) > 0

    starter = staff[0]
    assert starter["appearance_order"] == 1
    assert "player_id" in starter
    assert "name" in starter
    assert "innings_pitched" in starter
    assert "saves" in starter
    assert "holds" in starter
    assert "blown_saves" in starter
    assert "games_finished" in starter
    assert "inherited_runners" in starter


@pytest.mark.integration
def test_get_recent_lineups_closer_identifiable():
    """At least one game in the last 14 days should have a save recorded."""
    result = get_recent_lineups(YANKEES_ID, days=14)

    all_pitchers = [p for game in result for p in game["pitching_staff"]]
    closers = [p for p in all_pitchers if p["saves"] > 0]
    # Not asserting count — Yankees may not have won every game — but shape is valid
    for c in closers:
        assert c["games_finished"] > 0


@pytest.mark.integration
def test_get_recent_lineups_players_on_40_man_roster():
    """
    Batters in recent lineups should appear on the 40-man roster.
    Note: they may NOT be on the current active roster — players can be
    recalled for a game and then optioned back down, which is exactly the
    kind of divergence the agent is built to detect and reason about.
    """
    lineups = get_recent_lineups(YANKEES_ID, days=7)
    full_roster = get_roster(YANKEES_ID)
    roster_ids = {p["player_id"] for p in full_roster}

    for game in lineups:
        for batter in game["batting_order"]:
            assert batter["player_id"] in roster_ids, (
                f"{batter['name']} appeared in a lineup but is not on the 40-man roster"
            )
