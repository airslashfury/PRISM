"""Shared slowapi rate limiter, backed by Redis when REDIS_URL is set.

Applied only to endpoints that do real per-request work: background job
enqueueing (api/routers/jobs.py) and AI narrative streaming
(api/routers/reports.py). Read-only GeoJSON/MVT endpoints are unthrottled —
they're cheap (and cached, see api/cache.py + api/routers/tiles.py).

Falls back to an in-memory store if REDIS_URL isn't set (local dev without
Docker); per-process limits are still better than nothing there.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("REDIS_URL", "memory://"),
)
