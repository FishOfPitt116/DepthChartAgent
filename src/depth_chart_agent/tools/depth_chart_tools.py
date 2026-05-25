from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from agents import function_tool
from pydantic import BaseModel

from depth_chart_agent.mlb_client import get_active_roster

# Project root / data / depth_charts
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "depth_charts"

VALID_POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
VALID_ROTATION_SLOTS = {"SP1", "SP2", "SP3", "SP4", "SP5"}
VALID_BULLPEN_ROLES = {"closer", "setup", "middle_relief", "long_relief", "mop_up"}


# --- entry models (used as list elements in batch write tools) ---

class PositionEntry(BaseModel):
    position: str
    player_id: int
    name: str
    depth_string: int
    reasoning: str

class RotationEntry(BaseModel):
    slot: str
    player_id: int
    name: str
    reasoning: str

class BullpenEntry(BaseModel):
    player_id: int
    name: str
    role: str
    reasoning: str


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

def initialize_depth_chart(team_id: int, team_name: str) -> str:
    """
    Create a fresh, empty depth chart for a team. MUST only be called when
    read_depth_chart returns null — calling this on an existing chart will
    wipe all current entries. Fetches the current active roster automatically;
    do not pass roster IDs separately.

    Args:
        team_id: MLB team ID.
        team_name: Full team name (e.g. "New York Yankees").
    """
    roster = get_active_roster(team_id)
    active_roster_ids = [p["player_id"] for p in roster]
    active_roster = {
        str(p["player_id"]): {"name": p.get("name", ""), "position": p.get("position", "?")}
        for p in roster
    }
    with _get_lock(team_id):
        chart = {
            "team_id": team_id,
            "team_name": team_name,
            "generated_at": _now(),
            "active_roster_ids": active_roster_ids,
            "active_roster": active_roster,
            "positions": {pos: [] for pos in VALID_POSITIONS},
            "rotation": [],
            "bullpen": [],
        }
        _write(chart)
    return f"Initialized empty depth chart for {team_name} (team_id={team_id})"


def update_active_roster_ids(team_id: int) -> str:
    """
    Re-fetch the current active roster and replace the stored active_roster_ids
    on an existing chart without touching positions, rotation, or bullpen. MUST
    be called at the start of every update run so that validation reflects the
    current 26-man roster. Do not pass roster IDs — they are fetched automatically.

    Args:
        team_id: MLB team ID.
    """
    roster = get_active_roster(team_id)
    active_roster_ids = [p["player_id"] for p in roster]
    active_roster = {
        str(p["player_id"]): {"name": p.get("name", ""), "position": p.get("position", "?")}
        for p in roster
    }
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}. Call initialize_depth_chart first."
        chart["active_roster_ids"] = active_roster_ids
        chart["active_roster"] = active_roster
        chart["generated_at"] = _now()
        _write(chart)
    return f"Updated active_roster_ids for team_id={team_id} ({len(active_roster_ids)} players)"


# --- position tools ---

def set_position_players(team_id: int, entries: list[PositionEntry]) -> str:
    """
    Add or update one or more players at field positions in a single call.
    Pass a list with one entry for a targeted update or many entries to batch
    the entire position write in one round trip. Existing entries for a player
    at a position are replaced; other players at that position are unaffected.

    Args:
        team_id: MLB team ID.
        entries: List of position assignments. Each entry requires:
            position: Must be one of: C, 1B, 2B, 3B, SS, LF, CF, RF, DH.
            player_id: MLB player ID from the active roster.
            name: Player's full name.
            depth_string: 1 = starter, 2 = first backup, 3 = second backup.
            reasoning: Actual numbers observed in tool output — not estimates.
                Cite start count at this position and any relevant stat
                (e.g. "Started [N] of last [M] games in [POS]; [stat] last [M] games").
    """
    for e in entries:
        if e.position not in VALID_POSITIONS:
            return f"Error: '{e.position}' is not a valid position."
        if e.depth_string not in (1, 2, 3):
            return f"Error: depth_string must be 1, 2, or 3 (got {e.depth_string} for {e.name})."
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        for e in entries:
            existing = [x for x in chart["positions"][e.position] if x["player_id"] != e.player_id]
            existing.append({"player_id": e.player_id, "name": e.name, "depth_string": e.depth_string, "reasoning": e.reasoning})
            existing.sort(key=lambda x: x["depth_string"])
            chart["positions"][e.position] = existing
        _write(chart)
    lines = [f"{e.name} → {e.position} depth string {e.depth_string}" for e in entries]
    return f"Set {len(entries)} position player(s): " + "; ".join(lines)


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

def set_rotation_slots(team_id: int, entries: list[RotationEntry]) -> str:
    """
    Assign one or more pitchers to rotation slots in a single call. Pass a
    list with one entry for a targeted update or all starters at once to batch
    the entire rotation write in one round trip. Replaces any existing
    assignment at each slot.

    Args:
        team_id: MLB team ID.
        entries: List of rotation assignments. Each entry requires:
            slot: Must be one of: SP1, SP2, SP3, SP4, SP5. SP1 is the ace.
            player_id: MLB player ID from the active roster.
            name: Pitcher's full name.
            reasoning: Actual numbers from Phase 1.2 pitcher analysis — not
                estimates. Cite observed start count and avg IP/start
                (e.g. "Started [N] of last [M] games; avg [X.Y] IP/start").
    """
    for e in entries:
        if e.slot not in VALID_ROTATION_SLOTS:
            return f"Error: '{e.slot}' is not a valid rotation slot. Valid: {sorted(VALID_ROTATION_SLOTS)}"
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        for e in entries:
            chart["rotation"] = [x for x in chart["rotation"] if x["slot"] != e.slot]
            chart["rotation"].append({"player_id": e.player_id, "name": e.name, "slot": e.slot, "reasoning": e.reasoning})
        chart["rotation"].sort(key=lambda x: x["slot"])
        _write(chart)
    lines = [f"{e.name} → {e.slot}" for e in entries]
    return f"Set {len(entries)} rotation slot(s): " + "; ".join(lines)


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

