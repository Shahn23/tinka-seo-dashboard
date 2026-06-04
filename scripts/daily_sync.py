#!/usr/bin/env python3
"""Daily SEO Data Sync - orchestrates all 3 ingestion modules.

Runs GSC rankings sync, on-page error ingestion, and content idea
import in sequence. Logs to sync_log table and stdout.

Usage:
    python scripts/daily_sync.py --live          # Full sync with live GSC data
    python scripts/daily_sync.py --live --days 1 # Single-day GSC sync
    python scripts/daily_sync.py --dry-run       # Validate without writing
    python scripts/daily_sync.py --gsc-only      # Skip errors + content
"""

import argparse, logging, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("daily-sync")

BASE = Path(__file__).resolve().parent.parent
SCRIPTS = BASE / "scripts"
DB = BASE / "data" / "seo_dashboard.db"


# ── helpers ─────────────────────────────────────────────────────────────────


def get_conn():
    import sqlite3
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def log_sync_start(source: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO sync_log(source, status, started_at) VALUES (?, 'running', datetime('now'))",
        (source,),
    )
    sync_id = cur.lastrowid
    conn.commit()
    conn.close()
    return sync_id


def log_sync_end(sync_id: int, status: str, rows: int = 0, error: str = ""):
    conn = get_conn()
    conn.execute(
        "UPDATE sync_log SET status=?, rows_synced=?, completed_at=datetime('now'), error=? WHERE id=?",
        (status, rows, error or None, sync_id),
    )
    conn.commit()
    conn.close()


def check_today_sync(source: str) -> bool:
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT id FROM sync_log WHERE source=? AND status='success' AND date(started_at)=?",
        (source, today),
    ).fetchone()
    conn.close()
    return row is not None


def get_domains() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, display_name FROM domains WHERE is_active=1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_data_file(*names: str) -> str | None:
    """Look for a data file in the data/ directory by candidate names."""
    for name in names:
        path = BASE / "data" / name
        if path.exists():
            return str(path)
    return None


def run_subprocess(cmd: list[str], timeout: int = 120, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    """Run a subprocess and return the result."""
    return subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(cwd or BASE), timeout=timeout,
    )


# ── module runners ───────────────────────────────────────────────────────────


def run_gsc_sync(live: bool, days: int = 7, force: bool = False) -> dict:
    """Run the GSC rankings sync module."""
    log.info("=" * 40)
    log.info("GSC Rankings Sync")
    log.info("=" * 40)

    if not force and live and check_today_sync("gsc"):
        log.info("GSC already synced today. Use --force to re-sync.")
        return {"source": "gsc", "status": "skipped", "rows": 0}

    sync_id = log_sync_start("gsc")
    script = str(SCRIPTS / "sync_gsc.py")
    cmd = [sys.executable, script]
    if live:
        cmd.extend(["--live", "--days", str(days)])
        if force:
            cmd.append("--force")

    start = time.time()
    try:
        result = run_subprocess(cmd, timeout=300)
        elapsed = time.time() - start
        log.info(f"GSC sync completed in {elapsed:.1f}s (exit={result.returncode})")

        if result.returncode == 0:
            # Parse row count from output
            rows = 0
            for line in result.stdout.splitlines():
                m = re.search(r"Total rows[:\s]*(\d+)", line)
                if m:
                    rows = int(m.group(1))
            log_sync_end(sync_id, "success", rows)
            log.info(f"  ✅ GSC: {rows} rows synced")
            return {"source": "gsc", "status": "success", "rows": rows}
        else:
            err = (result.stderr[:500] or result.stdout[-500:]).strip()
            log_sync_end(sync_id, "failed", 0, err)
            log.error(f"  ❌ GSC sync failed: {err[:200]}")
            return {"source": "gsc", "status": "failed", "rows": 0, "error": err}

    except subprocess.TimeoutExpired:
        log_sync_end(sync_id, "failed", 0, "Timeout (300s)")
        return {"source": "gsc", "status": "failed", "rows": 0, "error": "Timeout"}

    except Exception as e:
        log_sync_end(sync_id, "failed", 0, str(e))
        return {"source": "gsc", "status": "failed", "rows": 0, "error": str(e)}


