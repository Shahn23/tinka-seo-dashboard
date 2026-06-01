"""Content Idea Ingestion — import content idea backlog from CSV into the SEO dashboard DB.

Usage:
    python scripts/ingest_content.py --csv data/sample_content_ideas.csv
    python scripts/ingest_content.py --csv /path/to/ideas.csv --domain-name giantbubbles.co.nz
"""

import argparse, csv, json, logging, os, sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("content-ingest")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"
SCHEMA = BASE / "data" / "schema.sql"

VALID_EFFORT = ("easy", "medium", "hard")
VALID_STATUS = ("draft", "backlog", "published", "archived")


def get_conn():
    import sqlite3
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def load_csv(path: str) -> list[dict]:
    """Load content ideas from a CSV file."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_json(path: str) -> list[dict]:
    """Load content ideas from a JSON file (array or wrapped)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    for key in ("ideas", "items", "content", "results", "data"):
        if key in data and isinstance(data[key], list):
            return data[key]
    raise ValueError(f"Unexpected JSON structure. Expected an array or {'ideas': [...]}")


def normalize_row(row: dict) -> dict | None:
    """Normalize a single content idea row into the canonical schema."""
    keys_lower = {k.strip().lower().replace(" ", "_").replace("-", "_"): k for k in row}

    def pick(*candidates: str) -> str:
        for c in candidates:
            if c in keys_lower:
                return row[keys_lower[c]]
            if c in row:
                return row[c]
        return ""

    title = pick("title", "idea", "name", "headline", "topic")
    if not title:
        return None

    target_kw = pick("target_keyword", "keyword", "kw", "primary_keyword", "focus_keyword", "main_keyword")
    category = pick("category", "topic_category", "content_category", "section")
    estimated_searches = pick("estimated_searches", "search_volume", "volume", "monthly_volume", "searches")
    opportunity_score = pick("opportunity_score", "opportunity", "score", "priority_score", "priority")
    effort = pick("effort", "difficulty", "complexity", "time_estimate")
    content_type = pick("content_type", "type", "format", "content_format")
    outline = pick("outline", "notes", "description", "summary", "brief")
    source = pick("source", "origin", "suggestion_source", "method")
    status = pick("status", "state", "stage")

    # Type conversions
    try:
        estimated_searches = int(estimated_searches) if estimated_searches else 0
    except (ValueError, TypeError):
        estimated_searches = 0

    try:
        opportunity_score = float(opportunity_score) if opportunity_score else 5.0
    except (ValueError, TypeError):
        opportunity_score = 5.0

    # Clamp
    effort = effort.strip().lower() if effort else "medium"
    if effort not in VALID_EFFORT:
        effort = "medium"

    status = status.strip().lower() if status else "draft"
    if status not in VALID_STATUS:
        status = "draft"

    source = source.strip().lower().replace(" ", "_") if source else "manual"

    return {
        "title": title.strip(),
        "target_keyword": target_kw.strip() if target_kw else "",
        "category": category.strip() if category else "",
        "estimated_searches": estimated_searches,
        "opportunity_score": opportunity_score,
        "effort": effort,
        "content_type": content_type.strip() if content_type else "blog",
        "outline": outline.strip() if outline else "",
        "source": source,
        "status": status,
    }


def ingest(
    file_path: str,
    dry_run: bool = False,
    format: str | None = None,
) -> dict:
    """Main content idea ingestion logic. Returns summary dict."""
    file_path = str(Path(file_path).resolve())
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if format is None:
        ext = Path(file_path).suffix.lower()
        if ext == ".json":
            format = "json"
        elif ext == ".csv":
            format = "csv"
        else:
            raise ValueError(f"Cannot detect format from extension '{ext}'.")

    if format == "json":
        raw_rows = load_json(file_path)
    else:
        raw_rows = load_csv(file_path)

    if not raw_rows:
        return {"imported": 0, "updated": 0, "skipped": 0, "warnings": ["No data found in file"]}

    conn = get_conn()
    imported = 0
    updated = 0
    skipped = 0
    warnings = []

    for row in raw_rows:
        normalized = normalize_row(row)
        if normalized is None:
            skipped += 1
            continue

        if dry_run:
            log.info(f"  [dry-run] WOULD import: {normalized['title'][:60]}")
            continue

        # Check if a content idea with this title already exists
        existing = conn.execute(
            "SELECT id FROM content_ideas WHERE title=?",
            (normalized["title"],),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE content_ideas SET
                   target_keyword=?, category=?, estimated_searches=?,
                   opportunity_score=?, effort=?, content_type=?, outline=?,
                   source=?, status=?
                   WHERE id=?""",
                (
                    normalized["target_keyword"],
                    normalized["category"],
                    normalized["estimated_searches"],
                    normalized["opportunity_score"],
                    normalized["effort"],
                    normalized["content_type"],
                    normalized["outline"],
                    normalized["source"],
                    normalized["status"],
                    existing["id"],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO content_ideas
                   (title, target_keyword, category, estimated_searches, opportunity_score,
                    effort, content_type, outline, source, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    normalized["title"],
                    normalized["target_keyword"],
                    normalized["category"],
                    normalized["estimated_searches"],
                    normalized["opportunity_score"],
                    normalized["effort"],
                    normalized["content_type"],
                    normalized["outline"],
                    normalized["source"],
                    normalized["status"],
                ),
            )
            imported += 1

    conn.commit()
    conn.close()

    log.info(f"Content ideas: {imported} new, {updated} updated, {skipped} skipped")
    if warnings:
        for w in warnings:
            log.warning(w)

    return {"imported": imported, "updated": updated, "skipped": skipped, "warnings": warnings}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest content ideas into SEO dashboard DB")
    p.add_argument("--csv", metavar="FILE", help="CSV file with content ideas")
    p.add_argument("--json", metavar="FILE", help="JSON file with content ideas")
    p.add_argument("--dry-run", action="store_true", help="Validate without importing")
    args = p.parse_args()

    if not args.csv and not args.json:
        p.error("Specify at least one of --csv or --json")

    result = ingest(
        file_path=args.csv or args.json,
        dry_run=args.dry_run,
        format="csv" if args.csv else "json",
    )
    print(f"\nResult: {result['imported']} new, {result['updated']} updated, {result['skipped']} skipped")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"  ⚠ {w}")
