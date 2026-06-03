#!/usr/bin/env python3
"""
Article Writer v0.4 — Tinka SEO Dashboard Content Pipeline

Generates SEO-optimized articles from content ideas, posts to Shopify as drafts,
and tracks everything in the dashboard DB.

Usage:
  # Post a pre-written article by content_idea_id
  python scripts/article_writer.py --idea 5 --body articles/rotorua.html

  # Post with direct params
  python scripts/article_writer.py --title "My Article" --body "<p>...</p>" --market NZ --keywords "bubbles, fun"

  # List available content ideas
  python scripts/article_writer.py --list-ideas

  # Post to Shopify with a generated article from a DataForSEO-enhanced template
  python scripts/article_writer.py --idea 5 --generate
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")
ENV_PATH = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
SHOPIFY_API_VERSION = "2024-01"
BLOG_ID = 106785898817

# ── DB helpers ─────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def ensure_articles_table():
    """Create the published_articles tracking table if it doesn't exist."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS published_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_idea_id INTEGER REFERENCES content_ideas(id),
            shopify_article_id INTEGER,
            title TEXT NOT NULL,
            market TEXT NOT NULL CHECK(market IN ('NZ', 'AU')),
            target_domain TEXT NOT NULL,
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'published', 'failed')),
            target_keywords TEXT,
            word_count INTEGER DEFAULT 0,
            seo_score REAL,
            shopify_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            published_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_shopify_token():
    """Read Shopify Admin API token from .env."""
    if not os.path.exists(ENV_PATH):
        print("❌ ~/.hermes/.env not found", file=sys.stderr)
        sys.exit(1)
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("SHOPIFY_ADMIN_TOKEN="):
                return line.split("=", 1)[1]
    print("❌ SHOPIFY_ADMIN_TOKEN not found in .env", file=sys.stderr)
    sys.exit(1)

def get_domain_for_market(market):
    """Get the correct domain for the market."""
    conn = get_conn()
    domain_name = "giantbubbles.co.nz" if market == "NZ" else "giantbubblesau.com"
    row = conn.execute("SELECT id FROM domains WHERE name = ?", (domain_name,)).fetchone()
    conn.close()
    if not row:
        print(f"❌ Domain not found for market {market}: {domain_name}", file=sys.stderr)
        sys.exit(1)
    return row["id"], domain_name

# ── Shopify API ────────────────────────────────────────────────────────────────
def post_to_shopify(title, body_html, tags, market, author="Tinka Blog"):
    """Post an article as a draft to the Shopify blog. Returns the article dict."""
    token = get_shopify_token()
    store = "giant-bubbles-by-tinka.myshopify.com"

    # Add market tag for easier filtering in Shopify admin
    all_tags = f"tinka-seo-dashboard, market-{market.lower()}"
    if tags:
        all_tags = f"{all_tags}, {tags}"

    payload = json.dumps({
        "article": {
            "title": title,
            "author": author,
            "tags": all_tags,
            "body_html": body_html,
            "published": False
        }
    })

    url = f"https://{store}/admin/api/{SHOPIFY_API_VERSION}/blogs/{BLOG_ID}/articles.json"
    r = subprocess.run(
        ["curl", "-s", "-X", "POST",
         url,
         "-H", f"X-Shopify-Access-Token: {token}",
         "-H", "Content-Type: application/json",
         "-d", payload],
        capture_output=True, text=True, timeout=30
    )

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"❌ Failed to parse Shopify response: {r.stdout[:300]}", file=sys.stderr)
        return None

    if "article" in data:
        a = data["article"]
        is_published = a.get("published", False) or a.get("published_at") is not None
        print(f"✅ Draft posted to Shopify!")
        print(f"   Title: {a['title']}")
        print(f"   Article ID: {a['id']}")
        print(f"   Published: {is_published}")
        print(f"   Admin URL: https://admin.shopify.com/store/giant-bubbles-by-tinka/admin/articles/{a['id']}")
        print(f"   Handle: {a.get('handle', 'n/a')}")
        return a
    else:
        print(f"❌ Shopify error: {r.stdout[:500]}", file=sys.stderr)
        return None

