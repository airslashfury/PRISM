"""Pluggable Infrastructure Asset interfaces - the architectural spine of PRISM.

Every infrastructure type (rail, road, transmission, fiber, water, sewer, emergency) implements the
same four models, so ONE optimization engine works across all of them:

    construction cost | maintenance | capacity | failure

The optimizer scores candidate routes/placements with `objective_value()`, which encodes long-term
societal value - not cheapest path. See plan section 3. This module is stdlib-only on purpose.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssetType(str, Enum):
    RAIL = "rail"
    ROAD = "road"
    BRIDGE = "bridge"
    TRANSMISSION = "transmission"
    FIBER = "fiber"
    WATER = "water"
    SEWER = "sewer"
    EMERGENCY = "emergency"


@dataclass
class Context:
    """Spatial/economic context a model needs to evaluate a segment.

    Populated from PostGIS in later phases (terrain, parcels, flood, population, ...). Kept as a
    loose mapping so the interface stays stable while the data layer grows.
    """

    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class FailureImpact:
    """What happens when an asset (graph node/edge) fails."""

    people_affected: int = 0
    critical_facilities: int = 0
    is_single_point_of_failure: bool = False
    notes: str = ""


@dataclass
class ObjectiveWeights:
    """Weights for the long-term-societal-value objective (plan section 3).

    Costs are minimized, benefits maximized. Tune per study; defaults are neutral placeholders.
    equity_weight: multiplier applied to population benefit for high-SVI areas.
      A substation serving tracts with svi_score=s gets benefit × (1 + equity_weight × s).
      0.0 = pure VOLL (Phase 5 behaviour); 1.0 = double weight for max-SVI areas.
    """

    construction: float = 1.0
    maintenance: float = 1.0
    property_impact: float = 1.0
    environmental_impact: float = 1.0
    disaster_vulnerability: float = 1.0
    population_benefit: float = 1.0
    economic_benefit: float = 1.0
    equity_weight: float = 0.0


class InfrastructureAsset(abc.ABC):
    """Base class every asset type implements. The optimizer depends only on this interface."""

    asset_type: AssetType

    @abc.abstractmethod
    def construction_cost(self, segment: Any, ctx: Context) -> float:
        """One-time build cost for a segment/placement (terrain, parcels, crossings)."""

    @abc.abstractmethod
    def maintenance_cost(self, segment: Any, ctx: Context, years: int = 30) -> float:
        """Lifecycle maintenance cost over `years` (use NPV in real implementations)."""

    @abc.abstractmethod
    def capacity(self, segment: Any, ctx: Context) -> float:
        """How much the asset can carry/serve (units depend on asset type)."""

    @abc.abstractmethod
    def failure_impact(self, asset_id: Any, graph: Any, ctx: Context) -> FailureImpact:
        """Consequence of this asset failing, computed over the knowledge graph."""


_REGISTRY: dict[AssetType, type[InfrastructureAsset]] = {}


def register(cls: type[InfrastructureAsset]) -> type[InfrastructureAsset]:
    """Class decorator: register an asset implementation by its `asset_type`."""
    _REGISTRY[cls.asset_type] = cls
    return cls


def get_asset(asset_type: AssetType) -> type[InfrastructureAsset]:
    return _REGISTRY[asset_type]


def registered() -> dict[AssetType, type[InfrastructureAsset]]:
    return dict(_REGISTRY)


def objective_value(
    *,
    construction: float,
    maintenance: float,
    property_impact: float,
    environmental_impact: float,
    disaster_vulnerability: float,
    population_benefit: float,
    economic_benefit: float,
    weights: ObjectiveWeights | None = None,
) -> float:
    """Long-term societal value score for a candidate (LOWER is better).

    minimize: construction + maintenance + property + environmental + disaster vulnerability
    maximize: population + economic benefit (subtracted)
    """
    w = weights or ObjectiveWeights()
    costs = (
        w.construction * construction
        + w.maintenance * maintenance
        + w.property_impact * property_impact
        + w.environmental_impact * environmental_impact
        + w.disaster_vulnerability * disaster_vulnerability
    )
    benefits = w.population_benefit * population_benefit + w.economic_benefit * economic_benefit
    return costs - benefits
