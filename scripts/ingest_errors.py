"""On-Page Error Ingestion — import error data from JSON/CSV into the SEO dashboard DB.

Usage:
    python scripts/ingest_errors.py --json data/sample_onpage_errors.json
    python scripts/ingest_errors.py --csv data/sample_onpage_errors.csv
    python scripts/ingest_errors.py --json path/to/file.json --domain-id 1
"""

import argparse, csv, json, logging, os, sys, uuid
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("error-ingest")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"
SCHEMA = BASE / "data" / "schema.sql"

# Canonical error types with descriptions
ERROR_TYPE_META = {
    "broken_link": "Page returns 4xx/5xx status",
    "missing_title": "Page has no <title> tag",
    "missing_meta": "Missing or empty meta description",
    "duplicate_title": "Duplicate or near-duplicate title tags",
    "duplicate_meta": "Duplicate or near-duplicate meta descriptions",
    "duplicate_content": "Duplicate content across pages/domains",
    "missing_hreflang": "Missing hreflang tags for multi-region",
    "stale_content": "Content not updated in 6+ months",
    "page_speed": "Slow page load speed",
    "alt_text": "Missing alt text on images",
    "missing_schema": "Missing structured data (Schema.org)",
    "thin_content": "Page has very little content",
    "missing_gmb": "No Google My Business listing found",
    "schema_url_mismatch": "Schema URLs point to wrong domain",
    "ssl_issues": "SSL certificate or mixed content issues",
    "mobile_usability": "Mobile usability problems",
    "redirect_chain": "Excessive redirects or redirect chains",
    "crawl_blocked": "Page blocked by robots.txt or noindex",
    "orphan_page": "Page has no internal links",
    "canonical_issues": "Canonical tag missing or misconfigured",
}

ERROR_TYPE_ALIASES = {
    "404": "broken_link", "4xx": "broken_link", "5xx": "broken_link",
    "dead_link": "broken_link", "link_rot": "broken_link",
    "no_title": "missing_title", "title_missing": "missing_title",
    "no_meta": "missing_meta", "meta_missing": "missing_meta",
    "missing_description": "missing_meta",
    "dup_title": "duplicate_title",
    "dup_meta": "duplicate_meta",
    "dup_content": "duplicate_content",
    "hreflang": "missing_hreflang",
    "old_content": "stale_content",
    "speed": "page_speed", "load_speed": "page_speed", "lcp": "page_speed",
    "img_alt": "alt_text", "image_alt": "alt_text",
    "schema": "missing_schema", "structured_data": "missing_schema",
    "gmb": "missing_gmb",
    "mobile": "mobile_usability",
    "redirect": "redirect_chain",
    "canonical": "canonical_issues",
}

SEVERITY_ALIASES = {
    "blocker": "critical", "emergency": "critical", "p0": "critical",
    "high": "high", "p1": "high",
    "medium": "moderate", "moderate": "moderate", "warning": "moderate", "p2": "moderate",
    "low": "low", "info": "low", "trivial": "low", "p3": "low", "p4": "low",
}


def normalize_error_type(raw: str) -> str:
    """Map aliases to canonical error types."""
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return ERROR_TYPE_ALIASES.get(key, key)


def normalize_severity(raw: str) -> str:
    """Map aliases to canonical severity levels."""
    key = raw.strip().lower()
    return SEVERITY_ALIASES.get(key, key)


def get_conn():
    """Get a SQLite connection with row factory and WAL mode."""
    import sqlite3
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_domain(conn, domain_id: int | None, domain_name: str | None) -> int:
    """Resolve domain_id from an explicit id, domain name, or auto-detect if only one domain exists."""
    if domain_id:
        row = conn.execute("SELECT id FROM domains WHERE id=?", (domain_id,)).fetchone()
        if row:
            return row["id"]
        raise ValueError(f"Domain id {domain_id} does not exist in database")

    if domain_name:
        row = conn.execute(
            "SELECT id FROM domains WHERE name=? OR display_name=?",
            (domain_name, domain_name),
        ).fetchone()
        if row:
            return row["id"]
        raise ValueError(f"Domain '{domain_name}' not found — available: ...")

    # Auto-detect if only one active domain
    rows = conn.execute("SELECT id, name FROM domains WHERE is_active=1").fetchall()
    if len(rows) == 1:
        log.info(f"Auto-detected domain: {rows[0]['name']} (id={rows[0]['id']})")
        return rows[0]["id"]
    if len(rows) == 0:
        raise ValueError("No active domains found in database. Run scripts/init_db.py first.")

    names = ", ".join(f"'{r['name']}' (id={r['id']})" for r in rows)
    raise ValueError(
        f"Multiple active domains found ({names}). "
        "Specify --domain-id or --domain-name to choose."
    )


