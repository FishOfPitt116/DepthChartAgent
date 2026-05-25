from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from depth_chart_agent.tools.depth_chart_tools import (
    BullpenEntry,
    PositionEntry,
    RotationEntry,
    get_depth_at_position,
    initialize_depth_chart,
    read_depth_chart,
    remove_bullpen_player,
    remove_player_everywhere,
    remove_position_player,
    remove_rotation_slot,
    set_bullpen_roles,
    set_position_players,
    set_rotation_slots,
    update_active_roster_ids,
    validate_depth_chart,
)

TEAM_ID = 147
ROSTER = [592450, 683011, 543037, 670280, 669224, 641355, 665862, 641857, 502671,
          607074, 700250, 642708, 676609, 641555, 621112, 518585, 657612, 666808,
          693645, 701542, 677960, 687396, 656234, 663757, 641857, 680474]

_ROSTER_DICTS = [{"player_id": pid} for pid in ROSTER]


@pytest.fixture(autouse=True)
def patch_data_dir(tmp_path):
    """Redirect all file I/O to a temporary directory."""
    with patch("depth_chart_agent.tools.depth_chart_tools._DATA_DIR", tmp_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def patch_get_active_roster():
    """Stub out the MLB API call so tests never hit the network."""
    with patch(
        "depth_chart_agent.tools.depth_chart_tools.get_active_roster",
        return_value=_ROSTER_DICTS,
    ):
        yield


# --- read_depth_chart ---

def test_read_depth_chart_returns_null_when_missing():
    result = json.loads(read_depth_chart(TEAM_ID))
    assert result is None


def test_read_depth_chart_returns_chart_after_init():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = json.loads(read_depth_chart(TEAM_ID))
    assert result["team_id"] == TEAM_ID
    assert result["team_name"] == "New York Yankees"


# --- get_depth_at_position ---

def test_get_depth_at_position_invalid_position():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = get_depth_at_position(TEAM_ID, "QB")
    assert result.startswith("Error:")


def test_get_depth_at_position_empty_on_fresh_chart():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = json.loads(get_depth_at_position(TEAM_ID, "C"))
    assert result == []


def test_get_depth_at_position_no_chart():
    result = get_depth_at_position(TEAM_ID, "C")
    assert result.startswith("Error:")


# --- initialize_depth_chart ---

def test_initialize_creates_all_positions():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    chart = json.loads(read_depth_chart(TEAM_ID))
    for pos in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"):
        assert pos in chart["positions"]
        assert chart["positions"][pos] == []


def test_initialize_sets_active_roster_ids():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    chart = json.loads(read_depth_chart(TEAM_ID))
    assert set(chart["active_roster_ids"]) == set(ROSTER)


# --- update_active_roster_ids ---

def test_update_active_roster_ids_updates_without_wiping():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Best player")])
    extended = [{"player_id": pid} for pid in ROSTER + [999999]]
    with patch("depth_chart_agent.tools.depth_chart_tools.get_active_roster", return_value=extended):
        update_active_roster_ids(TEAM_ID)

    chart = json.loads(read_depth_chart(TEAM_ID))
    assert 999999 in chart["active_roster_ids"]
    assert chart["positions"]["RF"][0]["player_id"] == 592450  # preserved


def test_update_active_roster_ids_no_chart():
    result = update_active_roster_ids(TEAM_ID)
    assert result.startswith("Error:")


# --- set_position_players ---

def test_set_position_players_adds_entry():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Starter")])
    entries = json.loads(get_depth_at_position(TEAM_ID, "RF"))
    assert len(entries) == 1
    assert entries[0]["player_id"] == 592450
    assert entries[0]["depth_string"] == 1


def test_set_position_players_replaces_existing():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Old reasoning")])
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="New reasoning")])
    entries = json.loads(get_depth_at_position(TEAM_ID, "RF"))
    assert len(entries) == 1
    assert entries[0]["reasoning"] == "New reasoning"


