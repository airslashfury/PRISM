"""Phase 9 — Sync CLI.

Usage:
    python -m prism.sync [--source wfs|osm|noaa] [--dry-run] [--drop]

Runs one full sync cycle: fetches WFS feature counts, compares checksums,
updates sync.data_sources for changed layers, logs to sync.sync_log, and
triggers a resilience re-score if any hazard layer was updated.
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PRISM Phase 9 — run one sync cycle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source", choices=["wfs", "osm", "noaa", "prepa", "luma"], default=None,
        help="Limit sync to one source type (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch checksums but do not write to DB",
    )
    parser.add_argument(
        "--drop", action="store_true",
        help="Drop sync schema and exit",
    )
    parser.add_argument(
        "--show-only", action="store_true",
        help="Print registered sources and last-sync status then exit",
    )
    args = parser.parse_args()

    from prism.load.db import get_engine
    from prism.sync.schema import create_schema, drop_schema
    from prism.sync.resync import SYNC_SOURCES, run_sync
    from prism.sync.trigger import should_trigger_rescore, trigger_rescore

    engine = get_engine()

    if args.drop:
        drop_schema(engine)
        print("sync schema dropped.")
        return

    create_schema(engine)

    if args.source == "prepa":
        from prism.sync.prepa_ops import sync_generation_status
        print("Fetching PREPA live generation feed ...")
        summary = sync_generation_status(engine, mirror=not args.dry_run)
        print(
            f"  plants: {summary['plants']}  matched: {summary['matched']}  "
            f"online: {summary['online']}\n"
            f"  island generation: {summary['system_mw']} MW  "
            f"spinning reserve: {summary.get('spinning_reserve_mw')} MW  "
            f"renewable: {summary.get('renewable_mw')} MW\n"
            f"  capacity history: {summary.get('capacity_history_rows', 0)} period rows\n"
            f"  history appended: {summary.get('snapshot_history_rows', 0)} island-wide + "
            f"{summary.get('plant_history_rows', 0)} per-plant rows  "
            f"as of {summary['as_of']}"
        )
        return

    if args.source == "luma":
        from prism.sync.luma_ops import sync_luma_outages
        print("Fetching LUMA delivery-side outage feed ...")
        summary = sync_luma_outages(engine, mirror=not args.dry_run)
        print(
            f"  regions: {summary['regions']}  "
            f"customers without service: {summary.get('total_without_service')}"
            f" ({summary.get('pct_without_service')}%)\n"
            f"  planned: {summary.get('total_planned_outage')}  "
            f"load-shed: {summary.get('total_load_shed')}  "
            f"history appended: {summary.get('history_rows', 0)} region rows"
        )
        return

    if args.show_only:
        from sqlalchemy import text
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT source_name, source_type, last_fetched_at, last_checksum, row_count, status
                FROM sync.data_sources
                ORDER BY source_name
            """)).fetchall()
        if not rows:
            print("No sources registered yet. Run python -m prism.sync to seed.")
        else:
            print(f"{'Source':<40} {'Type':<6} {'Last fetched':<22} {'Checksum':<18} {'Rows':>8} {'Status'}")
            print("-" * 110)
            for r in rows:
                fetched = str(r[2])[:19] if r[2] else "never"
                print(f"{r[0]:<40} {r[1]:<6} {fetched:<22} {str(r[3] or ''):<18} {(r[4] or 0):>8} {r[5]}")
        return

    # Compute filtered source count for an accurate banner
    active_sources = [s for s in SYNC_SOURCES if not args.source or s["source_type"] == args.source]
    if args.source and not active_sources:
        print(f"Warning: no sources of type '{args.source}' registered.", file=sys.stderr)
        return

    label = " (dry-run)" if args.dry_run else ""
    print(f"Running sync cycle{label} -- {len(active_sources)} source(s) ...")

    results = run_sync(engine, source_filter=args.source, dry_run=args.dry_run)

    # ── Summary ───────────────────────────────────────────────────────────────
    updated = [r for r in results if r.status == "updated"]
    skipped = [r for r in results if r.status == "skipped"]
    errors  = [r for r in results if r.status == "error"]

    print(f"\nSync complete -- {len(results)} source(s) checked")
    print(f"  updated : {len(updated)}")
    print(f"  skipped : {len(skipped)}")
    print(f"  errors  : {len(errors)}")

    for r in updated:
        tag = "(first fetch)" if r.old_checksum is None else f"{r.old_checksum} -> {r.new_checksum}"
        print(f"  + {r.source_name}: {r.rows_updated:,} features  [{tag}]  {r.duration_s:.1f}s")
    for r in skipped:
        print(f"  = {r.source_name}: unchanged  [{r.new_checksum}]  {r.duration_s:.1f}s")
    for r in errors:
        print(f"  ! {r.source_name}: {r.error_msg}", file=sys.stderr)

    # ── Rescore trigger ───────────────────────────────────────────────────────
    if not args.dry_run and should_trigger_rescore(results):
        from prism.sync.trigger import RESILIENCE_SOURCES
        from sqlalchemy import text as _text

        print("\nFlood/hazard layer updated -- triggering cat3 resilience re-score ...")
        try:
            trigger_rescore(engine, scenario="cat3")
            # Mark the triggering run(s) in sync_log
            triggered_names = [
                r.source_name for r in results
                if r.status == "updated" and r.source_name in RESILIENCE_SOURCES
            ]
            with engine.begin() as conn:
                conn.execute(_text("""
                    UPDATE sync.sync_log
                    SET triggered_rescore = true
                    WHERE source_name = ANY(:names)
                      AND run_at = (
                          SELECT MAX(run_at) FROM sync.sync_log sl2
                          WHERE sl2.source_name = sync_log.source_name
                      )
                """), {"names": triggered_names})
            print("Re-score complete. Check resilience.scenario_scores for updated rankings.")
        except Exception as exc:
            print(f"Re-score failed: {exc}", file=sys.stderr)
            sys.exit(1)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
