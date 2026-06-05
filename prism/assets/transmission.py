"""Transmission line asset model - the power-first, Phase 5 marquee asset."""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register


@register
class Transmission(InfrastructureAsset):
    asset_type = AssetType.TRANSMISSION

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        # TODO Phase 4/5: base $/km * length, scaled by slope, crossings, parcels (cost surface).
        raise NotImplementedError("build from the GRASS cost surface (slope, parcels, crossings)")

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        # TODO: annual O&M -> NPV over `years`; higher in flood/surge-exposed corridors.
        raise NotImplementedError

    def capacity(self, segment: Any, ctx: Context) -> float:
        # TODO: line rating (MW) from voltage + conductor.
        raise NotImplementedError

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        # TODO: drop the line/substation from the graph; downstream = served pop + critical facilities.
        # v1 uses the proximity / service-area approximation until LUMA/PREPA topology lands.
        raise NotImplementedError
