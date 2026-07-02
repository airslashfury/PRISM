"""Response cache decorator for heavy read-only endpoints.

Wraps a route handler that returns a JSON-serializable dict (GeoJSON
FeatureCollections in practice). Falls back to calling the handler directly
when Redis isn't reachable — caching is a perf layer, not a dependency.

Cache invalidation is driven by `prism.cache.invalidate_layer`, called from
the sync spine when an underlying table changes (see `prism/sync/resync.py`).
"""
from __future__ import annotations

import hashlib
import json
from functools import wraps
from typing import Any, Callable

from prism.cache import get_client


def cached_response(prefix: str, ttl: int = 3600) -> Callable:
    """Cache a route handler's dict return value in Redis under `geojson:{prefix}:...`."""

    def decorator(fn: Callable[..., dict]) -> Callable[..., dict]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            client = get_client()
            if client is None:
                return fn(*args, **kwargs)

            key_parts = {
                k: v for k, v in kwargs.items()
                if isinstance(v, (str, int, float, bool)) or v is None
            }
            digest = hashlib.sha256(json.dumps(key_parts, sort_keys=True).encode()).hexdigest()[:16]
            cache_key = f"geojson:{prefix}:{digest}"

            cached = client.get(cache_key)
            if cached is not None:
                return json.loads(cached)

            result = fn(*args, **kwargs)
            try:
                # default=str: handlers may return datetime fields (e.g.
                # /network/storm's issued_at/computed_at) — without it the dump
                # raises and the except below silently disables caching for
                # that endpoint. FastAPI re-validates cached responses against
                # the response model, so ISO-ish strings round-trip fine.
                client.set(cache_key, json.dumps(result, default=str), ex=ttl)
            except Exception:
                pass
            return result

        return wrapper

    return decorator
