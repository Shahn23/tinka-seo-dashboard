#!/usr/bin/env python3
"""
AI Content Suggestions v1.0 - Tinka SEO Dashboard Content Pipeline

Generates AI-powered content briefs from keywords using OpenRouter,
and reads SERP difficulty/volume data from the local database.

Usage:
  python scripts/ai_content_suggestions.py "giant bubble recipe"
  python scripts/ai_content_suggestions.py "giant bubble recipe" --location NZ --format markdown
  python scripts/ai_content_suggestions.py "party entertainment auckland" --format json
  python scripts/ai_content_suggestions.py "birthday party bubbles" --serp-only
  python scripts/ai_content_suggestions.py --list-keywords
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

# ── OpenRouter config ───────────────────────────────────────────────────────────
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "mistralai/mistral-small-24b-instruct-2501"
FALLBACK_MODEL = "deepseek/deepseek-chat"

# Try several locations for the API key
_ENV_CANDIDATES = [
    os.environ.get("OPENROUTER_API_KEY"),
    os.environ.get("OPENROUTER_KEY"),
]
_SECRET_PATHS = [
    os.path.join(os.path.expanduser("~"), "open-brain", ".env.secrets"),
    os.path.join(os.path.expanduser("~"), ".hermes", ".env"),
    os.path.join(PROJECT_DIR, ".env"),
    os.path.join(os.path.expanduser("~"), ".env"),
]

_OPENROUTER_API_KEY = None


def _load_api_key():
    """Load OpenRouter API key from env vars or secret files."""
    for candidate in _ENV_CANDIDATES:
        if candidate:
            return candidate
    for path in _SECRET_PATHS:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENROUTER_API_KEY="):
                            return line.split("=", 1)[1]
                        if line.startswith("OPENROUTER_KEY="):
                            return line.split("=", 1)[1]
            except (OSError, IOError):
                continue
    return None


# Cache the key at module load
_OPENROUTER_API_KEY = _load_api_key()


# ── DB helpers ──────────────────────────────────────────────────────────────────


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── SERP Analysis ───────────────────────────────────────────────────────────────


def analyze_serp_from_db(keyword):
    """
    Look up a keyword in the local DB and return SERP data including:
    - volume (estimated monthly searches)
    - difficulty (0-100 SEO difficulty score)
    - domain / market info
    - any related content_ideas

    Returns a dict with findings or None if not found.
    """
    conn = get_conn()
    results = {"keyword": keyword, "found": False, "db_matches": []}

    # Search keywords table (flexible matching)
    rows = conn.execute(
        """
        SELECT k.id, k.keyword, k.volume, k.difficulty, k.intent, k.category,
               k.opportunity_score, k.cluster, k.bid,
               d.name AS domain_name
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        WHERE k.keyword LIKE ? OR ? LIKE '%' || k.keyword || '%'
        ORDER BY k.volume DESC
        LIMIT 10
    """,
        (f"%{keyword}%", keyword),
    ).fetchall()

    for r in rows:
        results["db_matches"].append(dict(r))
        results["found"] = True

    # Also check content_ideas for this keyword
    idea_rows = conn.execute(
        """
        SELECT id, title, target_keyword, estimated_searches,
               opportunity_score, category, effort, content_type, status
        FROM content_ideas
        WHERE target_keyword LIKE ? OR title LIKE ?
        LIMIT 5
    """,
        (f"%{keyword}%", f"%{keyword}%"),
    ).fetchall()

    results["content_ideas"] = [dict(r) for r in idea_rows]
    conn.close()
    return results


def format_serp_analysis(results, fmt="markdown"):
    """Format SERP analysis results for display."""
    if fmt == "json":
        return json.dumps(results, indent=2, default=str)

    lines = []
    lines.append("## SERP Analysis from Local Database")
    lines.append("")

    if not results["found"]:
        lines.append(
            f":warning:  No direct DB match for '{results['keyword']}'. "
            "Consider adding this keyword to the dashboard."
        )
        return "\n".join(lines)

    for match in results["db_matches"]:
        lines.append(f"### Keyword: `{match['keyword']}`")
        lines.append(f"- **Volume:** {match.get('volume', 'N/A')} searches/mo")
        lines.append(
            f"- **Difficulty:** {match.get('difficulty', 'N/A')}"
            f"{' (0-100)' if match.get('difficulty') is not None else ''}"
        )
        lines.append(
            f"- **Intent:** {match.get('intent', 'N/A')}"
        )
        lines.append(
            f"- **Opportunity Score:** {match.get('opportunity_score', 'N/A')}"
        )
        lines.append(f"- **Domain:** {match.get('domain_name', 'N/A')}")
        lines.append(f"- **Cluster:** {match.get('cluster', 'N/A')}")
        lines.append("")

    if results["content_ideas"]:
        lines.append("### Related Content Ideas")
        for idea in results["content_ideas"]:
            lines.append(
                f"- **#{idea['id']}** {idea['title']} "
                f"(kw: `{idea['target_keyword']}`, "
                f"vol: {idea.get('estimated_searches', 'N/A')}, "
                f"score: {idea.get('opportunity_score', 'N/A')})"
            )
        lines.append("")

    return "\n".join(lines)


# ── AI Content Brief Generation ────────────────────────────────────────────────


def call_openrouter(prompt, system_prompt=None, model=None, max_tokens=2000):
    """
    Call the OpenRouter API with a prompt using curl subprocess.
    Returns the response text or raises on error.
    """
    api_key = _OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY not found. Set it in your environment or in "
            "~/.hermes/.env or ~/open-brain/.env.secrets"
        )

    model = model or DEFAULT_MODEL
    system_prompt = system_prompt or "You are an expert SEO content strategist."

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }

    payload_json = json.dumps(payload)
    temp_file = os.path.join(PROJECT_DIR, ".openrouter_payload.json")
    with open(temp_file, "w") as f:
        f.write(payload_json)

    # Use a variable to hold the key to avoid direct inline reference
    bearer_token = f"Bearer {api_key}"

    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        f"{OPENROUTER_API_BASE}/chat/completions",
        "-H", f"Authorization: {bearer_token}",
        "-H", "Content-Type: application/json",
        "-d", f"@{temp_file}",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("OpenRouter API call timed out after 60s")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")

    # Last line is HTTP status code
    parts = result.stdout.strip().rsplit("\n", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected curl output: {result.stdout[:300]}")

    body, status_code = parts
    try:
        status_code = int(status_code)
    except ValueError:
        raise RuntimeError(f"Non-numeric status code: {status_code}")

    if status_code != 200:
        error_detail = body[:500] if body.strip() else "no body"
        raise RuntimeError(
            f"OpenRouter API error (HTTP {status_code}): {error_detail}"
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse OpenRouter response: {e}\nBody: {body[:300]}")

    if "error" in data:
        raise RuntimeError(
            f"OpenRouter API error: {data['error'].get('message', data['error'])}"
        )

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices returned from OpenRouter")

    return choices[0]["message"]["content"]


def generate_brief(keyword, location="NZ", model=None):
    """
    Generate an AI content brief for a given keyword.

    Returns a dict with:
    - title_options: list of 3-5 SEO-optimised title suggestions
    - suggested_h2s: list of suggested H2 subheadings
    - key_points: list of key points / talking points to cover
    - target_word_count: recommended word count
    - location: the target market
    """
    prompt = f"""Generate a detailed SEO content brief for the keyword "{keyword}" targeting the {location} market.

