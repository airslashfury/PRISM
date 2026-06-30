"""Owner intelligence over the normalized CRIM ownership layer (ROADMAP F1).

Reads the derived `crim.owner_entities` + `crim.parcel_owner` tables built by
`prism.crim.normalize`. Two surfaces:

  * ``search_owners``    — resolve a name fragment to normalized owner entities
                           (spelling variants already collapsed to one key).
  * ``get_owner_detail`` — one owner's island-wide footprint, municipio
                           breakdown, holdings timeline across monthly snapshots,
                           and a top-parcels portfolio table.

The owner key is **modeled / best-effort** (deterministic normalization, no
fuzzy clustering), a notch below the authoritative raw CRIM record — responses
carry that tier. CRIM's `<MUNICIPIO> JOHN DOE` unknown-owner sentinel is
filtered from search so it never tops the owner rankings.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.query import _LAT, _LON, MAX_HIGHLIGHT_POINTS, _table_exists

# The normalized key is a heuristic collapse of the authoritative raw owner.
OWNER_TIER = "modeled"

# CRIM placeholder for an unknown owner ("<MUNICIPIO> JOHN DOE"); not a real entity.
_JOHN_DOE = "%JOHN DOE%"


def _available(engine: Engine) -> bool:
    """The owner layer exists only after `python -m prism.crim --normalize`."""
    return _table_exists(engine, "crim.owner_entities") and _table_exists(engine, "crim.parcel_owner")


# ── Owner search ────────────────────────────────────────────────────────────

def search_owners(engine: Engine, q: str, *, limit: int = 25) -> dict[str, Any]:
    """Resolve a name fragment to normalized owner entities, biggest first."""
    q = (q or "").strip()
    empty = {"query": q, "count": 0, "owners": [], "confidence_tier": OWNER_TIER,
             "available": _available(engine)}
    if not q or not empty["available"]:
        return empty

    params = {"sub": f"%{q}%", "jd": _JOHN_DOE, "lim": limit}
    with engine.connect() as conn:
        count = conn.execute(text("""
            SELECT COUNT(*) FROM crim.owner_entities
            WHERE display_name ILIKE :sub AND display_name NOT ILIKE :jd
        """), params).scalar() or 0
        rows = conn.execute(text("""
            SELECT owner_key, display_name, parcel_count, total_val, municipio_count
            FROM crim.owner_entities
            WHERE display_name ILIKE :sub AND display_name NOT ILIKE :jd
            ORDER BY parcel_count DESC, total_val DESC NULLS LAST
            LIMIT :lim
        """), params).mappings().fetchall()

    return {
        "query": q,
        "count": int(count),
        "owners": [
            {
                "owner_key": r["owner_key"],
                "display_name": r["display_name"],
                "parcel_count": int(r["parcel_count"]),
                "total_val": float(r["total_val"]) if r["total_val"] is not None else None,
                "municipio_count": int(r["municipio_count"]),
            }
            for r in rows
        ],
        "confidence_tier": OWNER_TIER,
        "available": True,
    }


# ── Owner detail ────────────────────────────────────────────────────────────

def get_owner_detail(engine: Engine, owner_key: str) -> dict[str, Any] | None:
    """Footprint + municipio split + holdings timeline + portfolio for one owner.

    Returns None when the key is unknown (or the owner layer is not built yet).
    """
    if not _available(engine):
        return None

    with engine.connect() as conn:
        ent = conn.execute(text("""
            SELECT owner_key, display_name, parcel_count, total_val, municipio_count
            FROM crim.owner_entities WHERE owner_key = :k
        """), {"k": owner_key}).mappings().fetchone()
        if ent is None:
            return None

        # Footprint: one capped centroid per parcel + the true bbox over all of them.
        agg = conn.execute(text(f"""
            SELECT MIN({_LON}) AS min_lon, MIN({_LAT}) AS min_lat,
                   MAX({_LON}) AS max_lon, MAX({_LAT}) AS max_lat
            FROM crim.parcel_owner po
            JOIN crim.parcelas p ON p.num_catastro = po.num_catastro
            WHERE po.owner_key = :k
        """), {"k": owner_key}).mappings().fetchone()
        pts = conn.execute(text(f"""
            SELECT DISTINCT ON (po.num_catastro)
                   po.num_catastro, po.municipio, po.totalval,
                   {_LON} AS lon, {_LAT} AS lat
            FROM crim.parcel_owner po
            JOIN crim.parcelas p ON p.num_catastro = po.num_catastro
            WHERE po.owner_key = :k
            ORDER BY po.num_catastro, p.totalval DESC NULLS LAST
            LIMIT :lim
        """), {"k": owner_key, "lim": MAX_HIGHLIGHT_POINTS}).mappings().fetchall()

        by_muni = conn.execute(text("""
            SELECT municipio, COUNT(*) AS parcel_count, SUM(totalval) AS total_val
            FROM crim.parcel_owner WHERE owner_key = :k
            GROUP BY municipio ORDER BY parcel_count DESC, total_val DESC NULLS LAST
        """), {"k": owner_key}).mappings().fetchall()

        # Holdings across monthly snapshots (current-holdings basis; grows monthly).
        timeline = conn.execute(text("""
            SELECT s.snapshot_month,
                   COUNT(DISTINCT s.num_catastro) AS parcels,
                   SUM(s.totalval) AS total_val
            FROM crim.parcela_snapshots s
            JOIN crim.parcel_owner po ON po.num_catastro = s.num_catastro
            WHERE po.owner_key = :k
            GROUP BY s.snapshot_month ORDER BY s.snapshot_month
        """), {"k": owner_key}).mappings().fetchall() if _table_exists(
            engine, "crim.parcela_snapshots") else []

        top = conn.execute(text("""
            SELECT num_catastro, municipio, totalval, address_norm
            FROM crim.parcel_owner WHERE owner_key = :k
            ORDER BY totalval DESC NULLS LAST
            LIMIT 25
        """), {"k": owner_key}).mappings().fetchall()

    bbox = None
    if agg and agg["min_lon"] is not None:
        bbox = [float(agg["min_lon"]), float(agg["min_lat"]),
                float(agg["max_lon"]), float(agg["max_lat"])]

    return {
        "owner_key": ent["owner_key"],
        "display_name": ent["display_name"],
        "parcel_count": int(ent["parcel_count"]),
        "total_val": float(ent["total_val"]) if ent["total_val"] is not None else None,
        "municipio_count": int(ent["municipio_count"]),
        "confidence_tier": OWNER_TIER,
        "bbox": bbox,
        "footprint_capped": int(ent["parcel_count"]) > len(pts),
        "footprint": [
            {
                "num_catastro": r["num_catastro"],
                "municipio": r["municipio"],
                "totalval": float(r["totalval"]) if r["totalval"] is not None else None,
                "lon": float(r["lon"]) if r["lon"] is not None else None,
                "lat": float(r["lat"]) if r["lat"] is not None else None,
            }
            for r in pts
        ],
        "by_municipio": [
            {
                "municipio": r["municipio"],
                "parcel_count": int(r["parcel_count"]),
                "total_val": float(r["total_val"]) if r["total_val"] is not None else None,
            }
            for r in by_muni
        ],
        "timeline": [
            {
                "snapshot_month": r["snapshot_month"].isoformat(),
                "parcels": int(r["parcels"]),
                "total_val": float(r["total_val"]) if r["total_val"] is not None else None,
            }
            for r in timeline
        ],
        "top_parcels": [
            {
                "num_catastro": r["num_catastro"],
                "municipio": r["municipio"],
                "totalval": float(r["totalval"]) if r["totalval"] is not None else None,
                "address_norm": r["address_norm"],
            }
            for r in top
        ],
    }
