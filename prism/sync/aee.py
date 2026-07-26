"""AEE/PREPA ArcGIS mirror — manual load-shedding live feed + distribution feeders.

Source: PREPA's public "Manual Load Shedding" ArcGIS dashboard
(`aeepr.maps.arcgis.com/apps/dashboards/1995c773fceb468db8b7f7d34899df94`), backed by
two keyless FeatureServers on `services3.arcgis.com/0n3sEGhALDkUSwc5`:

  * **Manual_Load_Shedding/0** — LIVE shed feeders (polygons): CLIENTS, MW, STAGE, STATUS,
    MUNICIPALI, predicted/pred_time. CLIENTS is the solid consequence metric (MW is unreliable).
  * **Manual_Load_Shedding_Base_Data/0** — the authoritative distribution feeder network:
    486,725 polyline segments from PREPA's GE Smallworld GIS, with topology (NODE1_ID/NODE2_ID),
    voltage, overhead/underground, circuit id. The real geometry behind PRISM's Voronoi feeders.

Per the data-sovereignty rule these public dashboards vanish, so every pull is mirrored to
`data/raw/` with a sha256 **before** we rely on it. Run from the host (durable bind path);
DB/PostGIS load is a downstream step off these mirrors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ORG = "https://services3.arcgis.com/0n3sEGhALDkUSwc5/arcgis/rest/services"
LS_QUERY = ORG + "/Manual_Load_Shedding/FeatureServer/0/query"
LS_META = ORG + "/Manual_Load_Shedding/FeatureServer/0"
FEEDER_QUERY = ORG + "/Manual_Load_Shedding_Base_Data/FeatureServer/0/query"
RAW = Path("data/raw")
_UA = {"User-Agent": "Mozilla/5.0 (PRISM data-sovereignty mirror)"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=120.0, follow_redirects=True, headers=_UA)


def _last_edit(client: httpx.Client) -> int | None:
    meta = client.get(LS_META, params={"f": "json"}).json()
    return (meta.get("editingInfo") or {}).get("lastEditDate")


def snapshot_load_shedding(client: httpx.Client | None = None) -> dict:
    """Capture one full snapshot of the live shed layer (geojson + geometry) to
    data/raw/aee_load_shedding/<utc>/ with a checksummed manifest."""
    own = client is None
    client = client or _client()
    try:
        last_edit = _last_edit(client)
        r = client.get(LS_QUERY, params={"where": "1=1", "outFields": "*",
                                         "returnGeometry": "true", "outSR": "4326", "f": "geojson"})
        raw = r.content
    finally:
        if own:
            client.close()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out = RAW / "aee_load_shedding" / ts
    out.mkdir(parents=True, exist_ok=True)
    (out / "load_shedding.geojson").write_bytes(raw)
    feats = json.loads(raw).get("features", [])
    clients = sum((f["properties"].get("CLIENTS") or 0) for f in feats)
    manifest = {
        "captured_utc": ts, "source": LS_QUERY, "records": len(feats),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "total_clients": clients, "lastEditDate_ms": last_edit,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def snapshot_loop(interval: int = 1800, max_iters: int = 96) -> None:
    """Poll the live layer; snapshot only when the source's lastEditDate changes
    (PREPA edits the shed plan a few times a day, not continuously)."""
    last_seen = object()  # sentinel so the first tick always captures
    with _client() as client:
        for _ in range(max_iters):
            try:
                le = _last_edit(client)
            except Exception as e:  # noqa: BLE001
                print(f"{datetime.now(timezone.utc).isoformat()} meta error {e}", flush=True)
                time.sleep(interval); continue
            if le != last_seen:
                m = snapshot_load_shedding(client)
                last_seen = le
                print(f"{m['captured_utc']} CHANGED records={m['records']} "
                      f"clients={m['total_clients']:,} lastEdit={le}", flush=True)
            else:
                print(f"{datetime.now(timezone.utc).isoformat()} no change (lastEdit {le})", flush=True)
            time.sleep(interval)


def mirror_feeder_network(page: int = 2000) -> dict:
    """One-time mirror of the 486K-segment feeder network to data/raw/aee_feeders/
    as paginated geojson chunks. Resumable (resumes from the last saved offset)."""
    out = RAW / "aee_feeders"
    out.mkdir(parents=True, exist_ok=True)
    existing = sorted(int(p.stem.split("_")[1]) for p in out.glob("chunk_*.geojson"))
    offset = (existing[-1] + page) if existing else 0
    saved = len(existing)
    with _client() as client:
        while True:
            r = client.get(FEEDER_QUERY, params={
                "where": "1=1", "outFields": "*", "returnGeometry": "true",
                "outSR": "4326", "resultOffset": offset, "resultRecordCount": page, "f": "geojson"})
            feats = json.loads(r.content).get("features", [])
            if not feats:
                break
            (out / f"chunk_{offset:07d}.geojson").write_bytes(r.content)
            saved += 1
            print(f"feeders offset={offset} got={len(feats)} chunks={saved}", flush=True)
            if len(feats) < page:
                break
            offset += page
            time.sleep(0.3)
    return {"last_offset": offset, "chunks": saved}


# ── Feeder network load (the authoritative distribution geometry) ───────────

FEEDER_DDL = [
    """
    CREATE TABLE IF NOT EXISTS sync.aee_feeders (
        g3e_fid       BIGINT PRIMARY KEY,   -- Smallworld GIS feature id, globally unique
        fid           INTEGER,              -- per-export row id (not stable across pulls)
        g3e_fno       INTEGER,              -- feature-type code
        circuit       TEXT,                 -- CIRCUIT1, e.g. '6603-01' (joins the shed feeders)
        state         TEXT,                 -- CD_STATE: In Service / Proposed Removed / ...
        status        TEXT,                 -- CD_STATUS: switch Open / Closed
        oh_ug         TEXT,                 -- overhead (OH) / underground (UG)
        condition     TEXT,
        size_material TEXT,                 -- conductor size + material, e.g. '4 CU HD'
        voltage_kv    TEXT,                 -- raw '7.62/13.20' (phase/line); kept unparsed
        phase_count   INTEGER,              -- PHASE_LEN
        phase_config  TEXT,                 -- CD_PHASE, e.g. 'BCA'
        node1_id      BIGINT,               -- topology: the segment's two endpoints
        node2_id      BIGINT,
        shape_length  DOUBLE PRECISION,     -- source-reported length (m)
        geom          geometry(LineString, 32161),
        loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_aee_feeders_geom ON sync.aee_feeders USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS ix_aee_feeders_circuit ON sync.aee_feeders (circuit)",
    "CREATE INDEX IF NOT EXISTS ix_aee_feeders_node1 ON sync.aee_feeders (node1_id)",
    "CREATE INDEX IF NOT EXISTS ix_aee_feeders_node2 ON sync.aee_feeders (node2_id)",
]

