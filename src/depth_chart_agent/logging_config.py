from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "app.log"

_FMT = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def configure_logging() -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    logger = logging.getLogger("depth_chart_agent")
    logger.setLevel(level)

    if logger.handlers:
        return  # already configured (e.g. uvicorn --reload re-enters lifespan)

    sh = logging.StreamHandler()
    sh.setFormatter(_FMT)
    logger.addHandler(sh)

    if not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        fh.setFormatter(_FMT)
        logger.addHandler(fh)