def run_error_ingest(dry_run: bool = False, force: bool = False) -> dict:
    """Run on-page error ingestion for each active domain."""
    log.info("=" * 40)
    log.info("On-Page Error Ingestion")
    log.info("=" * 40)

    if not force and check_today_sync("errors"):
        log.info("Error ingestion already ran today. Use --force to re-run.")
        return {"source": "errors", "status": "skipped", "rows": 0}

    source_file = find_data_file(
        "sample_onpage_errors.json", "errors.json", "onpage_errors.json"
    )
    if source_file:
        log.info(f"Found combined error file: {source_file}")

    sync_id = log_sync_start("errors")
    script = str(SCRIPTS / "ingest_errors.py")
    domains = get_domains()
    total = 0
    errors = []

    for domain in domains:
        # Use domain-specific file if it exists, otherwise use combined file
        domain_file = find_data_file(f"errors_{domain['name'].split('.')[0]}.json", f"errors_{domain['name']}.json")
        file_to_use = domain_file or source_file
        if not file_to_use:
            log.warning(f"No error data file for {domain['name']} - skipping")
            continue

        cmd = [sys.executable, script, "--json", file_to_use, "--domain-id", str(domain["id"])]
        if dry_run:
            cmd.append("--dry-run")

        try:
            result = run_subprocess(cmd, timeout=120)
            if result.returncode == 0:
                # Parse imported count
                imported = 0
                for line in result.stdout.splitlines():
                    m = re.search(r"imported[: ]+(\d+)", line)
                    if m:
                        imported = int(m.group(1))
                total += imported
                log.info(f"  ✅ {domain['name']}: {imported} errors imported")
            else:
                err = (result.stderr[:300] or result.stdout[-300:]).strip()
                errors.append(f"{domain['name']}: {err}")
                log.error(f"  ❌ {domain['name']}: {err[:100]}")
        except Exception as e:
            errors.append(f"{domain['name']}: {e}")
            log.error(f"  ❌ {domain['name']}: {e}")

    if errors:
        log_sync_end(sync_id, "failed", total, "; ".join(errors))
        return {"source": "errors", "status": "failed", "rows": total, "errors": errors}
    else:
        log_sync_end(sync_id, "success", total)
        log.info(f"  ✅ Errors total: {total} imported across {len(domains)} domains")
        return {"source": "errors", "status": "success", "rows": total}


def run_content_ingest(dry_run: bool = False, force: bool = False) -> dict:
    """Run content idea ingestion."""
    log.info("=" * 40)
    log.info("Content Idea Ingestion")
    log.info("=" * 40)

    if not force and check_today_sync("content"):
        log.info("Content ingestion already ran today. Use --force to re-run.")
        return {"source": "content", "status": "skipped", "rows": 0}

    source_file = find_data_file(
        "sample_content_ideas.csv", "content_ideas.csv", "backlog.csv", "sample_backlog.csv"
    )
    if not source_file:
        log.warning("No content idea data file found - skipping")
        return {"source": "content", "status": "skipped_no_data", "rows": 0}

    sync_id = log_sync_start("content")
    script = str(SCRIPTS / "ingest_content.py")
    cmd = [sys.executable, script, "--csv", source_file]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = run_subprocess(cmd, timeout=120)
        if result.returncode == 0:
            imported = 0
            updated = 0
            for line in result.stdout.splitlines():
                m = re.search(r"(\d+) new", line)
                if m:
                    imported = int(m.group(1))
                m = re.search(r"(\d+) updated", line)
                if m:
                    updated = int(m.group(1))
            total = imported + updated
            log_sync_end(sync_id, "success", total)
            log.info(f"  ✅ Content: {imported} new, {updated} updated")
            return {"source": "content", "status": "success", "rows": total, "new": imported, "updated": updated}
        else:
            err = (result.stderr[:500] or result.stdout[-500:]).strip()
            log_sync_end(sync_id, "failed", 0, err)
            log.error(f"  ❌ Content: {err[:200]}")
            return {"source": "content", "status": "failed", "rows": 0, "error": err}
    except Exception as e:
        log_sync_end(sync_id, "failed", 0, str(e))
        return {"source": "content", "status": "failed", "rows": 0, "error": str(e)}


