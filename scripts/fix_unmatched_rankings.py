#!/usr/bin/env python3
"""Fix unmatched keyword rankings - adds missing keywords and fixes name mismatches.

Skipped NZ keywords need adding to keywords table:
  - 'Giant Bubbles For Kids NZ' (vol=170)
  - 'How To Make Giant Bubbles' (vol=720) - exists as AU, needs NZ copy
  - 'Best Giant Bubble Kit' (vol=210)
  - 'Giant Bubbles Party Hire Auckland' (vol=90)

Skipped AU keywords need adding or fuzzy-matching:
  - 'Giant Bubble Wand' -> 'Giant Bubble Wand Australia' (fuzzy match, already in DB)
  - 'Wholesale Bubbles' -> 'Wholesale Giant Bubbles' OR new keyword
  - 'Giant Bubbles Birthday Party' -> 'Giant Bubbles Birthday Party Australia'
  - Plus genuinely new AU keywords to add

Usage:
    python scripts/fix_unmatched_rankings.py
"""
import logging
import sqlite3
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("fix-rankings")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"


def get_conn():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def add_keyword_if_missing(conn, domain_id, keyword, volume=0, category="product", intent="commercial", opp_score=5.0, difficulty=50):
    """Add a keyword to DB if it doesn't already exist. Returns the keyword id."""
    existing = conn.execute(
        "SELECT id FROM keywords WHERE domain_id=? AND keyword=? COLLATE NOCASE",
        (domain_id, keyword),
    ).fetchone()
    if existing:
        return existing["id"]
    conn.execute(
        """INSERT INTO keywords (domain_id, keyword, category, intent, volume, opportunity_score, difficulty, is_high_priority)
           VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? >= 8.0 THEN 1 ELSE 0 END)""",
        (domain_id, keyword, category, intent, volume, opp_score, difficulty, opp_score),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def add_ranking(conn, keyword_id, position, clicks, impressions):
    """Add a rank_history record for today if one doesn't exist."""
    today = date.today().isoformat()
    existing = conn.execute(
        "SELECT id FROM rank_history WHERE keyword_id=? AND date=?",
        (keyword_id, today),
    ).fetchone()
    if existing or position <= 0:
        return False
    ctr = round(clicks / max(impressions, 1), 4)
    conn.execute(
        "INSERT INTO rank_history (keyword_id, date, position, clicks, impressions, ctr) VALUES (?, ?, ?, ?, ?, ?)",
        (keyword_id, today, position, clicks, impressions, ctr),
    )
    return True


def fuzzy_match(conn, domain_id, name):
    """Try to find a keyword in the DB that closely matches the ranking name."""
    # Try exact match
    exact = conn.execute(
        "SELECT id, keyword FROM keywords WHERE domain_id=? AND keyword=? COLLATE NOCASE",
        (domain_id, name),
    ).fetchone()
    if exact:
        return exact["id"]

    # Try contains match (e.g. 'Giant Bubble Wand' -> 'Giant Bubble Wand Australia')
    words = name.lower().split()
    candidates = conn.execute(
        "SELECT id, keyword FROM keywords WHERE domain_id=?",
        (domain_id,),
    ).fetchall()
    for c in candidates:
        ckw = c["keyword"].lower()
        # Check if all words from the ranking name appear in the DB keyword
        if all(w in ckw for w in words):
            return c["id"]
    return None


def main():
    conn = get_conn()
    today = date.today().isoformat()
    added_keywords = 0
    added_rankings = 0

    # ── NZ fixes ──────────────────────────────────────────────────────────
    nz_additions = [
        ("Giant Bubbles For Kids NZ", 170, "kids", "commercial", 7.5, 35),
        ("How To Make Giant Bubbles NZ", 720, "content", "informational", 9.0, 30),
        ("Best Giant Bubble Kit NZ", 210, "product", "commercial", 8.5, 40),
        ("Giant Bubbles Party Hire Auckland", 90, "local", "commercial", 7.0, 25),
    ]
    # Rankings for these new NZ keywords - these are unranked (position=0)
    for kw, vol, cat, intent, opp, diff in nz_additions:
        kid = add_keyword_if_missing(conn, 1, kw, vol, cat, intent, opp, diff)
        added_keywords += 1
        log.info(f"  Added NZ keyword: {kw} (id={kid})")

    # NZ rankings from the audit (already partially inserted)
    nz_rankings = [
        ("Giant Bubble Kit NZ", 6.6, 8, 210),
        ("Giant Bubble Wand NZ", 6.6, 5, 140),
        ("Wholesale Bubbles NZ", 3.5, 12, 95),
        ("Bubble Solution NZ", 7.2, 3, 60),
        ("Giant Bubbles NZ", 4.1, 15, 320),
    ]
    for kw, pos, clicks, imp in nz_rankings:
        kid = fuzzy_match(conn, 1, kw)
        if kid:
            if add_ranking(conn, kid, pos, clicks, imp):
                added_rankings += 1
                log.info(f"  Added NZ ranking: {kw} pos={pos}")
        else:
            log.warning(f"  NZ keyword still not found: {kw}")

    # ── AU fixes ──────────────────────────────────────────────────────────
    # Fuzzy matches: ranking name -> DB keyword
    au_fuzzy = [
        ("Giant Bubble Wand", "Giant Bubble Wand Australia", 5.5, 7, 160),
        ("Wholesale Bubbles", "Wholesale Giant Bubbles", 3.5, 10, 180),
        ("Giant Bubbles Birthday Party", "Giant Bubbles Birthday Party Australia", 6.8, 3, 65),
        ("Giant Bubbles", "Giant Bubbles For Kids", 5.2, 25, 620),  # closest volume match
    ]
    for rank_name, db_name, pos, clicks, imp in au_fuzzy:
        row = conn.execute(
            "SELECT id FROM keywords WHERE domain_id=2 AND keyword=? COLLATE NOCASE",
            (db_name,),
        ).fetchone()
        if row:
            if add_ranking(conn, row["id"], pos, clicks, imp):
                added_rankings += 1
                log.info(f"  AU ranking via '{rank_name}' -> '{db_name}' pos={pos}")
        else:
            log.warning(f"  AU keyword not found: {db_name}")

    # Genuinely new AU keywords to add (these don't exist at all in the DB)
    au_new_keywords = [
        ("Giant Bubbles Australia", 480, "brand_general", "commercial", 8.0, 40, 4.2, 14, 300),
        ("Bubble Machine Australia", 210, "product", "commercial", 7.0, 35, 5.8, 4, 90),
        ("Party Bubble Machine", 170, "product", "commercial", 6.5, 30, 6.0, 3, 75),
        ("Bubble Solution Australia", 260, "product", "commercial", 7.5, 35, 6.2, 5, 110),
        ("Kids Bubble Machine", 140, "product", "commercial", 6.0, 30, 6.5, 2, 55),
        ("Bubble Wand Pack", 90, "product", "commercial", 5.5, 25, 7.0, 1, 30),
        ("Bubble Machine For Parties", 140, "product", "commercial", 6.5, 30, 7.5, 2, 40),
    ]
    for kw, vol, cat, intent, opp, diff, pos, clicks, imp in au_new_keywords:
        kid = add_keyword_if_missing(conn, 2, kw, vol, cat, intent, opp, diff)
        added_keywords += 1
        log.info(f"  Added AU keyword: {kw} (id={kid})")
        if pos > 0:
            if add_ranking(conn, kid, pos, clicks, imp):
                added_rankings += 1
                log.info(f"    with ranking pos={pos}")

    conn.commit()
    log.info(f"=== SUMMARY: {added_keywords} new keywords added, {added_rankings} new rankings inserted ===")

    # Final state
    for tbl in ["keywords", "rank_history", "onpage_errors"]:
        c = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        log.info(f"  {tbl}: {c}")

    ranked = conn.execute(
        "SELECT COUNT(DISTINCT keyword_id) as c FROM rank_history WHERE (keyword_id, date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)"
    ).fetchone()[0]
    log.info(f"  keywords with recent rank data: {ranked}")

    conn.close()


if __name__ == "__main__":
    main()
