"""Generic streaming HTTP file downloader with provenance."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "PRISM-mirror/0.1 (data sovereignty; contact rtechpr@gmail.com)"


def download_file(
    url: str,
    dest: Path,
    timeout: int = 300,
    chunk_size: int = 1024 * 1024,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Stream-download url → dest; return provenance dict. Skips if dest exists."""
    if dest.exists():
        return {"skipped": True, "file": str(dest), "url": url}

    dest.parent.mkdir(parents=True, exist_ok=True)
    sess = session or _SESSION
    pulled_at = datetime.now(timezone.utc).isoformat()

    r = sess.get(url, stream=True, timeout=timeout)
    r.raise_for_status()

    h = hashlib.sha256()
    with dest.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fh.write(chunk)
                h.update(chunk)

    size = dest.stat().st_size
    return {
        "skipped": False,
        "url": url,
        "file": str(dest),
        "size_bytes": size,
        "sha256": h.hexdigest(),
        "pulled_at": pulled_at,
    }
