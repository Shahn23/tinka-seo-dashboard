#!/usr/bin/env python3
"""Migration: Add stage column to content_ideas for content pipeline tracking.

Pipeline stages:
  ideation   — Idea was generated/collected, not yet validated
  research   — Keyword research & competitor analysis done
  writing    — Article being authored
  editing    — Draft complete, undergoing review/edits
  review     — Final review / SEO check before publish
  published  — Live on site
  archived   — Deprecated or no longer relevant

Current status values ('draft', 'published', 'backlog') are preserved but the
new `stage` column drives the pipeline funnel view.
"""

import sqlite3
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

# Mapping: current status → pipeline stage
STATUS_TO_STAGE = {
    "backlog":   "ideation",
    "draft":     "research",
    "in_progress": "writing",
    "in_review": "review",
    "published": "published",
}

STAGES = ["ideation", "research", "writing", "editing", "review", "published", "archived"]


def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # 1. Check if stage column already exists
    cur = conn.execute("PRAGMA table_info(content_ideas)")
    cols = {row[1] for row in cur.fetchall()}

    added = "stage" not in cols

    if added:
        # Add the stage column WITHOUT default — existing rows stay NULL
        stages_literal = ",".join(repr(s) for s in STAGES)
        conn.execute(f"""
            ALTER TABLE content_ideas
            ADD COLUMN stage TEXT CHECK(stage IN ({stages_literal}))
        """)
        print("+ Added 'stage' column to content_ideas")
    else:
        print("= 'stage' column already exists — updating any unmapped rows.")

    # 2. Migrate existing rows: map status → stage
    # Use COALESCE to skip already-mapped rows on re-runs
    for status, stage in STATUS_TO_STAGE.items():
        conn.execute(
            "UPDATE content_ideas SET stage = ? WHERE status = ? AND COALESCE(stage, '') = ''",
            (stage, status),
        )
        affected = conn.execute(
            "SELECT changes()"
        ).fetchone()[0]
        if affected:
            print(f"  → Mapped {affected} '{status}' rows to stage '{stage}'")

    # 3. Any remaining empty stages default to 'ideation'
    conn.execute(
        "UPDATE content_ideas SET stage = 'ideation' WHERE COALESCE(stage, '') = ''"
    )
    remaining = conn.execute("SELECT changes()").fetchone()[0]
    if remaining:
        print(f"  → Set {remaining} remaining null-stage rows to 'ideation'")

    conn.commit()

    # 4. Re-apply CHECK constraint via table rewrite if column was just added
    if added:
        # SQLite's ALTER TABLE ADD COLUMN doesn't enforce CHECK on existing rows,
        # so we do a no-op rewrite to trigger it.
        conn.execute("""
            CREATE TABLE content_ideas_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, target_keyword TEXT, category TEXT,
                estimated_searches INTEGER DEFAULT 0, opportunity_score REAL DEFAULT 5.0,
                effort TEXT CHECK(effort IN ('easy','medium','hard')) DEFAULT 'medium',
                content_type TEXT, outline TEXT, source TEXT DEFAULT 'seed',
                status TEXT DEFAULT 'draft', created_at TEXT DEFAULT (datetime('now')),
                stage TEXT CHECK(stage IN ('ideation','research','writing','editing','review','published','archived'))
            )
        """)
        conn.execute("INSERT INTO content_ideas_new SELECT * FROM content_ideas")
        conn.execute("DROP TABLE content_ideas")
        conn.execute("ALTER TABLE content_ideas_new RENAME TO content_ideas")
        conn.commit()
        print("  → Re-wrote table to enforce CHECK constraint on stage column.")

    print("✓ Content pipeline stage migration complete.")

    # 4. Verify
    cur = conn.execute("""
        SELECT stage, COUNT(*) AS cnt
        FROM content_ideas
        GROUP BY stage
        ORDER BY CASE stage
            WHEN 'ideation'  THEN 1
            WHEN 'research'  THEN 2
            WHEN 'writing'   THEN 3
            WHEN 'editing'   THEN 4
            WHEN 'review'    THEN 5
            WHEN 'published' THEN 6
            WHEN 'archived'  THEN 7
            ELSE 99
        END
    """)
    print("\nPipeline stage distribution:")
    total = 0
    for stage, cnt in cur.fetchall():
        print(f"  {stage:12s} : {cnt}")
        total += cnt
    print(f"  {'─'*20}\n  {'TOTAL':12s} : {total}")

    conn.close()
    print(f"\nDone: {DB_PATH}")


if __name__ == "__main__":
    migrate()
