#!/usr/bin/env python3
"""
Action Processor v1.0 - Tinka SEO Dashboard

Reads the action_queue table from the persistent local DB, processes each
pending action, updates the DB, copies the fresh DB to api/, and optionally
redeploys to Vercel.

Actions supported:
  - generate_keywords  -> calls ai_generator.py
  - generate_ideas     -> calls ai_generator.py
  - write_article      -> calls article_writer.py
  - delete_keyword     -> immediate (already applied on /tmp)
  - delete_idea        -> immediate (already applied on /tmp)
  - delete_article     -> immediate (already applied on /tmp)
  - mark_fixed         -> immediate (already applied on /tmp)

Usage:
  python scripts/process_actions.py              # dry run
  python scripts/process_actions.py --live        # actual processing
  python scripts/process_actions.py --deploy      # process + redeploy

Schedule (add to hermes cron):
  Every 30 min: python scripts/process_actions.py --live --deploy
"""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")
API_DB_PATH = os.path.join(PROJECT_DIR, "api", "seo_dashboard.db")
AI_GENERATOR = os.path.join(PROJECT_DIR, "scripts", "ai_generator.py")
ARTICLE_WRITER = os.path.join(PROJECT_DIR, "scripts", "article_writer.py")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_action_queue(conn):
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


def get_pending_actions(conn):
    return conn.execute(
        "SELECT * FROM action_queue WHERE status = 'pending' ORDER BY id ASC"
    ).fetchall()


def mark_action(conn, action_id, status, result=None, error=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE action_queue SET status=?, processed_at=?, result=?, error=? WHERE id=?",
        [status, now, result, error, action_id]
    )
    conn.commit()


def process_action(conn, action):
    aid = action["id"]
    atype = action["action_type"]
    try:
        params = json.loads(action["action_params"]) if action["action_params"] else {}
    except json.JSONDecodeError:
        params = {}

    print(f"  Processing action #{aid}: {atype} {json.dumps(params)[:80]}")

    if atype == "generate_keywords":
        topic = params.get("topic", "giant bubbles")
        market = params.get("market", "NZ")
        count = params.get("count", 15)
        result = subprocess.run(
            [sys.executable, AI_GENERATOR, "--generate-keywords", topic,
             "--market", market, "--count", str(count), "--json"],
            capture_output=True, text=True, timeout=120, cwd=PROJECT_DIR
        )
        if result.returncode != 0:
            return False, f"AI gen error: {result.stderr[:200]}"

        try:
            keywords = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False, f"Failed to parse AI output: {result.stdout[:200]}"

        domains = {r["name"]: r["id"] for r in
                   conn.execute("SELECT id, name FROM domains").fetchall()}
        target_domain_id = domains.get(
            "giantbubbles.co.nz" if market.upper() == "NZ" else "giantbubblesau.com"
        )
        if not target_domain_id:
            return False, f"Domain not found for market {market}"

        inserted = 0
        for kw in keywords:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO keywords
                       (domain_id, keyword, category, intent, volume, opportunity_score, difficulty)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    [target_domain_id, kw.get("keyword", ""), kw.get("category", "general"),
                     kw.get("intent", "informational"), kw.get("volume", 0),
                     kw.get("opportunity_score", 5.0), kw.get("difficulty", 30)]
                )
                if conn.total_changes > 0:
                    inserted += 1
            except Exception as e:
                print(f"    Skip kw '{kw.get('keyword')}': {e}")
        conn.commit()
        return True, f"Generated {inserted} keywords for {market}"

    elif atype == "generate_ideas":
        topic = params.get("topic", "giant bubbles")
        count = params.get("count", 10)
        result = subprocess.run(
            [sys.executable, AI_GENERATOR, "--generate-articles", topic,
             "--count", str(count), "--json"],
            capture_output=True, text=True, timeout=120, cwd=PROJECT_DIR
        )
        if result.returncode != 0:
            return False, f"AI gen error: {result.stderr[:200]}"

        try:
            ideas = json.loads(result.stdout)
        except json.JSONDecodeError:
            return False, f"Failed to parse AI output: {result.stdout[:200]}"

        inserted = 0
        for idea in ideas:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO content_ideas
                       (title, target_keyword, category, estimated_searches,
                        opportunity_score, effort, content_type, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    [idea.get("title", ""), idea.get("target_keyword", ""),
                     idea.get("category", "general"), idea.get("estimated_searches", 0),
                     idea.get("opportunity_score", 5.0), idea.get("effort", "medium"),
                     idea.get("content_type", "blog")]
                )
                inserted += 1
            except Exception as e:
                print(f"    Skip idea '{idea.get('title')}': {e}")
        conn.commit()
        return True, f"Generated {len(ideas)} content ideas"

    elif atype == "write_article":
        idea_id = params.get("idea_id")
        if not idea_id:
            return False, "Missing idea_id parameter"
        result = subprocess.run(
            [sys.executable, ARTICLE_WRITER, "--idea", str(idea_id), "--generate"],
            capture_output=True, text=True, timeout=180, cwd=PROJECT_DIR
        )
        success = result.returncode == 0
        msg = (result.stdout[:300] if result.stdout
               else (result.stderr[:200] if result.stderr else "OK"))
        return success, msg

    elif atype in ("delete_keyword", "delete_idea", "delete_article", "mark_fixed"):
        return True, "Already applied to /tmp (re-apply to persistent DB)"

    else:
        return False, f"Unknown action type: {atype}"


def main():
    parser = argparse.ArgumentParser(description="Process queued dashboard actions")
    parser.add_argument("--live", action="store_true", help="Actually process actions")
    parser.add_argument("--deploy", action="store_true",
                        help="Redeploy to Vercel after processing")
    args = parser.parse_args()

    conn = get_conn()
    ensure_action_queue(conn)

    pending = get_pending_actions(conn)
    if not pending:
        print("No pending actions to process.")
        conn.close()
        return

    print(f"Found {len(pending)} pending action(s):")
    for a in pending:
        print(f"  #{a['id']}: {a['action_type']} (created {a['created_at']})")

    if not args.live:
        print("\nDRY RUN - use --live to process")
        conn.close()
        return

    success_count = 0
    fail_count = 0
    for action in pending:
        ok, msg = process_action(conn, action)
        mark_action(conn, action["id"],
                    "completed" if ok else "failed",
                    result=msg if ok else None,
                    error=msg if not ok else None)
        if ok:
            success_count += 1
            print(f"  OK #{action['id']}: {msg}")
        else:
            fail_count += 1
            print(f"  FAIL #{action['id']}: {msg}")

    conn.close()
    print(f"\nDone: {success_count} ok, {fail_count} failed")

    import shutil
    shutil.copy2(DB_PATH, API_DB_PATH)
    print(f"Copied DB to api/")

    if args.deploy:
        print("\nRedeploying to Vercel...")
        result = subprocess.run(
            ["npx", "vercel", "--prod", "--yes"],
            capture_output=True, text=True, timeout=300, cwd=PROJECT_DIR
        )
        print(result.stdout[-500:])
        if result.returncode != 0:
            print(f"Deploy error: {result.stderr[:300]}")


if __name__ == "__main__":
    main()
