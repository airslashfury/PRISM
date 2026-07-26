"""Monthly change report (F14c).

Split deliberately: the classification and rendering logic is pure and tested
without a database, and the DB-backed shape tests are marked `integration` like
the rest of the suite's live-data tests.
"""
from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from prism.report import monthly


# ── Owner-change classification (pure) ──────────────────────────────────────

@pytest.mark.parametrize(
    "previous,new,expected",
    [
        # The finding that motivated this: CRIM's delta compares the raw string,
        # so a trailing space reads as a sale.
        ("MILLAN GUTIERREZ ALICIA ", "MILLAN GUTIERREZ ALICIA", "formatting_only"),
        ("PRODUCTORA DE AGREGADOS INC   ", "PRODUCTORA DE AGREGADOS INC", "formatting_only"),
        # Punctuation + legal-suffix folding comes from normalize_owner, so the
        # report agrees with owner identity everywhere else in PRISM.
        ("ACME, L.L.C.", "ACME LLC", "formatting_only"),
        # KNOWN LIMITATION, pinned deliberately: normalize_owner strips the
        # trailing legal-form suffix, so a change of legal ENTITY reads as
        # cosmetic. 3 such rows in the 2026-07 delta. Widening the classifier
        # would mean not using PRISM's canonical owner key here, and the report
        # would then disagree with owner identity everywhere else — a worse
        # trade than under-reporting three rows.
        ("ACME LLC", "ACME INC", "formatting_only"),
        ("RR PROPERTY", "RR PROPERTY LLC", "formatting_only"),
        # Same person, surname/given order swapped between snapshots.
        ("LOUIS  ATILANO GONZALEZ", "ATILANO GONZALEZ LOUIS", "reordered"),
        # A genuinely different owner — the only class the headline counts.
        ("ROLDAN VAZQUEZ LUZ E", "CRESPO ROLDAN OMAR", "substantive"),
        # A typo correction is NOT detectable as such; it must not be silently
        # swallowed into "cosmetic".
        ("ROMOS PEREZ DAVID", "RAMOS PEREZ DAVID", "substantive"),
        ("BANCO POPULAR DE PR", "BANCO POPULAR DE PUERTO RICO", "substantive"),
        # Blank → named is a first recording, not a transfer.
        (None, "SUCN MODESTO VALENTIN CRUZ", "first_recorded"),
        ("", "SUCN MODESTO VALENTIN CRUZ", "first_recorded"),
        ("   ", "ALGUIEN", "first_recorded"),
    ],
)
def test_classify_owner_change(previous, new, expected):
    assert monthly.classify_owner_change(previous, new) == expected


def test_every_class_has_a_label():
    for key in monthly.CHANGE_CLASSES:
        assert key in monthly.CHANGE_CLASS_LABEL


@pytest.mark.parametrize("previous,new", [
    ("CAMUY JOHN DOE", "JOHN DOE CAMUY"),
    ("JOHN DOE", "DOE JOHN"),
    ("john doe ponce", "PONCE JOHN DOE"),
])
def test_unknown_owner_sentinel_is_detected(previous, new):
    """Over a third of non-substantive owner changes are CRIM's placeholder
    being rewritten. The report says so rather than counting it as churn."""
    assert monthly._is_unknown_owner(previous, new)


def test_real_owners_are_not_flagged_as_the_sentinel():
    assert not monthly._is_unknown_owner("RAMOS PEREZ DAVID", "PEREZ RAMOS DAVID")


# ── Month parsing ───────────────────────────────────────────────────────────

def test_parse_month_accepts_string_date_and_none():
    assert monthly._parse_month("2026-07") == date(2026, 7, 1)
    assert monthly._parse_month(date(2026, 7, 23)) == date(2026, 7, 1)
    assert monthly._parse_month(None).day == 1


def test_parse_month_rejects_garbage():
    with pytest.raises(ValueError):
        monthly._parse_month("July 2026")


# ── Rendering (pure, from a fixture report) ─────────────────────────────────

def _empty_report() -> dict:
    return {
        "month": "2026-07",
        "month_label": "July 2026",
        "generated_at": "2026-07-26T00:00:00+00:00",
        "empty": True,
        "sections": {
            "parcel_ownership": {
                "key": "parcel_ownership", "title": "Parcel ownership",
                "source_tables": ["crim.parcel_deltas"], "available": False,
                "reason": "baseline month", "totals": {}, "by_municipio": [],
                "transfers": [], "sales": [], "notable_revaluations": [],
            },
            "corporate_status": {
                "key": "corporate_status", "title": "Corporate status",
                "source_tables": ["crim.rce_status_history"], "available": False,
                "reason": "not built", "transitions": [], "standing": {},
            },
            "contracts_added": {
                "key": "contracts_added", "title": "Government contracts added",
                "source_tables": ["ocpr.contracts"], "available": False,
                "reason": "no contracts", "totals": {}, "by_agency": [],
                "by_service_group": [], "largest": [],
            },
        },
    }


