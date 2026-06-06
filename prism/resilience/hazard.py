"""
Hazard overlay — P(failure | scenario) for each infrastructure entity.

Three hazard components are summed (clamped to 0.95):
  1. Flood zone membership   (FEMA/PR 1-pct and 0.2-pct zones)
  2. Sea-level-rise inundation extent (NOAA/PR WFS layers 0–10 ft)
  3. Terrain slope            (landslide/erosion proxy)

Scenarios defined here:
  "cat3"     — Cat-3 hurricane (storm-surge proxy via marejada + flood × 1.5, no SLR)
  "slr2ft"   — 2 ft sea-level rise (SLR inundation + base flood, no surge multiplier)
  "combined" — Cat-3 + 2 ft SLR (worst-case composite)

Flood zone base probabilities (above-ground infrastructure):
  VE  (coastal velocity):  0.85
  AE  (100-yr, BFE known): 0.70
  A   (100-yr, no BFE):    0.60
  AO  (shallow flood):     0.40
  X   (outside 500-yr):    0.05
  (not in any zone):       0.03
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# P(failure | in zone) — base, no multiplier
_FLOOD_ZONE_BASE: dict[str, float] = {
    "VE": 0.85,
    "AE": 0.70,
    "A":  0.60,
    "AO": 0.40,
    "X":  0.05,
}
_FLOOD_ZONE_DEFAULT = 0.03   # outside any mapped zone

# Additional probability contribution if entity is within SLR inundation extent
_SLR_ADDITIVE = 0.30

# Surge additive when Cat-3 storm surge (marejada) polygon intersects entity
_SURGE_ADDITIVE = 0.25

# Cat-3 multiplier on top of base flood zone probability
_CAT3_FLOOD_MULTIPLIER = 1.5

# Slope thresholds → additive probability (landslide/erosion)
_SLOPE_HIGH  = (20.0, 0.15)   # ≥ 20°
_SLOPE_MED   = (10.0, 0.08)   # 10–20°
# below 10°: 0.0

# Nearest-neighbour radius for slope lookup (metres, same CRS as everything)
_SLOPE_RADIUS_M = 500


@dataclass
class HazardScenario:
    name: str
    use_slr_ft: int | None      # None = no SLR layer; int = SLR ft (0–10)
    cat3_surge: bool            # include marejada (Cat-2 proxy) × Cat-3 scale
    flood_multiplier: float     # scalar applied to flood zone base probability
    description: str = ""


SCENARIOS: dict[str, HazardScenario] = {
    "cat3": HazardScenario(
        name="cat3",
        use_slr_ft=None,
        cat3_surge=True,
        flood_multiplier=_CAT3_FLOOD_MULTIPLIER,
        description="Category-3 hurricane (storm surge + elevated flood risk, no SLR)",
    ),
    "slr2ft": HazardScenario(
        name="slr2ft",
        use_slr_ft=2,
        cat3_surge=False,
        flood_multiplier=1.0,
        description="2-foot sea-level rise (chronic inundation + base flood risk)",
    ),
    "combined": HazardScenario(
        name="combined",
        use_slr_ft=2,
        cat3_surge=True,
        flood_multiplier=_CAT3_FLOOD_MULTIPLIER,
        description="Cat-3 hurricane under 2 ft SLR (worst-case)",
    ),
}


def compute_hazard_scores(
    engine: Engine,
    scenario: HazardScenario,
    entity_ids: list[int] | None = None,
) -> dict[int, float]:
    """
    Compute P(failure | scenario) for the given entity IDs (or all entities if None).
    Returns {entity_id: hazard_probability}.

    Pass entity_ids to restrict computation to a small set (e.g. just substations)
    and avoid full-table spatial joins against 48K entities.

    All spatial operations run in PostGIS — no Python geometry.
    """
    log.info("Computing hazard scores for scenario '%s' …", scenario.name)

    # WHERE clause fragment applied to every query when entity_ids is supplied
    entity_filter = "AND e.entity_id = ANY(:ids)" if entity_ids is not None else ""
    filter_params: dict = {"ids": entity_ids} if entity_ids is not None else {}

    # ── Step 1: flood zone membership ────────────────────────────────────────
    log.info("  Step 1/4: flood zone membership …")
    flood_sql = text(f"""
        SELECT e.entity_id, COALESCE(MAX(fz.fld_zone), 'NONE') AS worst_zone
        FROM graph.entities e
        LEFT JOIN flood_zones fz ON ST_Intersects(fz.geom, e.geom)
        WHERE TRUE {entity_filter}
        GROUP BY e.entity_id
    """)
    with engine.connect() as conn:
        flood_rows = conn.execute(flood_sql, filter_params).fetchall()

    flood_map: dict[int, float] = {}
    for eid, zone in flood_rows:
        base = _FLOOD_ZONE_BASE.get(zone, _FLOOD_ZONE_DEFAULT)
        flood_map[eid] = min(base * scenario.flood_multiplier, 0.95)

    # ── Step 2: SLR inundation ────────────────────────────────────────────────
    slr_set: set[int] = set()
    if scenario.use_slr_ft is not None:
        slr_table = f"g27_sea_level_rise_inundation_extent_{scenario.use_slr_ft:02d}ft_2019"
        log.info("  Step 2/4: SLR layer '%s' …", slr_table)
        slr_sql = text(f"""
            SELECT DISTINCT e.entity_id
            FROM graph.entities e
            JOIN {slr_table} slr ON ST_Intersects(slr.geom, e.geom)
            WHERE TRUE {entity_filter}
        """)
        with engine.connect() as conn:
            slr_set = {row[0] for row in conn.execute(slr_sql, filter_params).fetchall()}
        log.info("    %d entities within SLR %dft extent", len(slr_set), scenario.use_slr_ft)
    else:
        log.info("  Step 2/4: no SLR layer for this scenario")

    # ── Step 3: storm surge (Cat-2 marejada proxy) ───────────────────────────
    surge_set: set[int] = set()
    if scenario.cat3_surge:
        log.info("  Step 3/4: storm surge (marejada) overlay …")
        surge_sql = text(f"""
            SELECT DISTINCT e.entity_id
            FROM graph.entities e
            JOIN g23_riesgo_inunda_model_intrusion_marejada_cic_cat2 ms
                ON ST_Intersects(ms.geom, e.geom)
            WHERE TRUE {entity_filter}
        """)
        with engine.connect() as conn:
            surge_set = {row[0] for row in conn.execute(surge_sql, filter_params).fetchall()}
        log.info("    %d entities within storm surge extent", len(surge_set))
    else:
        log.info("  Step 3/4: no surge overlay for this scenario")

    # ── Step 4: terrain slope (nearest point within radius) ──────────────────
    log.info("  Step 4/4: terrain slope lookup …")
    slope_sql = text(f"""
        SELECT e.entity_id,
               COALESCE(
                   (SELECT ts.slope_deg
                    FROM terrain_slope ts
                    WHERE ST_DWithin(ts.geom, e.geom, :radius)
                    ORDER BY ts.geom <-> e.geom
                    LIMIT 1),
                   0.0
               ) AS nearest_slope
        FROM graph.entities e
        WHERE TRUE {entity_filter}
    """)
    slope_params = {"radius": _SLOPE_RADIUS_M, **filter_params}
    with engine.connect() as conn:
        slope_rows = conn.execute(slope_sql, slope_params).fetchall()

    slope_map: dict[int, float] = {}
    for eid, slope_deg in slope_rows:
        if slope_deg is None or slope_deg < _SLOPE_MED[0]:
            slope_map[eid] = 0.0
        elif slope_deg < _SLOPE_HIGH[0]:
            slope_map[eid] = _SLOPE_MED[1]
        else:
            slope_map[eid] = _SLOPE_HIGH[1]

    # ── Combine components ────────────────────────────────────────────────────
    scored_ids = {eid for eid, _ in flood_rows}
    scores: dict[int, float] = {}
    for eid in scored_ids:
        p = flood_map.get(eid, _FLOOD_ZONE_DEFAULT)
        if eid in slr_set:
            p += _SLR_ADDITIVE
        if eid in surge_set:
            p += _SURGE_ADDITIVE
        p += slope_map.get(eid, 0.0)
        scores[eid] = min(p, 0.95)

    log.info(
        "Hazard scores computed for %d entities (scenario='%s')",
        len(scores), scenario.name,
    )
    return scores