_FEEDER_INSERT = """
    INSERT INTO sync.aee_feeders
        (g3e_fid, fid, g3e_fno, circuit, state, status, oh_ug, condition,
         size_material, voltage_kv, phase_count, phase_config, node1_id, node2_id,
         shape_length, geom, loaded_at)
    VALUES
        (:g3e_fid, :fid, :g3e_fno, :circuit, :state, :status, :oh_ug, :condition,
         :size_material, :voltage_kv, :phase_count, :phase_config, :node1_id, :node2_id,
         :shape_length,
         CASE WHEN CAST(:geojson AS TEXT) IS NULL THEN NULL ELSE
            ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(CAST(:geojson AS TEXT)), 4326), 32161)
         END,
         now())
    ON CONFLICT (g3e_fid) DO UPDATE SET
        fid = EXCLUDED.fid, g3e_fno = EXCLUDED.g3e_fno, circuit = EXCLUDED.circuit,
        state = EXCLUDED.state, status = EXCLUDED.status, oh_ug = EXCLUDED.oh_ug,
        condition = EXCLUDED.condition, size_material = EXCLUDED.size_material,
        voltage_kv = EXCLUDED.voltage_kv, phase_count = EXCLUDED.phase_count,
        phase_config = EXCLUDED.phase_config, node1_id = EXCLUDED.node1_id,
        node2_id = EXCLUDED.node2_id, shape_length = EXCLUDED.shape_length,
        geom = EXCLUDED.geom, loaded_at = now()
"""


