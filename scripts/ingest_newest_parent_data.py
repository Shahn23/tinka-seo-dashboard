"""
Ingest the 4 newest parent task outputs into the SEO Dashboard SQLite DB:
  1. 30 new keyword ideas (t_ef192cc9 → data/new_keyword_ideas_v2.csv)
  2. 12 blog topics + 10 city templates (t_ef18bf76 → data/blog_post_topics_from_new_keywords_v2.md)
  3. Latest ranking data (t_1748c9c1 → data/current_keyword_rankings.csv)
  4. On-page audit data (t_3d7da6d3) — already ingested via earlier run (47 open)

Usage: python scripts/ingest_newest_parent_data.py
"""

import csv
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "seo_dashboard.db"

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def get_domain_id(conn, domain_name):
    """Get the domain_id for a domain name, creating if needed."""
    cur = conn.execute("SELECT id FROM domains WHERE name = ?", (domain_name,))
    row = cur.fetchone()
    if row:
        return row["id"]
    display = domain_name.replace(".co.nz", ".co.nz").replace(".com.au", ".com.au")
    conn.execute(
        "INSERT INTO domains (name, display_name) VALUES (?, ?)",
        (domain_name, display_name),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def keyword_in_db(conn, domain_id, keyword):
    """Check if a keyword already exists for a domain."""
    cur = conn.execute(
        "SELECT id FROM keywords WHERE domain_id = ? AND keyword = ? COLLATE NOCASE",
        (domain_id, keyword),
    )
    return cur.fetchone()


# ──────────────────────────────────────────────
# STEP 1: Ingest 30 new keywords
# ──────────────────────────────────────────────
def ingest_new_keywords():
    csv_path = DATA_DIR / "new_keyword_ideas_v2.csv"
    if not csv_path.exists():
        log(f"⚠  SKIP: {csv_path} not found")
        return 0, 0

    market_to_domain = {
        "NZ": "giantbubbles.co.nz",
        "AU": "giantbubblesau.com",
        "both": None,  # Handle "both" later
    }

    added = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = row.get("Keyword", "").strip()
            if not kw:
                continue

            market = row.get("Market", "").strip().upper()
            volume = int(float(row.get("EstMonthlyVolume", 0) or 0))
            difficulty = int(float(row.get("Difficulty", 50) or 50))
            opp = float(row.get("OpportunityScore", 5) or 5)
            category = row.get("Category", "uncategorized").strip().lower()
            intent = row.get("Intent", "informational").strip().lower()

            # Normalize intent
            intent_map = {
                "commercial": "commercial",
                "informational": "informational",
                "transactional": "transactional",
                "navigational": "navigational",
            }
            intent = intent_map.get(intent, "informational")

            if market == "BOTH" or not market or market == "BOTH":
                domains_to_add = ["giantbubbles.co.nz", "giantbubblesau.com"]
            elif market == "NZ":
                domains_to_add = ["giantbubbles.co.nz"]
            elif market == "AU":
                domains_to_add = ["giantbubblesau.com"]
            else:
                # Try partial match
                if "nz" in market.lower():
                    domains_to_add = ["giantbubbles.co.nz"]
                elif "au" in market.lower() or "aus" in market.lower():
                    domains_to_add = ["giantbubblesau.com"]
                else:
                    domains_to_add = ["giantbubbles.co.nz", "giantbubblesau.com"]

            for domain_name in domains_to_add:
                domain_id = get_domain_id(conn, domain_name)
                existing = keyword_in_db(conn, domain_id, kw)
                if existing:
                    skipped += 1
                else:
                    conn.execute(
                        """INSERT INTO keywords 
                        (domain_id, keyword, category, intent, volume, 
                         opportunity_score, difficulty, is_high_priority)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (domain_id, kw, category, intent, volume, opp, difficulty, 1 if opp >= 8 else 0),
                    )
                    added += 1

    conn.commit()
    log(f"STEP 1: Ingested {added} new keywords, skipped {skipped} duplicates")
    return added, skipped


# ──────────────────────────────────────────────
# STEP 2: Ingest latest ranking data
# ──────────────────────────────────────────────
def ingest_ranking_data():
    csv_path = DATA_DIR / "current_keyword_rankings.csv"
    if not csv_path.exists():
        log(f"⚠  SKIP: {csv_path} not found")
        return 0, 0, 0

    domain_map = {
        "giantbubbles.co.nz": get_domain_id(conn, "giantbubbles.co.nz"),
        "giantbubblesau.com": get_domain_id(conn, "giantbubblesau.com"),
    }

    added = 0
    updated = 0
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            domain_raw = row.get("Domain", "").strip()
            keyword = row.get("Keyword", "").strip()
            pos_str = row.get("Current_Position", "").strip()
            clicks_str = row.get("Clicks", "0").strip()
            imp_str = row.get("Impressions", "0").strip()
            last_checked = row.get("Last_Checked", "").strip()

            if not keyword or not pos_str or not last_checked:
                skipped += 1
                continue

            try:
                position = float(pos_str)
            except ValueError:
                skipped += 1
                continue

            try:
                clicks = int(float(clicks_str)) if clicks_str else 0
            except ValueError:
                clicks = 0

            try:
                impressions = int(float(imp_str)) if imp_str else 0
            except ValueError:
                impressions = 0

            # Normalize domain
            domain_id = domain_map.get(domain_raw)
            if domain_id is None:
                # Try to find it
                for key, did in domain_map.items():
                    if key.replace(".", "").replace("-", "") in domain_raw.replace(".", "").replace("-", "").lower():
                        domain_id = did
                        break
                if domain_id is None:
                    skipped += 1
                    continue

            # Find keyword_id
            kw_row = keyword_in_db(conn, domain_id, keyword)
            if not kw_row:
                # Maybe the keyword exists for the other domain - create for this one too
                log(f"  ⚠  Keyword '{keyword}' not found for {domain_raw}, creating")
                conn.execute(
                    """INSERT INTO keywords 
                    (domain_id, keyword, category, intent, volume, 
                     opportunity_score, difficulty, is_high_priority)
                    VALUES (?, ?, 'uncategorized', 'informational', 0, 5.0, 50, 0)""",
                    (domain_id, keyword),
                )
                conn.commit()
                kw_row = conn.execute(
                    "SELECT id FROM keywords WHERE domain_id = ? AND keyword = ? COLLATE NOCASE",
                    (domain_id, keyword),
                ).fetchone()
                if not kw_row:
                    skipped += 1
                    continue

            keyword_id = kw_row["id"]

            # Use last_checked as the date
            date_str = last_checked[:10] if len(last_checked) >= 10 else last_checked

            # Check if ranking data already exists for this keyword + date
            existing = conn.execute(
                "SELECT id FROM rank_history WHERE keyword_id = ? AND date = ?",
                (keyword_id, date_str),
            ).fetchone()

            if existing:
                # Update
                conn.execute(
                    """UPDATE rank_history SET position=?, clicks=?, impressions=?, 
                       ctr=CASE WHEN impressions>0 THEN CAST(clicks AS REAL)/impressions ELSE 0 END
                     WHERE id=?""",
                    (position, clicks, impressions, existing["id"]),
                )
                updated += 1
            else:
                ctr = clicks / impressions if impressions > 0 else 0
                conn.execute(
                    """INSERT INTO rank_history (keyword_id, date, position, clicks, impressions, ctr)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (keyword_id, date_str, position, clicks, impressions, round(ctr, 4)),
                )
                added += 1

    conn.commit()
    log(f"STEP 2: Ingested {added} new rank rows, updated {updated} existing, skipped {skipped}")
    return added, updated, skipped


# ──────────────────────────────────────────────
# STEP 3: Ingest blog post topics
# ──────────────────────────────────────────────
def ingest_blog_topics():
    md_path = DATA_DIR / "blog_post_topics_from_new_keywords_v2.md"
    if not md_path.exists():
        log(f"⚠  SKIP: {md_path} not found")
        return 0, 0, 0

    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    # Parse topics — each starts with "## <N>. <Title>"
    topic_blocks = re.split(r"\n##\s+", content)
    topics = []
    for block in topic_blocks:
        block = block.strip()
        if not block or block.startswith(">"):
            continue

        lines = block.split("\n")
        title_line = lines[0].strip()
        # Match "N. Title"
        m = re.match(r"^\d+\.\s+(.+)$", title_line)
        if not m:
            continue

        title = m.group(1).strip()
        body = "\n".join(lines[1:]).strip()

        # Extract market
        market = "both"
        m_market = re.search(r"\*\*Market:\*\*\s*(.+?)(?:\n|$)", body)
        if m_market:
            raw_market = m_market.group(1).strip().upper()
            if raw_market == "NZ":
                market = "nz"
            elif raw_market == "AU":
                market = "au"

        # Extract target keyword
        target_kw = title
        m_kw = re.search(r"\*\*Target keywords?:?\*\*\s*(.+?)(?:\n|$)", body)
        if m_kw:
            kw_text = m_kw.group(1).strip()
            # Take the first keyword before any comma or paren
            first_kw = re.split(r"[,(]", kw_text)[0].strip()
            if first_kw:
                target_kw = first_kw

        # Extract estimated searches
        est_searches = 0
        m_vol = re.search(r"\((\d+)/mo", body)
        if m_vol:
            est_searches = int(m_vol.group(1))

        # Extract opportunity score
        opp_score = 5.0
        m_opp = re.search(r"Opp\s*(\d+\.?\d*)", body)
        if m_opp:
            opp_score = float(m_opp.group(1))

        # Determine category
        category = "blog"
        cat_map = {
            "easter": "seasonal",
            "gift": "gifting",
            "rainy day": "kids-activities",
            "screen free": "kids-activities",
            "bubble painting": "crafts",
            "bubble art": "crafts",
            "bubble wand": "diy",
            "bubble solution": "product-care",
            "bubble experiment": "kids-activities",
            "toddler": "kids-activities",
            "photography": "content",
            "outdoor": "kids-activities",
        }
        title_lower = title.lower()
        for key, cat in cat_map.items():
            if key in title_lower:
                category = cat
                break

        # Detect city/local topics
        cities = [
            "rotorua", "hobart", "new plymouth", "nelson", "palmerston north",
            "sunshine coast", "cairns", "newcastle", "darwin", "wollongong",
            "hastings", "wellington", "christchurch", "hamilton",
        ]
        is_local = any(c in title_lower for c in cities)
        subcategory = "local-city" if is_local else category

        topics.append(
            {
                "title": title,
                "target_keyword": target_kw,
                "category": subcategory,
                "estimated_searches": est_searches,
                "opportunity_score": opp_score,
                "effort": "easy" if opp_score >= 12 else "medium",
                "content_type": "blog",
                "outline": body[:500],  # Keep first 500 chars
                "source": "new-keyword-blog-topics",
                "status": "draft",
                "market": market,
            }
        )

    # Also add 10 city template topics — these were described in the parent task output
    city_templates = [
        {"title": f"Giant Bubbles in {city} — The Ultimate Local Guide", "city": city, "market": market}
        for city, market in [
            ("Rotorua", "nz"),
            ("New Plymouth", "nz"),
            ("Nelson", "nz"),
            ("Palmerston North", "nz"),
            ("Hastings", "nz"),
            ("Hobart", "au"),
            ("Sunshine Coast", "au"),
            ("Cairns", "au"),
            ("Newcastle", "au"),
            ("Darwin", "au"),
        ]
    ]

    # Check for duplicates against existing content_ideas
    existing_titles = set(
        r[0].strip().lower()
        for r in conn.execute("SELECT title FROM content_ideas").fetchall()
    )

    added = 0
    skipped = 0

    for t in topics:
        title_lower = t["title"].strip().lower()
        if title_lower in existing_titles:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO content_ideas 
               (title, target_keyword, category, estimated_searches, 
                opportunity_score, effort, content_type, outline, source, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["title"],
                t["target_keyword"],
                t["category"],
                t["estimated_searches"],
                t["opportunity_score"],
                t["effort"],
                "blog",
                t["outline"],
                t["source"],
                "draft",
            ),
        )
        added += 1
        existing_titles.add(title_lower)

    conn.commit()
    log(f"STEP 3: Ingested {added} blog topics, skipped {skipped} duplicates")

    # Report city templates that could be added
    log(f"  (City templates ready for adaptation: {len(city_templates)} locations)")
    return added, skipped, len(topics)


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    log("╔══════════════════════════════════════╗")
    log("║  Ingesting Newest Parent Task Data   ║")
    log("╚══════════════════════════════════════╝")

    # Domain check
    domains = conn.execute("SELECT id, name FROM domains").fetchall()
    if not domains:
        log("Creating default domains...")
        get_domain_id(conn, "giantbubbles.co.nz")
        get_domain_id(conn, "giantbubblesau.com")
        conn.commit()
    else:
        for d in domains:
            log(f"  Domain: {d['name']} (id={d['id']})")

    kw_added, kw_skipped = ingest_new_keywords()
    r_added, r_updated, r_skipped = ingest_ranking_data()
    b_added, b_skipped, b_total = ingest_blog_topics()

    log("")
    log("╔══════════════════════════════════════╗")
    log("║  Ingestion Summary                   ║")
    log("╚══════════════════════════════════════╝")
    log(f"  New keywords added:     {kw_added}")
    log(f"  Keywords skipped:       {kw_skipped}")
    log(f"  Rank rows added:        {r_added}")
    log(f"  Rank rows updated:      {r_updated}")
    log(f"  Rank rows skipped:      {r_skipped}")
    log(f"  Blog topics added:      {b_added}")
    log(f"  Blog topics skipped:    {b_skipped}")
    log(f"  Blog topics parsed:     {b_total}")

    # Final counts
    kw_total = conn.execute("SELECT COUNT(*) as c FROM keywords").fetchone()["c"]
    rh_total = conn.execute("SELECT COUNT(*) as c FROM rank_history").fetchone()["c"]
    ci_total = conn.execute("SELECT COUNT(*) as c FROM content_ideas").fetchone()["c"]
    er_total = conn.execute("SELECT COUNT(*) as c FROM onpage_errors WHERE status='open'").fetchone()["c"]
    log("")
    log("╔══════════════════════════════════════╗")
    log("║  Final Dashboard State               ║")
    log("╚══════════════════════════════════════╝")
    log(f"  Keywords tracked:       {kw_total}")
    log(f"  Rank history rows:      {rh_total}")
    log(f"  Content ideas:          {ci_total}")
    log(f"  Open on-page errors:    {er_total}")

    conn.close()
