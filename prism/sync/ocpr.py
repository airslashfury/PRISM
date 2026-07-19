"""OCPR government-contracts loader (F11 chunk F11e).

Government contracts from the Oficina del Contralor de Puerto Rico
(`consultacontratos.ocpr.gov.pr`) — a **supplement** to the F11 owner intelligence.
Each contract's contractor name joins to the corporations-registry companies
(`crim.rce_entities`) and CRIM owners, giving an owner its government-contract
footprint ($ total, count, contracting agencies).

Endpoints (assessed live 2026-07-18, see memory `ocpr-contralor-contracts.md`):
  * bulk search — `POST /contract/search`, DataTables server-side body, paginate
    `start` by `length` (1000). Needs a session: GET `/contract/` first for the
    `__RequestVerificationToken` cookie + form token, echo the token in the header.
    `recordsFiltered` = all-time total (~1.14M contracts, 2012→now).
  * doc pull — `GET contract/downloaddocument?code={DocumentWithoutSocialSecurityId}`
    (no session needed) → the public redacted PDF. Lazy-fetch only, never bulk.

The source serves Latin-1 bytes (also true of the CSVs) — decoded accordingly here.
Gentle-access posture: the system is fragile/unmaintained; polite paced pulls only.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prism.crim.normalize import normalize_owner
from prism.load.db import get_engine

log = logging.getLogger(__name__)

BASE = "https://consultacontratos.ocpr.gov.pr"
SEARCH_URL = BASE + "/contract/search"
DOC_URL = BASE + "/contract/downloaddocument"
PAGE_URL = BASE + "/contract/"

REQUEST_DELAY = 0.4          # polite pacing — fragile source
PAGE_LENGTH = 1000
PROGRESS_ID = "api"
_DOTNET_DATE = re.compile(r"/Date\((-?\d+)")

# DataTables column template the endpoint requires (indices per the site's search page).
_COL_NAMES = [None, "ContractNumber", "Contractors", "DateOfGrant", "EffectiveDateFrom",
              "EffectiveDateTo", "AmountToPay", "Service", "EntityId", "CancellationDate", None]


def _columns() -> list[dict]:
    return [{"data": n, "name": "", "searchable": n is not None,
             "orderable": n is not None, "search": {"value": "", "regex": False}}
            for n in _COL_NAMES]


_DDL = [
    "CREATE SCHEMA IF NOT EXISTS ocpr",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    """
    CREATE TABLE IF NOT EXISTS ocpr.contracts (
        contract_id         BIGINT PRIMARY KEY,
        contract_number     TEXT,
        amendment           TEXT,
        entity_id           BIGINT,
        entity_name         TEXT,
        date_of_grant       DATE,
        effective_from      DATE,
        effective_to        DATE,
        service             TEXT,
        service_group       TEXT,
        amount_to_pay       DOUBLE PRECISION,
        amount_to_receive   DOUBLE PRECISION,
        cancellation_date   DATE,
        has_amendments      BOOLEAN,
        doc_without_ssn_id  TEXT,
        doc_with_ssn_id     TEXT,
        cancellation_doc_id TEXT,
        source              TEXT NOT NULL DEFAULT 'api',
        raw                 JSONB,
        loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ocpr_contracts_amount ON ocpr.contracts (amount_to_pay DESC NULLS LAST)",
    "CREATE INDEX IF NOT EXISTS idx_ocpr_contracts_entity ON ocpr.contracts (entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_ocpr_contracts_grant  ON ocpr.contracts (date_of_grant)",
    """
    CREATE TABLE IF NOT EXISTS ocpr.contract_contractors (
        contract_id     BIGINT NOT NULL,
        contractor_name TEXT NOT NULL,
        contractor_key  TEXT,             -- normalize_owner() — the owner join key
        PRIMARY KEY (contract_id, contractor_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_ocpr_contractors_key ON ocpr.contract_contractors (contractor_key)",
    "CREATE INDEX IF NOT EXISTS idx_ocpr_contractors_name_trgm "
    "ON ocpr.contract_contractors USING gin (contractor_name gin_trgm_ops)",
    """
    CREATE TABLE IF NOT EXISTS ocpr.pull_progress (
        id          TEXT PRIMARY KEY,
        last_start  BIGINT NOT NULL,
        total       BIGINT,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))


# ── HTTP session ────────────────────────────────────────────────────────────

