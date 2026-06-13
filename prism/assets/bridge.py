"""
Bridge asset model.

Cost basis:
  Construction : FEMA BRIC + DTOP/FHWA post-Maria bridge contracts
    Short span  (< 20 m) : $3.0 M flat
    Medium span (20-60 m) : $250 K/m
    Long span   (> 60 m)  : $350 K/m
  Maintenance  : $100 K/bridge/year, 30-yr NPV at 5%
  Capacity     : load rating in metric tons (proxy: 36 t standard, 23 t posted)
  Failure      : cuts off communities on far side; uses road detour model
"""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register

_BRIDGE_MAINT_PER_YR = 100_000          # USD / bridge / year
_NPV_30_5PCT         = 15.3725
_LOAD_STANDARD_T     = 36.0             # metric tons, HL-93 standard
_LOAD_POSTED_T       = 23.0             # typical PR posted bridge
_TRIP_COST_PER_KM_P  = 0.03


@register
class Bridge(InfrastructureAsset):
    asset_type = AssetType.BRIDGE

    PLAYGROUND_SCHEMA = {
        "geometry": "point",
        "icon": "milestone",
        "default_unit_cost_usd_per_km": None,
        "params": [
            {"name": "span_m", "type": "float", "label": "Span length (m)", "default": 30.0},
            {"name": "posted", "type": "bool", "label": "Load-posted", "default": False},
        ],
    }

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        """
        segment must carry:
          - span_m : float — total bridge span in metres
        """
        span_m = float(segment.get("span_m", 20.0))
        if span_m < 20:
            return 3_000_000
        elif span_m <= 60:
            return span_m * 250_000
        else:
            return span_m * 350_000

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        if years == 30:
            return _BRIDGE_MAINT_PER_YR * _NPV_30_5PCT
        r = 0.05
        npv_factor = (1 - (1 + r) ** -years) / r
        return _BRIDGE_MAINT_PER_YR * npv_factor

    def capacity(self, segment: Any, ctx: Context) -> float:
        """Load rating in metric tons."""
        posted = segment.get("posted", False)
        return _LOAD_POSTED_T if posted else _LOAD_STANDARD_T

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        """
        graph must carry:
          - isolated_pop : int
          - detour_km    : float
        """
        isolated_pop = int(graph.get("isolated_pop", 0))
        detour_km    = float(graph.get("detour_km", 0.0))
        trips_per_year = 12
        annual_cost    = isolated_pop * detour_km * _TRIP_COST_PER_KM_P * trips_per_year
        return FailureImpact(
            people_affected=isolated_pop,
            notes=f"Bridge failure: {isolated_pop:,} isolated, {detour_km:.1f} km detour, "
                  f"30yr NPV loss ${annual_cost * _NPV_30_5PCT / 1e6:.1f}M",
        )
