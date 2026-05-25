from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "depth_charts"


def chart_path(team_id: int) -> Path:
    return DATA_DIR / f"{team_id}.json"


def read_chart(team_id: int) -> dict | None:
    path = chart_path(team_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_chart(chart: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = chart_path(chart["team_id"])
    with tempfile.NamedTemporaryFile("w", dir=DATA_DIR, suffix=".tmp", delete=False) as f:
        json.dump(chart, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)
