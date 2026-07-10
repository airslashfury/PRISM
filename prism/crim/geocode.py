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
import threading
import time
from typing import Any, Literal

import requests
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressPR"
BENCHMARK = "Public_AR_Current"
LICENSE = "public domain (U.S. Census Bureau)"

MatchTier = Literal["match", "tie", "no_match"]

# Keyless public endpoint — self-throttle to be a polite caller regardless of
# how many parcel searches route through this client concurrently.
_MIN_INTERVAL_S = 0.5
_last_call_lock = threading.Lock()
_last_call_ts = 0.0


def _throttle() -> None:
    global _last_call_ts
    with _last_call_lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()


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

    _throttle()
    resp = requests.get(GEOCODE_URL, params=params, timeout=timeout)
    if resp.status_code == 400:
        # The addressPR endpoint requires Urb+Municipio OR City/ZIP; a caller
        # that omits all three gets a 400 — treat that as an unmatchable query
        # rather than raising, so a malformed/underspecified address degrades
        # to "no confident match" instead of a 500.
        return {"result": {"addressMatches": []}}
    resp.raise_for_status()
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
        except requests.RequestException as exc:
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