def create_feeder_schema(engine) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sync"))
        for stmt in FEEDER_DDL:
            conn.execute(text(stmt))


def _feeder_rows(feature_collection: dict) -> list[dict]:
    out = []
    for f in feature_collection.get("features", []):
        p = f.get("properties") or {}
        fid = p.get("G3E_FID")
        if fid is None:
            continue
        out.append({
            "g3e_fid": fid,
            "fid": p.get("FID"),
            "g3e_fno": p.get("G3E_FNO"),
            "circuit": _clean(p.get("CIRCUIT1")),
            "state": _clean(p.get("CD_STATE")),
            "status": _clean(p.get("CD_STATUS")),
            "oh_ug": _clean(p.get("CD_OH_UG")),
            "condition": _clean(p.get("CONDITION")),
            "size_material": _clean(p.get("SIZE_MATER")),
            "voltage_kv": _clean(p.get("VOLTAGE_KV")),
            "phase_count": p.get("PHASE_LEN"),
            "phase_config": _clean(p.get("CD_PHASE")),
            "node1_id": p.get("NODE1_ID"),
            "node2_id": p.get("NODE2_ID"),
            "shape_length": p.get("Shape__Length"),
            "geojson": json.dumps(f.get("geometry")) if f.get("geometry") else None,
        })
    return out


def load_feeders(engine=None) -> dict:
    """Load the mirrored feeder network (data/raw/aee_feeders/chunk_*.geojson) into
    sync.aee_feeders. Off the mirror only, never the network. Idempotent — keyed on
    the Smallworld G3E_FID, so a re-run upserts rather than duplicates. Chunk-at-a-
    time so an interrupted load resumes cleanly on the next run.

    This is the authoritative distribution geometry (486,725 conductor segments with
    NODE1_ID/NODE2_ID topology) behind PRISM's Voronoi feeder proxy.
    """
    from sqlalchemy import text

    engine = engine or _default_engine()
    create_feeder_schema(engine)
    chunks = sorted((RAW / "aee_feeders").glob("chunk_*.geojson"),
                    key=lambda p: int(p.stem.split("_")[1]))
    if not chunks:
        return {"chunks": 0, "segments": 0}

    total = 0
    for i, chunk in enumerate(chunks, 1):
        rows = _feeder_rows(json.loads(chunk.read_bytes()))
        if not rows:
            continue
        with engine.begin() as conn:
            conn.execute(text(_FEEDER_INSERT), rows)
        total += len(rows)
        if i % 20 == 0 or i == len(chunks):
            print(f"feeders load: {i}/{len(chunks)} chunks, {total:,} segments", flush=True)

    circuits = _build_circuit_rollup(engine)
    return {"chunks": len(chunks), "segments": total, "circuits": circuits}


