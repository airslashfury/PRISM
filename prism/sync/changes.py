"""What-changed + stale-data aggregation for the overview cockpit (ROADMAP F2).

A digital twin feels alive when it says, unprompted, what is fresh, what is
stale, and what moved. This module reads signals that *already exist* — the sync
registry (`sync.data_sources`), the sync log, recent earthquakes, and CRIM
month-over-month deltas — and folds them into two lists the overview leads with:

  * ``feeds``   — every live source with its age and a stale flag (age beyond its
                  declared `sync_interval_hours`).
  * ``changes`` — a newest-first, typed event stream (a layer re-synced, a hazard
                  rescore fired, a significant quake, parcels that changed hands).

No new computation, no new tables — pure honest surfacing of state.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# A feed older than this multiple of its declared interval is flagged stale
# (a little grace so a feed isn't "stale" the instant it passes its interval).
_STALE_GRACE = 1.5

# Only surface quakes at/above this magnitude in the change stream.
_QUAKE_MIN_MAG = 3.5


def _exists(engine: Engine, qualified: str) -> bool:
    with engine.connect() as conn:
        return conn.execute(text("SELECT to_regclass(:t)"), {"t": qualified}).scalar() is not None


# The live operational feeds track freshness on their own tables (not the
# data_sources registry). (label, table, timestamp column, expected interval h, where).
_LIVE_SPECS = [
    ("PREPA generation", "sync.grid_snapshot", "fetched_at", 1.0, "WHERE id = 1"),
    ("LUMA outages", "sync.luma_outages", "fetched_at", 1.0, ""),
    ("USGS earthquakes", "sync.seismic_events", "updated_at", 1.0, ""),
]


def _live_feeds(engine: Engine) -> list[dict[str, Any]]:
    """Freshness for the time-sensitive live feeds, read from their own tables."""
    out: list[dict[str, Any]] = []
    for name, table, col, interval_h, where in _LIVE_SPECS:
        if not _exists(engine, table):
            continue
        with engine.connect() as conn:
            row = conn.execute(text(
                f"SELECT max({col}) AS ts, "  # noqa: S608 — table/col from a fixed constant
                f"EXTRACT(EPOCH FROM (now() - max({col}))) AS age_s FROM {table} {where}"
            )).mappings().fetchone()
        ts = row["ts"] if row else None
        age_s = float(row["age_s"]) if row and row["age_s"] is not None else None
        stale = age_s is None or age_s > interval_h * 3600 * _STALE_GRACE
        out.append({
            "source_name": name,
            "source_type": "live",
            "layer_name": None,
            "status": "ok" if ts else "never",
            "row_count": None,
            "interval_hours": interval_h,
            "last_fetched_at": ts.isoformat() if ts else None,
            "age_seconds": age_s,
            "stale": stale,
        })
    return out


def _feeds(engine: Engine) -> list[dict[str, Any]]:
    """Every non-test sync source with its freshness + a stale flag."""
    if not _exists(engine, "sync.data_sources"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text(r"""
            SELECT source_name, source_type, layer_name, status, row_count,
                   sync_interval_hours, last_fetched_at,
                   EXTRACT(EPOCH FROM (now() - last_fetched_at)) AS age_s
            FROM sync.data_sources
            WHERE source_name NOT LIKE '\_test\_%'
            ORDER BY last_fetched_at DESC NULLS LAST
        """)).mappings().fetchall()

    feeds = []
    for r in rows:
        age_s = float(r["age_s"]) if r["age_s"] is not None else None
        interval_h = float(r["sync_interval_hours"]) if r["sync_interval_hours"] else None
        stale = False
        if age_s is None:
            stale = True  # never fetched
        elif interval_h:
            stale = age_s > interval_h * 3600 * _STALE_GRACE
        feeds.append({
            "source_name": r["source_name"],
            "source_type": r["source_type"],
            "layer_name": r["layer_name"],
            "status": r["status"],
            "row_count": int(r["row_count"]) if r["row_count"] is not None else None,
            "interval_hours": interval_h,
            "last_fetched_at": r["last_fetched_at"].isoformat() if r["last_fetched_at"] else None,
            "age_seconds": age_s,
            "stale": stale,
        })
    return feeds


def _sync_changes(engine: Engine, limit: int) -> list[dict[str, Any]]:
    """Recent meaningful sync runs: layer updates and hazard rescores."""
    if not _exists(engine, "sync.sync_log"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT run_at, source_name, rows_updated, triggered_rescore
            FROM sync.sync_log
            WHERE status = 'ok'
              AND (rows_updated > 0 OR triggered_rescore IS NOT NULL)
            ORDER BY run_id DESC
            LIMIT :lim
        """), {"lim": limit}).mappings().fetchall()

    out = []
    for r in rows:
        at = r["run_at"].isoformat() if r["run_at"] else None
        if r["triggered_rescore"]:
            out.append({
                "kind": "rescore",
                "headline": f"Hazard rescore ({r['triggered_rescore']}) triggered",
                "detail": f"by a change in {r['source_name']}",
                "at": at,
                "href": "/resilience",
            })
        elif r["rows_updated"]:
            out.append({
                "kind": "sync",
                "headline": f"{r['source_name']}: {int(r['rows_updated']):,} rows updated",
                "detail": None,
                "at": at,
                "href": "/sync",
            })
    return out


