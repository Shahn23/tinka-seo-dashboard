#!/usr/bin/env python3
"""Ingest all parent task data into SEO dashboard DB.

Integrates:
1. 47 new keyword ideas from tinka_keyword_research.csv
2. Existing keyword position data from the same CSV
3. 10 blog post ideas from tinka_blog_post_ideas.md
4. Real on-page error data from errors_au.json + errors_nz.json

Usage:
    python scripts/ingest_parent_data.py
    python scripts/ingest_parent_data.py --dry-run
"""

import argparse
import csv
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("parent-ingest")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"
KW_CSV = BASE / "data" / "tinka_keyword_research.csv"
BLOG_MD = BASE / "data" / "tinka_blog_post_ideas.md"
ERR_AU = BASE / "data" / "errors_au.json"
ERR_NZ = BASE / "data" / "errors_nz.json"


def get_conn():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def domain_for_market(market: str) -> int:
    """Return domain_id based on market."""
    return 1 if market.upper() == "NZ" else 2  # NZ=1, AU=2


def normalize_category(raw: str) -> str:
    """Map raw categories from CSV to canonical values."""
    c = raw.strip().lower()
    m = {
        "product": "product",
        "local": "local",
        "party": "party",
        "b2b": "b2b",
        "content": "content",
        "kids": "kids",
        "brand_general": "brand_general",
        "seasonal": "seasonal",
    }
    return m.get(c, c)


def normalize_intent(raw: str) -> str:
    i = raw.strip().lower()
    valid = {"informational", "commercial", "transactional", "navigational"}
    return i if i in valid else "commercial"


# ── 1. Ingest keyword research CSV ────────────────────────────────────────


