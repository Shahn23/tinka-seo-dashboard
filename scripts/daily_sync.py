#!/usr/bin/env python3
"""
Daily sync runner for the SEO Dashboard.
Runs all three ingestion tasks: GSC, on-page errors, and content backlog.

Usage:
    python scripts/daily_sync.py              # Run all syncs
    python scripts/daily_sync.py --gsc-only   # Only GSC
    python scripts/daily_sync.py --dry-run    # Print what would be done
    python scripts/daily_sync.py --live       # Use live GSC API
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.database import Database
from src.gsc_client import GSCClient


def run_daily_sync(
    live: bool = False,
    dry_run: bool = False,
    gsc_only: bool = False,
) -> dict[str, Any]:
    """Run daily data sync for all ingestion modules."""

    db_path = os.path.join(BASE_DIR, "data", "seo_dashboard.db")
    schema_path = os.path.join(BASE_DIR, "data", "schema.sql")
    db = Database(db_path, schema_path)

    results: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "gsc": {"status": "skipped", "records": 0},
        "onpage": {"status": "skipped", "errors": 0},
        "backlog": {"status": "skipped", "ideas": 0},
    }

    # ── 1. GSC Sync ────────────────────────────────────────────────────
    if not gsc_only:
        gsc = GSCClient()
        domains = db.list_domains()

        if live and not gsc.is_live_available():
            print("[sync] ⚠ Live GSC requested but service account not configured. Falling back to mock.")
            live = False

        if db.check_already_synced_today("gsc") and not dry_run:
            print("[sync] ✅ GSC already synced today. Use --force to re-sync.")
            results["gsc"]["status"] = "already_synced"
        else:
            if dry_run:
                print(f"[sync] 📋 [DRY-RUN] Would sync GSC for {len(domains)} domains (live={live})")
                results["gsc"]["status"] = "dry_run"
            else:
                sync_id = db.start_sync("gsc")
                try:
                    total_records = 0
                    for d in domains:
                        site_url = f"sc-domain:{d.url}"
                        print(f"[sync] 🔍 Fetching GSC data for {d.url}...")
                        gsc_results = gsc.fetch_rankings(site_url, days=1, live=live)
                        kw_records = gsc.records_for_db(gsc_results, d.id)
                        for kw_text, records in kw_records.items():
                            db.upsert_ranks_batch(records)
                            total_records += len(records)
                        print(f"[sync]   → {len(gsc_results)} rows from API, {len(kw_records)} keywords matched")

                    db.complete_sync(sync_id, rows_processed=total_records)
                    results["gsc"] = {"status": "completed", "records": total_records}
                    print(f"[sync] ✅ GSC sync complete: {total_records} records")
                except Exception as e:
                    db.complete_sync(sync_id, error=str(e))
                    results["gsc"] = {"status": "failed", "error": str(e)}
                    print(f"[sync] ❌ GSC sync failed: {e}")

    # ── 2. On-Page Error Ingestion ─────────────────────────────────────
    if not dry_run:
        json_path = os.path.join(BASE_DIR, "data", "sample_onpage_errors.json")
        if os.path.exists(json_path):
            try:
                from src.onpage_ingestion import OnPageIngestion
                ing = OnPageIngestion(db_path, schema_path)
                domains = db.list_domains()
                total_errors = 0
                for d in domains:
                    batch_id = f"daily-{datetime.now().strftime('%Y%m%d')}"
                    result = ing.ingest_json(json_path, domain_id=d.id, batch_id=batch_id, close_previous=False)
                    total_errors += result["imported"]
                    print(f"[sync] 🔧 Ingested {result['imported']} on-page errors for {d.label}")
                results["onpage"] = {"status": "completed", "errors": total_errors}
            except ImportError:
                print("[sync] ⚠ On-page ingestion module not available")
                results["onpage"]["status"] = "unavailable"
            except Exception as e:
                print(f"[sync] ❌ On-page ingestion failed: {e}")
                results["onpage"] = {"status": "failed", "error": str(e)}

    # ── 3. Backlog Import ──────────────────────────────────────────────
    if not dry_run:
        csv_path = os.path.join(BASE_DIR, "data", "sample_backlog.csv")
        if os.path.exists(csv_path):
            try:
                from src.backlog_importer import BacklogImporter
                importer = BacklogImporter(db_path, schema_path)
                result = importer.import_csv(csv_path)
                results["backlog"] = {"status": "completed", "ideas": result.get("imported", 0)}
                print(f"[sync] 📄 Imported {result.get('imported', 0)} backlog ideas")
            except ImportError:
                print("[sync] ⚠ Backlog importer not available")
                results["backlog"]["status"] = "unavailable"
            except Exception as e:
                print(f"[sync] ❌ Backlog import failed: {e}")
                results["backlog"] = {"status": "failed", "error": str(e)}

    print(f"\n[sync] ✅ Daily sync complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run daily SEO dashboard sync")
    parser.add_argument("--gsc-only", action="store_true", help="Only run GSC sync")
    parser.add_argument("--dry-run", action="store_true", help="Preview without running")
    parser.add_argument("--live", action="store_true", help="Use live GSC API")
    args = parser.parse_args()
    run_daily_sync(live=args.live, dry_run=args.dry_run, gsc_only=args.gsc_only)
