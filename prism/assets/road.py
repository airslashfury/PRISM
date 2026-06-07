"""
Road segment asset model.

Cost basis:
  Construction : FEMA BRIC + DTOP post-Maria unit costs
    - Hardening (flood-proof/elevate road) : $2.0 M/km
    - New access corridor                  : $3.5 M/km
  Maintenance  : $50 K/km/year, 30-yr NPV at 5% → × 15.37
  Capacity     : 1,800 veh/hr per lane (HCM LOS C, rural PR roads)
  Failure      : isolated population × detour_km × $0.03/km/person/trip
"""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register

# USD / metre
_HARDEN_PER_M     = 2_000_000 / 1_000   # $2 M/km
_NEW_ROAD_PER_M   = 3_500_000 / 1_000   # $3.5 M/km
_MAINT_PER_M_YR   = 50_000 / 1_000      # $50 K/km/year
_NPV_30_5PCT      = 15.3725              # annuity factor, 30 yr @ 5%
_VEHICLES_PER_LANE_HR = 1_800
_TRIP_COST_PER_KM_PERSON = 0.03         # generalised travel cost, USD/km/person


@register
class Road(InfrastructureAsset):
    asset_type = AssetType.ROAD

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        """
        segment must carry:
          - length_m  : float
          - intervention : 'hardening' | 'new_corridor'
        """
        length_m = float(segment.get("length_m", 0))
        itype    = segment.get("intervention", "hardening")
        rate     = _NEW_ROAD_PER_M if itype == "new_corridor" else _HARDEN_PER_M
        return length_m * rate

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        length_m = float(segment.get("length_m", 0))
        annual   = length_m * _MAINT_PER_M_YR
        # Simple NPV if years != 30; otherwise use pre-computed factor.
        if years == 30:
            return annual * _NPV_30_5PCT
        r = 0.05
        npv_factor = (1 - (1 + r) ** -years) / r
        return annual * npv_factor

    def capacity(self, segment: Any, ctx: Context) -> float:
        """Vehicles per hour based on lane count (default 2 lanes)."""
        lanes = int(segment.get("lanes", 2))
        return lanes * _VEHICLES_PER_LANE_HR

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        """
        graph must carry:
          - isolated_pop  : int    — population cut off if this segment fails
          - detour_km     : float  — extra km to reach nearest hospital
        """
        isolated_pop = int(graph.get("isolated_pop", 0))
        detour_km    = float(graph.get("detour_km", 0.0))
        # Direct cost: population × detour × trips_per_year × cost_per_km
        trips_per_year = 12  # ~monthly hospital/service trip
        annual_cost    = isolated_pop * detour_km * _TRIP_COST_PER_KM_PERSON * trips_per_year
        return FailureImpact(
            people_affected=isolated_pop,
            notes=f"Road failure: {isolated_pop:,} isolated, {detour_km:.1f} km detour, "
                  f"30yr NPV loss ${annual_cost * _NPV_30_5PCT / 1e6:.1f}M",
        )