def ingest_keywords(dry_run: bool) -> dict:
    """Ingest new keyword ideas from CSV. Returns {new: int, updated: int, skipped: int}."""
    if not KW_CSV.exists():
        log.warning(f"Keyword CSV not found: {KW_CSV}")
        return {"new": 0, "updated": 0, "skipped": 0}

    new = 0
    updated = 0
    skipped = 0
    rank_updates = 0

    with open(str(KW_CSV), "r", encoding="utf-8") as f:
        content = f.read()

    # Split into two sections: new keyword ideas + existing keywords
    parts = content.split("--- EXISTING KEYWORDS")
    new_keywords_section = parts[0].strip()
    existing_keywords_section = parts[1].strip() if len(parts) > 1 else ""

    conn = get_conn() if not dry_run else None

    def process_row(row: dict, is_existing: bool):
        nonlocal new, updated, skipped, rank_updates

        market = row.get("Market", "").strip().upper()
        keyword = row.get("Keyword", "").strip()
        category = normalize_category(row.get("Category", ""))
        intent = normalize_intent(row.get("Intent", ""))
        volume = int(row.get("Est. Search Volume", row.get("Volume", 0)) or 0)
        difficulty = int(row.get("Keyword Difficulty", row.get("Difficulty", 50)) or 50)
        opp_score = float(row.get("Opportunity Score", 5.0) or 5.0)

        if not keyword:
            skipped += 1
            return

        domain_id = domain_for_market(market)

        if dry_run:
            if is_existing:
                pos_str = row.get("Current Position", "N/A")
                log.info(f"  [dry-run] UPDATE: {keyword} ({market}) pos={pos_str}, vol={volume}")
                updated += 1
            else:
                log.info(f"  [dry-run] NEW: {keyword} ({market}) vol={volume}, opp={opp_score}")
                new += 1
            return

        # Check if keyword exists
        existing = conn.execute(
            "SELECT id FROM keywords WHERE domain_id=? AND keyword=? COLLATE NOCASE",
            (domain_id, keyword),
        ).fetchone()

        if existing:
            # Update existing keyword's metadata
            conn.execute(
                """UPDATE keywords SET
                   category=?, intent=?, volume=?, opportunity_score=?, difficulty=?
                   WHERE id=?""",
                (category, intent, volume, opp_score, difficulty, existing["id"]),
            )
            updated += 1

            # If existing keyword has positions in the CSV, add rank_history
            if is_existing:
                pos_str = row.get("Current Position", "")
                if pos_str:
                    try:
                        position = float(pos_str)
                    except ValueError:
                        position = 0.0
                    clicks = int(row.get("Clicks (30d)", row.get("clicks", 0)) or 0)
                    impressions = int(row.get("Imp (30d)", row.get("impressions", 0)) or 0)
                    today = datetime.now().strftime("%Y-%m-%d")
                    # Only insert if not already present today
                    existing_rh = conn.execute(
                        "SELECT id FROM rank_history WHERE keyword_id=? AND date=?",
                        (existing["id"], today),
                    ).fetchone()
                    if not existing_rh and position > 0:
                        ctr = round(clicks / max(impressions, 1), 4)
                        conn.execute(
                            """INSERT INTO rank_history
                               (keyword_id, date, position, clicks, impressions, ctr)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (existing["id"], today, round(position, 1), clicks, impressions, ctr),
                        )
                        rank_updates += 1
        else:
            # Insert new keyword
            conn.execute(
                """INSERT INTO keywords
                   (domain_id, keyword, category, intent, volume, opportunity_score, difficulty, is_high_priority)
                   VALUES (?, ?, ?, ?, ?, ?, ?,
                       CASE WHEN ? >= 8.0 THEN 1 ELSE 0 END)""",
                (domain_id, keyword, category, intent, volume, opp_score, difficulty, opp_score),
            )
            new += 1

    # Parse the new keyword ideas section (top portion)
    reader = csv.DictReader(new_keywords_section.splitlines())
    for row in reader:
        process_row(row, is_existing=False)

    # Parse the existing keywords section (bottom portion)
    if existing_keywords_section:
        reader2 = csv.DictReader(existing_keywords_section.splitlines())
        for row in reader2:
            process_row(row, is_existing=True)

    if conn:
        conn.commit()
        log.info(f"Keywords: {new} new, {updated} updated, {rank_updates} position records added, {skipped} skipped")
        conn.close()

    return {"new": new, "updated": updated, "rank_updates": rank_updates, "skipped": skipped}


# ── 2. Ingest blog post ideas ─────────────────────────────────────────────


def parse_blog_ideas(md_content: str) -> list[dict]:
    """Parse blog post ideas from the markdown file into structured dicts."""
    ideas = []

    # Split by ## headers
    sections = re.split(r"\n##\s+", md_content)

    for section in sections:
        if not section.strip():
            continue

        title_match = re.match(r"(\d+)\.\s+(.+?)(?:\n|$)", section)
        if not title_match:
            continue

        idea_num = int(title_match.group(1))
        title = title_match.group(2).strip()
        # Remove trailing markdown bold
        title = title.replace("**", "").strip()

        # Extract target keywords from **Target keywords:**
        kw_match = re.search(r"\*\*Target keywords?:\*\*\s*(.+?)(?:\n|$)", section)
        target_keywords = ""
        if kw_match:
            target_keywords = kw_match.group(1).strip()
            # Extract just first keyword name for the main target
            first_kw = re.split(r"[\(\,]", target_keywords)[0].strip()

        # Extract outline items
        outline_items = re.findall(r"^- (.+)", section)
        outline = "\n".join(f"- {item}" for item in outline_items) if outline_items else ""

        # Estimate combined search volume from the keywords line
        vol_total = 0
        kw_vols = re.findall(r"\((\d+)/mo", section)
        vol_total = sum(int(v) for v in kw_vols)

        # Get opportunity score
        best_opp = 0.0
        opp_matches = re.findall(r"Opp:\s*([\d.]+)", section)
        if opp_matches:
            best_opp = max(float(o) for o in opp_matches)

        # Determine effort level based on content type hints
        effort = "medium"
        if "easy" in section.lower()[:200]:
            effort = "easy"
        elif "hard" in section.lower()[:200]:
            effort = "hard"

        # Determine category
        # Check target keywords for hints
        category = "blog"
        if any(w in section.lower() for w in ["party", "birthday"]):
            category = "party"
        elif any(w in section.lower() for w in ["city", "sydney", "melbourne", "auckland", "local"]):
            category = "local"
        elif any(w in section.lower() for w in ["b2b", "wholesale", "bulk", "business"]):
            category = "b2b"
        elif any(w in section.lower() for w in ["school", "education", "science"]):
            category = "educational"
        elif any(w in section.lower() for w in ["photo", "photography"]):
            category = "how-to"
        elif any(w in section.lower() for w in ["non-toxic", "bio-grade", "safe", "eco"]):
            category = "safety"
        elif any(w in section.lower() for w in ["diy"]):
            category = "how-to"
        elif any(w in section.lower() for w in ["how to make", "recipe", "guide"]):
            category = "how-to"
        elif any(w in section.lower() for w in ["product", "wand", "people in a bubble"]):
            category = "product"

        # First keyword as target
        first_kw = target_keywords.split(",")[0] if target_keywords else ""
        # Clean up: remove parenthetical volume/difficulty info
        first_kw = re.sub(r"\s*\([^)]*\)", "", first_kw).strip()

        ideas.append({
            "title": title,
            "target_keyword": first_kw,
            "category": category,
            "estimated_searches": vol_total,
            "opportunity_score": round(best_opp, 1),
            "effort": effort,
            "content_type": "blog",
            "outline": outline,
            "source": "keyword-research",
            "status": "backlog",
        })

    return ideas


def ingest_blog_ideas(dry_run: bool) -> dict:
    """Ingest blog post ideas from markdown into content_ideas."""
    if not BLOG_MD.exists():
        log.warning(f"Blog ideas file not found: {BLOG_MD}")
        return {"new": 0, "updated": 0, "skipped": 0}

    with open(str(BLOG_MD), "r", encoding="utf-8") as f:
        content = f.read()

    ideas = parse_blog_ideas(content)
    log.info(f"Parsed {len(ideas)} blog ideas from markdown")

    if dry_run:
        for idea in ideas:
            log.info(f"  [dry-run] WOULD ADD: {idea['title'][:60]} (opp={idea['opportunity_score']}, vol={idea['estimated_searches']})")
        return {"new": len(ideas), "updated": 0, "skipped": 0}

    conn = get_conn()
    new_count = 0
    updated_count = 0

    for idea in ideas:
        existing = conn.execute(
            "SELECT id FROM content_ideas WHERE title=? COLLATE NOCASE",
            (idea["title"],),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE content_ideas SET
                   target_keyword=?, category=?, estimated_searches=?,
                   opportunity_score=?, effort=?, content_type=?, outline=?,
                   source=?, status=?
                   WHERE id=?""",
                (
                    idea["target_keyword"], idea["category"], idea["estimated_searches"],
                    idea["opportunity_score"], idea["effort"], idea["content_type"],
                    idea["outline"], idea["source"], idea["status"],
                    existing["id"],
                ),
            )
            updated_count += 1
        else:
            conn.execute(
                """INSERT INTO content_ideas
                   (title, target_keyword, category, estimated_searches, opportunity_score,
                    effort, content_type, outline, source, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    idea["title"], idea["target_keyword"], idea["category"],
                    idea["estimated_searches"], idea["opportunity_score"], idea["effort"],
                    idea["content_type"], idea["outline"], idea["source"], idea["status"],
                ),
            )
            new_count += 1

    conn.commit()
    log.info(f"Blog ideas: {new_count} new, {updated_count} updated")
    conn.close()
    return {"new": new_count, "updated": updated_count, "skipped": 0}


# ── 3. Re-ingest on-page errors ───────────────────────────────────────────


def ingest_errors(dry_run: bool) -> dict:
    """Re-ingest real on-page error data from JSON files."""
    imported = 0
    skipped = 0

    error_files = [
        ("giantbubbles.co.nz", ERR_NZ),
        ("giantbubblesau.com", ERR_AU),
    ]

    for domain_name, err_file in error_files:
        if not err_file.exists():
            log.warning(f"Error file not found: {err_file}")
            continue

        with open(str(err_file), "r", encoding="utf-8") as f:
            errors = json.load(f)

        if not isinstance(errors, list):
            errors = [errors]

        if dry_run:
            log.info(f"  [dry-run] WOULD import {len(errors)} errors for {domain_name}")
            for e in errors:
                log.info(f"    {e.get('severity', 'moderate')}: {e.get('error_type')} @ {e.get('url','?')}")
            imported += len(errors)
            continue

        conn = get_conn()
        domain = conn.execute(
            "SELECT id FROM domains WHERE name=?",
            (domain_name,),
        ).fetchone()
        if not domain:
            log.warning(f"Domain {domain_name} not found in DB, skipping")
            skipped += len(errors)
            continue

        domain_id = domain["id"]

        for err in errors:
            url = err.get("url", "").strip()
            error_type = err.get("error_type", "unknown").strip()
            severity = err.get("severity", "moderate").strip()
            description = err.get("description", "").strip()
            suggestion = err.get("suggestion", "").strip()

            # Check if this exact error already exists as open
            existing = conn.execute(
                """SELECT id FROM onpage_errors
                   WHERE domain_id=? AND error_type=? AND page_url=? AND status='open'""",
                (domain_id, error_type, url),
            ).fetchone()

            if existing:
                # Update description/suggestion but keep status
                conn.execute(
                    """UPDATE onpage_errors SET description=?, suggestion=? WHERE id=?""",
                    (description, suggestion, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO onpage_errors
                       (domain_id, error_type, severity, page_url, description, suggestion, status, batch_id)
                       VALUES (?, ?, ?, ?, ?, ?, 'open', 'parent-task-audit')""",
                    (domain_id, error_type, severity, url, description, suggestion),
                )
                imported += 1

        conn.commit()
        conn.close()

    log.info(f"Errors: {imported} imported, {skipped} skipped")
    return {"imported": imported, "skipped": skipped}