def _quake_changes(engine: Engine, limit: int) -> list[dict[str, Any]]:
    if not _exists(engine, "sync.seismic_events"):
        return []
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT event_time, mag, place
            FROM sync.seismic_events
            WHERE event_time >= now() - interval '14 days' AND mag >= :m
            ORDER BY event_time DESC
            LIMIT :lim
        """), {"m": _QUAKE_MIN_MAG, "lim": limit}).mappings().fetchall()
    return [
        {
            "kind": "quake",
            "headline": f"M{r['mag']:.1f} earthquake",
            "detail": r["place"],
            "at": r["event_time"].isoformat() if r["event_time"] else None,
            "href": "/resilience",
        }
        for r in rows
    ]


def _rank_changes(engine: Engine) -> list[dict[str, Any]]:
    """Substations that moved inside the top-10 ranking between the two most
    recent rescores of a scenario (F4 — reads resilience.score_history)."""
    if not _exists(engine, "resilience.score_runs"):
        return []
    from datetime import datetime, timedelta, timezone

    from prism.resilience.history import rank_movements

    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    out = []
    for m in rank_movements(engine):
        if m.run_at is None or m.run_at < cutoff:
            continue
        name = m.entity_name or f"substation {m.entity_id}"
        if m.prev_rank is None:
            headline = f"{name} entered the top 10 at #{m.new_rank}"
        else:
            verb = "rose" if m.new_rank < m.prev_rank else "fell"
            headline = f"{name} {verb} #{m.prev_rank} → #{m.new_rank}"
        out.append({
            "kind": "rank",
            "headline": headline,
            "detail": f"under the {m.scenario_name} scenario",
            "at": m.run_at.isoformat() if m.run_at else None,
            "href": "/resilience",
        })
    return out


def _crim_changes(engine: Engine) -> list[dict[str, Any]]:
    """One headline per change type in the most recent CRIM delta month."""
    if not _exists(engine, "crim.parcel_deltas"):
        return []
    with engine.connect() as conn:
        month = conn.execute(text(
            "SELECT max(to_month) FROM crim.parcel_deltas"
        )).scalar()
        if month is None:
            return []
        by_type = dict(conn.execute(text("""
            SELECT change_type, count(*) FROM crim.parcel_deltas
            WHERE to_month = :m GROUP BY change_type
        """), {"m": month}).fetchall())

    label = {
        "sale": "recorded a new sale",
        "owner_change": "changed owner",
        "value_change": "were reassessed",
        "new_parcel": "are newly registered",
    }
    at = month.isoformat()
    return [
        {
            "kind": "crim",
            "headline": f"{int(n):,} parcels {label.get(t, t)}",
            "detail": f"since the {month:%B %Y} snapshot",
            "at": at,
            "href": "/trends",
        }
        for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])
        if n
    ]


def _crim_baseline(engine: Engine) -> dict[str, Any]:
    """CRIM snapshot status — the honest 'baseline 2026-06, next delta pending'."""
    out: dict[str, Any] = {"snapshot_month": None, "snapshots": 0,
                           "deltas_available": False, "latest_delta_month": None}
    if _exists(engine, "crim.parcela_snapshots"):
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT max(snapshot_month) AS latest,
                       count(DISTINCT snapshot_month) AS n
                FROM crim.parcela_snapshots
            """)).mappings().fetchone()
        if row and row["latest"]:
            out["snapshot_month"] = row["latest"].isoformat()
            out["snapshots"] = int(row["n"])
            out["deltas_available"] = int(row["n"]) >= 2
    if _exists(engine, "crim.parcel_deltas"):
        with engine.connect() as conn:
            m = conn.execute(text("SELECT max(to_month) FROM crim.parcel_deltas")).scalar()
        out["latest_delta_month"] = m.isoformat() if m else None
    return out


def whatsnew(engine: Engine, *, change_limit: int = 12) -> dict[str, Any]:
    """Feed freshness + a newest-first typed change stream for the overview."""
    changes = (
        _sync_changes(engine, change_limit)
        + _quake_changes(engine, change_limit)
        + _rank_changes(engine)
        + _crim_changes(engine)
    )
    # Newest first; None timestamps sink to the bottom.
    changes.sort(key=lambda c: c["at"] or "", reverse=True)
    # Live operational feeds first (most time-sensitive), then the WFS registry.
    feeds = _live_feeds(engine) + _feeds(engine)
    return {
        "feeds": feeds,
        "stale_count": sum(1 for f in feeds if f["stale"]),
        "changes": changes[:change_limit],
        "crim_baseline": _crim_baseline(engine),
    }
