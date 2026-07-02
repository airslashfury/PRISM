"""MVP3 Pillar 1 — provenance/confidence module and API. No DB required."""
from __future__ import annotations

import pytest

from prism import provenance


def test_list_tiers_has_four_ordered_tiers():
    tiers = provenance.list_tiers()
    assert list(tiers.keys()) == ["authoritative", "modeled", "proxy", "estimated"]
    for key, tier in tiers.items():
        assert tier["label"]
        assert tier["description"]
        assert tier["color"].startswith("#")


def test_list_assumptions_have_required_fields():
    assumptions = provenance.list_assumptions()
    assert len(assumptions) >= 5
    tiers = set(provenance.list_tiers())
    for a in assumptions:
        assert a["key"]
        assert a["label"]
        assert a["confidence_tier"] in tiers
        assert a["assumptions"]


def test_get_table_provenance_known_table():
    prov = provenance.get_table_provenance("graph.relationships")
    assert prov is not None
    assert prov["confidence_tier"] == "proxy"
    assert prov["method"] == "proxy"
    assert "FEEDS" in prov["assumptions"]
    assert prov["upgrade_path"]
    assert prov["row_count"] == 68272


def test_get_table_provenance_unknown_table_returns_none():
    assert provenance.get_table_provenance("not.a.real.table") is None


def test_get_layer_provenance_defaults_to_authoritative():
    prov = provenance.get_layer_provenance("pr_geodata:g03_legales_barrios_2023")
    assert prov is not None
    assert prov["confidence_tier"] == "authoritative"
    assert prov["method"] == "measured"
    assert prov["feature_count"] == 901


def test_get_layer_provenance_unknown_layer_returns_none():
    assert provenance.get_layer_provenance("does:not-exist") is None


def test_list_inventory_covers_every_catalog_entry():
    import json
    from prism.provenance.catalog import CATALOG_PATH

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    inventory = provenance.list_inventory()
    assert len(inventory) == len(catalog["layers"])

    derived = [e for e in inventory if e["is_derived"]]
    sources = [e for e in inventory if not e["is_derived"]]
    assert derived and sources

    tiers = set(provenance.list_tiers())
    for entry in inventory:
        assert entry["confidence_tier"] in tiers
        assert entry["method"]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    return TestClient(app)


def test_api_tiers(client):
    r = client.get("/provenance/tiers")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 4
    assert {t["key"] for t in body} == {"authoritative", "modeled", "proxy", "estimated"}


def test_api_assumptions(client):
    r = client.get("/provenance/assumptions")
    assert r.status_code == 200
    assert len(r.json()) >= 5


def test_api_inventory(client):
    r = client.get("/provenance/inventory")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 183
    assert all("confidence_tier" in e for e in body)


def test_api_table_provenance(client):
    r = client.get("/provenance/graph.relationships")
    assert r.status_code == 200
    body = r.json()
    assert body["confidence_tier"] == "proxy"
    assert body["table"] == "graph.relationships"


def test_api_table_provenance_404(client):
    r = client.get("/provenance/no.such.table")
    assert r.status_code == 404


def test_api_layer_provenance(client):
    r = client.get("/provenance/layer/pr_geodata:g03_legales_barrios_2023")
    assert r.status_code == 200
    body = r.json()
    assert body["confidence_tier"] == "authoritative"


def test_api_layer_provenance_404(client):
    r = client.get("/provenance/layer/does:not-exist")
    assert r.status_code == 404


def test_every_derived_table_in_catalog_has_confidence_stamp():
    """Every `derived:*` catalog entry should be stamped in config/confidence.yml
    (MVP3 P1 task 1: 'stamp every derived table's catalog entry with a method and
    a one-line assumptions note')."""
    import json
    import yaml
    from prism.provenance.catalog import CATALOG_PATH, CONFIDENCE_PATH

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    confidence = yaml.safe_load(CONFIDENCE_PATH.read_text(encoding="utf-8"))
    stamped = set(confidence["tables"])

    derived_tables = {
        key[len("derived:"):] for key in catalog["layers"] if key.startswith("derived:")
    }
    missing = derived_tables - stamped
    assert not missing, f"derived tables missing a confidence.yml stamp: {missing}"