def test_set_position_players_sorts_by_depth_string():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [
        PositionEntry(position="RF", player_id=641355, name="Cody Bellinger", depth_string=2, reasoning="Backup"),
        PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Starter"),
    ])
    entries = json.loads(get_depth_at_position(TEAM_ID, "RF"))
    assert entries[0]["depth_string"] == 1
    assert entries[1]["depth_string"] == 2


def test_set_position_players_invalid_position():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = set_position_players(TEAM_ID, [PositionEntry(position="QB", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="n/a")])
    assert result.startswith("Error:")


def test_set_position_players_invalid_depth_string():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=5, reasoning="n/a")])
    assert result.startswith("Error:")


# --- remove_position_player ---

def test_remove_position_player_removes_entry():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Starter")])
    remove_position_player(TEAM_ID, "RF", 592450)
    entries = json.loads(get_depth_at_position(TEAM_ID, "RF"))
    assert entries == []


def test_remove_position_player_only_removes_from_one_position():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [
        PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="RF starter"),
        PositionEntry(position="DH", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="DH backup"),
    ])
    remove_position_player(TEAM_ID, "RF", 592450)
    assert json.loads(get_depth_at_position(TEAM_ID, "RF")) == []
    assert len(json.loads(get_depth_at_position(TEAM_ID, "DH"))) == 1


def test_remove_position_player_not_present_returns_message():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = remove_position_player(TEAM_ID, "RF", 592450)
    assert "was not in" in result


# --- set_rotation_slots ---

def test_set_rotation_slots_adds_entry():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_rotation_slots(TEAM_ID, [RotationEntry(slot="SP1", player_id=543037, name="Gerrit Cole", reasoning="Ace")])
    chart = json.loads(read_depth_chart(TEAM_ID))
    assert chart["rotation"][0]["player_id"] == 543037
    assert chart["rotation"][0]["slot"] == "SP1"


def test_set_rotation_slots_replaces_existing():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_rotation_slots(TEAM_ID, [RotationEntry(slot="SP1", player_id=543037, name="Gerrit Cole", reasoning="Ace")])
    set_rotation_slots(TEAM_ID, [RotationEntry(slot="SP1", player_id=607074, name="Carlos Rodon", reasoning="New SP1")])
    chart = json.loads(read_depth_chart(TEAM_ID))
    sp1_entries = [e for e in chart["rotation"] if e["slot"] == "SP1"]
    assert len(sp1_entries) == 1
    assert sp1_entries[0]["player_id"] == 607074


def test_set_rotation_slots_invalid_slot():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = set_rotation_slots(TEAM_ID, [RotationEntry(slot="SP6", player_id=543037, name="Gerrit Cole", reasoning="n/a")])
    assert result.startswith("Error:")


# --- remove_rotation_slot ---

def test_remove_rotation_slot_clears_slot():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_rotation_slots(TEAM_ID, [RotationEntry(slot="SP1", player_id=543037, name="Gerrit Cole", reasoning="Ace")])
    remove_rotation_slot(TEAM_ID, "SP1")
    chart = json.loads(read_depth_chart(TEAM_ID))
    assert not any(e["slot"] == "SP1" for e in chart["rotation"])


def test_remove_rotation_slot_already_empty():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = remove_rotation_slot(TEAM_ID, "SP1")
    assert "already empty" in result


# --- set_bullpen_roles ---

def test_set_bullpen_roles_adds_entry():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_bullpen_roles(TEAM_ID, [BullpenEntry(player_id=670280, name="David Bednar", role="closer", reasoning="10 saves")])
    chart = json.loads(read_depth_chart(TEAM_ID))
    assert chart["bullpen"][0]["player_id"] == 670280
    assert chart["bullpen"][0]["role"] == "closer"


def test_set_bullpen_roles_replaces_existing():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_bullpen_roles(TEAM_ID, [BullpenEntry(player_id=670280, name="David Bednar", role="setup", reasoning="old role")])
    set_bullpen_roles(TEAM_ID, [BullpenEntry(player_id=670280, name="David Bednar", role="closer", reasoning="promoted")])
    chart = json.loads(read_depth_chart(TEAM_ID))
    entries = [e for e in chart["bullpen"] if e["player_id"] == 670280]
    assert len(entries) == 1
    assert entries[0]["role"] == "closer"


