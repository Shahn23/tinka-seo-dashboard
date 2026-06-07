#!/usr/bin/env python3
"""Content Pipeline Funnel — shows count of ideas at each pipeline stage.

This script can be run standalone or imported to get funnel data.

Usage:
    python scripts/content_pipeline_funnel.py          # print table
    python scripts/content_pipeline_funnel.py --json    # print JSON
    python scripts/content_pipeline_funnel.py --view    # ensure SQL view exists
"""

import sqlite3
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

# Ordered pipeline stages
PIPELINE_STAGES = [
    "ideation",
    "research",
    "writing",
    "editing",
    "review",
    "published",
    "archived",
]

# Funnel SQL — aggregate query
FUNNEL_QUERY = """
SELECT
    stage,
    COUNT(*)                              AS count,
    ROUND(100.0 * COUNT(*) / MAX(SUM_COUNT) OVER (), 1) AS pct_of_max,
    ROUND(100.0 * COUNT(*) / SUM_COUNT, 1)             AS pct_of_total
FROM (
    SELECT
        COALESCE(stage, 'ideation') AS stage,
        (SELECT COUNT(*) FROM content_ideas) AS SUM_COUNT
    FROM content_ideas
)
GROUP BY stage
ORDER BY
    CASE stage
        WHEN 'ideation'  THEN 1
        WHEN 'research'  THEN 2
        WHEN 'writing'   THEN 3
        WHEN 'editing'   THEN 4
        WHEN 'review'    THEN 5
        WHEN 'published' THEN 6
        WHEN 'archived'  THEN 7
        ELSE 99
    END
"""

# The view definition — a rolling funnel showing how many ideas
# have reached at least each stage (cumulative from left to right)
FUNNEL_VIEW_DDL = """
CREATE VIEW IF NOT EXISTS v_content_pipeline_funnel AS
WITH stage_counts AS (
    SELECT
        COALESCE(stage, 'ideation') AS stage,
        COUNT(*) AS ideas
    FROM content_ideas
    GROUP BY stage
),
stage_ordering AS (
    SELECT stage, ideas,
        CASE stage
            WHEN 'ideation'  THEN 1
            WHEN 'research'  THEN 2
            WHEN 'writing'   THEN 3
            WHEN 'editing'   THEN 4
            WHEN 'review'    THEN 5
            WHEN 'published' THEN 6
            WHEN 'archived'  THEN 7
            ELSE 99
        END AS sort_order
    FROM stage_counts
),
funnel AS (
    SELECT
        stage,
        ideas,
        sort_order,
        SUM(ideas) OVER (ORDER BY sort_order) AS cumulative,
        ROUND(100.0 * ideas / (SELECT COUNT(*) FROM content_ideas), 1) AS pct_of_total
    FROM stage_ordering
)
SELECT
    stage,
    ideas,
    cumulative,
    pct_of_total
FROM funnel
ORDER BY sort_order
"""


def get_funnel_data(conn=None) -> list[dict]:
    """Fetch funnel data as list of dicts."""
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

    cur = conn.execute(FUNNEL_QUERY)
    rows = [dict(r) for r in cur.fetchall()]

    if close:
        conn.close()
    return rows


def ensure_view(conn=None):
    """Create/replace the funnel SQL view."""
    close = conn is None
    if close:
        conn = sqlite3.connect(DB_PATH)

    conn.executescript(FUNNEL_VIEW_DDL)
    conn.commit()
    print("✓ View v_content_pipeline_funnel created/updated.")

    if close:
        conn.close()


def print_table(rows: list[dict]):
    """Print funnel data as a pretty ASCII table."""
    if not rows:
        print("(no content ideas found)")
        return

    stg_width = max(len(r["stage"]) for r in rows)
    stg_width = max(stg_width, 5)

    header = f"  {'Stage':<{stg_width}}   {'Count':>6}   {'% of Max':>9}   {'% of Total':>10}"
    sep = f"  {'─'*stg_width}───{'─'*6}───{'─'*9}───{'─'*10}"

    total = sum(r["count"] for r in rows)
    max_cnt = max(r["count"] for r in rows) if rows else 0

    print(f"\n{'📊 Content Pipeline Funnel':^{len(header)}}\n")
    print(header)
    print(sep)
    for r in rows:
        bar = "█" * int(20 * r["count"] / max_cnt) if max_cnt > 0 else ""
        print(
            f"  {r['stage']:<{stg_width}}   {r['count']:>6}   {r['pct_of_max']:>8.1f}%   {r['pct_of_total']:>9.1f}%  {bar}"
        )
    print(sep)
    print(f"  {'TOTAL':<{stg_width}}   {total:>6}\n")


def run():
    action = "table"
    if "--json" in sys.argv:
        action = "json"
    if "--view" in sys.argv:
        action = "view"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if action == "view":
        ensure_view(conn)
        return

    rows = get_funnel_data(conn)
    conn.close()

    if action == "json":
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)


if __name__ == "__main__":
    run()
