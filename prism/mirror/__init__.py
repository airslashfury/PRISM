"""Phase 0 — immutable versioned raw archive.

`python -m prism.mirror [--priority P0|P1|P2|all]`

Downloads WFS layers from the OGP/PRITS keystone into data/raw/wfs/<date>/,
writes provenance to catalog/metadata.json.
"""
from prism.mirror.catalog import load, save, add_entry  # noqa: F401
