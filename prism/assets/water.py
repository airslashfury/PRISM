"""Water asset model (PRASA-style supply; pipe topology not public in v1)."""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register


@register
class Water(InfrastructureAsset):
    asset_type = AssetType.WATER

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        raise NotImplementedError("Phase 4: pipe/main cost model from cost surface")

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        raise NotImplementedError

    def capacity(self, segment: Any, ctx: Context) -> float:
        raise NotImplementedError

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        # TODO: plant/pump failure -> municipality supply; pumps depend on power (cross-domain).
        raise NotImplementedError
