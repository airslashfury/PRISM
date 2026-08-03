"""Census PR forward geocoder client (F9d D1) — address text -> standardized
address + point, for the "search by address" affordance on `/parcels`.

The endpoint (`geocoding.geo.census.gov/geocoder/locations/addressPR`) is
keyless and free but is a live external host, so every response is mirrored
into `crim.geocode_cache` (data-sovereignty rule) and looked up there first.
This is call-time enrichment, not a batch pull — see
`docs/data_requests/address_enrichment_research.md` for why a blind 1.53M
batch geocode is low-yield and not worth the external API cost.

Match-quality policy (roadmap F9d build note): only the geocoder's exact
match tier is treated as confident. Multiple candidates ("tie") or no
candidates are both treated as "no confident match" — PRISM never guesses
between ambiguous matches.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine
from prism.sync import http as prism_http

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressPR"
BENCHMARK = "Public_AR_Current"
LICENSE = "public domain (U.S. Census Bureau)"

MatchTier = Literal["match", "tie", "no_match"]

# Keyless public endpoint — self-throttle to be a polite caller regardless of
# how many parcel searches route through this client concurrently. Enforced by
# the shared client's per-host rate limiter (`rate_limit_s` below), not a
# module-local throttle.
_MIN_INTERVAL_S = 0.5


def _cache_key(street: str, urb: str | None, municipio: str | None, zip_code: str | None) -> str:
    norm = "|".join(
        (part or "").strip().lower()
        for part in (street, urb, municipio, zip_code)
    )
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _query_census(street: str, urb: str | None, municipio: str | None,
                   zip_code: str | None, timeout: int) -> dict[str, Any]:
    # addressPR only accepts two combos: (street + urb + municipio) or
    # (street + city/ZIP) — a bare `municipio` with no `urb` is rejected, so
    # route a municipio-only query through the `city` param instead.
    params: dict[str, str] = {"street": street, "state": "PR",
                               "benchmark": BENCHMARK, "format": "json"}
    if urb and municipio:
        params["urb"] = urb
        params["municipio"] = municipio
    elif municipio:
        params["city"] = municipio
    if zip_code:
        params["zip"] = zip_code

    # Throttling is the shared client's job now (rate_limit_s below); keeping
    # this module's own `_throttle()` too would double the wait to ~1s a call.
    try:
        resp = prism_http.fetch(
            GEOCODE_URL, source="census_geocoder", params=params,
            policy=prism_http.RetryPolicy(attempts=3, read_timeout=float(timeout),
                                          rate_limit_s=_MIN_INTERVAL_S),
        )
    except prism_http.PermanentError as exc:
        # A 400 is a real answer from addressPR, not a failure: the endpoint
        # requires Urb+Municipio OR City/ZIP, so a query omitting all three is
        # unmatchable. Degrade to "no confident match" rather than a 500.
        # `fetch` raises on any 4xx, so this is the only place a 400 surfaces.
        if "HTTP 400" not in str(exc):
            raise
        return {"result": {"addressMatches": []}}
    return resp.json()


def _classify(payload: dict[str, Any]) -> tuple[MatchTier, dict[str, Any] | None]:
    matches = (payload.get("result") or {}).get("addressMatches") or []
    if len(matches) == 1:
        return "match", matches[0]
    if len(matches) > 1:
        return "tie", None
    return "no_match", None


def geocode_address(
    engine: Engine,
    street: str,
    *,
    urb: str | None = None,
    municipio: str | None = None,
    zip_code: str | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """Forward-geocode one address, cache-first. Returns:

    ``{status, standardized_address, lon, lat}`` where ``status`` is one of
    'match' (single confident hit), 'no_confident_match' (tie or no match —
    the caller should present an honest fallback), from either the local
    cache or a fresh Census call (which is then cached).
    """
    street = (street or "").strip()
    if not street:
        return {"status": "no_confident_match", "standardized_address": None, "lon": None, "lat": None}

    key = _cache_key(street, urb, municipio, zip_code)
    with engine.connect() as conn:
        cached = conn.execute(text("""
            SELECT match_tier, matched_address, lon, lat
            FROM crim.geocode_cache WHERE cache_key = :k
        """), {"k": key}).mappings().fetchone()

    if cached is not None:
        tier = cached["match_tier"]
    else:
        try:
            payload = _query_census(street, urb, municipio, zip_code, timeout)
        except (requests.RequestException, prism_http.PullError) as exc:
            # `_query_census` goes through the shared client (F14d), which
            # never lets a `requests.RequestException` escape — transients and
            # permanents both come out as `prism_http.PullError` subclasses.
            # Catching only the old exception type left this unreachable: a
            # Census outage stopped degrading to an honest "no confident
            # match" and instead raised straight through to the caller,
            # 500-ing the parcel-360 card (F14d gate finding).
            log.warning("geocode_address: Census geocoder call failed for %r: %s", street, exc)
            return {"status": "no_confident_match", "standardized_address": None, "lon": None, "lat": None}
        tier, match = _classify(payload)
        matched_address = match["matchedAddress"] if match else None
        lon = float(match["coordinates"]["x"]) if match else None
        lat = float(match["coordinates"]["y"]) if match else None
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO crim.geocode_cache
                    (cache_key, query_street, query_urb, query_municipio, query_zip,
                     match_tier, matched_address, lon, lat, raw_response)
                VALUES (:k, :street, :urb, :muni, :zip, :tier, :addr, :lon, :lat, :raw)
                ON CONFLICT (cache_key) DO NOTHING
            """), {
                "k": key, "street": street, "urb": urb, "muni": municipio, "zip": zip_code,
                "tier": tier, "addr": matched_address, "lon": lon, "lat": lat,
                "raw": json.dumps(payload),
            })
        cached = {"match_tier": tier, "matched_address": matched_address, "lon": lon, "lat": lat}

    if cached["match_tier"] != "match":
        log.info("geocode_address: no confident match for %r (tier=%s)", street, cached["match_tier"])
        return {"status": "no_confident_match", "standardized_address": None, "lon": None, "lat": None}

    return {
        "status": "match",
        "standardized_address": cached["matched_address"],
        "lon": float(cached["lon"]) if cached["lon"] is not None else None,
        "lat": float(cached["lat"]) if cached["lat"] is not None else None,
    }