def _new_session() -> tuple[httpx.Client, str]:
    """Bootstrap a session: the search POST needs the antiforgery token in both a
    cookie (set by GET /contract/) and a matching request header (from the form)."""
    client = httpx.Client(timeout=60.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (PRISM data-sovereignty mirror)"})
    page = client.get(PAGE_URL)
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page.text)
    if not m:
        raise RuntimeError("OCPR: could not obtain __RequestVerificationToken from /contract/")
    return client, m.group(1)


def _decode_json(resp: httpx.Response) -> dict:
    """Response body is UTF-8. Some pages carry a leading UTF-8 BOM, so decode with
    utf-8-sig (strips a BOM if present, otherwise identical to utf-8). Any mojibake
    seen in a terminal is a Windows console display artifact, not the data."""
    return json.loads(resp.content.decode("utf-8-sig"))


def search_page(client: httpx.Client, token: str, start: int, *, length: int = PAGE_LENGTH,
                date_from: str = "01/01/2012", date_to: str | None = None,
                order_col: int = 1, order_dir: str = "asc") -> tuple[list[dict], int]:
    """One page of the contract search. Returns (records, records_filtered)."""
    if date_to is None:
        date_to = datetime.now().strftime("%d/%m/%Y")
    body = {
        "draw": 1, "columns": _columns(),
        "order": [{"column": order_col, "dir": order_dir}],
        "start": start, "length": length, "search": {"value": "", "regex": False},
        "EntityId": None, "ContractNumber": None, "ContractorName": None,
        "DateOfGrantFrom": date_from, "DateOfGrantTo": date_to,
        "EffectiveDateFrom": None, "EffectiveDateTo": None, "AmountFrom": None, "AmountTo": None,
        "ServiceGroupId": None, "ServiceId": None, "FundId": None,
        "ContractingFormId": None, "PCONumber": None,
    }
    resp = client.post(SEARCH_URL, json=body, headers={
        "Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest",
        "__RequestVerificationToken": token, "Referer": PAGE_URL, "Origin": BASE,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    })
    resp.raise_for_status()
    j = _decode_json(resp)
    return j.get("data", []), int(j.get("recordsFiltered") or 0)


# ── Parsing / storage ───────────────────────────────────────────────────────

def _dotnet_date(v: Any) -> date | None:
    if not v:
        return None
    m = _DOTNET_DATE.search(str(v))
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date()


def _num(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _store(engine: Engine, records: Iterable[dict], *, source: str = "api") -> int:
    rows = list(records)
    if not rows:
        return 0
    with engine.begin() as conn:
        for d in rows:
            cid = d.get("ContractId")
            if cid is None:
                continue
            conn.execute(text("""
                INSERT INTO ocpr.contracts
                    (contract_id, contract_number, amendment, entity_id, entity_name,
                     date_of_grant, effective_from, effective_to, service, service_group,
                     amount_to_pay, amount_to_receive, cancellation_date, has_amendments,
                     doc_without_ssn_id, doc_with_ssn_id, cancellation_doc_id, source, raw)
                VALUES
                    (:cid, :cn, :amd, :eid, :ename, :grant, :effrom, :efto, :svc, :svcg,
                     :pay, :recv, :cancel, :hasamd, :dwo, :dw, :cdoc, :source, CAST(:raw AS jsonb))
                ON CONFLICT (contract_id) DO UPDATE SET
                    amount_to_pay = EXCLUDED.amount_to_pay,
                    cancellation_date = EXCLUDED.cancellation_date,
                    doc_without_ssn_id = EXCLUDED.doc_without_ssn_id,
                    raw = EXCLUDED.raw, loaded_at = now()
            """), {
                "cid": cid, "cn": d.get("ContractNumber"), "amd": d.get("Amendment"),
                "eid": d.get("EntityId"), "ename": d.get("EntityName"),
                "grant": _dotnet_date(d.get("DateOfGrant")),
                "effrom": _dotnet_date(d.get("EffectiveDateFrom")),
                "efto": _dotnet_date(d.get("EffectiveDateTo")),
                "svc": d.get("Service"), "svcg": d.get("ServiceGroup"),
                "pay": _num(d.get("AmountToPay")), "recv": _num(d.get("AmountToReceive")),
                "cancel": _dotnet_date(d.get("CancellationDate")),
                "hasamd": d.get("HasAmendments"),
                "dwo": d.get("DocumentWithoutSocialSecurityId"),
                "dw": d.get("DocumentWithSocialSecurityId"),
                "cdoc": d.get("CancellationDocumentId"),
                "source": source, "raw": json.dumps(d, ensure_ascii=False),
            })
            for cont in (d.get("Contractors") or []):
                name = (cont.get("Name") or "").strip()
                if not name:
                    continue
                conn.execute(text("""
                    INSERT INTO ocpr.contract_contractors (contract_id, contractor_name, contractor_key)
                    VALUES (:cid, :name, :key)
                    ON CONFLICT (contract_id, contractor_name) DO UPDATE SET contractor_key = EXCLUDED.contractor_key
                """), {"cid": cid, "name": name, "key": normalize_owner(name)})
    return len(rows)


def _resume_start(engine: Engine) -> int:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT last_start FROM ocpr.pull_progress WHERE id = :id"),
                           {"id": PROGRESS_ID}).scalar()
    return int(row) if row is not None else 0


