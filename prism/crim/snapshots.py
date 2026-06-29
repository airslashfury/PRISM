"""Monthly CRIM snapshots + delta capture (item 6).

The CRIM Catastro register is re-pulled monthly. Each pull, we freeze a
per-parcel snapshot (`crim.parcela_snapshots`) and diff it against the previous
month to capture what actually changed (`crim.parcel_deltas`): new parcels,
recorded sales, assessed-value changes, and ownership transfers. The deltas are
the longitudinal signal nobody else is tracking — they feed the sales-trend
tracking once two or more snapshots exist.

Snapshots are taken from `crim.parcelas_dedup` (one row per num_catastro). The
first snapshot is a baseline (no deltas until the second pull).
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

_DDL = [
    "CREATE SCHEMA IF NOT EXISTS crim",

    # One frozen row per parcel per monthly pull — the versioned record.
    """
    CREATE TABLE IF NOT EXISTS crim.parcela_snapshots (
        snapshot_month  DATE NOT NULL,          -- first-of-month the pull represents
        num_catastro    TEXT NOT NULL,
        municipio       TEXT,
        contact         TEXT,                   -- owner of record at snapshot time
        totalval        DOUBLE PRECISION,
        land            DOUBLE PRECISION,
        structure       DOUBLE PRECISION,
        salesamt        DOUBLE PRECISION,       -- last recorded sale at snapshot time
        salesdttm       TIMESTAMPTZ,
        PRIMARY KEY (snapshot_month, num_catastro)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_crim_snap_month ON crim.parcela_snapshots (snapshot_month)",
    "CREATE INDEX IF NOT EXISTS idx_crim_snap_nc    ON crim.parcela_snapshots (num_catastro)",

    # Append-only record of what changed between two consecutive snapshots.
    """
    CREATE TABLE IF NOT EXISTS crim.parcel_deltas (
        delta_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        from_month    DATE NOT NULL,
        to_month      DATE NOT NULL,
        num_catastro  TEXT NOT NULL,
        municipio     TEXT,
        change_type   TEXT NOT NULL,            -- new_parcel | sale | value_change | owner_change
        old_value     TEXT,
        new_value     TEXT,
        delta_num     DOUBLE PRECISION,         -- numeric delta where meaningful
        detected_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_crim_delta_tomonth ON crim.parcel_deltas (to_month)",
    "CREATE INDEX IF NOT EXISTS idx_crim_delta_muni    ON crim.parcel_deltas (municipio)",
    "CREATE INDEX IF NOT EXISTS idx_crim_delta_type    ON crim.parcel_deltas (change_type)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_crim_delta "
    "ON crim.parcel_deltas (to_month, num_catastro, change_type)",
]

_DROP_DDL = [
    "DROP TABLE IF EXISTS crim.parcel_deltas CASCADE",
    "DROP TABLE IF EXISTS crim.parcela_snapshots CASCADE",
]

# Reassessments below this absolute delta are noise (rounding); ignore.
_VALUE_CHANGE_MIN = 1.0


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


def drop_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DROP_DDL:
            conn.execute(text(stmt))


def _month_floor(d: date) -> date:
    return d.replace(day=1)


def list_snapshots(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT snapshot_month, count(*) AS parcels
            FROM crim.parcela_snapshots
            GROUP BY snapshot_month ORDER BY snapshot_month
        """)).mappings().fetchall()
    return [{"snapshot_month": r["snapshot_month"].isoformat(), "parcels": int(r["parcels"])} for r in rows]


def take_snapshot(engine: Engine, month: date | None = None) -> dict:
    """Freeze the current parcel state into crim.parcela_snapshots for `month`.

    Idempotent: re-running for the same month is a no-op (ON CONFLICT DO NOTHING).
    Sources from crim.parcelas_dedup if present, else collapses crim.parcelas.
    """
    create_schema(engine)
    snap_month = _month_floor(month or date.today())

    with engine.connect() as conn:
        has_dedup = conn.execute(
            text("SELECT to_regclass('crim.parcelas_dedup')")
        ).scalar() is not None

    source = (
        "SELECT num_catastro, municipio, contact, totalval, land, structure, salesamt, salesdttm "
        "FROM crim.parcelas_dedup WHERE num_catastro IS NOT NULL"
        if has_dedup else
        "SELECT DISTINCT ON (num_catastro) num_catastro, municipio, contact, totalval, land, "
        "structure, salesamt, salesdttm FROM crim.parcelas WHERE num_catastro IS NOT NULL "
        "ORDER BY num_catastro, totalval DESC NULLS LAST"
    )

    with engine.begin() as conn:
        inserted = conn.execute(text(f"""
            INSERT INTO crim.parcela_snapshots
                (snapshot_month, num_catastro, municipio, contact, totalval, land, structure, salesamt, salesdttm)
            SELECT :m, num_catastro, municipio, contact, totalval, land, structure, salesamt, salesdttm
            FROM ({source}) s
            ON CONFLICT (snapshot_month, num_catastro) DO NOTHING
        """), {"m": snap_month}).rowcount

    log.info("Snapshot %s: %d parcels frozen", snap_month, inserted)
    return {"snapshot_month": snap_month.isoformat(), "parcels_frozen": inserted}


