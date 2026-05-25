from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

RefreshStatus = Literal["pending", "running", "complete", "failed"]

_JOB_TTL = 3600   # job records expire after 1 hour
_LOCK_TTL = 900   # lock expires after 15 min (safety valve for crashed runs)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RefreshManager:
    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def close(self) -> None:
        await self._redis.aclose()

    async def get_lock(self, team_id: int) -> str | None:
        """Return the refresh_id for an in-progress run, or None."""
        return await self._redis.get(f"refresh:lock:{team_id}")

    async def create_job(self, team_id: int, team_name: str) -> str:
        """Create a job record and in-progress lock. Returns the new refresh_id."""
        refresh_id = str(uuid.uuid4())
        job = {
            "refresh_id": refresh_id,
            "team_id": team_id,
            "team_name": team_name,
            "status": "pending",
            "triggered_at": _now(),
            "completed_at": None,
            "error": None,
        }
        pipe = self._redis.pipeline()
        pipe.set(f"refresh:{refresh_id}", json.dumps(job), ex=_JOB_TTL)
        pipe.set(f"refresh:lock:{team_id}", refresh_id, ex=_LOCK_TTL)
        await pipe.execute()
        logger.info("refresh job created refresh_id=%s team_id=%s team=%s", refresh_id, team_id, team_name)
        return refresh_id

    async def get_job(self, refresh_id: str) -> dict | None:
        data = await self._redis.get(f"refresh:{refresh_id}")
        return json.loads(data) if data else None

    async def update_status(
        self,
        refresh_id: str,
        status: RefreshStatus,
        error: str | None = None,
    ) -> None:
        data = await self._redis.get(f"refresh:{refresh_id}")
        if data is None:
            return
        job = json.loads(data)
        job["status"] = status
        if status in ("complete", "failed"):
            job["completed_at"] = _now()
        if error:
            job["error"] = error
        await self._redis.set(f"refresh:{refresh_id}", json.dumps(job), ex=_JOB_TTL)
        level = logging.ERROR if status == "failed" else logging.INFO
        logger.log(level, "refresh job %s status=%s team_id=%s%s",
                   refresh_id, status, job["team_id"], f" error={error}" if error else "")

    async def release_lock(self, team_id: int) -> None:
        await self._redis.delete(f"refresh:lock:{team_id}")
