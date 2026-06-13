"""Structured (JSON) logging for the API and worker services.

In prod (`PRISM_LOG_FORMAT=json`, set in docker-compose.prod.yml), every log
record — including uvicorn's access log — is emitted as one JSON object per
line, so it can be picked up by a log aggregator without a parsing step.
Local dev keeps the default human-readable uvicorn format.
"""
from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    if os.getenv("PRISM_LOG_FORMAT", "").lower() != "json":
        return

    from pythonjsonlogger import jsonlogger

    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )

    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.handlers = [handler]
    root.setLevel(os.getenv("PRISM_LOG_LEVEL", "INFO"))

    # uvicorn installs its own handlers on these loggers — replace them too so
    # access/error logs are also JSON.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False