def run_rank_report() -> dict:
    """Run the rank tracker and produce a summary."""
    from datetime import date
    log.info("=" * 40)
    log.info("Rank Tracker Report")
    log.info("=" * 40)

    import sqlite3
    from pathlib import Path
    BASE = Path(__file__).resolve().parent.parent

    # Get counts directly
    conn = sqlite3.connect(str(BASE / "data" / "seo_dashboard.db"))
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]
    ranked = conn.execute("""
        SELECT COUNT(DISTINCT k.id) as c FROM keywords k
        JOIN rank_history rh ON k.id = rh.keyword_id
    """).fetchone()["c"]
    avg_pos = conn.execute("""
        SELECT AVG(position) FROM rank_history
        WHERE (keyword_id, date) IN (
            SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
        )
    """).fetchone()[0]

    # Rising / falling counts
    today_latest = conn.execute("""
        SELECT keyword_id, position FROM rank_history rh1
        WHERE id = (SELECT MAX(id) FROM rank_history rh2 WHERE rh2.keyword_id = rh1.keyword_id)
    """).fetchall()
    today_map = {r["keyword_id"]: r["position"] for r in today_latest}

    week_ago = (date.today() - __import__("datetime").timedelta(days=7)).isoformat()
    past_rows = conn.execute("""
        SELECT keyword_id, position FROM rank_history
        WHERE date = ?
    """, (week_ago,)).fetchall()
    past_map = {r["keyword_id"]: r["position"] for r in past_rows}

    rising = falling = stable = 0
    for kw_id, t_pos in today_map.items():
        p_pos = past_map.get(kw_id)
        if p_pos is None:
            continue
        diff = p_pos - t_pos
        if diff > 0.5:
            rising += 1
        elif diff < -0.5:
            falling += 1
        else:
            stable += 1

    new_entrants = sum(1 for kw_id in today_map if kw_id not in past_map)
    conn.close()

    unranked = total - ranked
    log.info(f"Keywords: {total} total, {ranked} ranked ({ranked/total*100:.0f}%), {unranked} unranked")
    log.info(f"Avg position: {avg_pos:.1f}")
    log.info(f"7-day change: {rising} ↑, {falling} ↓, {stable} -, {new_entrants} new")
    log.info("Rank Tracker Report - complete")

    return {"source": "rank_tracker", "status": "success",
            "rows": total, "metadata": f"{ranked}/{total} ranked, avg {avg_pos:.1f}, {rising}↑/{falling}↓"}


# ── main ─────────────────────────────────────────────────────────────────────


def run_all(live: bool, days: int, dry_run: bool, force: bool, gsc_only: bool):
    """Run all three ingestion modules and report results."""
    log.info("=" * 55)
    log.info(f"  DAILY SYNC - {'LIVE' if live else 'DRY-RUN'}" +
             (" (FORCE)" if force else "") +
             (" (GSC ONLY)" if gsc_only else ""))
    log.info(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    results = []

    # 1. GSC Rankings
    r1 = run_gsc_sync(live=live, days=days, force=force)
    results.append(r1)

    # 2. Rank Tracker Report
    r_report = run_rank_report()
    results.append(r_report)

    if not gsc_only:
        # 3. On-Page Errors
        r2 = run_error_ingest(dry_run=dry_run, force=force)
        results.append(r2)

        # 4. Content Ideas
        r3 = run_content_ingest(dry_run=dry_run, force=force)
        results.append(r3)

    # Summary
    log.info("=" * 55)
    log.info("  SYNC SUMMARY")
    log.info("=" * 55)
    all_ok = True
    for r in results:
        icon = "✅" if r["status"] == "success" else "⏭" if r["status"].startswith("skip") else "❌"
        msg = f"  {icon} {r['source']}: {r['status']}"
        if "rows" in r and r.get("rows"):
            msg += f" ({r['rows']} rows)"
        log.info(msg)
        if r["status"] == "failed":
            all_ok = False
    log.info("=" * 55)
    if all_ok:
        log.info("  ✅ Daily sync completed successfully")
    else:
        log.warning("  ⚠ Daily sync finished with some failures")
    log.info("=" * 55)

    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Daily SEO data sync orchestrator")
    p.add_argument("--live", action="store_true", help="Fetch live GSC data")
    p.add_argument("--days", type=int, default=7, help="Days of GSC data to sync (default 7)")
    p.add_argument("--dry-run", action="store_true", help="Validate error/content ingestion without importing")
    p.add_argument("--force", action="store_true", help="Re-sync even if already completed today")
    p.add_argument("--gsc-only", action="store_true", help="Only sync GSC, skip errors and content")
    args = p.parse_args()

    run_all(
        live=args.live,
        days=args.days,
        dry_run=args.dry_run,
        force=args.force,
        gsc_only=args.gsc_only,
    )
