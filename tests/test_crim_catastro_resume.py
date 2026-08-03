"""F14d gate follow-up: `download_layer`'s page checkpoint has to survive the
failure mode this project actually suffers (a hard kill mid-write — the WSL VM
recycled under a running host pull), not just a clean stop-and-resume.

Each test simulates the on-disk state a kill leaves behind and asserts the next
run lands on exactly `total` unique features either way: by trusting a genuinely
consistent checkpoint, or by discarding an inconsistent one and re-walking the
layer from offset 0. Never silently duplicating or dropping rows.
"""
from __future__ import annotations

import json

from prism.mirror import crim_catastro

META = {"geometryType": "esriGeometryPoint", "fields": [{"name": "NUM_CATASTRO"}]}


def _pool(total: int) -> list[dict]:
    return [{"attributes": {"NUM_CATASTRO": f"C{i}"}} for i in range(total)]


def _fake_get(pool: list[dict], total: int):
    def _get(url: str, params: dict, use_proxy: bool = True) -> dict:
        if params.get("returnCountOnly"):
            return {"count": total}
        if params == {"f": "json"}:
            return dict(META)
        offset = params["resultOffset"]
        size = params["resultRecordCount"]
        return {"features": pool[offset:offset + size]}

    return _get


def _catastros(out_path) -> list[str]:
    fc = json.loads(out_path.read_text(encoding="utf-8"))
    return [f["properties"]["NUM_CATASTRO"] for f in fc["features"]]


def test_download_layer_resumes_from_a_consistent_checkpoint(tmp_path, monkeypatch):
    """The happy path: offset and banked-feature-count in the marker agree with
    what's actually on disk, so the walk continues from where it left off
    instead of re-fetching pages it already has."""
    total = 6
    pool = _pool(total)
    monkeypatch.setattr(crim_catastro, "_get", _fake_get(pool, total))

    name = "test_layer"
    part_path = tmp_path / f"{name}.features.jsonl"
    with part_path.open("w", encoding="utf-8") as fh:
        for feat in pool[:2]:
            fh.write(json.dumps(crim_catastro._to_geojson(feat, META["geometryType"])) + "\n")
    crim_catastro._write_offset(part_path, 2, 2)

    out_path = crim_catastro.download_layer(name, "https://example.test/layer", tmp_path, page_size=2)

    catastros = _catastros(out_path)
    assert len(catastros) == total
    assert len(set(catastros)) == total
    assert not part_path.exists()
    assert not part_path.with_suffix(".offset").exists()


def test_download_layer_restarts_on_a_truncated_trailing_line(tmp_path, monkeypatch):
    """A kill mid-flush: the marker claims 4 banked features but the sidecar's
    4th line is a truncated write. The old code crashed on json.loads() here;
    the fix has to detect the mismatch and re-walk from scratch."""
    total = 6
    pool = _pool(total)
    monkeypatch.setattr(crim_catastro, "_get", _fake_get(pool, total))

    name = "test_layer"
    part_path = tmp_path / f"{name}.features.jsonl"
    with part_path.open("w", encoding="utf-8") as fh:
        for feat in pool[:3]:
            fh.write(json.dumps(crim_catastro._to_geojson(feat, META["geometryType"])) + "\n")
        fh.write('{"type": "Feature", "properties": {"NUM_CAT')  # truncated, no newline
    crim_catastro._write_offset(part_path, 4, 4)

    out_path = crim_catastro.download_layer(name, "https://example.test/layer", tmp_path, page_size=2)

    catastros = _catastros(out_path)
    assert len(catastros) == total
    assert len(set(catastros)) == total


def test_download_layer_restarts_on_a_stale_or_empty_marker(tmp_path, monkeypatch):
    """A kill mid-marker-write: the sidecar has 2 banked features but the
    `.offset` marker is empty (the write never completed). The old code failed
    open to offset=0 while still loading the 2 banked features, duplicating
    them once the walk restarted from page 1. The fix discards the whole
    checkpoint rather than trusting half of it."""
    total = 6
    pool = _pool(total)
    monkeypatch.setattr(crim_catastro, "_get", _fake_get(pool, total))

    name = "test_layer"
    part_path = tmp_path / f"{name}.features.jsonl"
    with part_path.open("w", encoding="utf-8") as fh:
        for feat in pool[:2]:
            fh.write(json.dumps(crim_catastro._to_geojson(feat, META["geometryType"])) + "\n")
    part_path.with_suffix(".offset").write_text("", encoding="utf-8")

    out_path = crim_catastro.download_layer(name, "https://example.test/layer", tmp_path, page_size=2)

    catastros = _catastros(out_path)
    assert len(catastros) == total
    assert len(set(catastros)) == total