def test_empty_month_renders_honestly_instead_of_crashing():
    """A month with nothing in it is a real outcome, not an error — and it must
    not print fabricated zeros as if they were measurements."""
    html = monthly.render_html(_empty_report())
    assert "baseline month" in html
    assert "not built" in html
    assert "no contracts" in html
    assert html.startswith("<!doctype html>")
    assert monthly.render_csvs(_empty_report()) == {}


def test_html_is_self_contained():
    """No external stylesheet, script, font or image — it has to open and print
    standalone, off a USB stick, at an agency with no network."""
    html = monthly.render_html(_empty_report())
    for forbidden in ("<link", "<script", "src=\"http", "href=\"http", "@import"):
        assert forbidden not in html


def test_html_escapes_hostile_source_strings():
    """Owner and contractor names come from government registers, not from us."""
    report = _empty_report()
    sec = report["sections"]["parcel_ownership"]
    sec["available"] = True
    sec["from_month"] = "2026-06-01"
    sec["totals"] = {
        "owner_change": 1, "owner_change_substantive": 1,
        "sale": 0, "new_parcel": 0, "value_change": 0,
    }
    sec["transfer_classes"] = {"substantive": 1, "reordered": 0,
                               "formatting_only": 0, "first_recorded": 0}
    sec["by_municipio"] = [{
        "municipio": "<script>alert(1)</script>", "owner_changes": 1,
        "owner_changes_substantive": 1, "sales": 0, "new_parcels": 0,
        "revaluations": 0, "total": 1,
    }]
    html = monthly.render_html(report)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_bar_chart_is_inline_svg_and_empty_input_renders_nothing():
    assert monthly._bar_chart([]) == ""
    svg = monthly._bar_chart([("Ponce", 684), ("Camuy", 668)])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "Ponce" in svg and "684" in svg


def test_csv_round_trips():
    rows = [{"municipio": "Ponce", "n": 684}, {"municipio": "Camuy", "n": 668}]
    parsed = list(csv.DictReader(io.StringIO(monthly._csv(rows))))
    assert parsed == [{"municipio": "Ponce", "n": "684"}, {"municipio": "Camuy", "n": "668"}]


def test_money_and_int_formatting_never_fabricate():
    assert monthly._fmt_int(None) == "—"
    assert monthly._fmt_usd(None) == "—"
    assert monthly._fmt_int(7722) == "7,722"
    assert monthly._fmt_usd(1_805_322_262) == "$1.81B"


# ── Live shape (integration) ────────────────────────────────────────────────

@pytest.mark.integration
def test_build_against_live_db():
    from prism.load.db import get_engine

    report = monthly.build_monthly_report(get_engine(), "2026-07")
    assert set(report["sections"]) == {
        "parcel_ownership", "corporate_status", "contracts_added"
    }
    for section in report["sections"].values():
        # Every section states its provenance whether or not it has data.
        assert section["source_tables"]
        assert section["available"] or section["reason"]

    parcels = report["sections"]["parcel_ownership"]
    if parcels["available"]:
        t = parcels["totals"]
        # The headline must never exceed the raw count it is derived from.
        assert t["owner_change_substantive"] <= t["owner_change"]
        classes = parcels["transfer_classes"]
        # The four classes partition the raw count exactly. `sentinel_churn` is
        # a cross-cutting count over the non-substantive ones, not a fifth class,
        # so it is excluded from the partition check on purpose.
        partition = {k: v for k, v in classes.items() if k in monthly.CHANGE_CLASSES}
        assert sum(partition.values()) == t["owner_change"]
        assert classes["sentinel_churn"] <= (
            classes["reordered"] + classes["formatting_only"] + classes["first_recorded"]
        )
        assert (
            classes["substantive"] + classes["first_recorded"]
            == t["owner_change_substantive"]
        )
        # The per-municipio breakdown has to add up to the island figure.
        assert (
            sum(r["owner_changes_substantive"] for r in parcels["by_municipio"])
            == t["owner_change_substantive"]
        )


@pytest.mark.integration
def test_html_and_csvs_build_against_live_db():
    from prism.load.db import get_engine

    report = monthly.build_monthly_report(get_engine(), "2026-07")
    html = monthly.render_html(report)
    assert "PRISM" in html and report["month_label"] in html
    for name, body in monthly.render_csvs(report).items():
        assert name.endswith(".csv")
        assert body.count("\n") >= 1, f"{name} has a header but no rows"
