"""GSC Sync — Fetch Google Search Console data and store in SQLite.
Usage: python scripts/sync_gsc.py --live --days 7
       python scripts/sync_gsc.py --test
"""
import json, os, sys, datetime, sqlite3, argparse, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("gsc-sync")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"
CREDENTIALS = Path.home() / ".hermes" / "gsc-credentials.json"

def get_conn():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def load_domains(conn):
    rows = conn.execute("SELECT id, name, gsc_site_url FROM domains WHERE is_active=1 AND gsc_site_url IS NOT NULL").fetchall()
    return [dict(r) for r in rows]

def get_keyword_map(conn):
    rows = conn.execute("SELECT id, domain_id, keyword FROM keywords").fetchall()
    return [dict(r) for r in rows]

def check_today_sync(conn, source="gsc"):
    today = datetime.date.today().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT id FROM sync_log WHERE source=? AND status='success' AND date(started_at)=?",
        (source, today)
    ).fetchone()
    return row is not None

def run_sync(live=False, days=7, test=False, dry_run=False, force=False):
    conn = get_conn()
    domains = load_domains(conn)
    kw_map = get_keyword_map(conn)
    log.info(f"Loaded {len(domains)} domain(s) with GSC site URLs")

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days - 1)
    log.info(f"Date range: {start_date} to {end_date} ({days} days)")

    if not force and live and check_today_sync(conn):
        log.info("Data already exists for today. Use --force to re-sync. Skipping.")
        conn.close()
        return

    if test:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            creds = service_account.Credentials.from_service_account_file(
                str(CREDENTIALS), scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
            )
            service = build("searchconsole", "v1", credentials=creds)
            sites = service.sites().list().execute()
            for site in sites.get("siteEntry", []):
                log.info(f"  Site: {site['siteUrl']} (permission: {site['permissionLevel']})")
            log.info(f"Connection OK — {len(sites.get('siteEntry',[]))} site(s) found")
        except Exception as e:
            log.error(f"Test failed: {e}")
        conn.close()
        return

    if not live:
        log.info("Dry-run mode (no --live). Use --live to fetch real data.")
        conn.close()
        return

    # Mark sync start
    if not dry_run:
        curs = conn.execute("INSERT INTO sync_log(source, status, started_at) VALUES ('gsc', 'running', datetime('now'))")
        sync_id = curs.lastrowid
        conn.commit()
    else:
        sync_id = None

    total_rows = 0
    errors = []

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            str(CREDENTIALS), scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=creds)

        for domain in domains:
            site_url = domain["gsc_site_url"]
            log.info(f"Processing: {domain['name']} ({site_url})")

            domain_kws = [k for k in kw_map if k["domain_id"] == domain["id"]]
            domain_kw_texts = {k["keyword"].lower(): k["id"] for k in domain_kws}

            for d in range(days):
                date = (start_date + datetime.timedelta(days=d)).strftime("%Y-%m-%d")
                request = {
                    "startDate": date, "endDate": date,
                    "dimensions": ["query", "device"],
                    "rowLimit": 25000
                }
                try:
                    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
                    rows = response.get("rows", [])
                    domain_rows = 0
                    for row in rows:
                        query = row["keys"][0].strip().lower()
                        # Exact match first, then substring
                        kw_id = domain_kw_texts.get(query)
                        if kw_id is None:
                            for kw_text, kid in domain_kw_texts.items():
                                if kw_text in query or query in kw_text:
                                    kw_id = kid
                                    break
                        if kw_id is None:
                            continue
                        clicks = row.get("clicks", 0)
                        impressions = row.get("impressions", 0)
                        ctr = row.get("ctr", 0)
                        position = row.get("position", 0)
                        if not dry_run:
                            conn.execute(
                                "INSERT OR IGNORE INTO rank_history(keyword_id,date,position,clicks,impressions,ctr) VALUES(?,?,?,?,?,?)",
                                (kw_id, date, round(position, 1), clicks, impressions, round(ctr, 4))
                            )
                        domain_rows += 1
                    total_rows += domain_rows
                    log.info(f"  {date}: {domain_rows} rows")
                except Exception as e:
                    err = f"  {date}: {site_url} — {e}"
                    log.warning(err)
                    errors.append(err)

            conn.commit()
    except Exception as e:
        log.error(f"Sync failed: {e}")
        if not dry_run and sync_id:
            conn.execute("UPDATE sync_log SET status='failed', error=?, completed_at=datetime('now') WHERE id=?", (str(e), sync_id))
            conn.commit()
        conn.close()
        return

    if not dry_run and sync_id:
        conn.execute("UPDATE sync_log SET status='success', rows_synced=?, completed_at=datetime('now') WHERE id=?", (total_rows, sync_id))
        conn.commit()

    conn.close()
    log.info(f"Sync complete. Total rows: {total_rows}")
    if errors:
        log.warning(f"{len(errors)} error(s) during sync (partial failure)")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Sync GSC data to SEO dashboard DB")
    p.add_argument("--live", action="store_true", help="Fetch real GSC data")
    p.add_argument("--days", type=int, default=7, help="Days of data to sync (default 7)")
    p.add_argument("--test", action="store_true", help="Test GSC connection and exit")
    p.add_argument("--dry-run", action="store_true", help="Show what would be synced without writing")
    p.add_argument("--force", action="store_true", help="Skip daily sync guard (re-sync today)")
    args = p.parse_args()
    run_sync(live=args.live, days=args.days, test=args.test, dry_run=args.dry_run, force=args.force)
