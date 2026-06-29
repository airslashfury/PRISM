"""Physical network geometry: the transmission grid as renderable GeoJSON."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Engine

from api import schemas
from api.cache import cached_response
from api.db import fetch_all, fetch_geojson, fetch_one
from api.deps import engine_dep

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/generation", response_model=schemas.GenerationStatus)
@cached_response("generation", ttl=120)
def generation(engine: Engine = Depends(engine_dep)) -> dict:
    """Live PREPA generation: per-plant current output + the island-wide reading.

    Supply-side AUTHORITATIVE data (operationdata.prepa.pr.gov). `status` is
    INFERRED from MW (no explicit field in the feed). Updated by the prepa_ops
    sync; this endpoint is a read of sync.generation_status + sync.grid_snapshot.
    """
    plants = fetch_all(
        engine,
        """
        SELECT g.plant_name, g.plant_type, g.entity_id, e.name AS entity_name,
               g.matched, g.site_total_mw, g.n_units, g.online_units, g.status,
               ST_X(ST_Centroid(ST_Transform(e.geom, 4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(e.geom, 4326))) AS lat
        FROM sync.generation_status g
        LEFT JOIN graph.entities e ON e.entity_id = g.entity_id
        ORDER BY g.site_total_mw DESC, g.plant_name
        """,
    )
    system = fetch_one(
        engine,
        """
        SELECT generation_mw, frequency_hz, reading_hour, as_of, fetched_at,
               spinning_reserve_mw, operational_reserve_mw, available_capacity_mw,
               prepa_pct, ppoa_pct, renewable_mw, solar_mw, wind_mw, hydro_mw, fuel_mix
        FROM sync.grid_snapshot WHERE id = 1
        """,
    )
    as_of = system["as_of"] if system else None
    return {
        "system": system,
        "plants": plants,
        "as_of": as_of,
        "total_plants": len(plants),
        "online": sum(1 for p in plants if p["status"] == "online"),
        "matched": sum(1 for p in plants if p["matched"]),
    }


@router.get("/outages", response_model=schemas.LumaOutages)
@cached_response("outages", ttl=120)
def outages(engine: Engine = Depends(engine_dep)) -> dict:
    """Live LUMA delivery-side outages by operational region.

    DELIVERY-side AUTHORITATIVE data (miluma.lumapr.com) — customers without
    service per LUMA region. Complements /network/generation (supply-side):
    generation tells us MW produced, this tells us customers actually served.
    Read of sync.luma_outages, refreshed by the luma_ops sync.
    """
    regions = fetch_all(
        engine,
        """
        SELECT region, total_clients, clients_without_service, clients_with_service,
               clients_planned_outage, clients_load_shed,
               pct_without_service, pct_with_service, fetched_at
        FROM sync.luma_outages
        ORDER BY clients_without_service DESC, region
        """,
    )
    total_clients = sum(r["total_clients"] for r in regions)
    total_out = sum(r["clients_without_service"] for r in regions)
    return {
        "regions": regions,
        "total_clients": total_clients,
        "total_without_service": total_out,
        "total_planned_outage": sum(r["clients_planned_outage"] for r in regions),
        "total_load_shed": sum(r["clients_load_shed"] for r in regions),
        "pct_without_service": round(100.0 * total_out / total_clients, 3) if total_clients else 0.0,
        "as_of": max((r["fetched_at"] for r in regions), default=None),
    }


@router.get("/seismic", response_model=schemas.SeismicResponse)
@cached_response("seismic", ttl=300)
def seismic(days: int = 30, engine: Engine = Depends(engine_dep)) -> dict:
    """Live USGS earthquakes for the PR / USVI region (last `days`).

    AUTHORITATIVE (USGS is the seismic authority), no key. Read of
    sync.seismic_events, refreshed by the usgs_quakes sync. The SW (Guánica)
    cluster dominates — PR's active aftershock zone since the 2020 sequence.
    """
    events = fetch_all(
        engine,
        """
        SELECT event_id, mag, place, depth_km, event_time, updated_at, felt,
               tsunami, url, lon, lat
        FROM sync.seismic_events
        WHERE event_time >= now() - make_interval(days => :days)
        ORDER BY event_time DESC
        """,
        days=days,
    )
    mags = [e["mag"] for e in events if e["mag"] is not None]
    felt = sum(1 for e in events if (e["felt"] or 0) > 0)
    return {
        "events": events,
        "count": len(events),
        "max_mag": max(mags) if mags else None,
        "felt_count": felt,
        "window_days": days,
        "latest": max((e["event_time"] for e in events), default=None),
        "confidence_tier": "authoritative",
    }


@router.get("/transmission", response_model=schemas.FeatureCollection)
@cached_response("transmission", ttl=21600)
def transmission(engine: Engine = Depends(engine_dep)) -> dict:
    """Transmission network, one MultiLineString feature per connected component.

    Collecting by component (74 of them) keeps the payload ~2 MB while still
    drawing the full grid web; geometry is simplified to ~90 m and reprojected.
    """
    return fetch_geojson(
        engine,
        """
        SELECT json_build_object(
          'type','FeatureCollection',
          'features', COALESCE(json_agg(f), '[]'::json)
        )
        FROM (
          SELECT json_build_object(
            'type','Feature',
            'geometry', ST_AsGeoJSON(
                ST_Transform(ST_SimplifyPreserveTopology(ST_Collect(geom), 90), 4326), 5)::json,
            'properties', json_build_object('comp_id', comp_id, 'segments', count(*))
          ) AS f
          FROM graph.tx_network
          GROUP BY comp_id
        ) sub
        """,
    )


@router.get("/consequence/{entity_id}", response_model=schemas.ConsequenceSummary)
@cached_response("consequence", ttl=21600)
def consequence(entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Consequence Lens (M5a): precomputed downstream ripple + one-line headline.

    Backed by `graph.downstream_summary`, refreshed by the sync spine. Only
    substations (the only entities with FEEDS/POWERS downstream cascades)
    have a summary.
    """
    row = fetch_one(
        engine,
        """
        SELECT entity_id, kind, name, population_affected, hospitals,
               water_plants, health_centers, barrios, downstream_ids, headline
        FROM graph.downstream_summary
        WHERE entity_id = :entity_id
        """,
        entity_id=entity_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="no downstream summary for this entity")

    downstream_ids = row.pop("downstream_ids") or []
    downstream = fetch_all(
        engine,
        """
        SELECT entity_id, kind, name,
               ST_X(ST_Centroid(ST_Transform(geom,4326))) AS lon,
               ST_Y(ST_Centroid(ST_Transform(geom,4326))) AS lat
        FROM graph.entities
        WHERE entity_id = ANY(:ids)
        """,
        ids=downstream_ids,
    ) if downstream_ids else []

    return {**row, "downstream": downstream}


@router.get("/water-consequence/{entity_id}", response_model=schemas.WaterConsequence)
@cached_response("water_consequence", ttl=21600)
def water_consequence(entity_id: int, engine: Engine = Depends(engine_dep)) -> dict:
    """Power→water coupling: if this substation fails, which areas lose water?

    Chain: substation →(POWERS) pump/well/plant →(WATER_SERVES) barrios. Built by
    `prism.graph.water`. Proxy-tier (no real electric feeder / pipe routing) — the
    barrio set is honest at operating-area granularity, not feeder-level.
    """
    from prism.graph.water import water_downstream_of

    return water_downstream_of(engine, entity_id)
