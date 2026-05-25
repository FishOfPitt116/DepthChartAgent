"""
Integration tests — hit the real MLB Stats API.

Run with:
    pytest -m integration
"""
from __future__ import annotations

import pytest

from depth_chart_agent.mlb_client import MLBApiError, get_active_roster, get_roster, get_transactions

# New York Yankees — stable, well-known team ID
YANKEES_ID = 147


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
