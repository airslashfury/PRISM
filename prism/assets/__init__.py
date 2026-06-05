"""Pluggable Infrastructure Asset models (plan section 3).

Importing this package registers every asset implementation (via @register), so the optimizer
can discover them with `registered()`.
"""
from prism.assets.base import (
    AssetType,
    Context,
    FailureImpact,
    InfrastructureAsset,
    ObjectiveWeights,
    get_asset,
    objective_value,
    register,
    registered,
)

# Import implementations so they self-register on package import.
from prism.assets import transmission, road, water, rail  # noqa: E402,F401

__all__ = [
    "AssetType",
    "Context",
    "FailureImpact",
    "InfrastructureAsset",
    "ObjectiveWeights",
    "get_asset",
    "objective_value",
    "register",
    "registered",
]
