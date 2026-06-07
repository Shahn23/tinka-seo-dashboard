"""
Content Scoring — evaluate article body against a target keyword.

Scores 0-100 based on keyword placement, density, and word count.
Also provides a DB helper to estimate recommended word count from
keyword search volumes.

Scoring breakdown:
    keyword_in_title       — 20 pts
    keyword_in_h1          — 15 pts
    keyword_in_first_100   — 10 pts
    keyword_density        — 15 pts  (1-3 % target)
    word_count_vs_serp_avg — 10 pts  (within 70-130 % of recommended)

Usage:
    from scripts.content_scorer import score_content, estimate_recommended_word_count

    result = score_content("keyword here", article_body)
    print(result["score"], result["breakdown"], result["recommendations"])

    recommended_wc = estimate_recommended_word_count()
    print(f"Recommended word count: {recommended_wc}")
"""

import re
import os
import sqlite3
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")


# ── DB helper ──────────────────────────────────────────────────────────────────

def estimate_recommended_word_count(db_path: Optional[str] = None) -> int:
    """Estimate a recommended word count from the DB.

    Averages the volumes of the top 20 keywords (highest volume) and maps
    the result to a reasonable word-count range:

        avg_volume < 100    →  800 words
        avg_volume 100-500  → 1200 words
        avg_volume 500-2000 → 1800 words
        avg_volume > 2000   → 2500 words

    Falls back to 1500 if the DB is empty or unreachable.
    """
    path = db_path or DB_PATH
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        # Average volume of top 20 keywords by volume (non-zero)
        row = conn.execute(
            """
            SELECT AVG(volume) AS avg_vol
            FROM (
                SELECT volume FROM keywords
                WHERE volume IS NOT NULL AND volume > 0
                ORDER BY volume DESC
                LIMIT 20
            )
            """
        ).fetchone()
        conn.close()

        avg_vol = row["avg_vol"] if row and row["avg_vol"] is not None else 0
    except Exception:
        avg_vol = 0

    if avg_vol < 100:
        return 800
    elif avg_vol < 500:
        return 1200
    elif avg_vol < 2000:
        return 1800
    else:
        return 2500


# ── Text extraction helpers ────────────────────────────────────────────────────

def _extract_title(text: str) -> str:
    """Extract page title from markdown, HTML, or plain text."""
    # HTML <title> tag
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # Markdown H1 (# Title)
    m = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # First non-empty line (assumed title)
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _extract_h1(text: str) -> str:
    """Extract the first H1 from HTML or markdown."""
    # HTML <h1> tag
    m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r'<[^>]+>', '', m.group(1)).strip()
    # Markdown H1
    m = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def _strip_html(text: str) -> str:
    """Remove HTML tags for plain-text analysis."""
    return re.sub(r'<[^>]+>', ' ', text)


def _count_words(text: str) -> int:
    """Number of whitespace-separated words in text."""
    return len(text.split())


def _keyword_occurrences(keyword: str, text: str) -> int:
    """Case-insensitive count of keyword occurrences in text."""
    pattern = re.escape(keyword.strip())
    return len(re.findall(pattern, text, re.IGNORECASE))


def _first_n_words(text: str, n: int) -> str:
    """Return the first *n* whitespace-separated words."""
    words = text.split()
    return " ".join(words[:n])


# ── Scoring ────────────────────────────────────────────────────────────────────

