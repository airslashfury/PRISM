"""Smoke tests - confirm the scaffold imports and the objective function behaves."""
from prism.assets.base import AssetType, objective_value


def test_package_imports():
    import prism

    assert prism.__version__


def test_objective_prefers_more_benefit():
    base = dict(
        construction=100.0,
        maintenance=20.0,
        property_impact=10.0,
        environmental_impact=5.0,
        disaster_vulnerability=15.0,
        population_benefit=0.0,
        economic_benefit=0.0,
    )
    low = objective_value(**base)
    more = objective_value(**{**base, "population_benefit": 50.0})
    assert more < low  # more benefit -> lower (better) score


def test_assets_register():
    import prism.assets  # noqa: F401  (import triggers registration)
    from prism.assets.base import registered

    reg = registered()
    assert AssetType.TRANSMISSION in reg
    assert AssetType.ROAD in reg
