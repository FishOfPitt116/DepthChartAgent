from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from agents import function_tool

# Project root / data / depth_charts
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "depth_charts"

VALID_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
VALID_ROTATION_SLOTS = {"SP1", "SP2", "SP3", "SP4", "SP5"}
VALID_BULLPEN_ROLES = {"closer", "setup", "middle_relief", "long_relief", "mop_up"}


# --- internal helpers ---

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_lock(team_id: int) -> threading.Lock:
    with _locks_guard:
        if team_id not in _locks:
            _locks[team_id] = threading.Lock()
        return _locks[team_id]


def _chart_path(team_id: int) -> Path:
    return _DATA_DIR / f"{team_id}.json"


def _read(team_id: int) -> dict | None:
    path = _chart_path(team_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write(chart: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _chart_path(chart["team_id"]).write_text(json.dumps(chart, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- read tools ---

def read_depth_chart(team_id: int) -> str:
    """
    Return the current depth chart for a team as a JSON string, or the string
    'null' if no chart exists yet. MUST be called before any write operations
    to determine whether to initialize or update an existing chart.

    Args:
        team_id: MLB team ID (e.g. 147 for the New York Yankees).
    """
    chart = _read(team_id)
    return json.dumps(chart)


def get_depth_at_position(team_id: int, position: str) -> str:
    """
    Return the current depth at a single field position as a JSON array of
    entries sorted by depth_string, or an error string if the chart or
    position does not exist.

    Args:
        team_id: MLB team ID.
        position: Field position to query. Must be one of: C, 1B, 2B, 3B,
            SS, LF, CF, RF, DH.
    """
    if position not in VALID_POSITIONS:
        return f"Error: '{position}' is not a valid position. Valid: {sorted(VALID_POSITIONS)}"
    chart = _read(team_id)
    if chart is None:
        return f"Error: no depth chart found for team_id={team_id}"
    return json.dumps(chart["positions"].get(position, []))


# --- initialize / roster tools ---

def initialize_depth_chart(team_id: int, team_name: str, active_roster_ids: list[int]) -> str:
    """
    Create a fresh, empty depth chart for a team. MUST only be called when
    read_depth_chart returns null — calling this on an existing chart will
    wipe all current entries.

    Args:
        team_id: MLB team ID.
        team_name: Full team name (e.g. "New York Yankees").
        active_roster_ids: List of player_ids from get_active_roster. Every
            player in this list must be charted before validation will pass.
    """
    with _get_lock(team_id):
        chart = {
            "team_id": team_id,
            "team_name": team_name,
            "generated_at": _now(),
            "active_roster_ids": active_roster_ids,
            "positions": {pos: [] for pos in VALID_POSITIONS},
            "rotation": [],
            "bullpen": [],
        }
        _write(chart)
    return f"Initialized empty depth chart for {team_name} (team_id={team_id})"


def update_active_roster_ids(team_id: int, active_roster_ids: list[int]) -> str:
    """
    Replace the stored active_roster_ids on an existing chart without touching
    positions, rotation, or bullpen. MUST be called at the start of every
    update run after fetching the latest active roster, so that validation
    reflects the current 26-man roster.

    Args:
        team_id: MLB team ID.
        active_roster_ids: Complete list of player_ids from get_active_roster.
            Replaces the previous list entirely.
    """
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}. Call initialize_depth_chart first."
        chart["active_roster_ids"] = active_roster_ids
        chart["generated_at"] = _now()
        _write(chart)
    return f"Updated active_roster_ids for team_id={team_id} ({len(active_roster_ids)} players)"


# --- position tools ---

def set_position_player(
    team_id: int,
    position: str,
    player_id: int,
    name: str,
    depth_string: int,
    reasoning: str,
) -> str:
    """
    Add or update a player at a field position. If the player already exists
    at this position their entry is replaced; other players at the position
    are unaffected.

    Args:
        team_id: MLB team ID.
        position: Field position. Must be one of: C, 1B, 2B, 3B, SS, LF,
            CF, RF, DH.
        player_id: MLB player ID from the active roster.
        name: Player's full name (e.g. "Aaron Judge").
        depth_string: Ranking at this position. 1 = starter (required for
            every position), 2 = first backup, 3 = second backup.
        reasoning: At least one specific signal justifying this ranking:
            a lineup appearance frequency, a recent stat, or a transaction
            (e.g. "Started 11 of last 14 games in RF; .310 BA last 14 games").
    """
    if position not in VALID_POSITIONS:
        return f"Error: '{position}' is not a valid position."
    if depth_string not in (1, 2, 3):
        return f"Error: depth_string must be 1, 2, or 3."
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        entries = [e for e in chart["positions"][position] if e["player_id"] != player_id]
        entries.append({"player_id": player_id, "name": name, "depth_string": depth_string, "reasoning": reasoning})
        entries.sort(key=lambda e: e["depth_string"])
        chart["positions"][position] = entries
        _write(chart)
    return f"Set {name} as {position} depth string {depth_string}"


def remove_position_player(team_id: int, position: str, player_id: int) -> str:
    """
    Remove a player from a specific field position. Does not affect their
    entries at other positions, in the rotation, or in the bullpen. Use
    remove_player_everywhere instead when the player must be fully purged.

    Args:
        team_id: MLB team ID.
        position: Field position to remove the player from. Must be one of:
            C, 1B, 2B, 3B, SS, LF, CF, RF, DH.
        player_id: MLB player ID to remove.
    """
    if position not in VALID_POSITIONS:
        return f"Error: '{position}' is not a valid position."
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        before = len(chart["positions"][position])
        chart["positions"][position] = [e for e in chart["positions"][position] if e["player_id"] != player_id]
        _write(chart)
        removed = before - len(chart["positions"][position])
    return f"Removed player_id={player_id} from {position}" if removed else f"player_id={player_id} was not in {position}"


# --- rotation tools ---

def set_rotation_slot(team_id: int, slot: str, player_id: int, name: str, reasoning: str) -> str:
    """
    Assign a pitcher to a rotation slot. Replaces any existing assignment at
    that slot; the displaced pitcher is removed from the rotation entirely.

    Args:
        team_id: MLB team ID.
        slot: Rotation position. Must be one of: SP1, SP2, SP3, SP4, SP5.
            SP1 is the ace, SP5 is the fifth starter.
        player_id: MLB player ID from the active roster.
        name: Pitcher's full name.
        reasoning: At least one specific signal: recent start order,
            innings pitched, or transaction (e.g. "Has taken the ball every
            5th day; leads staff with 7.2 IP per start").
    """
    if slot not in VALID_ROTATION_SLOTS:
        return f"Error: '{slot}' is not a valid rotation slot. Valid: {sorted(VALID_ROTATION_SLOTS)}"
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        chart["rotation"] = [e for e in chart["rotation"] if e["slot"] != slot]
        chart["rotation"].append({"player_id": player_id, "name": name, "slot": slot, "reasoning": reasoning})
        chart["rotation"].sort(key=lambda e: e["slot"])
        _write(chart)
    return f"Set {name} as {slot}"


def remove_rotation_slot(team_id: int, slot: str) -> str:
    """
    Clear a rotation slot. Use when a starter is placed on the IL or optioned
    and no replacement has been identified yet. The slot will remain empty
    until explicitly filled with set_rotation_slot.

    Args:
        team_id: MLB team ID.
        slot: Rotation slot to clear. Must be one of: SP1, SP2, SP3, SP4, SP5.
    """
    if slot not in VALID_ROTATION_SLOTS:
        return f"Error: '{slot}' is not a valid rotation slot."
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        before = len(chart["rotation"])
        chart["rotation"] = [e for e in chart["rotation"] if e["slot"] != slot]
        _write(chart)
        removed = before - len(chart["rotation"])
    return f"Cleared {slot}" if removed else f"{slot} was already empty"


# --- bullpen tools ---

def set_bullpen_role(team_id: int, player_id: int, name: str, role: str, reasoning: str) -> str:
    """
    Add or update a pitcher's bullpen role. If the pitcher already has a
    bullpen entry it is replaced with the new role.

    Args:
        team_id: MLB team ID.
        player_id: MLB player ID from the active roster.
        name: Pitcher's full name.
        role: Bullpen role. Must be one of:
            - closer: records saves; typically enters with a lead in the 9th.
            - setup: records holds; typically enters in the 7th or 8th.
            - middle_relief: multi-inning or situational middle innings work.
            - long_relief: routinely pitches 2+ innings, often after a short start.
            - mop_up: enters in blowouts; lowest-leverage appearances.
        reasoning: At least one specific signal: saves, holds, appearance
            order, or innings pitched from recent games (e.g. "3 saves in
            last 14 days; entered in 9th inning in all appearances").
    """
    if role not in VALID_BULLPEN_ROLES:
        return f"Error: '{role}' is not a valid bullpen role. Valid: {sorted(VALID_BULLPEN_ROLES)}"
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        chart["bullpen"] = [e for e in chart["bullpen"] if e["player_id"] != player_id]
        chart["bullpen"].append({"player_id": player_id, "name": name, "role": role, "reasoning": reasoning})
        _write(chart)
    return f"Set {name} as {role}"


def remove_bullpen_player(team_id: int, player_id: int) -> str:
    """
    Remove a pitcher from the bullpen. Does not affect their rotation slot
    if they have one. Use remove_player_everywhere to remove from all sections.

    Args:
        team_id: MLB team ID.
        player_id: MLB player ID to remove from the bullpen.
    """
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        before = len(chart["bullpen"])
        chart["bullpen"] = [e for e in chart["bullpen"] if e["player_id"] != player_id]
        _write(chart)
        removed = before - len(chart["bullpen"])
    return f"Removed player_id={player_id} from bullpen" if removed else f"player_id={player_id} was not in bullpen"


# --- cross-cutting tools ---

def remove_player_everywhere(team_id: int, player_id: int) -> str:
    """
    Remove a player from all positions, rotation slots, and bullpen entries
    in one call. Prefer this over multiple remove_position_player calls when
    a player is traded, DFA'd, or placed on the IL and must be fully purged.

    Args:
        team_id: MLB team ID.
        player_id: MLB player ID to remove from the entire depth chart.
    """
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."

        removed_from = []
        for pos in VALID_POSITIONS:
            before = len(chart["positions"][pos])
            chart["positions"][pos] = [e for e in chart["positions"][pos] if e["player_id"] != player_id]
            if len(chart["positions"][pos]) < before:
                removed_from.append(pos)

        before = len(chart["rotation"])
        chart["rotation"] = [e for e in chart["rotation"] if e["player_id"] != player_id]
        if len(chart["rotation"]) < before:
            removed_from.append("rotation")

        before = len(chart["bullpen"])
        chart["bullpen"] = [e for e in chart["bullpen"] if e["player_id"] != player_id]
        if len(chart["bullpen"]) < before:
            removed_from.append("bullpen")

        _write(chart)
    if removed_from:
        return f"Removed player_id={player_id} from: {', '.join(removed_from)}"
    return f"player_id={player_id} was not found anywhere in the depth chart"


# --- validation ---

def validate_depth_chart(team_id: int) -> str:
    """
    Validate the depth chart against all correctness rules. Returns a JSON
    object with 'valid' (bool) and 'violations' (list[str]). MUST be called
    after every write pass. If valid is true, stop — do not make further
    changes. If valid is false, correct only the flagged violations and
    validate again (up to 3 attempts).

    Rules checked:
        1. Every active roster player appears at least once in the chart.
        2. No player absent from the active roster appears anywhere.
        3. Every field position (C, 1B, 2B, 3B, SS, LF, CF, RF, DH) has a
           depth_string=1 assignment.
        4. The rotation contains between 1 and 5 entries.
        5. Every active-roster pitcher not in the rotation appears in the bullpen.

    Args:
        team_id: MLB team ID.
    """
    chart = _read(team_id)
    if chart is None:
        return json.dumps({"valid": False, "violations": [f"No depth chart found for team_id={team_id}"]})

    violations = []
    active_ids = set(chart["active_roster_ids"])

    # Collect all player_ids present anywhere in the chart
    charted_ids: set[int] = set()
    for pos in VALID_POSITIONS:
        for e in chart["positions"].get(pos, []):
            charted_ids.add(e["player_id"])
    for e in chart["rotation"]:
        charted_ids.add(e["player_id"])
    for e in chart["bullpen"]:
        charted_ids.add(e["player_id"])

    # Rule 1: every active roster player must appear at least once
    missing = active_ids - charted_ids
    for pid in sorted(missing):
        violations.append(f"Active roster player_id={pid} does not appear anywhere in the depth chart")

    # Rule 2: no player outside the active roster may appear
    extra = charted_ids - active_ids
    for pid in sorted(extra):
        violations.append(f"player_id={pid} appears in the depth chart but is not on the active roster")

    # Rule 3: every field position must have a 1st-string entry
    for pos in VALID_POSITIONS:
        entries = chart["positions"].get(pos, [])
        if not any(e["depth_string"] == 1 for e in entries):
            violations.append(f"Position {pos} has no 1st-string player assigned")

    # Rule 4: rotation must have between 1 and 5 slots
    if not (1 <= len(chart["rotation"]) <= 5):
        violations.append(f"Rotation has {len(chart['rotation'])} slots (must be 1–5)")

    # Rule 5: every active-roster pitcher not in rotation must be in bullpen
    rotation_ids = {e["player_id"] for e in chart["rotation"]}
    bullpen_ids = {e["player_id"] for e in chart["bullpen"]}
    position_ids = {e["player_id"] for pos in VALID_POSITIONS for e in chart["positions"].get(pos, [])}

    # A player is considered a pitcher if they appear in rotation or bullpen but
    # not exclusively in field positions
    pitchers_in_chart = (rotation_ids | bullpen_ids) & active_ids
    unassigned_pitchers = pitchers_in_chart - rotation_ids - bullpen_ids
    for pid in sorted(unassigned_pitchers):
        violations.append(f"Pitcher player_id={pid} is on the active roster but not in rotation or bullpen")

    return json.dumps({"valid": len(violations) == 0, "violations": violations})


# --- agent tool wrappers ---
# These are the FunctionTool objects passed to the Agent. The plain functions
# above are used directly in tests and other internal callers.

DEPTH_CHART_TOOLS = [
    function_tool(read_depth_chart),
    function_tool(get_depth_at_position),
    function_tool(initialize_depth_chart),
    function_tool(update_active_roster_ids),
    function_tool(set_position_player),
    function_tool(remove_position_player),
    function_tool(set_rotation_slot),
    function_tool(remove_rotation_slot),
    function_tool(set_bullpen_role),
    function_tool(remove_bullpen_player),
    function_tool(remove_player_everywhere),
    function_tool(validate_depth_chart),
]