def score_content(
    keyword: str,
    article_body: str,
    recommended_word_count: Optional[int] = None,
) -> dict:
    """Score an article body against a target keyword (0–100).

    Parameters
    ----------
    keyword : str
        The target keyword to evaluate against.
    article_body : str
        Full article text (plain text, markdown, or HTML).
    recommended_word_count : int, optional
        Target word count. If None, fetched from
        ``estimate_recommended_word_count()``.

    Returns
    -------
    dict
        {
            "score": int,              # 0–100
            "breakdown": {             # per-criterion scores
                "keyword_in_title": int,
                "keyword_in_h1": int,
                "keyword_in_first_100": int,
                "keyword_density": int,
                "word_count_vs_serp_avg": int,
            },
            "details": {               # diagnostic values
                "total_words": int,
                "first_100_words": str,
                "keyword_occurrences": int,
                "keyword_density_pct": float,
                "recommended_word_count": int,
            },
            "recommendations": [str],  # actionable improvement tips
        }
    """
    kw = keyword.strip().lower()
    if not kw or not article_body.strip():
        return {
            "score": 0,
            "breakdown": {k: 0 for k in (
                "keyword_in_title", "keyword_in_h1", "keyword_in_first_100",
                "keyword_density", "word_count_vs_serp_avg",
            )},
            "details": {},
            "recommendations": ["No keyword or article body provided."],
        }

    if recommended_word_count is None:
        recommended_word_count = estimate_recommended_word_count()

    title = _extract_title(article_body)
    h1 = _extract_h1(article_body)
    plain = _strip_html(article_body)
    total_words = _count_words(plain)
    first_100 = _first_n_words(plain, 100)
    kw_occurrences = _keyword_occurrences(kw, plain)
    kw_density = (kw_occurrences / total_words * 100) if total_words > 0 else 0

    # ── Criterion scores ──────────────────────────────────────────────────

    # 1. Keyword in title (20 pts)
    score_title = 20 if _keyword_occurrences(kw, title) > 0 else 0

    # 2. Keyword in H1 (15 pts)
    score_h1 = 15 if _keyword_occurrences(kw, h1) > 0 else 0

    # 3. Keyword in first 100 words (10 pts)
    score_first_100 = 10 if _keyword_occurrences(kw, first_100) > 0 else 0

    # 4. Keyword density (15 pts) — target 1-3 %
    if kw_density <= 0:
        score_density = 0
    elif 1.0 <= kw_density <= 3.0:
        score_density = 15
    elif kw_density < 1.0:
        # Pro-rate: 0 % → 0 pts, 1 % → 15 pts
        score_density = round(15 * (kw_density / 1.0))
    else:
        # Over 3 % — penalise: drop 5 pts for each % above 3
        excess = kw_density - 3.0
        penalty = min(15, int(excess * 5))
        score_density = max(0, 15 - penalty)

    # 5. Word count vs SERP average (10 pts)
    if recommended_word_count > 0:
        ratio = total_words / recommended_word_count
        if 0.7 <= ratio <= 1.3:
            score_word_count = 10
        elif ratio < 0.7:
            # Pro-rate: 0 → 0 pts, 0.7 → 10 pts
            score_word_count = round(10 * (ratio / 0.7))
        else:
            # Over 130 % — penalise gently
            excess_ratio = ratio - 1.3
            penalty = min(10, int(excess_ratio * 10))
            score_word_count = max(0, 10 - penalty)
    else:
        score_word_count = 0

    total_score = score_title + score_h1 + score_first_100 + score_density + score_word_count

    # ── Recommendations ────────────────────────────────────────────────────

    recommendations = []

    if score_title < 20:
        recommendations.append(
            f"Add '{keyword}' to the page title (HTML <title> tag or markdown first line)."
        )
    if score_h1 < 15:
        recommendations.append(
            f"Include '{keyword}' in an H1 heading."
        )
    if score_first_100 < 10:
        recommendations.append(
            f"Use '{keyword}' within the first 100 words of the article."
        )
    if kw_density < 1.0 and total_words > 0:
        recommendations.append(
            f"Keyword density is {kw_density:.1f}% (target 1-3%). "
            f"Mention '{keyword}' approximately "
            f"{max(1, round(total_words * 0.01) - kw_occurrences)} more time(s)."
        )
    elif kw_density > 3.0:
        recommendations.append(
            f"Keyword density is {kw_density:.1f}% (target 1-3%). "
            f"Consider reducing repetition of '{keyword}' to avoid over-optimisation."
        )
    if score_word_count < 10:
        if total_words < recommended_word_count * 0.7:
            recommendations.append(
                f"Article is {total_words} words — aim for ~{recommended_word_count} "
                f"words (add ~{recommended_word_count - total_words} more words)."
            )
        else:
            recommendations.append(
                f"Article is {total_words} words vs recommended "
                f"~{recommended_word_count}. Trim or expand for best results."
            )

    if not recommendations:
        recommendations.append("Content is well-optimised for this keyword.")

    return {
        "score": total_score,
        "breakdown": {
            "keyword_in_title": score_title,
            "keyword_in_h1": score_h1,
            "keyword_in_first_100": score_first_100,
            "keyword_density": score_density,
            "word_count_vs_serp_avg": score_word_count,
        },
        "details": {
            "total_words": total_words,
            "keyword_occurrences": kw_occurrences,
            "keyword_density_pct": round(kw_density, 2),
            "recommended_word_count": recommended_word_count,
        },
        "recommendations": recommendations,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: python scripts/content_scorer.py <keyword> <body_file> [--recommended-wc N]")
        sys.exit(1)

    keyword = sys.argv[1]
    body_file = sys.argv[2]
    recommended_wc = None

    if "--recommended-wc" in sys.argv:
        idx = sys.argv.index("--recommended-wc")
        if idx + 1 < len(sys.argv):
            recommended_wc = int(sys.argv[idx + 1])

    with open(body_file, "r", encoding="utf-8") as f:
        body = f.read()

    result = score_content(keyword, body, recommended_word_count=recommended_wc)
    print(json.dumps(result, indent=2))
