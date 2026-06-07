#!/usr/bin/env python3
"""
Auto-Publish — Generate and publish articles from content_ideas via OpenRouter + Shopify.

Reads content_ideas with stage='writing' or 'editing', generates an SEO-optimised
article via OpenRouter (deepseek/deepseek-chat), and posts it as a draft to the
Shopify blog (giant-bubbles-by-tinka.myshopify.com, blog 106785898817).

Usage:
  python scripts/auto_publish.py --dry-run    # Show what would be published
  python scripts/auto_publish.py               # Publish the first ready article

Requires (via .env or dotenv):
  SHOPIFY_ADMIN_TOKEN=<your-shopify-admin-token>
  OPENROUTER_API_KEY=<your-openrouter-key>
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime

import dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")
ENV_CANDIDATES = [
    os.path.join(PROJECT_DIR, ".env"),
    os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
    os.path.join(os.path.expanduser("~"), "open-brain", ".env.secrets"),
]
SHOPIFY_API_VERSION = "2024-01"
BLOG_ID = 106785898817
STORE = "giant-bubbles-by-tinka.myshopify.com"
DEFAULT_MARKET = "NZ"

# ── Config loading (dotenv-first, fallback to raw file) ──────────────────────
def load_config():
    """Load SHOPIFY_ADMIN_TOKEN and OPENROUTER_API_KEY from env or secret files."""
    # Try dotenv on each candidate
    for p in ENV_CANDIDATES:
        if os.path.exists(p):
            dotenv.load_dotenv(p)

    shopify_token = os.getenv("SHOPIFY_ADMIN_TOKEN")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    # Fallback: raw file scraping
    if not shopify_token or not openrouter_key:
        for p in ENV_CANDIDATES:
            if not os.path.exists(p):
                continue
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SHOPIFY_ADMIN_TOKEN=") and not shopify_token:
                        shopify_token = line.split("=", 1)[1].strip().strip("'\"")
                    elif line.startswith("OPENROUTER_API_KEY=") and not openrouter_key:
                        openrouter_key = line.split("=", 1)[1].strip().strip("'\"")

    if not shopify_token:
        print("❌ SHOPIFY_ADMIN_TOKEN not found in any .env / secrets file", file=sys.stderr)
        sys.exit(1)
    if not openrouter_key:
        print("❌ OPENROUTER_API_KEY not found in any .env / secrets file", file=sys.stderr)
        sys.exit(1)

    return shopify_token, openrouter_key


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_ready_ideas():
    """Return content_ideas with stage='writing' or 'editing', ordered by priority."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, target_keyword, category, estimated_searches,
               opportunity_score, effort, outline, content_type, stage
        FROM content_ideas
        WHERE stage IN ('writing', 'editing')
        ORDER BY
            CASE stage WHEN 'writing' THEN 1 WHEN 'editing' THEN 2 ELSE 3 END,
            opportunity_score DESC,
            estimated_searches DESC
    """).fetchall()
    conn.close()
    return rows


def get_domain_for_market(market):
    """Get domain id and name for a market."""
    conn = get_conn()
    domain_name = "giantbubbles.co.nz" if market == "NZ" else "giantbubblesau.com"
    row = conn.execute("SELECT id, name FROM domains WHERE name = ?", (domain_name,)).fetchone()
    conn.close()
    if not row:
        print(f"⚠️  Domain not found for market {market}: {domain_name}, using fallback", file=sys.stderr)
        return None, domain_name
    return row["id"], row["name"]


def infer_market(idea):
    """Try to infer the target market from the idea data. Defaults to NZ."""
    keyword = (idea["target_keyword"] or "").lower()
    title = (idea["title"] or "").lower()
    category = (idea["category"] or "").lower()
    combined = f"{keyword} {title} {category}"
    if any(x in combined for x in ["au ", "australia", "aussie", "sydney", "melbourne",
                                     "brisbane", "perth", "auckland"]):
        return "AU"
    return DEFAULT_MARKET


# ── OpenRouter article generation ─────────────────────────────────────────────
def generate_article(title, target_keyword, outline, category, openrouter_key):
    """Call OpenRouter to generate an SEO-optimised blog article. Returns (body_html, tags)."""
    system_prompt = """You are an expert SEO content writer for Giant Bubbles By Tinka, a New Zealand
and Australia based company that sells giant bubble kits and accessories.