def close_seed_errors(dry_run: bool) -> int:
    """Mark old seed errors (from init_db.py, not from parent tasks) as fixed."""
    if dry_run:
        return 0

    conn = get_conn()
    # Mark errors that are from the seed (batch_id IS NULL or old batch) as fixed
    # But only if they're duplicate entries of what we just imported
    result = conn.execute(
        """UPDATE onpage_errors SET status='fixed', fixed_at=datetime('now')
           WHERE batch_id IS NULL AND status='open'"""
    )
    closed = result.rowcount
    conn.commit()
    conn.close()
    if closed > 0:
        log.info(f"Closed {closed} old seed errors (no batch_id)")
    return closed


# ── Main ──────────────────────────────────────────────────────────────────


def run_all(dry_run: bool = False):
    log.info("=" * 55)
    log.info(f"PARENT TASK DATA INGESTION{' (DRY RUN)' if dry_run else ''}")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    # 1. Keywords
    kw_result = ingest_keywords(dry_run=dry_run)
    log.info(f"  ✅ Keywords: {kw_result}")

    # 2. Blog ideas
    blog_result = ingest_blog_ideas(dry_run=dry_run)
    log.info(f"  ✅ Blog ideas: {blog_result}")

    # 3. On-page errors
    err_result = ingest_errors(dry_run=dry_run)
    log.info(f"  ✅ Errors: {err_result}")

    # 4. Close old seed errors
    closed = close_seed_errors(dry_run=dry_run)
    log.info(f"  ✅ Old seed errors closed: {closed}")

    log.info("=" * 55)
    all_ok = True
    total_new = kw_result.get("new", 0) + blog_result.get("new", 0) + err_result.get("imported", 0)
    total_updates = kw_result.get("updated", 0) + blog_result.get("updated", 0)
    log.info(f"SUMMARY: {total_new} new items, {total_updates} updated items")
    log.info("=" * 55)

    if not dry_run:
        # Check final counts
        conn = get_conn()
        for tbl in ["domains", "keywords", "rank_history", "onpage_errors", "content_ideas"]:
            c = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            log.info(f"  {tbl}: {c}")
        conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest all parent task data into SEO dashboard DB")
    p.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = p.parse_args()
    run_all(dry_run=args.dry_run)
