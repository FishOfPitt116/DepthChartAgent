from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "depth_charts"


def _chart_dir(team_id: int) -> Path:
    return DATA_DIR / str(team_id)


def _ts_to_stem(dt: datetime) -> str:
    """Convert a datetime to a filesystem-safe stem: 2026-05-30T14-32-11Z"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _stem_to_ts(stem: str) -> datetime:
    return datetime.strptime(stem, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)


def read_chart(team_id: int) -> dict | None:
    chart_dir = _chart_dir(team_id)
    if not chart_dir.exists():
        return None
    snapshots = sorted(chart_dir.glob("*.json"))
    if not snapshots:
        return None
    return json.loads(snapshots[-1].read_text())


def write_chart(chart: dict) -> None:
    chart_dir = _chart_dir(chart["team_id"])
    chart_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.fromisoformat(chart["generated_at"])
    path = chart_dir / f"{_ts_to_stem(generated_at)}.json"
    with tempfile.NamedTemporaryFile("w", dir=chart_dir, suffix=".tmp", delete=False) as f:
        json.dump(chart, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)


def list_charts(team_id: int) -> list[dict]:
    """Return all snapshots for a team, newest first."""
    chart_dir = _chart_dir(team_id)
    if not chart_dir.exists():
        return []
    snapshots = sorted(chart_dir.glob("*.json"), reverse=True)
    return [
        {"snapshot_id": p.stem, "generated_at": _stem_to_ts(p.stem).isoformat()}
        for p in snapshots
    ]


def read_chart_at(team_id: int, snapshot_id: str) -> dict | None:
    path = _chart_dir(team_id) / f"{snapshot_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
