"""Road asset model (routes over the existing network via pgRouting)."""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register


@register
class Road(InfrastructureAsset):
    asset_type = AssetType.ROAD

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        raise NotImplementedError("Phase 4: terrain + parcels + crossings cost model")

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        raise NotImplementedError

    def capacity(self, segment: Any, ctx: Context) -> float:
        # TODO: lane capacity (vehicles/hour).
        raise NotImplementedError

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        # TODO: bridge/segment removal -> communities cut off, detour length, isolation.
        raise NotImplementedError