Return your response STRICTLY as a JSON object with these exact keys:
- title_options: a list of 3-5 SEO-optimised article title suggestions
- suggested_h2s: a list of 6-10 suggested H2 subheadings that cover the topic comprehensively
- key_points: a list of 5-8 key talking points or facts to include
- target_word_count: an integer suggesting the ideal word count for a well-optimised article

Example format:
{{
    "title_options": ["Title 1", "Title 2", "Title 3"],
    "suggested_h2s": ["H2 1", "H2 2"],
    "key_points": ["Point 1", "Point 2"],
    "target_word_count": 1500
}}

Be specific, actionable, and SEO-aware. Include long-tail keyword opportunities where relevant.
For the {location} market, mention local relevance if applicable.
Return ONLY the JSON object, no other text."""

    system_prompt = (
        "You are an expert SEO content strategist with deep knowledge of "
        "search optimisation, content planning, and the NZ/AU markets. "
        "You always return valid JSON."
    )

    raw = call_openrouter(prompt, system_prompt=system_prompt, model=model)

    # Try to parse as JSON
    # Handle potential markdown code block wrapping
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Extract JSON from code block
        lines = cleaned.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            cleaned = "\n".join(json_lines)

    try:
        brief = json.loads(cleaned)
    except json.JSONDecodeError:
        # If JSON parsing fails, try to salvage by finding JSON-like content
        import re
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            try:
                brief = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                brief = _build_fallback_brief(keyword, raw)
        else:
            brief = _build_fallback_brief(keyword, raw)

    # Ensure all expected keys exist
    brief.setdefault("title_options", [f"Complete Guide to {keyword.title()}"])
    brief.setdefault("suggested_h2s", [])
    brief.setdefault("key_points", [])
    brief.setdefault("target_word_count", 1500)
    brief["keyword"] = keyword
    brief["location"] = location
    brief["generated_at"] = datetime.now().isoformat()

    return brief


def _build_fallback_brief(keyword, raw_text):
    """Build a basic brief from raw text if JSON parsing fails."""
    return {
        "title_options": [
            f"The Ultimate Guide to {keyword.title()}",
            f"10 Tips for {keyword.title()}",
            f"How to Master {keyword.title()}",
        ],
        "suggested_h2s": [
            f"What is {keyword.title()}?",
            "Why It Matters",
            "Step-by-Step Guide",
            "Common Mistakes to Avoid",
            "Expert Tips",
            "Frequently Asked Questions",
        ],
        "key_points": [
            "Explain the basics clearly",
            "Include actionable steps",
            "Address common misconceptions",
            "Provide expert insights",
        ],
        "target_word_count": 1500,
        "_parse_warning": "JSON parsing failed; using fallback structure",
        "_raw_response": raw_text[:500],
    }


# ── Display formatting ─────────────────────────────────────────────────────────


def format_brief(brief, fmt="markdown"):
    """Format a content brief for CLI display."""
    if fmt == "json":
        return json.dumps(brief, indent=2, default=str)

    lines = []
    lines.append(f"# Content Brief: `{brief['keyword']}`")
    lines.append(f"**Target Market:** {brief['location']}")
    lines.append(f"**Generated:** {brief.get('generated_at', 'now')}")
    lines.append("")

    # Title options
    lines.append("## :label: Title Options")
    for i, title in enumerate(brief.get("title_options", []), 1):
        lines.append(f"{i}. {title}")
    lines.append("")

    # Word count
    lines.append(
        f"**Recommended Word Count:** {brief.get('target_word_count', 'N/A')} words"
    )
    lines.append("")

    # Suggested H2s
    lines.append("## :bookmark_tabs: Suggested H2 Headings")
    for h2 in brief.get("suggested_h2s", []):
        lines.append(f"- `{h2}`")
    lines.append("")

    # Key points
    lines.append("## :bulb: Key Points to Cover")
    for point in brief.get("key_points", []):
        lines.append(f"- {point}")
    lines.append("")

    if brief.get("_parse_warning"):
        lines.append("---")
        lines.append(f":warning: Note: {brief['_parse_warning']}")
        lines.append("")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────


def list_keywords(limit=20):
    """List top keywords from the DB for reference."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT k.keyword, k.volume, k.difficulty, k.opportunity_score,
               d.name AS domain
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        ORDER BY k.volume DESC
        LIMIT ?
    """,
        (limit,),
    ).fetchall()
    conn.close()

    if not rows:
        print("No keywords found in the database.")
        return

    print(f"\n{'Keyword':<35} {'Volume':<8} {'Diff':<6} {'Score':<6} Domain")
    print("-" * 75)
    for r in rows:
        kw = r["keyword"][:34] if len(r["keyword"]) > 34 else r["keyword"]
        vol = r["volume"] or 0
        diff = r["difficulty"] if r["difficulty"] is not None else "-"
        score = r["opportunity_score"] if r["opportunity_score"] is not None else "-"
        print(f"{kw:<35} {vol:<8} {str(diff):<6} {str(score):<6} {r['domain']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Tinka SEO AI Content Suggestions v1.0"
    )
    parser.add_argument("keyword", nargs="?", help="Keyword to generate a content brief for")
    parser.add_argument(
        "--location", "-l",
        default="NZ",
        choices=["NZ", "AU"],
        help="Target market (default: NZ)",
    )
    parser.add_argument(
        "--format", "-f",
        default="markdown",
        choices=["markdown", "json"],
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--serp-only",
        action="store_true",
        help="Only show SERP data from DB, skip AI generation",
    )
    parser.add_argument(
        "--list-keywords",
        action="store_true",
        help="List top keywords in the database",
    )
    parser.add_argument(
        "--model",
        help=f"OpenRouter model to use (default: {DEFAULT_MODEL})",
    )

    args = parser.parse_args()

    if args.list_keywords:
        list_keywords()
        return

    if not args.keyword:
        parser.print_help()
        sys.exit(1)

    keyword = args.keyword.strip()

    # ── Step 1: SERP Analysis ──────────────────────────────────────────────
    print("🔍 Analyzing keyword in local database...", file=sys.stderr)
    serp_data = analyze_serp_from_db(keyword)
    print(format_serp_analysis(serp_data, fmt=args.format))
    print()  # blank line

    if args.serp_only:
        return

    # ── Step 2: AI Content Brief ───────────────────────────────────────────
    print("🤖 Generating AI content brief via OpenRouter...", file=sys.stderr)
    print(f"   Model: {args.model or DEFAULT_MODEL}", file=sys.stderr)
    print(f"   Market: {args.location}", file=sys.stderr)

    try:
        brief = generate_brief(keyword, location=args.location, model=args.model)
    except RuntimeError as e:
        print(f"\n❌ Failed to generate content brief: {e}", file=sys.stderr)
        sys.exit(1)

    print()  # separator
    print(format_brief(brief, fmt=args.format))

    # Add SERP enrichment if available in markdown mode
    if args.format == "markdown" and serp_data["found"]:
        print("---")
        print("### 📊 SERP Enrichment")
        for match in serp_data["db_matches"]:
            vol = match.get("volume", "?")
            diff = match.get("difficulty", "?")
            score = match.get("opportunity_score", "?")
            print(f"- Keyword `{match['keyword']}`: {vol} searches/mo, "
                  f"difficulty {diff}, opportunity {score}")

    print()
    print("✅ Content brief generated successfully!", file=sys.stderr)


if __name__ == "__main__":
    main()
