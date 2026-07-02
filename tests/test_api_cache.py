"""cached_response must not silently skip caching on non-JSON-native payloads
(the F5 gate found /network/storm's datetimes disabled its cache entirely)."""
from __future__ import annotations

from datetime import datetime, timezone


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value


def test_cached_response_serializes_datetime_payloads(monkeypatch):
    import api.cache as api_cache

    fake = _FakeRedis()
    monkeypatch.setattr(api_cache, "get_client", lambda: fake)

    calls = {"n": 0}

    @api_cache.cached_response("_test_dt", ttl=60)
    def handler(x: int = 1) -> dict:
        calls["n"] += 1
        return {"at": datetime(2026, 7, 2, tzinfo=timezone.utc), "x": x}

    first = handler(x=1)
    assert calls["n"] == 1
    assert first["x"] == 1
    # The datetime payload actually landed in the cache …
    assert any(k.startswith("geojson:_test_dt:") for k in fake.store)

    # … and the second call is served from it (handler not re-invoked).
    second = handler(x=1)
    assert calls["n"] == 1
    assert second["x"] == 1
