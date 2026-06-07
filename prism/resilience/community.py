"""
Community resilience score per barrio.

resilience_score ∈ [0, 1] — 1 = most resilient.

Components
----------
svi_component        = 1 - avg_svi_score of Census tracts covering this barrio
                        (higher SVI → lower resilience)
infra_density_score  = normalised count of hospitals + water_plants within 10 km
                        per 1,000 population; capped at 1.0
recovery_factor      = based on the intervention type assigned to the substation
                        that POWERS this barrio in the latest portfolio run:
                          hardening      → 0.9 (fast, in-place hardening)
                          redundant_feed → 0.8 (new feed, no downtime)
                          elevation      → 0.7 (moderate construction window)
                          relocation     → 0.5 (long construction, site clearing)
                          no intervention→ 0.3 (baseline, no improvement funded)

resilience_score = 0.5 × svi_component + 0.3 × infra_density_score
                 + 0.2 × recovery_factor

Stored in resilience.community_resilience.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.resilience.schema import create_schema

log = logging.getLogger(__name__)

# Infrastructure density threshold: 0.02 facilities per 1,000 people = 2 per 100,000
# At or above this density → infra_density_score = 1.0
_INFRA_DENSITY_THRESHOLD = 0.02


def compute_community_resilience(engine: Engine) -> int:
    """
    Compute community resilience score for every barrio entity.
    Returns count of barrios upserted.
    """
    create_schema(engine)

    sql = text(f"""
        WITH
        -- SVI component: avg svi_score of Census tracts covering this barrio
        -- (barrio centroid → tract join for reliability)
        svi AS (
            SELECT
                b.entity_id AS barrio_id,
                COALESCE(AVG(be.svi_score), 0.5)        AS avg_svi,
                COALESCE(SUM(be.population), 0)         AS tract_pop
            FROM graph.entities b
            LEFT JOIN economy.barrio_economics be
                ON ST_Within(ST_Centroid(b.geom), be.geom)
            WHERE b.kind = 'barrio'
            GROUP BY b.entity_id
        ),
        -- Infrastructure density: critical facilities within 10 km per 1,000 population
        infra AS (
            SELECT
                b.entity_id AS barrio_id,
                COUNT(DISTINCT CASE WHEN e2.kind = 'hospital'    THEN e2.entity_id END)
              + COUNT(DISTINCT CASE WHEN e2.kind = 'water_plant' THEN e2.entity_id END)
              + COUNT(DISTINCT CASE WHEN e2.kind = 'health_center' THEN e2.entity_id END)
                AS n_facilities
            FROM graph.entities b
            LEFT JOIN graph.entities e2
                ON ST_DWithin(b.geom, e2.geom, 10000)
                AND e2.kind IN ('hospital', 'water_plant', 'health_center')
            WHERE b.kind = 'barrio'
            GROUP BY b.entity_id
        ),
        -- Recovery factor from latest portfolio run
        -- Find barrio → serving substation via POWERS relationship,
        -- then look up the intervention type in the most recent portfolio run
        serving AS (
            SELECT r.dst_entity AS barrio_id, r.src_entity AS substation_id
            FROM graph.relationships r
            WHERE r.rel_type = 'POWERS'
        ),
        latest_portfolio AS (
            SELECT pi.entity_id, pi.intervention_type
            FROM optimize.portfolio_items pi
            JOIN optimize.portfolio_runs pr ON pr.run_id = pi.run_id
            WHERE pr.run_id = (SELECT max(run_id) FROM optimize.portfolio_runs)
        ),
        recovery AS (
            SELECT
                s.barrio_id,
                COALESCE(
                    MAX(CASE lp.intervention_type
                        WHEN 'hardening'       THEN 0.9
                        WHEN 'redundant_feed'  THEN 0.8
                        WHEN 'elevation'       THEN 0.7
                        WHEN 'relocation'      THEN 0.5
                        ELSE 0.3
                    END),
                    0.3
                ) AS recovery_factor
            FROM serving s
            LEFT JOIN latest_portfolio lp ON lp.entity_id = s.substation_id
            GROUP BY s.barrio_id
        ),
        -- Assemble final scores
        scored AS (
            SELECT
                b.entity_id                                    AS barrio_id,
                b.name                                         AS barrio_name,
                COALESCE(sv.avg_svi, 0.5)                      AS avg_svi_score,
                -- Normalise facility density: facilities per 1,000 pop, cap at threshold
                LEAST(
                    COALESCE(inf.n_facilities, 0)
                        / (NULLIF(sv.tract_pop, 0) / 1000.0),
                    :infra_threshold
                ) / :infra_threshold                           AS infra_density_score,
                COALESCE(rec.recovery_factor, 0.3)             AS recovery_factor,
                b.geom
            FROM graph.entities b
            LEFT JOIN svi    sv  ON sv.barrio_id  = b.entity_id
            LEFT JOIN infra  inf ON inf.barrio_id = b.entity_id
            LEFT JOIN recovery rec ON rec.barrio_id = b.entity_id
            WHERE b.kind = 'barrio'
        )
        INSERT INTO resilience.community_resilience
            (barrio_id, barrio_name, avg_svi_score, infra_density_score,
             recovery_factor, resilience_score, geom)
        SELECT
            barrio_id,
            barrio_name,
            avg_svi_score,
            infra_density_score,
            recovery_factor,
            -- resilience_score: higher = more resilient
            0.50 * (1.0 - avg_svi_score)
            + 0.30 * infra_density_score
            + 0.20 * recovery_factor                          AS resilience_score,
            geom
        FROM scored
        ON CONFLICT (barrio_id) DO UPDATE SET
            barrio_name         = EXCLUDED.barrio_name,
            avg_svi_score       = EXCLUDED.avg_svi_score,
            infra_density_score = EXCLUDED.infra_density_score,
            recovery_factor     = EXCLUDED.recovery_factor,
            resilience_score    = EXCLUDED.resilience_score,
            geom                = EXCLUDED.geom,
            computed_at         = now()
    """)

    with engine.begin() as conn:
        result = conn.execute(sql, {"infra_threshold": _INFRA_DENSITY_THRESHOLD})

    n = result.rowcount
    log.info("Community resilience computed for %d barrios", n)
    return n


def load_community_resilience(engine: Engine) -> list[dict]:
    """Return community resilience rows as list of dicts for reporting."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT barrio_id, barrio_name, avg_svi_score,
                   infra_density_score, recovery_factor, resilience_score
            FROM resilience.community_resilience
            ORDER BY resilience_score ASC
        """)).fetchall()
    return [
        {
            "barrio_id":          r[0],
            "barrio_name":        r[1],
            "avg_svi_score":      r[2],
            "infra_density_score":r[3],
            "recovery_factor":    r[4],
            "resilience_score":   r[5],
        }
        for r in rows
    ]