Generate a complete, publication-ready blog article in HTML format.

RULES:
- Return ONLY the HTML content — no markdown fences, no explanations, no wrapper text.
- Use <h2> for section headings, <h3> for subsections.
- Write 800-1500 words of high-quality, original content.
- Include natural keyword placement (primary and related keywords).
- Use short paragraphs, bullet lists (<ul><li>), and bold (<strong>) for emphasis.
- NO em dashes — use hyphens only.
- Include a compelling introduction paragraph and a conclusion/call-to-action.
- The tone should be friendly, helpful, and enthusiastic about bubbles.
- Ensure all links are placeholders or omitted — do not include actual URLs.
- Wrap everything in a single <div> (no <html>/<body> tags)."""

    user_prompt = f"""Write an SEO blog article with the following specifications:

Title: {title}
Primary Keyword: {target_keyword or '(none specified)'}
Category: {category or 'General'}
"""

    if outline:
        user_prompt += f"\nUse this outline/structure:\n{outline}\n"

    user_prompt += """
Return ONLY the HTML content, starting with an <h1> for the article title.
Include appropriate heading hierarchy and SEO-friendly formatting.
No explanations, no markdown code fences — just raw HTML."""

    payload = json.dumps({
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
    }).encode()

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tinka-seo-dashboard.vercel.app",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
    except Exception as e:
        return None, None, f"OpenRouter API error: {e}"

    # Strip potential markdown fences
    content = content.strip()
    if content.startswith("```html"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Build tags
    tags = f"tinka-seo-dashboard, market-{DEFAULT_MARKET.lower()}"
    if target_keyword:
        tags += f", {target_keyword}"
    if category:
        tags += f", {category}"

    return content, tags, None


# ── Shopify API (using urllib — no external HTTP lib needed) ──────────────────
def post_to_shopify(title, body_html, tags, market, shopify_token):
    """Post an article as a draft to the Shopify blog via Admin REST API.
    Returns the article dict on success, or None on error."""
    all_tags = f"tinka-seo-dashboard, auto-publish, market-{market.lower()}"
    if tags:
        all_tags = f"{all_tags}, {tags}"

    payload = json.dumps({
        "article": {
            "title": title,
            "author": "Tinka Blog",
            "tags": all_tags,
            "body_html": body_html,
            "published": False,
        }
    }).encode()

    url = f"https://{STORE}/admin/api/{SHOPIFY_API_VERSION}/blogs/{BLOG_ID}/articles.json"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-Shopify-Access-Token": shopify_token,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"❌ Shopify HTTP {e.code}: {body[:500]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Shopify request error: {e}", file=sys.stderr)
        return None

    if "article" not in data:
        print(f"❌ Unexpected Shopify response: {json.dumps(data)[:300]}", file=sys.stderr)
        return None

    return data["article"]


def record_article(content_idea_id, shopify_article_id, title, market,
                   target_domain, tags, body_html, shopify_url=None):
    """Record the published article in the DB and update the content_idea stage."""
    word_count = len(re.findall(r"\w+", re.sub(r"<[^>]+>", "", body_html)))
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO published_articles
                (content_idea_id, shopify_article_id, title, market,
                 target_domain, status, target_keywords, word_count, shopify_url)
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?)
        """, (content_idea_id, shopify_article_id, title, market,
              target_domain, tags, word_count, shopify_url))
        conn.commit()
        article_db_id = conn.lastrowid
        print(f"📝 Recorded in DB as draft (id: {article_db_id}, words: {word_count})")

        # Update the content_idea stage to 'published'
        if content_idea_id:
            conn.execute(
                "UPDATE content_ideas SET stage = 'published', status = 'published' WHERE id = ?",
                (content_idea_id,),
            )
            conn.commit()
            print(f"   Content idea #{content_idea_id} marked as stage='published'")
    except Exception as e:
        print(f"❌ DB recording error: {e}", file=sys.stderr)
    finally:
        conn.close()