def _build_circuit_rollup(engine) -> int:
    """One row per feeder circuit — collected geometry + length, indexed. A
    downstream helper for substation/barrio assignment (fewer, coarser rows than
    the 486K segments). Rebuilt from sync.aee_feeders, so it's reproducible."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sync.aee_circuit"))
        conn.execute(text("""
            CREATE TABLE sync.aee_circuit AS
            SELECT circuit,
                   count(*)              AS seg_count,
                   sum(ST_Length(geom))  AS length_m,
                   max(voltage_kv)       AS voltage_kv,
                   ST_Multi(ST_Collect(geom)) AS geom
            FROM sync.aee_feeders
            WHERE circuit IS NOT NULL
            GROUP BY circuit
        """))
        conn.execute(text("ALTER TABLE sync.aee_circuit ADD PRIMARY KEY (circuit)"))
        conn.execute(text(
            "CREATE INDEX ix_aee_circuit_geom ON sync.aee_circuit USING GIST (geom)"))
        return conn.execute(text("SELECT count(*) FROM sync.aee_circuit")).scalar() or 0


def _default_engine():
    from prism.load.db import get_engine
    return get_engine()


# ── PostGIS load (off the mirrors, never off the network) ───────────────────

DDL = [
    """
    CREATE TABLE IF NOT EXISTS sync.aee_shed_feeders (
        feeder       TEXT PRIMARY KEY,
        circuit      TEXT,
        name         TEXT,
        region       TEXT,
        municipio    TEXT,
        sectors      TEXT,
        voltage      DOUBLE PRECISION,
        block        INTEGER,
        stage        TEXT,             -- '1'..'3' | 'CRITICAL STAGE'
        is_shed      BOOLEAN,          -- source STATUS: SI = currently shed
        clients      INTEGER,          -- the solid consequence metric
        mw           DOUBLE PRECISION, -- unreliable per the dashboard; kept, not trusted
        critical_load TEXT,
        transfer_to  TEXT,
        predicted    BOOLEAN,
        pred_time    TEXT,
        time_out     TEXT,
        geom         geometry(MultiPolygon, 32161),
        captured_at  TIMESTAMPTZ,      -- the snapshot this row came from
        loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_aee_shed_feeders_geom ON sync.aee_shed_feeders USING GIST (geom)",
    "CREATE INDEX IF NOT EXISTS ix_aee_shed_feeders_muni ON sync.aee_shed_feeders (municipio)",
    """
    CREATE TABLE IF NOT EXISTS sync.aee_shed_history (
        captured_at TIMESTAMPTZ NOT NULL,
        feeder      TEXT NOT NULL,
        stage       TEXT,
        is_shed     BOOLEAN,
        clients     INTEGER,
        mw          DOUBLE PRECISION,
        predicted   BOOLEAN,
        PRIMARY KEY (captured_at, feeder)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_aee_shed_history_feeder ON sync.aee_shed_history (feeder, captured_at DESC)",
]


def create_schema(engine) -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS sync"))
        for stmt in DDL:
            conn.execute(text(stmt))


def _yn(v: object) -> bool | None:
    """Source booleans are the strings 'SI'/'NO' (with stray whitespace)."""
    if v is None:
        return None
    s = str(v).strip().upper()
    return True if s == "SI" else False if s == "NO" else None


def _clean(v: object) -> str | None:
    """Blank-ish source strings (' ') carry no information — store NULL."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _rows(feature_collection: dict, captured_at: datetime) -> list[dict]:
    out = []
    for f in feature_collection.get("features", []):
        p = f.get("properties") or {}
        feeder = _clean(p.get("FEEDER")) or _clean(p.get("CIRCUIT1"))
        if not feeder:
            continue
        out.append({
            "feeder": feeder,
            "circuit": _clean(p.get("CIRCUIT1")),
            "name": _clean(p.get("NAME")),
            "region": _clean(p.get("REGION")),
            "municipio": _clean(p.get("MUNICIPALI")),
            "sectors": _clean(p.get("SECTORS")),
            "voltage": p.get("VOLTAGE"),
            "block": p.get("BLOCK"),
            "stage": _clean(p.get("STAGE")),
            "is_shed": _yn(p.get("STATUS")),
            "clients": p.get("CLIENTS"),
            "mw": p.get("MW"),
            "critical_load": _clean(p.get("CRITICAL_L")),
            "transfer_to": _clean(p.get("TRANS_TO")),
            "predicted": _yn(p.get("predicted")),
            "pred_time": _clean(p.get("pred_time")),
            "time_out": _clean(p.get("TIME_OUT_APP")),
            "geojson": json.dumps(f.get("geometry")) if f.get("geometry") else None,
            "captured_at": captured_at,
        })
    return out


def _captured_at(snapshot_dir: Path) -> datetime:
    """The directory name is the capture instant (…/2026-07-19T030530Z)."""
    return datetime.strptime(snapshot_dir.name, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def load_snapshot(engine, snapshot_dir: Path, *, current: bool = True) -> dict:
    """Load one mirrored snapshot: history always, current-state only if asked.

    Idempotent — re-loading a snapshot rewrites the same history rows.
    """
    from sqlalchemy import text

    captured_at = _captured_at(snapshot_dir)
    fc = json.loads((snapshot_dir / "load_shedding.geojson").read_bytes())
    rows = _rows(fc, captured_at)
    if not rows:
        return {"snapshot": snapshot_dir.name, "rows": 0, "history_rows": 0}

    with engine.begin() as conn:
        for r in rows:
            conn.execute(text("""
                INSERT INTO sync.aee_shed_history
                    (captured_at, feeder, stage, is_shed, clients, mw, predicted)
                VALUES (:captured_at, :feeder, :stage, :is_shed, :clients, :mw, :predicted)
                ON CONFLICT (captured_at, feeder) DO UPDATE SET
                    stage = EXCLUDED.stage, is_shed = EXCLUDED.is_shed,
                    clients = EXCLUDED.clients, mw = EXCLUDED.mw,
                    predicted = EXCLUDED.predicted
            """), r)

            if current:
                conn.execute(text("""
                    INSERT INTO sync.aee_shed_feeders
                        (feeder, circuit, name, region, municipio, sectors, voltage, block,
                         stage, is_shed, clients, mw, critical_load, transfer_to, predicted,
                         pred_time, time_out, geom, captured_at, loaded_at)
                    VALUES
                        (:feeder, :circuit, :name, :region, :municipio, :sectors, :voltage, :block,
                         :stage, :is_shed, :clients, :mw, :critical_load, :transfer_to, :predicted,
                         :pred_time, :time_out,
                         -- 20 of 792 source polygons have nested shells (invalid in
                         -- PREPA's own data). ST_MakeValid + CollectionExtract(3)
                         -- repairs to polygons-only on load; the data/raw mirror keeps
                         -- the source exactly as published.
                         CASE WHEN CAST(:geojson AS TEXT) IS NULL THEN NULL ELSE
                            ST_Multi(ST_CollectionExtract(ST_MakeValid(
                                ST_Transform(ST_SetSRID(
                                    ST_GeomFromGeoJSON(CAST(:geojson AS TEXT)),
                                    4326), 32161)), 3)) END,
                         :captured_at, now())
                    ON CONFLICT (feeder) DO UPDATE SET
                        circuit = EXCLUDED.circuit, name = EXCLUDED.name,
                        region = EXCLUDED.region, municipio = EXCLUDED.municipio,
                        sectors = EXCLUDED.sectors, voltage = EXCLUDED.voltage,
                        block = EXCLUDED.block, stage = EXCLUDED.stage,
                        is_shed = EXCLUDED.is_shed, clients = EXCLUDED.clients,
                        mw = EXCLUDED.mw, critical_load = EXCLUDED.critical_load,
                        transfer_to = EXCLUDED.transfer_to, predicted = EXCLUDED.predicted,
                        pred_time = EXCLUDED.pred_time, time_out = EXCLUDED.time_out,
                        geom = EXCLUDED.geom, captured_at = EXCLUDED.captured_at,
                        loaded_at = now()
                """), r)

    return {"snapshot": snapshot_dir.name, "rows": len(rows),
            "shed": sum(1 for r in rows if r["is_shed"]),
            "clients_shed": sum((r["clients"] or 0) for r in rows if r["is_shed"])}


def load_all(engine) -> dict:
    """Load every mirrored snapshot into history; the newest also sets current state."""
    create_schema(engine)
    dirs = sorted(
        (d for d in (RAW / "aee_load_shedding").iterdir()
         if d.is_dir() and (d / "load_shedding.geojson").exists()),
        key=lambda d: d.name,
    )
    if not dirs:
        return {"snapshots": 0}
    results = [load_snapshot(engine, d, current=(d is dirs[-1])) for d in dirs]
    return {
        "snapshots": len(results),
        "latest": results[-1],
        "history_rows": sum(r["rows"] for r in results),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["snapshot", "loop", "feeders", "load", "feeders-load"])
    ap.add_argument("--interval", type=int, default=1800)
    a = ap.parse_args()
    if a.cmd == "snapshot":
        print(json.dumps(snapshot_load_shedding(), indent=2))
    elif a.cmd == "loop":
        snapshot_loop(interval=a.interval)
    elif a.cmd == "feeders":                       # mirror the network off the API
        print(json.dumps(mirror_feeder_network(), indent=2))
    elif a.cmd == "load":                          # load-shedding snapshots -> PostGIS
        print(json.dumps(load_all(_default_engine()), indent=2, default=str))
    elif a.cmd == "feeders-load":                  # feeder network mirror -> PostGIS
        print(json.dumps(load_feeders(), indent=2, default=str))
