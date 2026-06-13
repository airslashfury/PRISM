"""Asset registry — reflects over prism/assets/* for the Playground palette.

Any `InfrastructureAsset` subclass that declares a `PLAYGROUND_SCHEMA` class
attribute appears in the palette automatically (zero frontend changes to add
a new asset type). Classes without one (e.g. `Water`, which has no
implemented models yet) are excluded.

`Transmission` is line-oriented (redundant feed), but the palette also needs
a point "substation" placement (relocation). That's a synthetic entry derived
from `Transmission` here, not a new asset class.
"""
from __future__ import annotations

from prism.assets.base import AssetType, InfrastructureAsset, registered

# Import every asset module so its @register decorator runs and populates
# _REGISTRY before asset_type_schemas()/resolve_asset_class() are called.
from prism.assets import bridge as _bridge  # noqa: F401
from prism.assets import rail as _rail  # noqa: F401
from prism.assets import road as _road  # noqa: F401
from prism.assets import transmission as _transmission  # noqa: F401

SUBSTATION_ASSET_TYPE = "substation"

_SUBSTATION_SCHEMA = {
    "asset_type": SUBSTATION_ASSET_TYPE,
    "geometry": "point",
    "icon": "building-2",
    "default_unit_cost_usd_per_km": None,
    "default_unit_cost_usd": 35_000_000,
    "params": [
        {"name": "intervention_type", "type": "enum", "label": "Intervention type",
         "options": ["relocation"], "default": "relocation"},
        {"name": "capacity_mw", "type": "float", "label": "Capacity (MW)", "default": 50.0},
    ],
}


def asset_type_schemas() -> list[dict]:
    """All playground-eligible asset type schemas, including the synthetic substation."""
    out: list[dict] = []
    for atype, cls in registered().items():
        schema = getattr(cls, "PLAYGROUND_SCHEMA", None)
        if schema is None:
            continue
        out.append({"asset_type": atype.value, **schema})
    out.append(dict(_SUBSTATION_SCHEMA))
    return out


def resolve_asset_class(asset_type: str) -> type[InfrastructureAsset]:
    """Map a playground asset_type string (incl. synthetic 'substation') to its model class."""
    if asset_type == SUBSTATION_ASSET_TYPE:
        from prism.assets.transmission import Transmission
        return Transmission
    return registered()[AssetType(asset_type)]


def known_asset_types() -> set[str]:
    return {s["asset_type"] for s in asset_type_schemas()}