def load_json(path: str) -> list[dict]:
    """Load errors from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Try common wrappers
        for key in ("errors", "items", "results", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError(f"Unexpected JSON structure: {type(data)}")


def load_csv(path: str) -> list[dict]:
    """Load errors from a CSV file with flexible column mapping."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def normalize_row(row: dict) -> dict:
    """Normalize a single error row into the canonical schema."""
    keys_lower = {k.strip().lower().replace(" ", "_").replace("-", "_"): k for k in row}

    def pick(*candidates: str) -> str:
        for c in candidates:
            if c in keys_lower:
                return row[keys_lower[c]]
            # Try exact match
            if c in row:
                return row[c]
        return ""

    url = pick("url", "page_url", "page", "pageurl", "link")
    error_type_raw = pick("error_type", "error", "type", "issue", "issue_type")
    error_type = normalize_error_type(error_type_raw) if error_type_raw else "unknown"
    severity_raw = pick("severity", "priority", "level", "importance")
    severity = normalize_severity(severity_raw) if severity_raw else "moderate"
    description = pick("description", "detail", "details", "message", "note", "title")
    suggestion = pick("suggestion", "fix", "resolution", "recommendation", "advice")

    if not url:
        log.warning(f"Skipping row with no URL: {row}")
        return None

    return {
        "url": url.strip(),
        "error_type": error_type,
        "severity": severity if severity in ("critical", "high", "moderate", "low") else "moderate",
        "description": description,
        "suggestion": suggestion,
    }


def ingest(
    file_path: str,
    domain_id: int | None = None,
    domain_name: str | None = None,
    batch_id: str | None = None,
    close_previous: bool = True,
    dry_run: bool = False,
    format: str | None = None,  # auto-detect if None
) -> dict:
    """Main ingestion logic. Returns summary dict."""
    file_path = str(Path(file_path).resolve())
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Detect format from extension if not specified
    if format is None:
        ext = Path(file_path).suffix.lower()
        if ext == ".json":
            format = "json"
        elif ext == ".csv":
            format = "csv"
        else:
            raise ValueError(f"Cannot detect format from extension '{ext}'. Specify --json or --csv.")

    # Load data
    if format == "json":
        raw_rows = load_json(file_path)
    else:
        raw_rows = load_csv(file_path)

    if not raw_rows:
        return {"imported": 0, "skipped": 0, "warnings": ["No data found in file"]}

    conn = get_conn()
    domain_id = ensure_domain(conn, domain_id, domain_name)
    batch = batch_id or f"ingest-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    imported = 0
    skipped = 0
    warnings = []

    for row in raw_rows:
        normalized = normalize_row(row)
        if normalized is None:
            skipped += 1
            continue

        if dry_run:
            log.info(f"  [dry-run] WOULD import: {normalized['url']} ({normalized['error_type']})")
            continue

        conn.execute(
            """INSERT OR IGNORE INTO onpage_errors
               (domain_id, error_type, severity, page_url, description, suggestion, status, batch_id)
               VALUES (?, ?, ?, ?, ?, ?, 'open', ?)""",
            (
                domain_id,
                normalized["error_type"],
                normalized["severity"],
                normalized["url"],
                normalized["description"],
                normalized["suggestion"],
                batch,
            ),
        )
        imported += 1

    # Close errors from previous batches that aren't in this one.
    # Matches NULL batch_ids too (from old seeds or unbatched imports).
    if close_previous and not dry_run and imported > 0:
        conn.execute(
            """UPDATE onpage_errors SET status='fixed', fixed_at=datetime('now')
               WHERE domain_id=? AND (batch_id IS NULL OR batch_id != ?) AND status='open'""",
            (domain_id, batch),
        )
        closed = conn.cursor().rowcount
        if closed and closed > 0:
            log.info(f"  Closed {closed} old errors from previous batches")

    conn.commit()
    conn.close()

    log.info(f"Imported {imported} on-page errors (batch: {batch})")
    if skipped:
        log.warning(f"Skipped {skipped} invalid rows")
    if warnings:
        for w in warnings:
            log.warning(w)

    return {"imported": imported, "skipped": skipped, "batch": batch, "warnings": warnings}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest on-page errors into SEO dashboard DB")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", metavar="FILE", help="JSON file with error data")
    group.add_argument("--csv", metavar="FILE", help="CSV file with error data")
    p.add_argument("--domain-id", type=int, help="Domain database id")
    p.add_argument("--domain-name", help="Domain name (looked up in DB)")
    p.add_argument("--batch-id", help="Optional batch identifier")
    p.add_argument("--no-close", action="store_true", help="Don't auto-close previous batch errors")
    p.add_argument("--dry-run", action="store_true", help="Validate without importing")
    args = p.parse_args()

    result = ingest(
        file_path=args.json or args.csv,
        domain_id=args.domain_id,
        domain_name=args.domain_name,
        batch_id=args.batch_id or f"manual-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        close_previous=not args.no_close,
        dry_run=args.dry_run,
        format="json" if args.json else "csv",
    )
    print(f"\nResult: {result['imported']} imported, {result['skipped']} skipped, batch={result['batch']}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"  ⚠ {w}")
