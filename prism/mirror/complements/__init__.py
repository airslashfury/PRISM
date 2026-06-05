"""Complement source registry — each module exposes mirror(raw_dir, date_str, cfg, timeout)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

MirrorFn = Callable[[Path, str, dict, int], list[dict[str, Any]]]


def get_all() -> dict[str, MirrorFn]:
    """Return {source_key: mirror_fn} for every registered complement."""
    from prism.mirror.complements import (
        census_acs,
        census_tiger,
        crim,
        fema_nfhl,
        hifld,
        noaa_slr,
        osm,
        usgs_3dep,
    )

    return {
        "osm": osm.mirror,
        "census_tiger": census_tiger.mirror,
        "fema_nfhl": fema_nfhl.mirror,
        "usgs_3dep": usgs_3dep.mirror,
        "noaa_slr": noaa_slr.mirror,
        "crim_parcels": crim.mirror,
        "census_acs": census_acs.mirror,
        "hifld_next": hifld.mirror,
    }