# ── DB Recording ───────────────────────────────────────────────────────────────
def record_article(content_idea_id, shopify_article_id, title, market,
                   target_domain, tags, body_html):
    """Record a published article in the DB."""
    word_count = len(re.findall(r'\w+', re.sub(r'<[^>]+>', '', body_html)))
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO published_articles
                (content_idea_id, shopify_article_id, title, market,
                 target_domain, status, target_keywords, word_count)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)
        """, (content_idea_id, shopify_article_id, title, market,
              target_domain, tags, word_count))
        conn.commit()
        print(f"📝 Recorded in DB as draft (id: {conn.lastrowid}, word count: {word_count})")

        # Mark the content idea as published
        if content_idea_id:
            conn.execute("UPDATE content_ideas SET status = 'published' WHERE id = ?",
                        (content_idea_id,))
            conn.commit()
            print(f"   Content idea #{content_idea_id} marked as 'published'")
    except Exception as e:
        print(f"❌ DB recording error: {e}", file=sys.stderr)
    finally:
        conn.close()

# ── Article Reading/Generation ────────────────────────────────────────────────
def generate_article_html(title, target_keywords, outline_text, market, domain_name):
    """
    Generate a basic SEO article template with proper HTML structure.
    The outline_text is used to create structured content sections.
    Returns (body_html, tags_string).
    """
    lines = [l.strip() for l in outline_text.split('\n') if l.strip()]
    sections = []
    current_section = []
    for line in lines:
        if any(line.startswith(f"{i}.") for i in range(1, 20)):
            if current_section:
                sections.append(' '.join(current_section))
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(' '.join(current_section))

    # Build sections into reading-friendly body
    # This is a placeholder; the full article content is provided via --body or --generate-with-agent
    return None

# ── CLI ────────────────────────────────────────────────────────────────────────
def list_ideas():
    """List content ideas available for article writing."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, target_keyword, estimated_searches,
               opportunity_score, category, status, effort
        FROM content_ideas
        WHERE status != 'published'
        ORDER BY opportunity_score DESC, estimated_searches DESC
    """).fetchall()
    conn.close()

    if not rows:
        print("No unpublished content ideas found.")
        return

    print(f"\n{'ID':<4} {'Score':<6} {'Volume':<8} {'Effort':<8} {'Category':<20} {'Status':<12} Title")
    print("-" * 100)
    for r in rows:
        title_trunc = (r["title"][:40] + "..") if len(r["title"]) > 42 else r["title"]
        print(f"{r['id']:<4} {r['opportunity_score'] or 0:<6.1f} {r['estimated_searches'] or 0:<8} "
              f"{r['effort'] or 'medium':<8} {r['category'] or '-':<20} {r['status'] or 'draft':<12} {title_trunc}")
    print()

def read_file_content(path):
    """Read HTML/markdown content from a file."""
    full_path = path if os.path.isabs(path) else os.path.join(PROJECT_DIR, path)
    if not os.path.exists(full_path):
        print(f"❌ File not found: {full_path}", file=sys.stderr)
        sys.exit(1)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    parser = argparse.ArgumentParser(description="Tinka SEO Article Writer v0.4")
    parser.add_argument("--idea", type=int, help="Content idea ID from the DB")
    parser.add_argument("--list-ideas", action="store_true", help="List available content ideas")
    parser.add_argument("--title", help="Article title")
    parser.add_argument("--body", help="Path to HTML body file or inline HTML string")
    parser.add_argument("--market", choices=["NZ", "AU"], default="NZ",
                       help="Target market (default: NZ)")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--keywords", help="Comma-separated target keywords")

    args = parser.parse_args()

    if args.list_ideas:
        list_ideas()
        return

    # Ensure the articles tracking table exists
    ensure_articles_table()

    # Load topic details from DB if --idea is provided
    title = args.title
    target_keywords = args.keywords or ""
    outline_text = ""
    content_idea_id = args.idea
    category = "general"

    if args.idea:
        conn = get_conn()
        row = conn.execute("""
            SELECT id, title, target_keyword, estimated_searches,
                   opportunity_score, category, outline, status
            FROM content_ideas WHERE id = ?
        """, (args.idea,)).fetchone()
        conn.close()

        if not row:
            print(f"❌ Content idea #{args.idea} not found")
            sys.exit(1)

        if row["status"] == "published":
            print(f"⚠️ Content idea #{args.idea} already marked as published. Use --force to override.")

        if not title:
            title = row["title"]
        if not target_keywords:
            target_keywords = row["target_keyword"] or ""
        if row["outline"]:
            outline_text = row["outline"]
        if row["category"]:
            category = row["category"]

    if not title:
        print("❌ Title is required (--title or --idea)", file=sys.stderr)
        sys.exit(1)

    # Read body HTML
    if not args.body:
        print("❌ --body is required (path to HTML file)", file=sys.stderr)
        sys.exit(1)

    body_html = read_file_content(args.body)

    # Post to Shopify
    domain_id, domain_name = get_domain_for_market(args.market)
    result = post_to_shopify(title, body_html, args.tags or target_keywords,
                            args.market, author="Tinka Blog")

    if result:
        record_article(content_idea_id, result["id"], result["title"],
                      args.market, domain_name, args.tags or target_keywords, body_html)
        print(f"\n🎉 Article pipeline complete! Check your Shopify admin → Blog Posts (in Drafts)")

if __name__ == "__main__":
    main()
