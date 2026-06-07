from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import boto3

logger = logging.getLogger(__name__)

RefreshStatus = Literal["pending", "running", "complete", "failed"]

_JOB_TTL = 3600   # job records expire after 1 hour
_LOCK_TTL = 900   # lock expires after 15 min (safety valve for crashed runs)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RefreshManager:
    def __init__(self) -> None:
        self._table = boto3.resource("dynamodb").Table(os.environ["DYNAMODB_TABLE"])

    async def close(self) -> None:
        pass

    async def get_lock(self, team_id: int) -> str | None:
        """Return the refresh_id for an in-progress run, or None."""
        resp = await asyncio.to_thread(
            self._table.get_item, Key={"pk": f"lock#{team_id}"}
        )
        item = resp.get("Item")
        return item["refresh_id"] if item else None

    async def create_job(self, team_id: int, team_name: str) -> str:
        """Create a job record and in-progress lock. Returns the new refresh_id."""
        refresh_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        job_ttl = int((now + timedelta(seconds=_JOB_TTL)).timestamp())
        lock_ttl = int((now + timedelta(seconds=_LOCK_TTL)).timestamp())

        await asyncio.to_thread(
            self._table.put_item,
            Item={
                "pk": f"job#{refresh_id}",
                "refresh_id": refresh_id,
                "team_id": team_id,
                "team_name": team_name,
                "status": "pending",
                "triggered_at": now.isoformat(),
                "completed_at": None,
                "error": None,
                "ttl": job_ttl,
            },
        )
        await asyncio.to_thread(
            self._table.put_item,
            Item={
                "pk": f"lock#{team_id}",
                "refresh_id": refresh_id,
                "ttl": lock_ttl,
            },
        )
        logger.info("refresh job created refresh_id=%s team_id=%s team=%s", refresh_id, team_id, team_name)
        return refresh_id

    async def get_job(self, refresh_id: str) -> dict | None:
        resp = await asyncio.to_thread(
            self._table.get_item, Key={"pk": f"job#{refresh_id}"}
        )
        item = resp.get("Item")
        if not item:
            return None
        return {
            "refresh_id": item["refresh_id"],
            "team_id": int(item["team_id"]),
            "team_name": item["team_name"],
            "status": item["status"],
            "triggered_at": item["triggered_at"],
            "completed_at": item.get("completed_at"),
            "error": item.get("error"),
        }

    async def update_status(
        self,
        refresh_id: str,
        status: RefreshStatus,
        error: str | None = None,
    ) -> None:
        update_expr = "SET #status = :status"
        expr_names = {"#status": "status"}
        expr_values = {":status": status}

        if status in ("complete", "failed"):
            update_expr += ", completed_at = :completed_at"
            expr_values[":completed_at"] = _now()
        if error:
            update_expr += ", #error = :error"
            expr_names["#error"] = "error"
            expr_values[":error"] = error

        await asyncio.to_thread(
            self._table.update_item,
            Key={"pk": f"job#{refresh_id}"},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
        level = logging.ERROR if status == "failed" else logging.INFO
        logger.log(level, "refresh job %s status=%s%s",
                   refresh_id, status, f" error={error}" if error else "")

    async def release_lock(self, team_id: int) -> None:
        await asyncio.to_thread(
            self._table.delete_item, Key={"pk": f"lock#{team_id}"}
        )
