#!/usr/bin/env python3
"""AI Generator Module — Keyword & Article Idea Generation via OpenRouter/DeepSeek.

Used by the dashboard for inline generation of:
- Keyword ideas from a topic/seed
- Article/blog post ideas from keywords
- Full article bodies (SEO-optimized HTML)

No em dashes ever — uses hyphens only.
"""

import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

# ── OpenRouter config (read from open-brain secrets) ─────────────────────────
def get_openrouter_key():
    """Try multiple locations for the OpenRouter API key."""
    candidates = [
        os.path.join(os.path.expanduser("~"), "open-brain", ".env.secrets"),
        os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val and val != "***":
                            return val
    return None

def ask_ai(system_prompt, user_prompt, model="deepseek/deepseek-chat"):
    """Call OpenRouter AI and return the response text."""
    key = get_openrouter_key()
    if not key:
        return None

    payload = json.dumps({
        "model": model,
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
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tinka-seo-dashboard.vercel.app",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


# ── Keyword Generation ──────────────────────────────────────────────────────
def generate_keywords(topic, market="NZ", count=15):
    """Generate keyword ideas from a topic seed. Returns a list of dicts."""
    system = """You are an SEO keyword research expert. Generate realistic, high-quality keyword ideas.

Rules:
- Return ONLY valid JSON array - no markdown, no code fences, no explanation
- Each item: {"keyword": "phrase", "volume": 100, "difficulty": 25, "intent": "informational|commercial|navigational|transactional", "category": "category_name"}
- Volume: realistic monthly search count (10-2000 range)
- Difficulty: 1-100 scale (higher = harder to rank)
- Intent: one of informational/commercial/navigational/transactional
- Category: e.g. "products", "parties", "educational", "local", "reviews"
- Use hyphens NOT em dashes in any generated text
- Keywords should be in English and relevant to the market specified
- Include a mix of head terms (high volume) and long-tail (low competition)
- Make sure keywords are realistic and research-backed"""

    user = f"""Market: {'New Zealand' if market.upper() == 'NZ' else 'Australia'}
Topic: {topic}
Domain: giantbubbles.co.nz (NZ) / giantbubblesau.com (AU)

Generate {count} keyword ideas for a giant bubble product business. Include keywords related to:
- Giant bubble kits and accessories (product-focused)
- Party planning and events (commercial)
- Outdoor activities and kids entertainment (informational)
- Local/regional specific keywords (local)
- Comparisons and reviews (commercial)
- Educational and school activities (educational)

Return a JSON array with {count} objects."""

    raw = ask_ai(system, user)
    if not raw:
        return []
    if raw.startswith("ERROR"):
        print(f"AI error: {raw}", file=sys.stderr)
        return []

    # Strip code fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())

    try:
        results = json.loads(raw)
        if isinstance(results, list):
            return results
        return []
    except json.JSONDecodeError:
        print(f"Failed to parse AI response: {raw[:200]}", file=sys.stderr)
        return []


# ── Article Idea Generation ─────────────────────────────────────────────────
def generate_article_ideas(keywords_or_topic, count=10):
    """Generate article/blog post ideas from keywords or topics. Returns list of dicts."""
    system = """You are an SEO content strategist. Generate article/blog post ideas with detailed outlines.

Rules:
- Return ONLY valid JSON array - no markdown, no code fences
- Each item: {"title": "Article Title", "target_keyword": "main keyword", "category": "category", "estimated_searches": 500, "opportunity_score": 8.5, "effort": "easy|medium|hard", "outline": "1. Intro\\n2. Section 1\\n3. Section 2\\n4. Conclusion", "content_type": "blog|guide|list|howto"}
- opportunity_score: 1-10 (higher = better ROI)
- Use hyphens NOT em dashes in titles and outlines
- Titles should be compelling, SEO-optimized, and under 70 chars
- Include a mix of easy wins and high-impact pieces
- Target keywords should have realistic search volume estimates"""

    user = f"""Generate {count} article/blog post ideas for a giant bubble product business.
    
Source topics/keywords: {keywords_or_topic}

The business sells giant bubble kits in NZ (giantbubbles.co.nz) and AU (giantbubblesau.com).

Cover these angles:
- How-to guides and tutorials
- Local/regional guides (city-specific)
- Product comparisons and reviews
- Party planning and events
- Science/educational content
- Seasonal and occasion-based content

Return JSON array of {count} article ideas."""

    raw = ask_ai(system, user)
    if not raw:
        return []
    if raw.startswith("ERROR"):
        print(f"AI error: {raw}", file=sys.stderr)
        return []

    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())

    try:
        results = json.loads(raw)
        if isinstance(results, list):
            return results
        return []
    except json.JSONDecodeError:
        print(f"Failed to parse AI response: {raw[:200]}", file=sys.stderr)
        return []


# ── Full Article Generation ────────────────────────────────────────────────
def generate_article_body(title, target_keyword, outline=None, market="NZ"):
    """Generate a full SEO-optimized HTML article body."""
    outline_text = outline or "Create a comprehensive guide"

    system = """You are an expert SEO content writer. Write a full HTML article body.

Rules:
- Write SEO-optimized article body HTML only - NO markdown, NO code fences
- Start with <h2> (h1 is the page title, don't include it)
- Use proper heading hierarchy: <h2>, <h3>
- Include the target keyword in the first 100 words
- Include related LSI keywords naturally
- Use short paragraphs (2-4 sentences)
- Use <ul>/<ol> for lists where appropriate
- Use hyphens NOT em dashes in all text
- Target length: 1200-1800 words
- No JavaScript, no CSS, no <html> or <body> tags
- Include a FAQ section with <h2>FAQ</h2> and 3-5 Q&A items
- Include a call-to-action at the end mentioning Tinka's products
- Make it genuinely useful and readable, not keyword-stuffed"""

    user = f"""Write a complete SEO-optimized HTML article for a giant bubble product blog.
Market: {'New Zealand' if market.upper() == 'NZ' else 'Australia'}
Title: {title}
Target Keyword: {target_keyword}
Outline: {outline_text}

The brand is "Tinka" and the website sells giant bubble kits.
Include relevant local references for the market."""

    raw = ask_ai(system, user)
    if not raw:
        return "<p>Article generation failed. Please try again.</p>"
    if raw.startswith("ERROR"):
        return f"<p>AI error: {raw}</p>"

    # Strip code fences
    raw = re.sub(r'^```(?:html)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    return raw


# ── CLI Entry Point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Generator for Tinka SEO Dashboard")
    parser.add_argument("--generate-keywords", help="Topic to generate keywords for")
    parser.add_argument("--generate-articles", help="Keywords/topic to generate article ideas for")
    parser.add_argument("--generate-body", help="Title for full article body generation")
    parser.add_argument("--keyword", help="Target keyword (used with --generate-body)")
    parser.add_argument("--outline", help="Optional outline (used with --generate-body)")
    parser.add_argument("--market", default="NZ", choices=["NZ", "AU"])
    parser.add_argument("--count", type=int, default=10, help="Number of results")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.generate_keywords:
        results = generate_keywords(args.generate_keywords, args.market, args.count)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nGenerated {len(results)} keyword ideas:\n")
            for i, kw in enumerate(results, 1):
                print(f"{i:2d}. {kw['keyword']:40s} Vol:{kw.get('volume',0):>5d}  Diff:{kw.get('difficulty',0):>3d}  [{kw.get('intent','')}]")

    elif args.generate_articles:
        results = generate_article_ideas(args.generate_articles, args.count)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\nGenerated {len(results)} article ideas:\n")
            for i, idea in enumerate(results, 1):
                print(f"{i:2d}. {idea['title'][:60]:60s} Score:{idea.get('opportunity_score',0):.1f}  Effort:{idea.get('effort','')}")

    elif args.generate_body:
        body = generate_article_body(args.generate_body, args.keyword or "", args.outline, args.market)
        print(body)
    else:
        parser.print_help()
