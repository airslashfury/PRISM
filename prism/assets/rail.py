"""Rail asset model - Phase 8. Built last; falls out of the engine built in Phases 0-7."""
from __future__ import annotations

from typing import Any

from prism.assets.base import AssetType, Context, FailureImpact, InfrastructureAsset, register


@register
class Rail(InfrastructureAsset):
    asset_type = AssetType.RAIL

    def construction_cost(self, segment: Any, ctx: Context) -> float:
        # TODO Phase 8: grade-limited alignment cost; needs substations + transmission (power-first).
        raise NotImplementedError

    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        raise NotImplementedError

    def capacity(self, segment: Any, ctx: Context) -> float:
        raise NotImplementedError

    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        raise NotImplementedError
