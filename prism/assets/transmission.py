"""Transmission asset model — substations and lines.

construction_cost / maintenance_cost are implemented for the four substation
intervention types used by Phase 4.  Greenfield line routing is Phase 5.

ctx.data keys consumed:
    intervention_type : str  one of hardening | redundant_feed | elevation | relocation
    hazard_score      : float  current P(failure|event)   (Phase 3)
    cascade_impact    : float  current downstream impact  (Phase 3)
    betweenness       : float  current betweenness        (Phase 3)
    composite_score   : float  current composite          (Phase 3)
"""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register

# ── unit costs (USD) per intervention type ──────────────────────────────────
# Sources: FEMA BRIC program, PREPA/AEE post-Maria hardening contracts,
# EPRI distribution hardening cost survey (2022).  ±40 % accuracy.
_COST: dict[str, dict[str, float]] = {
    "hardening": {
        "construction": 2_500_000,   # flood barriers + enclosures + waterproofing
        "annual_om":        50_000,  # inspection + maintenance of barriers
    },
    "redundant_feed": {
        "construction": 8_000_000,   # ~5 km 115 kV line + interconnect equipment
        "annual_om":        80_000,
    },
    "elevation": {
        "construction": 4_500_000,   # civil platform + equipment relift
        "annual_om":        30_000,
    },
    "relocation": {
        "construction": 35_000_000,  # new substation + site + decommission old
        "annual_om":       200_000,
    },
}

# How each intervention reduces the three score components
# (multipliers applied to current value)
_HAZARD_FACTOR: dict[str, float] = {
    "hardening":     0.50,   # flood barrier halves hazard exposure
    "redundant_feed":0.85,   # feed redundancy has modest hazard effect
    "elevation":     0.30,   # elevation eliminates most flood/SLR risk
    "relocation":    0.03,   # new safe site → background hazard only
}
_CASCADE_FACTOR: dict[str, float] = {
    "hardening":     1.00,   # hardening doesn't add alternate supply
    "redundant_feed":0.60,   # 40 % of downstream covered by alternate feed
    "elevation":     1.00,
    "relocation":    1.00,
}
_BETWEENNESS_FACTOR: dict[str, float] = {
    "hardening":     1.00,
    "redundant_feed":0.50,   # second feed path halves network centrality
    "elevation":     1.00,
    "relocation":    1.00,
}


@register
class Transmission(InfrastructureAsset):
    asset_type = AssetType.TRANSMISSION

    PLAYGROUND_SCHEMA = {
        "geometry": "line",
        "icon": "zap",
        "default_unit_cost_usd_per_km": 8_000_000 / 5,  # redundant_feed ~5 km
        "params": [
            {"name": "intervention_type", "type": "enum", "label": "Intervention type",
             "options": ["redundant_feed"], "default": "redundant_feed"},
            {"name": "voltage_kv", "type": "int", "label": "Voltage (kV)", "default": 115},
        ],
    }

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        itype = ctx.get("intervention_type", "")
        if itype not in _COST:
            raise NotImplementedError(
                f"construction_cost not implemented for intervention_type={itype!r}; "
                "pass intervention_type in ctx for Phase 4 use."
            )
        return float(_COST[itype]["construction"])

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        itype = ctx.get("intervention_type", "")
        if itype not in _COST:
            raise NotImplementedError(f"maintenance_cost not implemented for {itype!r}")
        # Simple NPV at 4 % discount rate
        r = 0.04
        npv_factor = (1 - (1 + r) ** -years) / r
        return float(_COST[itype]["annual_om"] * npv_factor)

    def capacity(self, segment: Any, ctx: Context) -> float:
        raise NotImplementedError("line rating (MW) — Phase 5")

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        cascade = ctx.get("cascade_impact", 0.0)
        betw    = ctx.get("betweenness",    0.0)
        return FailureImpact(
            people_affected=0,               # Phase 5: link to barrio population
            critical_facilities=int(cascade),
            is_single_point_of_failure=betw > 0.01,
            notes="Phase 3 cascade proxy; Phase 5 adds parcel-level population.",
        )


def composite_after(
    hazard: float,
    cascade: float,
    betweenness: float,
    intervention_type: str,
) -> float:
    """Composite score after applying an intervention (same formula as Phase 3)."""
    h = hazard     * _HAZARD_FACTOR[intervention_type]
    c = cascade    * _CASCADE_FACTOR[intervention_type]
    b = betweenness * _BETWEENNESS_FACTOR[intervention_type]
    return h * c * (1.0 + b)