# ── Core publish function ─────────────────────────────────────────────────────
def publish_next_article(dry_run=False):
    """
    Find the highest-priority content_idea with stage='writing' or 'editing',
    generate the article via OpenRouter, post to Shopify, and record in the DB.

    Args:
        dry_run: If True, only show what would be published without doing it.

    Returns:
        dict with keys: success (bool), idea_id (int or None), title (str or None),
                        shopify_url (str or None), error (str or None)
    """
    print(f"{'🔍 DRY RUN' if dry_run else '🤖 Auto-Publish'} — checking content pipeline...\n")

    # ── 1. Load config ───────────────────────────────────────────────────────
    shopify_token, openrouter_key = load_config()

    # ── 2. Find ready ideas ──────────────────────────────────────────────────
    ideas = get_ready_ideas()
    if not ideas:
        msg = "No content ideas with stage='writing' or 'editing' found."
        print(f"ℹ️  {msg}")
        return {"success": False, "idea_id": None, "title": None,
                "shopify_url": None, "error": msg}

    idea = ideas[0]
    total = len(ideas)
    print(f"📋 Found {total} ready idea(s). Processing the highest-priority one:\n")
    print(f"   ID:        {idea['id']}")
    print(f"   Title:     {idea['title']}")
    print(f"   Keyword:   {idea['target_keyword'] or '(none)'}")
    print(f"   Stage:     {idea['stage']}")
    print(f"   Category:  {idea['category'] or '(none)'}")
    print(f"   Score:     {idea['opportunity_score'] or 'N/A'}")
    print(f"   Effort:    {idea['effort'] or 'N/A'}")
    if idea['outline']:
        outline_preview = idea['outline'][:200]
        if len(idea['outline']) > 200:
            outline_preview += "..."
        print(f"   Outline:   {outline_preview}")

    if dry_run:
        print(f"\n✅ Dry-run complete. Would generate and publish this article next.")
        return {"success": True, "idea_id": idea["id"], "title": idea["title"],
                "shopify_url": None, "error": None, "dry_run": True}

    # ── 3. Generate article via OpenRouter ──────────────────────────────────
    print(f"\n✍️  Generating article via OpenRouter...")
    body_html, tags, error = generate_article(
        idea["title"], idea["target_keyword"], idea["outline"],
        idea["category"], openrouter_key,
    )
    if error or not body_html:
        print(f"❌ Article generation failed: {error}", file=sys.stderr)
        return {"success": False, "idea_id": idea["id"], "title": idea["title"],
                "shopify_url": None, "error": error or "Empty response from OpenRouter"}
    word_count = len(re.findall(r"\w+", re.sub(r"<[^>]+>", "", body_html)))
    print(f"✅ Article generated ({word_count} words)")

    # ── 4. Infer market ──────────────────────────────────────────────────────
    market = infer_market(idea)
    domain_id, domain_name = get_domain_for_market(market)
    print(f"   Market: {market}, Domain: {domain_name}")
    tags_combined = tags if tags else idea.get("target_keyword", "")

    # ── 5. Post to Shopify ───────────────────────────────────────────────────
    print(f"   Posting to Shopify (blog #{BLOG_ID})...")
    article = post_to_shopify(idea["title"], body_html, tags_combined, market, shopify_token)
    if not article:
        msg = "Failed to post article to Shopify."
        print(f"❌ {msg}", file=sys.stderr)
        return {"success": False, "idea_id": idea["id"], "title": idea["title"],
                "shopify_url": None, "error": msg}

    article_id = article["id"]
    admin_url = f"https://admin.shopify.com/store/giant-bubbles-by-tinka/admin/articles/{article_id}"
    shopify_url = article.get("handle")
    if shopify_url:
        shopify_url = f"https://{STORE}/blogs/blog/{shopify_url}"
    print(f"✅ Article posted to Shopify!")
    print(f"   Shopify Article ID: {article_id}")
    print(f"   Admin URL: {admin_url}")
    published = article.get("published", False) or article.get("published_at") is not None
    print(f"   Published: {published}")
    if shopify_url:
        print(f"   URL: {shopify_url}")

    # ── 6. Record in DB ─────────────────────────────────────────────────────
    record_article(idea["id"], article_id, article["title"],
                   market, domain_name, tags_combined, body_html, shopify_url)

    print(f"\n🎉 Auto-publish complete! Check your Shopify admin → Blog Posts.")
    return {
        "success": True,
        "idea_id": idea["id"],
        "title": article["title"],
        "shopify_url": admin_url,
        "error": None,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Auto-Publish — Generate and publish articles from content_ideas"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be published without actually doing it"
    )
    args = parser.parse_args()

    result = publish_next_article(dry_run=args.dry_run)

    if args.dry_run:
        return

    if result.get("success"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