def test_set_bullpen_roles_invalid_role():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = set_bullpen_roles(TEAM_ID, [BullpenEntry(player_id=670280, name="David Bednar", role="starter", reasoning="n/a")])
    assert result.startswith("Error:")


# --- remove_bullpen_player ---

def test_remove_bullpen_player_removes_entry():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_bullpen_roles(TEAM_ID, [BullpenEntry(player_id=670280, name="David Bednar", role="closer", reasoning="10 saves")])
    remove_bullpen_player(TEAM_ID, 670280)
    chart = json.loads(read_depth_chart(TEAM_ID))
    assert not any(e["player_id"] == 670280 for e in chart["bullpen"])


# --- remove_player_everywhere ---

def test_remove_player_everywhere_removes_from_all_sections():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    set_position_players(TEAM_ID, [
        PositionEntry(position="RF", player_id=592450, name="Aaron Judge", depth_string=1, reasoning="Starter"),
        PositionEntry(position="DH", player_id=592450, name="Aaron Judge", depth_string=2, reasoning="DH option"),
    ])
    result = remove_player_everywhere(TEAM_ID, 592450)
    assert "RF" in result
    assert "DH" in result
    assert json.loads(get_depth_at_position(TEAM_ID, "RF")) == []
    assert json.loads(get_depth_at_position(TEAM_ID, "DH")) == []


def test_remove_player_everywhere_not_found():
    initialize_depth_chart(TEAM_ID, "New York Yankees")
    result = remove_player_everywhere(TEAM_ID, 999999)
    assert "not found" in result


# --- validate_depth_chart ---

def _build_valid_chart(team_id: int) -> None:
    """Helper: build a minimal valid chart using the ROSTER constant."""
    initialize_depth_chart(team_id, "Test Team")
    positions = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
    set_position_players(team_id, [
        PositionEntry(position=pos, player_id=pid, name=f"Player {pid}", depth_string=1, reasoning="reason")
        for pos, pid in zip(positions, ROSTER[:9])
    ])
    set_rotation_slots(team_id, [
        RotationEntry(slot="SP1", player_id=ROSTER[9], name=f"Player {ROSTER[9]}", reasoning="reason")
    ])
    set_bullpen_roles(team_id, [
        BullpenEntry(player_id=pid, name=f"Player {pid}", role="middle_relief", reasoning="reason")
        for pid in ROSTER[10:]
    ])


def test_validate_passes_on_valid_chart():
    _build_valid_chart(TEAM_ID)
    result = json.loads(validate_depth_chart(TEAM_ID))
    assert result["valid"] is True
    assert result["violations"] == []


def test_validate_fails_missing_active_player():
    _build_valid_chart(TEAM_ID)
    # Add a player to active roster but don't chart them
    extended = [{"player_id": pid} for pid in ROSTER] + [{"player_id": 999}]
    with patch("depth_chart_agent.tools.depth_chart_tools.get_active_roster", return_value=extended):
        update_active_roster_ids(TEAM_ID)
    result = json.loads(validate_depth_chart(TEAM_ID))
    assert result["valid"] is False
    assert any("999" in v for v in result["violations"])


def test_validate_fails_player_not_on_active_roster():
    _build_valid_chart(TEAM_ID)
    # Add a player to the chart who isn't on the active roster
    set_position_players(TEAM_ID, [PositionEntry(position="RF", player_id=9999, name="Ghost Player", depth_string=3, reasoning="shouldn't be here")])
    result = json.loads(validate_depth_chart(TEAM_ID))
    assert result["valid"] is False
    assert any("9999" in v for v in result["violations"])


def test_validate_fails_missing_first_string():
    _build_valid_chart(TEAM_ID)
    # Remove the 1st-string catcher
    remove_position_player(TEAM_ID, "C", ROSTER[0])
    result = json.loads(validate_depth_chart(TEAM_ID))
    assert result["valid"] is False
    assert any("C" in v and "1st-string" in v for v in result["violations"])


def test_validate_no_chart():
    result = json.loads(validate_depth_chart(TEAM_ID))
    assert result["valid"] is False
    assert len(result["violations"]) > 0
