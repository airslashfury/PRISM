"""
Rail corridor asset model — Phase 10.

Cost basis:
  Construction : DTOP / FTA PRIITS unit costs (2024 estimate)
    - Standard at-grade    : $15 M/km
    - Elevated structure   : $40 M/km
    - Tunnel (mountain)    : $120 M/km
  Maintenance  : $500 K/km/year, 30-yr NPV at 5 % → × 15.37
  Capacity     : 20,000 passengers/day (modern LRT single track)
  Ridership    : barrio population within 5 km × 5 % mode share
  Failure      : isolated population × VOLL-derived transit disruption cost

terrain_type is determined by slope from the cost surface:
  slope < 5 %   → standard
  5 % ≤ slope < 15 % → elevated
  slope ≥ 15 %  → tunnel
"""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register

# USD / metre
_COST_PER_M: dict[str, float] = {
    "standard": 15_000_000 / 1_000,
    "elevated": 40_000_000 / 1_000,
    "tunnel":  120_000_000 / 1_000,
}
_MAINT_PER_M_YR = 500_000 / 1_000      # $500 K/km/year
_NPV_30_5PCT    = 15.3725               # annuity factor, 30 yr @ 5 %

_CAPACITY_PAX_PER_DAY = 20_000          # passengers/day, single-track LRT
_MODE_SHARE           = 0.05            # 5 % of population within 5 km uses the line
_SERVICE_RADIUS_M     = 5_000           # 5 km catchment

# Transit disruption value: $10/trip × 2 trips/day × 260 commuting days × NPV
_DISRUPTION_COST_PER_PERSON_30YR = 10 * 2 * 260 * _NPV_30_5PCT   # ≈ $800 K / person


@register
class Rail(InfrastructureAsset):
    """Pluggable rail segment asset.

    `segment` dict keys:
      length_m      float   — segment length in metres
      terrain_type  str     — 'standard' | 'elevated' | 'tunnel'

    `graph` dict keys (for failure_impact):
      population_within_5km  int   — catchment population
      detour_available        bool  — whether alternative transport exists
    """
    asset_type = AssetType.RAIL

    PLAYGROUND_SCHEMA = {
        "geometry": "line",
        "icon": "train",
        "default_unit_cost_usd_per_km": 15_000_000,
        "params": [
            {"name": "auto_route", "type": "bool", "default": True,
             "label": "Auto-route to terrain"},
        ],
    }

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        length_m     = float(segment.get("length_m", 0))
        terrain_type = segment.get("terrain_type", "standard")
        rate = _COST_PER_M.get(terrain_type, _COST_PER_M["standard"])
        return length_m * rate

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        length_m = float(segment.get("length_m", 0))
        annual   = length_m * _MAINT_PER_M_YR
        if years == 30:
            return annual * _NPV_30_5PCT
        r = 0.05
        return annual * ((1 - (1 + r) ** -years) / r)

    def capacity(self, segment: Any, ctx: Context) -> float:
        """Passengers per day (LRT single-track bidirectional)."""
        return _CAPACITY_PAX_PER_DAY

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        pop = int(graph.get("population_within_5km", 0))
        detour = bool(graph.get("detour_available", True))

        riders = int(pop * _MODE_SHARE)
        if detour:
            notes = f"Rail failure: {riders:,} affected riders; detour available"
        else:
            notes = f"Rail failure: {riders:,} affected riders; NO alternative transport"

        return FailureImpact(
            people_affected=riders,
            is_single_point_of_failure=not detour,
            notes=notes,
        )

    def ridership(self, segment: Any, ctx: Context) -> int:
        """Expected daily riders = catchment pop × mode share."""
        pop = int(segment.get("population_within_5km", 0))
        return int(pop * _MODE_SHARE)
