from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "depth_charts"


def _chart_dir(team_id: int) -> Path:
    return DATA_DIR / str(team_id)


def _ts_to_stem(dt: datetime) -> str:
    """Convert a datetime to a filesystem/S3-safe stem: 2026-05-30T14-32-11Z"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _stem_to_ts(stem: str) -> datetime:
    return datetime.strptime(stem, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)


def _s3():
    return boto3.client("s3")


def read_chart(team_id: int) -> dict | None:
    if bucket := os.getenv("S3_BUCKET"):
        resp = _s3().list_objects_v2(Bucket=bucket, Prefix=f"{team_id}/")
        objects = resp.get("Contents", [])
        if not objects:
            return None
        latest = sorted(objects, key=lambda o: o["Key"])[-1]
        obj = _s3().get_object(Bucket=bucket, Key=latest["Key"])
        return json.loads(obj["Body"].read())
    chart_dir = _chart_dir(team_id)
    if not chart_dir.exists():
        return None
    snapshots = sorted(chart_dir.glob("*.json"))
    if not snapshots:
        return None
    return json.loads(snapshots[-1].read_text())


def write_chart(chart: dict) -> None:
    generated_at = datetime.fromisoformat(chart["generated_at"])
    stem = _ts_to_stem(generated_at)
    if bucket := os.getenv("S3_BUCKET"):
        _s3().put_object(
            Bucket=bucket,
            Key=f"{chart['team_id']}/{stem}.json",
            Body=json.dumps(chart, indent=2),
        )
        return
    chart_dir = _chart_dir(chart["team_id"])
    chart_dir.mkdir(parents=True, exist_ok=True)
    path = chart_dir / f"{stem}.json"
    with tempfile.NamedTemporaryFile("w", dir=chart_dir, suffix=".tmp", delete=False) as f:
        json.dump(chart, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)


def list_charts(team_id: int) -> list[dict]:
    """Return all snapshots for a team, newest first."""
    if bucket := os.getenv("S3_BUCKET"):
        resp = _s3().list_objects_v2(Bucket=bucket, Prefix=f"{team_id}/")
        objects = sorted(resp.get("Contents", []), key=lambda o: o["Key"], reverse=True)
        return [
            {
                "snapshot_id": o["Key"].split("/")[-1].removesuffix(".json"),
                "generated_at": _stem_to_ts(o["Key"].split("/")[-1].removesuffix(".json")).isoformat(),
            }
            for o in objects
        ]
    chart_dir = _chart_dir(team_id)
    if not chart_dir.exists():
        return []
    snapshots = sorted(chart_dir.glob("*.json"), reverse=True)
    return [
        {"snapshot_id": p.stem, "generated_at": _stem_to_ts(p.stem).isoformat()}
        for p in snapshots
    ]


def read_chart_at(team_id: int, snapshot_id: str) -> dict | None:
    if bucket := os.getenv("S3_BUCKET"):
        try:
            obj = _s3().get_object(Bucket=bucket, Key=f"{team_id}/{snapshot_id}.json")
            return json.loads(obj["Body"].read())
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
    path = _chart_dir(team_id) / f"{snapshot_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
