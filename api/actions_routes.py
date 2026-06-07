"""Interactive Action Routes for Tinka SEO Dashboard (Vercel).

POST endpoints that users trigger from dashboard buttons:
  - Queue generation of keywords / content ideas / articles
  - Delete keywords / ideas / articles / mark issues fixed
  - Check pending action status

On Vercel serverless, writes go to the /tmp/ DB for immediate feedback.
Actions are queued in the action_queue table; a local Hermes processor
script picks them up and applies them to the persistent DB + redeploys.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse

THIS_DIR = Path(__file__).resolve().parent
DB_PATH = Path("/tmp") / "seo_dashboard.db"
LOCAL_DB = THIS_DIR / "seo_dashboard.db"

router = APIRouter(prefix="/api", tags=["actions"])

# ── DB helpers ──────────────────────────────────────────────────────────────

def get_conn():
    p = DB_PATH if DB_PATH.exists() else LOCAL_DB
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.row_factory = sqlite3.Row
    return conn

def queue_action(action_type: str, params: dict) -> dict:
    """Insert an action into the queue and return the action record."""
    conn = get_conn()
    try:
        # Ensure the action_queue table exists (handles first-time /tmp DB)
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
        cur = conn.execute(
            "INSERT INTO action_queue (action_type, action_params) VALUES (?, ?)",
            [action_type, json.dumps(params)]
        )
        action_id = cur.lastrowid
        conn.commit()
        return {"id": action_id, "action_type": action_type, "status": "pending"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def modify_tmp_db(sql: str, params: list) -> dict:
    """Execute a SQL write on the /tmp DB (for immediate UI feedback).
    Also writes the same change to LOCAL_DB so it persists on next deploy.
    """
    results = {}
    for db_path in [DB_PATH, LOCAL_DB]:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute(sql, params)
            conn.commit()
            conn.close()
            results[str(db_path)] = "ok"
        except Exception as e:
            results[str(db_path)] = str(e)
    return results

# ── POST Endpoints ──────────────────────────────────────────────────────────

@router.post("/queue-action")
async def api_queue_action(
    action_type: str = Form(...),
    action_params: str = Form("{}"),
):
    """Queue an action for local processing (generate, write, etc.)."""
    try:
        params = json.loads(action_params)
    except json.JSONDecodeError:
        params = {}
    result = queue_action(action_type, params)
    if "error" in result:
        return JSONResponse({"status": "error", "message": result["error"]}, status_code=500)
    return JSONResponse({
        "status": "queued",
        "action_id": result["id"],
        "action_type": action_type,
        "message": f"Action queued (ID: {result['id']}). Processing typically completes within 30 minutes."
    })

@router.post("/delete/keyword/{kw_id}")
async def api_delete_keyword(kw_id: int):
    """Delete a keyword + its rank history from /tmp DB immediately."""
    r = modify_tmp_db("DELETE FROM rank_history WHERE keyword_id=?", [kw_id])
    r2 = modify_tmp_db("DELETE FROM keywords WHERE id=?", [kw_id])
    ok = all(v == "ok" for v in {**r, **r2}.values())
    return JSONResponse({
        "status": "ok" if ok else "partial",
        "message": "Keyword deleted (will persist on next deploy)" if ok else "Delete applied to /tmp only",
        "details": {**r, **r2}
    })

@router.post("/delete/idea/{idea_id}")
async def api_delete_idea(idea_id: int):
    """Delete a content idea from /tmp DB immediately."""
    r = modify_tmp_db("DELETE FROM content_ideas WHERE id=?", [idea_id])
    ok = all(v == "ok" for v in r.values())
    return JSONResponse({
        "status": "ok" if ok else "partial",
        "message": "Content idea deleted" if ok else "Delete applied to /tmp only",
        "details": r
    })

@router.post("/delete/article/{article_id}")
async def api_delete_article(article_id: int):
    """Delete a published article record."""
    r = modify_tmp_db("DELETE FROM published_articles WHERE id=?", [article_id])
    ok = all(v == "ok" for v in r.values())
    return JSONResponse({
        "status": "ok" if ok else "partial",
        "message": "Article record deleted" if ok else "Delete applied to /tmp only",
        "details": r
    })

@router.post("/mark-fixed/{error_id}")
async def api_mark_fixed(error_id: int):
    """Mark an on-page error as fixed."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    r = modify_tmp_db(
        "UPDATE onpage_errors SET status='fixed', fixed_at=? WHERE id=?",
        [now, error_id]
    )
    ok = all(v == "ok" for v in r.values())
    return JSONResponse({
        "status": "ok" if ok else "partial",
        "message": "Issue marked as fixed" if ok else "Updated on /tmp only",
        "details": r
    })

@router.get("/pending-actions")
async def api_pending_actions(limit: int = Query(10)):
    """Get the list of pending / recent actions from the action_queue."""
    try:
        conn = get_conn()
        # Ensure table exists
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
        rows = conn.execute(
            f"""SELECT id, action_type, action_params, status, created_at, processed_at, result, error
                FROM action_queue ORDER BY id DESC LIMIT ?""",
            [limit]
        ).fetchall()
        conn.close()
        return JSONResponse({
            "actions": [dict(r) for r in rows],
            "pending_count": sum(1 for r in rows if r["status"] == "pending")
        })
    except Exception as e:
        return JSONResponse({"actions": [], "pending_count": 0, "error": str(e)})
