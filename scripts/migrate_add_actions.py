#!/usr/bin/env python3
"""Migration: Add action_queue table for interactive dashboard actions."""

import sqlite3, os, sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS action_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            action_params TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            processed_at TEXT,
            result TEXT,
            error TEXT
        )
    """)
    conn.commit()
    # Check if column exists
    cur = conn.execute("PRAGMA table_info(action_queue)")
    cols = [c[1] for c in cur.fetchall()]
    needed = {'action_type', 'action_params', 'status', 'created_at', 'processed_at', 'result', 'error'}
    missing = needed - set(cols)
    if missing:
        print(f"WARNING: Missing columns: {missing}")
    else:
        print(f"OK: action_queue table ready with {len(cols)} columns: {cols}")
    conn.close()
    print(f"Migrated: {DB_PATH}")

if __name__ == "__main__":
    migrate()