def compute_deltas(engine: Engine, to_month: date | None = None) -> dict:
    """Diff the `to_month` snapshot against the immediately-prior snapshot.

    Writes new_parcel / sale / value_change / owner_change rows to
    crim.parcel_deltas. Idempotent via the unique (to_month, num_catastro,
    change_type) index. Returns counts per change type.
    """
    create_schema(engine)
    to_m = _month_floor(to_month or date.today())

    with engine.connect() as conn:
        from_m = conn.execute(text("""
            SELECT max(snapshot_month) FROM crim.parcela_snapshots
            WHERE snapshot_month < :to_m
        """), {"to_m": to_m}).scalar()

    if from_m is None:
        log.info("No prior snapshot before %s — baseline only, no deltas", to_m)
        return {"from_month": None, "to_month": to_m.isoformat(), "deltas": 0, "by_type": {}}

    params = {"from_m": from_m, "to_m": to_m, "min": _VALUE_CHANGE_MIN}
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO crim.parcel_deltas
                (from_month, to_month, num_catastro, municipio, change_type, old_value, new_value, delta_num)
            -- new parcels
            SELECT :from_m, :to_m, t.num_catastro, t.municipio, 'new_parcel',
                   NULL, t.num_catastro, NULL
            FROM crim.parcela_snapshots t
            LEFT JOIN crim.parcela_snapshots f
              ON f.snapshot_month = :from_m AND f.num_catastro = t.num_catastro
            WHERE t.snapshot_month = :to_m AND f.num_catastro IS NULL

            UNION ALL
            -- recorded sales (a newer sale date appeared since last month)
            SELECT :from_m, :to_m, t.num_catastro, t.municipio, 'sale',
                   f.salesdttm::text, t.salesdttm::text, t.salesamt
            FROM crim.parcela_snapshots t
            JOIN crim.parcela_snapshots f
              ON f.snapshot_month = :from_m AND f.num_catastro = t.num_catastro
            WHERE t.snapshot_month = :to_m
              AND t.salesdttm IS NOT NULL
              AND (f.salesdttm IS NULL OR t.salesdttm > f.salesdttm)

            UNION ALL
            -- assessed-value changes (reassessments)
            SELECT :from_m, :to_m, t.num_catastro, t.municipio, 'value_change',
                   f.totalval::text, t.totalval::text, (t.totalval - f.totalval)
            FROM crim.parcela_snapshots t
            JOIN crim.parcela_snapshots f
              ON f.snapshot_month = :from_m AND f.num_catastro = t.num_catastro
            WHERE t.snapshot_month = :to_m
              AND t.totalval IS NOT NULL AND f.totalval IS NOT NULL
              AND abs(t.totalval - f.totalval) >= :min

            UNION ALL
            -- ownership transfers
            SELECT :from_m, :to_m, t.num_catastro, t.municipio, 'owner_change',
                   f.contact, t.contact, NULL
            FROM crim.parcela_snapshots t
            JOIN crim.parcela_snapshots f
              ON f.snapshot_month = :from_m AND f.num_catastro = t.num_catastro
            WHERE t.snapshot_month = :to_m
              AND t.contact IS DISTINCT FROM f.contact
              AND t.contact IS NOT NULL
            ON CONFLICT (to_month, num_catastro, change_type) DO NOTHING
        """), params)

        by_type = dict(conn.execute(text("""
            SELECT change_type, count(*) FROM crim.parcel_deltas
            WHERE to_month = :to_m GROUP BY change_type
        """), {"to_m": to_m}).fetchall())

    total = sum(by_type.values())
    log.info("Deltas %s→%s: %d (%s)", from_m, to_m, total, by_type)
    return {
        "from_month": from_m.isoformat(),
        "to_month": to_m.isoformat(),
        "deltas": total,
        "by_type": {k: int(v) for k, v in by_type.items()},
    }


def run_monthly(engine: Engine, month: date | None = None) -> dict:
    """One monthly cycle: snapshot the current state, then diff vs. last month.

    Call this *after* a fresh CRIM re-download + load. Safe to re-run.
    """
    snap = take_snapshot(engine, month)
    deltas = compute_deltas(engine, month)
    return {"snapshot": snap, "deltas": deltas}
