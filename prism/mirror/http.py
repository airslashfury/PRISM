"""Generic streaming HTTP file downloader with provenance."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prism.sync import http as prism_http


def download_file(
    url: str,
    dest: Path,
    timeout: int = 300,
    chunk_size: int = 1024 * 1024,
    source: str = "file_mirror",
) -> dict[str, Any]:
    """Stream-download url → dest; return provenance dict. Skips if dest exists.

    Writes to a `.part` file and renames on completion, so an interrupted
    download can never be mistaken for a finished mirror — `dest.exists()` is
    what makes this idempotent, and a truncated file passing that check would
    poison the mirror permanently (F14d).
    """
    if dest.exists():
        return {"skipped": True, "file": str(dest), "url": url}

    dest.parent.mkdir(parents=True, exist_ok=True)
    pulled_at = datetime.now(timezone.utc).isoformat()

    # Retried at the request level, not mid-stream: resuming a byte range needs
    # server support PRISM's sources don't reliably offer, and a re-download of
    # a mirror file is cheap next to a silently corrupt one.
    r = prism_http.fetch(
        url, source=source, stream=True,
        policy=prism_http.RetryPolicy(attempts=3, read_timeout=float(timeout)),
    )

    part = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    try:
        with part.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
                    h.update(chunk)
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    size = dest.stat().st_size
    return {
        "skipped": False,
        "url": url,
        "file": str(dest),
        "size_bytes": size,
        "sha256": h.hexdigest(),
        "pulled_at": pulled_at,
    }
