"""Thin Redis helper shared by the API cache layer and the sync spine.

Optional dependency: if `redis` isn't installed or `REDIS_URL` isn't set
(e.g. local non-Docker runs), every function here is a no-op. The sync spine
must work without Redis — caching is a perceived-performance layer, not a
correctness dependency.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover - redis is an optional dependency
    redis = None  # type: ignore[assignment]

_client = None
_client_checked = False


def get_client():
    """Process-wide Redis client, or None if unavailable/unconfigured."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if redis is None:
        return None
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        _client = client
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Redis unavailable (%s); caching disabled", exc)
        _client = None
    return _client


# Maps a PostGIS table (the unit a sync source updates) to the API cache-key
# prefixes that serve data derived from it. Used to invalidate stale
# GeoJSON/MVT caches after `prism.sync` detects a change.
LAYER_CACHE_PREFIXES: dict[str, list[str]] = {
    "flood_zones": ["flood"],
    "graph.tx_network": ["transmission"],
    "economy.barrio_economics": ["tracts"],
}


def invalidate_layer(table: str) -> int:
    """Delete cached GeoJSON/MVT responses derived from `table`. Returns keys deleted."""
    client = get_client()
    if client is None:
        return 0
    deleted = 0
    for prefix in LAYER_CACHE_PREFIXES.get(table, []):
        for pattern in (f"geojson:{prefix}*", f"tiles:{prefix}:*"):
            keys = client.keys(pattern)
            if keys:
                deleted += client.delete(*keys)
    return deleted