def _checkpoint(engine: Engine, last_start: int, total: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ocpr.pull_progress (id, last_start, total, updated_at)
            VALUES (:id, :s, :t, now())
            ON CONFLICT (id) DO UPDATE SET last_start = EXCLUDED.last_start,
                total = EXCLUDED.total, updated_at = now()
        """), {"id": PROGRESS_ID, "s": last_start, "t": total})


def _month_windows(start_year: int = 2012) -> list[tuple[int, str, str]]:
    """Monthly (YYYYMM, DateOfGrantFrom, DateOfGrantTo) windows from start_year to
    this month. Chunking by month keeps every window's row count well under the
    server's deep-offset limit (~54K), which 500s on large `start` values."""
    import calendar
    from datetime import date
    today = date.today()
    out: list[tuple[int, str, str]] = []
    y, m = start_year, 1
    while (y, m) <= (today.year, today.month):
        last = calendar.monthrange(y, m)[1]
        out.append((y * 100 + m, f"01/{m:02d}/{y}", f"{last:02d}/{m:02d}/{y}"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def pull(engine: Engine | None = None, *, start_year: int = 2012, resume: bool = True) -> dict:
    """Load all contracts into ocpr.contracts (+ contractors), month by month.

    Per-month windows keep pagination offsets shallow (the server 500s past
    ~54K), each window paginated with `start`/`length`. Resumable via
    ocpr.pull_progress (last completed YYYYMM). Idempotent (upsert on contract_id).
    """
    engine = engine or get_engine()
    create_schema(engine)
    client, token = _new_session()
    windows = _month_windows(start_year)
    done_through = _resume_start(engine) if resume else 0   # YYYYMM already completed
    grand_total = 0
    try:
        for wkey, df, dt in windows:
            if wkey <= done_through:
                continue
            start = 0
            fails = 0
            while True:
                try:
                    records, filtered = search_page(client, token, start,
                                                    date_from=df, date_to=dt, order_col=1)
                except Exception as e:          # HTML/500, token expiry, or network blip
                    fails += 1
                    if fails > 6:
                        raise
                    wait = min(20 * fails, 120)
                    log.warning("OCPR %d start=%d failed (%s) — refresh session, retry in %ds",
                                wkey, start, type(e).__name__, wait)
                    time.sleep(wait)
                    client.close()
                    client, token = _new_session()
                    continue
                fails = 0
                if not records:
                    break
                grand_total += _store(engine, records)
                start += len(records)
                if start >= filtered:
                    break
                time.sleep(REQUEST_DELAY)
            _checkpoint(engine, wkey, grand_total)
            log.info("OCPR window %d complete (%d contracts this month; %d stored total)",
                     wkey, start, grand_total)
    finally:
        client.close()
    log.info("OCPR pull complete: %d contracts stored across %d months", grand_total, len(windows))
    return {"stored": grand_total, "windows": len(windows)}


# ── Lazy document download ──────────────────────────────────────────────────

def download_doc(code: str, dest: str | Path) -> Path:
    """Fetch one contract PDF by its document GUID (no session needed). Lazy/on-demand."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0, headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = c.get(DOC_URL, params={"code": code})
        r.raise_for_status()
        if r.content[:4] != b"%PDF":
            raise RuntimeError(f"OCPR doc {code}: not a PDF (status {r.status_code})")
        dest.write_bytes(r.content)
    return dest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    pull()
