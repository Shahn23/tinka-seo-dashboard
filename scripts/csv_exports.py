#!/usr/bin/env python3
"""CSV Export Endpoints for Tinka SEO Dashboard.

FastAPI routes and standalone CLI for exporting dashboard data as CSV.
Three exports:
  - keywords.csv       → All keywords with domain, rank, volume, difficulty
  - rank_history.csv   → Daily rank positions with clicks/impressions per keyword
  - content_ideas.csv  → All content ideas with scores, effort, keyword target

Usage (API, mounted on the existing FastAPI app in api/index.py):
    from scripts.csv_exports import csv_router
    app.include_router(csv_router)

Usage (CLI):
    python scripts/csv_exports.py keywords          # Print keywords.csv to stdout
    python scripts/csv_exports.py rank-history      # Print rank_history.csv to stdout
    python scripts/csv_exports.py content-ideas     # Print content_ideas.csv to stdout
    python scripts/csv_exports.py --all             # Print all three, separated by headers
"""

import argparse
import csv
import io
import os
import sqlite3
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
# Same pattern used by other scripts (alerts.py, weekly_digest.py, etc.)
BASE = Path(__file__).resolve().parent.parent
DATA_DB = BASE / "data" / "seo_dashboard.db"
API_DB = BASE / "api" / "seo_dashboard.db"
TMP_DB = Path("/tmp") / "seo_dashboard.db"


def get_conn() -> sqlite3.Connection:
    """Return a connection to the best available DB copy."""
    candidates = [DATA_DB, API_DB, TMP_DB]
    for p in candidates:
        if p.exists():
            conn = sqlite3.connect(str(p))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=OFF")
            return conn
    raise FileNotFoundError(
        f"No database found at any of: {', '.join(str(c) for c in candidates)}"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch(sql: str, params=()) -> list[dict]:
    """Run a read query and return rows as dicts."""
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def rows_to_csv(rows: list[dict]) -> str:
    """Convert a list of dicts into a CSV string."""
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ── Queries ───────────────────────────────────────────────────────────────────

def export_keywords() -> list[dict]:
    """Export all keywords with domain name and latest rank info."""
    return fetch("""
        SELECT
            k.id,
            d.name AS domain,
            d.display_name AS domain_display,
            k.keyword,
            k.category,
            k.intent,
            k.volume,
            k.opportunity_score,
            k.difficulty,
            k.is_high_priority,
            rh.position AS current_position,
            rh.clicks AS last_7d_clicks,
            rh.impressions AS last_7d_impressions,
            rh.date AS last_rank_update,
            k.created_at
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN (
            SELECT keyword_id, position, clicks, impressions, date
            FROM rank_history
            WHERE (keyword_id, date) IN (
                SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id
            )
        ) rh ON k.id = rh.keyword_id
        ORDER BY d.name, k.keyword
    """)


def export_rank_history() -> list[dict]:
    """Export all rank history rows with keyword and domain names."""
    return fetch("""
        SELECT
            rh.id,
            rh.date,
            d.name AS domain,
            d.display_name AS domain_display,
            k.keyword,
            k.category,
            k.intent,
            rh.position,
            rh.clicks,
            rh.impressions,
            rh.ctr
        FROM rank_history rh
        JOIN keywords k ON rh.keyword_id = k.id
        JOIN domains d ON k.domain_id = d.id
        ORDER BY d.name, k.keyword, rh.date DESC
    """)


def export_content_ideas() -> list[dict]:
    """Export all content ideas."""
    return fetch("""
        SELECT
            id,
            title,
            target_keyword,
            category,
            estimated_searches,
            opportunity_score,
            effort,
            content_type,
            outline,
            source,
            status,
            created_at
        FROM content_ideas
        ORDER BY status, opportunity_score DESC
    """)


# ── FastAPI Router ────────────────────────────────────────────────────────────

try:
    from fastapi import APIRouter
    from fastapi.responses import StreamingResponse

    csv_router = APIRouter(prefix="/api/export", tags=["csv-exports"])

    @csv_router.get("/keywords.csv")
    async def get_keywords_csv():
        """Export keywords as CSV."""
        rows = export_keywords()
        csv_content = rows_to_csv(rows)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=keywords.csv",
                "Content-Type": "text/csv; charset=utf-8",
            },
        )

    @csv_router.get("/rank-history.csv")
    async def get_rank_history_csv():
        """Export rank history as CSV."""
        rows = export_rank_history()
        csv_content = rows_to_csv(rows)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=rank_history.csv",
                "Content-Type": "text/csv; charset=utf-8",
            },
        )

    @csv_router.get("/content-ideas.csv")
    async def get_content_ideas_csv():
        """Export content ideas as CSV."""
        rows = export_content_ideas()
        csv_content = rows_to_csv(rows)
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=content_ideas.csv",
                "Content-Type": "text/csv; charset=utf-8",
            },
        )

except ImportError:
    # FastAPI not installed — no-op for CLI-only usage
    csv_router = None


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli_main():
    parser = argparse.ArgumentParser(
        description="Export Tinka SEO Dashboard data as CSV to stdout."
    )
    parser.add_argument(
        "export",
        nargs="?",
        choices=["keywords", "rank-history", "content-ideas"],
        help="Which export to produce. Omit to see available options.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all three datasets, separated by named headers.",
    )
    args = parser.parse_args()

    if args.all:
        for label, fn in [
            ("=== keywords.csv ===", export_keywords),
            ("=== rank_history.csv ===", export_rank_history),
            ("=== content_ideas.csv ===", export_content_ideas),
        ]:
            print(label, file=sys.stderr)
            print(rows_to_csv(fn()), end="")
            print(file=sys.stderr)  # blank line between datasets
        return

    if args.export == "keywords":
        print(rows_to_csv(export_keywords()), end="")
    elif args.export == "rank-history":
        print(rows_to_csv(export_rank_history()), end="")
    elif args.export == "content-ideas":
        print(rows_to_csv(export_content_ideas()), end="")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
