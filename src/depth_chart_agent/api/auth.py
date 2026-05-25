from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_header)) -> None:
    expected = os.getenv("DEPTH_CHART_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="DEPTH_CHART_API_KEY is not configured on this server")
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