def set_bullpen_roles(team_id: int, entries: list[BullpenEntry]) -> str:
    """
    Add or update one or more pitchers' bullpen roles in a single call. Pass
    a list with one entry for a targeted update or all relievers at once to
    batch the entire bullpen write in one round trip. Existing entries for a
    pitcher are replaced with the new role.

    Args:
        team_id: MLB team ID.
        entries: List of bullpen assignments. Each entry requires:
            player_id: MLB player ID from the active roster.
            name: Pitcher's full name.
            role: Must be one of:
                closer — records saves; enters with a lead in the 9th.
                setup — records holds; enters in the 7th or 8th.
                middle_relief — situational middle innings, 1–2 IP.
                long_relief — 3+ IP; often follows a short start or opener.
                mop_up — enters in blowouts; lowest-leverage appearances.
            reasoning: Actual numbers from Phase 1.2 pitcher analysis — not
                estimates. Cite appearance count and role-defining stat
                (e.g. "[N] saves, [N] blown saves; entered 9th in [N] of [M] appearances").
    """
    for e in entries:
        if e.role not in VALID_BULLPEN_ROLES:
            return f"Error: '{e.role}' is not a valid bullpen role. Valid: {sorted(VALID_BULLPEN_ROLES)}"
    with _get_lock(team_id):
        chart = _read(team_id)
        if chart is None:
            return f"Error: no depth chart found for team_id={team_id}."
        for e in entries:
            chart["bullpen"] = [x for x in chart["bullpen"] if x["player_id"] != e.player_id]
            chart["bullpen"].append({"player_id": e.player_id, "name": e.name, "role": e.role, "reasoning": e.reasoning})
        _write(chart)
    lines = [f"{e.name} → {e.role}" for e in entries]
    return f"Set {len(entries)} bullpen role(s): " + "; ".join(lines)


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
    active_roster_map: dict[str, dict] = chart.get("active_roster", {})

    def _roster_info(pid: int) -> tuple[str, str]:
        """Return (name, position) for a player_id, falling back to bare ID."""
        info = active_roster_map.get(str(pid), {})
        return info.get("name") or f"player_id={pid}", info.get("position", "?")

    # Collect all player_ids present anywhere in the chart
    charted_ids: set[int] = set()
    for pos in VALID_POSITIONS:
        for e in chart["positions"].get(pos, []):
            charted_ids.add(e["player_id"])
    for e in chart["rotation"]:
        charted_ids.add(e["player_id"])
    for e in chart["bullpen"]:
        charted_ids.add(e["player_id"])

    rotation_ids = {e["player_id"] for e in chart["rotation"]}
    bullpen_ids = {e["player_id"] for e in chart["bullpen"]}

    # Rule 1: every active roster player must appear at least once
    missing = active_ids - charted_ids
    for pid in sorted(missing):
        name, pos = _roster_info(pid)
        violations.append(
            f"{name} (player_id={pid}, position={pos}) is on the active roster but missing from the depth chart"
        )

    # Rule 2: no player outside the active roster may appear
    extra = charted_ids - active_ids
    for pid in sorted(extra):
        name = next(
            (e["name"] for pos in VALID_POSITIONS for e in chart["positions"].get(pos, []) if e["player_id"] == pid),
            next((e["name"] for e in chart["rotation"] + chart["bullpen"] if e["player_id"] == pid), f"player_id={pid}"),
        )
        violations.append(
            f"{name} (player_id={pid}) is in the depth chart but is not on the active roster"
        )

    # Rule 3: every field position must have a 1st-string entry
    for pos in VALID_POSITIONS:
        entries = chart["positions"].get(pos, [])
        if not any(e["depth_string"] == 1 for e in entries):
            violations.append(f"Position {pos} has no 1st-string player assigned")

    # Rule 4: rotation must have between 1 and 5 slots
    if not (1 <= len(chart["rotation"]) <= 5):
        violations.append(f"Rotation has {len(chart['rotation'])} slots (must be 1–5)")

    # Rule 5: active-roster pitchers must appear in rotation or bullpen, not just field positions
    for pid in sorted(active_ids):
        name, pos = _roster_info(pid)
        if pos == "P" and pid in charted_ids and pid not in rotation_ids and pid not in bullpen_ids:
            violations.append(
                f"{name} (player_id={pid}) is a pitcher but only appears in field positions"
            )

    return json.dumps({"valid": len(violations) == 0, "violations": violations})


# --- agent tool wrappers ---
# These are the FunctionTool objects passed to the Agent. The plain functions
# above are used directly in tests and other internal callers.

DEPTH_CHART_TOOLS = [
    function_tool(read_depth_chart),
    function_tool(get_depth_at_position),
    function_tool(initialize_depth_chart),
    function_tool(update_active_roster_ids),
    function_tool(set_position_players),
    function_tool(remove_position_player),
    function_tool(set_rotation_slots),
    function_tool(remove_rotation_slot),
    function_tool(set_bullpen_roles),
    function_tool(remove_bullpen_player),
    function_tool(remove_player_everywhere),
    function_tool(validate_depth_chart),
]
