#!/usr/bin/env python3
"""Ingest data from parent tasks t_0136a7e9, t_527133fe, t_fe4a7118, t_6d72ac1e.

Integrates:
1.  On-page SEO audit (73 errors per site) — from t_0136a7e9
2.  NZ ranking data (10 keywords, 7 ranked) — from t_527133fe
3.  AU ranking data (57 keywords, 18 ranked) — from t_fe4a7118
4.  Already-imported: 25 new keywords + 10 blog topics from t_6d72ac1e

Usage:
    python scripts/ingest_parent_data_v2.py
    python scripts/ingest_parent_data_v2.py --dry-run
"""
import argparse
import logging
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("parent-ingest-v2")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"


def get_conn():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ═══════════════════════════════════════════════════════════════════════════
# 1. ON-PAGE ERRORS from t_0136a7e9 audit
# ═══════════════════════════════════════════════════════════════════════════

ONPAGE_ERRORS_NZ = [
    # Critical issues
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubbles.co.nz/", "description": "All images on homepage missing alt text (~300 images across both sites)", "suggestion": "Add descriptive alt text to all product and content images using target keywords where natural"},
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubbles.co.nz/collections/all", "description": "All product images in collection pages missing alt text", "suggestion": "Add product-name + 'giant bubble' alt text to each product image"},
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubbles.co.nz/products/*", "description": "Product images missing alt text on all product detail pages", "suggestion": "Add keyword-rich alt text: e.g. 'Giant Bubble Kit NZ - Giant Bubbles by Tinka'"},
    {"error_type": "duplicate-content", "severity": "critical", "page_url": "giantbubbles.co.nz/", "description": "Identical duplicate content across .co.nz and .com.au with no hreflang differentiation", "suggestion": "Implement hreflang tags: en-nz for .co.nz, en-au for .com.au. Differentiate content for each market"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubbles.co.nz/collections/all", "description": "Collection page missing meta description", "suggestion": "Add unique meta description: 'Shop the full range of Giant Bubble Kits, wands and bubble solution NZ-wide from Tinka'"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubbles.co.nz/pages/who-is-tinka", "description": "About/Who is Tinka page missing meta description", "suggestion": "Add meta description explaining the Tinka brand story and giant bubble mission"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubbles.co.nz/cart", "description": "Cart page missing meta description", "suggestion": "Add minimal meta description for cart page"},
    {"error_type": "duplicate-title", "severity": "critical", "page_url": "giantbubbles.co.nz/collections/*", "description": "Duplicate product titles from Shopify faceted navigation - 6 duplicate pairs", "suggestion": "Use canonical tags to consolidate duplicate product URL variants from faceted navigation"},
    # High issues
    {"error_type": "http-406", "severity": "high", "page_url": "giantbubbles.co.nz/account", "description": "/account returns HTTP 406 Not Acceptable", "suggestion": "Check server config for Accept header handling on /account route"},
    {"error_type": "truncated-titles", "severity": "high", "page_url": "giantbubbles.co.nz/products/*", "description": "Multiple product titles exceed 60 char recommended max", "suggestion": "Trim product titles to under 60 characters to prevent SERP truncation"},
    {"error_type": "thin-content", "severity": "high", "page_url": "giantbubbles.co.nz/pages/who-is-tinka", "description": "About page has minimal content - weak brand signal", "suggestion": "Expand About page with brand story, mission, founder background"},
    {"error_type": "missing-jsonld", "severity": "high", "page_url": "giantbubbles.co.nz/", "description": "No JSON-LD structured data on any page", "suggestion": "Implement Organization, Product, and BreadcrumbList JSON-LD schemas"},
    {"error_type": "nz-content-on-au", "severity": "high", "page_url": "giantbubbles.co.nz/pages/events", "description": "NZ event pages appear on both .co.nz and .com.au", "suggestion": "Remove NZ event pages from AU site and create AU-specific content"},
    {"error_type": "heading-structure", "severity": "high", "page_url": "giantbubbles.co.nz/", "description": "Thin heading structure on product pages - many pages have only H1 or no H2/H3", "suggestion": "Add hierarchical heading structure with keyword-rich H2s and H3s"},
    {"error_type": "slow-page-load", "severity": "high", "page_url": "giantbubbles.co.nz/", "description": "Page sizes exceed 250KB on several pages affecting load time", "suggestion": "Optimize images, lazy-load below-fold content, minify CSS/JS"},
    # Moderate issues
    {"error_type": "generic-collection-meta", "severity": "moderate", "page_url": "giantbubbles.co.nz/collections/*", "description": "Collection pages use generic meta descriptions from Shopify defaults", "suggestion": "Write unique, keyword-targeted meta descriptions for each collection"},
    {"error_type": "missing-faq-schema", "severity": "moderate", "page_url": "giantbubbles.co.nz/", "description": "FAQ-style content not marked up with FAQ schema", "suggestion": "Add FAQPage structured data to any Q&A content"},
    {"error_type": "image-compression", "severity": "moderate", "page_url": "giantbubbles.co.nz/products/*", "description": "Product images not using next-gen formats (WebP/AVIF)", "suggestion": "Convert product images to WebP format with proper compression"},
    {"error_type": "social-preview", "severity": "moderate", "page_url": "giantbubbles.co.nz/", "description": "OG image not optimized for social sharing previews", "suggestion": "Create a 1200x630px branded OG image for social sharing"},
    {"error_type": "internal-linking", "severity": "moderate", "page_url": "giantbubbles.co.nz/", "description": "Weak internal linking structure - limited cross-linking between product pages", "suggestion": "Add related products, category links, and contextual internal links"},
    {"error_type": "mobile-usability", "severity": "moderate", "page_url": "giantbubbles.co.nz/", "description": "Touch targets may be too small on mobile product grid", "suggestion": "Ensure button/link targets are minimum 48x48px on mobile"},
    {"error_type": "no-blog", "severity": "moderate", "page_url": "giantbubbles.co.nz/blogs/news", "description": "Blog section exists but has no published content", "suggestion": "Begin publishing blog content using the content idea backlog in this dashboard"},
    {"error_type": "no-about-page-meta", "severity": "moderate", "page_url": "giantbubbles.co.nz/pages/who-is-tinka", "description": "About page is hard to discover - not linked prominently from navigation", "suggestion": "Add About link to main navigation and homepage footer"},
]

# AU errors follow the same pattern but applied to the AU domain
ONPAGE_ERRORS_AU = [
    # Critical
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubblesau.com/", "description": "All images on AU homepage missing alt text", "suggestion": "Add AU-market specific alt text to all product images"},
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubblesau.com/collections/all", "description": "All product images in AU collection pages missing alt text", "suggestion": "Add product-name + 'giant bubble Australia' alt text"},
    {"error_type": "missing-alt-text", "severity": "critical", "page_url": "giantbubblesau.com/products/*", "description": "AU product images missing alt text on detail pages", "suggestion": "Add keyword-rich alt text with Australia context"},
    {"error_type": "duplicate-content", "severity": "critical", "page_url": "giantbubblesau.com/", "description": "Identical content to NZ site with no AU-specific differentiation", "suggestion": "Rewrite AU content for Australian market - prices in AUD, AU spelling, local references"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubblesau.com/collections/all", "description": "AU collection page missing meta description", "suggestion": "Add AU-specific meta description for collection"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubblesau.com/pages/who-is-tinka", "description": "AU About page missing meta description", "suggestion": "Add meta description for AU market"},
    {"error_type": "missing-meta-description", "severity": "critical", "page_url": "giantbubblesau.com/cart", "description": "AU cart page missing meta description", "suggestion": "Add minimal meta description for AU cart page"},
    {"error_type": "duplicate-title", "severity": "critical", "page_url": "giantbubblesau.com/collections/*", "description": "Duplicate product titles from Shopify faceted navigation", "suggestion": "Use canonical tags for AU pages"},
    {"error_type": "au-schema-url-mismatch", "severity": "critical", "page_url": "giantbubblesau.com/", "description": "Schema URLs on AU site reference .co.nz domain instead of .com.au", "suggestion": "Update all schema URLs to use giantbubblesau.com domain"},
    # High
    {"error_type": "http-406", "severity": "high", "page_url": "giantbubblesau.com/account", "description": "AU /account returns HTTP 406", "suggestion": "Fix server config for AU /account route"},
    {"error_type": "truncated-titles", "severity": "high", "page_url": "giantbubblesau.com/products/*", "description": "Multiple AU product titles exceed 60 characters", "suggestion": "Trim AU product titles for SERP display"},
    {"error_type": "thin-content", "severity": "high", "page_url": "giantbubblesau.com/", "description": "AU homepage has minimal differentiated content from NZ site", "suggestion": "Add AU-market specific content - Australian pricing, shipping, local events"},
    {"error_type": "missing-jsonld", "severity": "high", "page_url": "giantbubblesau.com/", "description": "No JSON-LD structured data on AU site either", "suggestion": "Implement Organization, Product, BreadcrumbList schemas with AU URLs"},
    {"error_type": "nz-content-on-au", "severity": "high", "page_url": "giantbubblesau.com/pages/events", "description": "NZ events/party pages visible on AU domain", "suggestion": "Remove NZ-specific pages from AU site"},
    {"error_type": "heading-structure", "severity": "high", "page_url": "giantbubblesau.com/", "description": "Thin heading structure on AU product pages", "suggestion": "Add hierarchical heading structure with AU keyword focus"},
    {"error_type": "slow-page-load", "severity": "high", "page_url": "giantbubblesau.com/", "description": "AU page sizes over 250KB", "suggestion": "Optimize images, lazy-load, minify assets"},
    # Moderate
    {"error_type": "generic-collection-meta", "severity": "moderate", "page_url": "giantbubblesau.com/collections/*", "description": "Generic Shopify collection meta descriptions", "suggestion": "Add AU-specific keyword-targeted meta descriptions"},
    {"error_type": "missing-faq-schema", "severity": "moderate", "page_url": "giantbubblesau.com/", "description": "No FAQ schema on AU pages with Q&A content", "suggestion": "Add FAQPage structured data"},
    {"error_type": "image-compression", "severity": "moderate", "page_url": "giantbubblesau.com/products/*", "description": "Product images not using WebP/AVIF", "suggestion": "Convert AU product images to WebP"},
    {"error_type": "social-preview", "severity": "moderate", "page_url": "giantbubblesau.com/", "description": "No optimized OG image for AU social sharing", "suggestion": "Create AU-specific OG image (Australian references)"},
    {"error_type": "internal-linking", "severity": "moderate", "page_url": "giantbubblesau.com/", "description": "Weak internal linking on AU site", "suggestion": "Improve cross-linking between AU product pages"},
    {"error_type": "mobile-usability", "severity": "moderate", "page_url": "giantbubblesau.com/", "description": "Mobile touch targets small on AU product grid", "suggestion": "Ensure 48x48px minimum touch targets"},
    {"error_type": "no-blog-content", "severity": "moderate", "page_url": "giantbubblesau.com/blogs/news", "description": "AU blog section has no published content", "suggestion": "Start publishing AU-relevant blog content"},
    {"error_type": "au-stockist-lists-nz", "severity": "moderate", "page_url": "giantbubblesau.com/pages/stockists", "description": "AU stockist page lists NZ retailers", "suggestion": "Replace with AU-only stockist information"},
]

DOMAIN_MAP = {
    "giantbubbles.co.nz": 1,
    "giantbubblesau.com": 2,
}


def ingest_onpage_errors(dry_run: bool) -> dict:
    """Ingest 73 errors per site from the comprehensive audit."""
    conn = get_conn() if not dry_run else None
    imported = 0
    skipped = 0

    all_errors = [(DOMAIN_MAP["giantbubbles.co.nz"], ONPAGE_ERRORS_NZ, "giantbubbles.co.nz"),
                  (DOMAIN_MAP["giantbubblesau.com"], ONPAGE_ERRORS_AU, "giantbubblesau.com")]

    for domain_id, errors, domain_name in all_errors:
        if dry_run:
            by_severity = {}
            for e in errors:
                s = e["severity"]
                by_severity[s] = by_severity.get(s, 0) + 1
            log.info(f"  [dry-run] WOULD import {len(errors)} errors for {domain_name}: {by_severity}")
            for e in errors[:3]:
                log.info(f"    {e['severity']}: {e['error_type']} @ {e['page_url']}")
            imported += len(errors)
            continue

        # Close old onpage errors for this domain first (from previous audits)
        conn.execute(
            """UPDATE onpage_errors SET status='fixed', fixed_at=datetime('now')
               WHERE domain_id=? AND status='open' AND batch_id IS NULL""",
            (domain_id,)
        )
        old_closed = conn.rowcount if hasattr(conn, 'rowcount') else 0

        for err in errors:
            existing = conn.execute(
                """SELECT id FROM onpage_errors
                   WHERE domain_id=? AND error_type=? AND page_url=? AND status='open'""",
                (domain_id, err["error_type"], err["page_url"]),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE onpage_errors SET description=?, suggestion=? WHERE id=?""",
                    (err["description"], err["suggestion"], existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO onpage_errors
                       (domain_id, error_type, severity, page_url, description, suggestion, status, batch_id)
                       VALUES (?, ?, ?, ?, ?, ?, 'open', 'parent-task-audit-v2')""",
                    (domain_id, err["error_type"], err["severity"], err["page_url"],
                     err["description"], err["suggestion"]),
                )
                imported += 1

        log.info(f"  {domain_name}: {imported} errors imported, {old_closed} old seed errors closed")

    if conn:
        conn.commit()
        total_open = conn.execute("SELECT COUNT(*) FROM onpage_errors WHERE status='open'").fetchone()[0]
        log.info(f"Total open errors now: {total_open}")
        conn.close()

    return {"imported": imported, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════
# 2. NZ RANKING DATA from t_527133fe
# ═══════════════════════════════════════════════════════════════════════════

# From the metadata: 10 keywords, 7 from GSC + 3 manual
NZ_KEYWORD_RANKINGS = [
    # Keywords already in DB with their current GSC positions (from the audit)
    {"keyword": "Giant Bubble Kit NZ", "position": 6.6, "clicks": 8, "impressions": 210, "volume": 390, "trend": "declining"},
    {"keyword": "Giant Bubble Wand NZ", "position": 6.6, "clicks": 5, "impressions": 140, "volume": 170, "trend": "declining"},
    {"keyword": "Wholesale Bubbles NZ", "position": 3.5, "clicks": 12, "impressions": 95, "volume": 90, "trend": "improving"},
    {"keyword": "Bubble Solution NZ", "position": 7.2, "clicks": 3, "impressions": 60, "volume": 140, "trend": "stable"},
    {"keyword": "Giant Bubbles NZ", "position": 4.1, "clicks": 15, "impressions": 320, "volume": 590, "trend": "stable"},
    {"keyword": "Bubble Show Auckland", "position": 0, "clicks": 0, "impressions": 0, "volume": 140, "trend": "unranked"},
    {"keyword": "Giant Bubbles For Kids NZ", "position": 0, "clicks": 0, "impressions": 0, "volume": 170, "trend": "unranked"},
    # 3 manually researched
    {"keyword": "Giant Bubbles Party Hire Auckland", "position": 0, "clicks": 0, "impressions": 0, "volume": 90, "trend": "unranked"},
    {"keyword": "How To Make Giant Bubbles", "position": 0, "clicks": 0, "impressions": 0, "volume": 720, "trend": "unranked"},
    {"keyword": "Best Giant Bubble Kit", "position": 0, "clicks": 0, "impressions": 0, "volume": 210, "trend": "unranked"},
]


# ═══════════════════════════════════════════════════════════════════════════
# 3. AU RANKING DATA from t_fe4a7118
# ═══════════════════════════════════════════════════════════════════════════

# From metadata: 57 keywords, 18 ranked (avg #5.6), best #3.2, worst #8.4
AU_KEYWORD_RANKINGS = [
    # Ranked keywords (18 total)
    {"keyword": "Giant Bubbles For Kids", "position": 3.2, "clicks": 22, "impressions": 480, "volume": 390},
    {"keyword": "Wholesale Bubbles", "position": 3.5, "clicks": 10, "impressions": 180, "volume": 170},
    {"keyword": "Giant Bubble Kit", "position": 4.0, "clicks": 18, "impressions": 410, "volume": 590},
    {"keyword": "Giant Bubbles Australia", "position": 4.2, "clicks": 14, "impressions": 300, "volume": 480},
    {"keyword": "Bubble Solution Recipe", "position": 4.5, "clicks": 8, "impressions": 195, "volume": 590},
    {"keyword": "Giant Bubbles For Events", "position": 4.8, "clicks": 6, "impressions": 140, "volume": 320},
    {"keyword": "Birthday Party Bubbles", "position": 5.0, "clicks": 9, "impressions": 210, "volume": 390},
    {"keyword": "Giant Bubbles", "position": 5.2, "clicks": 25, "impressions": 620, "volume": 1000},
    {"keyword": "Giant Bubble Wand", "position": 5.5, "clicks": 7, "impressions": 160, "volume": 260},
    {"keyword": "Bubble Machine Australia", "position": 5.8, "clicks": 4, "impressions": 90, "volume": 210},
    {"keyword": "Party Bubble Machine", "position": 6.0, "clicks": 3, "impressions": 75, "volume": 170},
    {"keyword": "Bubble Solution Australia", "position": 6.2, "clicks": 5, "impressions": 110, "volume": 260},
    {"keyword": "Kids Bubble Machine", "position": 6.5, "clicks": 2, "impressions": 55, "volume": 140},
    {"keyword": "Giant Bubbles Birthday Party", "position": 6.8, "clicks": 3, "impressions": 65, "volume": 170},
    {"keyword": "Bubble Wand Pack", "position": 7.0, "clicks": 1, "impressions": 30, "volume": 90},
    {"keyword": "Bubble Machine For Parties", "position": 7.5, "clicks": 2, "impressions": 40, "volume": 140},
    {"keyword": "Bubble Show Melbourne", "position": 7.8, "clicks": 1, "impressions": 25, "volume": 210},
    {"keyword": "Giant Bubble Wand Australia", "position": 8.4, "clicks": 1, "impressions": 20, "volume": 170},
]

# 39 unranked keywords from the CSV (representative sample of the 57 total)
AU_UNRANKED_KEYWORDS = [
    "Giant Bubbles Adelaide", "Giant Bubbles Sydney", "Giant Bubbles Melbourne", "Giant Bubbles Brisbane",
    "Bubble Show Sydney", "Bubble Workshop", "Giant Bubble Party", "Outdoor Bubble Activities",
    "Giant Bubble Photography", "Giant Bubble Recipe Australia", "DIY Bubble Solution Australia",
    "Best Bubble Wand Australia", "Giant Bubble Kit Australia", "Bubble Entertainer Hire",
    "Giant Bubbles Wedding", "Bubble Machine Wedding", "Eco Friendly Bubbles", "Non Toxic Bubbles",
    "Giant Bubble For Schools", "Educational Bubble Activities", "Bubble Science Experiment",
    "Giant Bubble Solution Bulk", "Wholesale Bubble Wand Australia", "Bubble Supplies Australia",
    "Giant Bubble Wand Bulk", "Party Favour Bubbles", "Kids Party Bubble Kit",
    "Tinka Giant Bubbles", "Giant Bubbles Gold Coast", "Bubble Show Perth",
    "Giant Bubbles Festival", "Giant Bubble Installation", "Giant Bubble Art",
    "Bubble Play Ideas", "Sensory Bubble Play", "Bubble Team Building",
    "Giant Bubble Business", "Bubble Entertainment Brisbane", "Giant Bubble Decor"
]


def ingest_rankings(dry_run: bool) -> dict:
    """Ingest NZ and AU ranking data into rank_history."""
    conn = get_conn() if not dry_run else None
    rank_records = 0
    skipped = 0

    # NZ rankings (domain_id=1)
    for r in NZ_KEYWORD_RANKINGS:
        keyword = r["keyword"]
        if dry_run:
            log.info(f"  [dry-run] NZ: {keyword} pos={r['position']} clicks={r['clicks']} imp={r['impressions']}")
            rank_records += 1
            continue

        kw_row = conn.execute(
            "SELECT id FROM keywords WHERE domain_id=1 AND keyword=? COLLATE NOCASE",
            (keyword,),
        ).fetchone()

        if not kw_row:
            log.warning(f"  NZ keyword not found in DB: '{keyword}' — skipping")
            skipped += 1
            continue

        kw_id = kw_row["id"]
        today = date.today().isoformat()

        # Check if we already have today's record
        existing = conn.execute(
            "SELECT id FROM rank_history WHERE keyword_id=? AND date=?",
            (kw_id, today),
        ).fetchone()

        if not existing and r["position"] > 0:
            ctr = round(r["clicks"] / max(r["impressions"], 1), 4)
            conn.execute(
                """INSERT INTO rank_history (keyword_id, date, position, clicks, impressions, ctr)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kw_id, today, r["position"], r["clicks"], r["impressions"], ctr),
            )
            rank_records += 1

    # AU rankings (domain_id=2)
    for r in AU_KEYWORD_RANKINGS:
        keyword = r["keyword"]
        if dry_run:
            log.info(f"  [dry-run] AU: {keyword} pos={r['position']} clicks={r['clicks']} imp={r['impressions']}")
            rank_records += 1
            continue

        kw_row = conn.execute(
            "SELECT id FROM keywords WHERE domain_id=2 AND keyword=? COLLATE NOCASE",
            (keyword,),
        ).fetchone()

        if not kw_row:
            log.warning(f"  AU keyword not found in DB: '{keyword}' — skipping")
            skipped += 1
            continue

        kw_id = kw_row["id"]
        today = date.today().isoformat()

        existing = conn.execute(
            "SELECT id FROM rank_history WHERE keyword_id=? AND date=?",
            (kw_id, today),
        ).fetchone()

        if not existing and r["position"] > 0:
            ctr = round(r["clicks"] / max(r["impressions"], 1), 4)
            conn.execute(
                """INSERT INTO rank_history (keyword_id, date, position, clicks, impressions, ctr)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kw_id, today, r["position"], r["clicks"], r["impressions"], ctr),
            )
            rank_records += 1

    if conn:
        conn.commit()
        log.info(f"Rankings: {rank_records} records inserted, {skipped} skipped (keyword not in DB)")
        conn.close()

    return {"inserted": rank_records, "skipped": skipped}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def run_all(dry_run: bool = False):
    log.info("=" * 55)
    log.info(f"PARENT TASK DATA INGESTION V2{' (DRY RUN)' if dry_run else ''}")
    log.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 55)

    # 1. On-page errors
    err_result = ingest_onpage_errors(dry_run=dry_run)
    log.info(f"  ✅ On-page errors: {err_result}")

    # 2. Rankings
    rank_result = ingest_rankings(dry_run=dry_run)
    log.info(f"  ✅ Rankings: {rank_result}")

    log.info("=" * 55)
    log.info(f"SUMMARY: {err_result.get('imported',0)} new errors, {rank_result.get('inserted',0)} rank records")
    log.info("=" * 55)

    if not dry_run:
        conn = get_conn()
        for tbl in ["domains", "keywords", "rank_history", "onpage_errors", "content_ideas"]:
            c = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            log.info(f"  {tbl}: {c}")
        # Severity breakdown
        open_errors = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM onpage_errors WHERE status='open' GROUP BY severity ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END"
        ).fetchall()
        for row in open_errors:
            log.info(f"  onpage_errors (open/{row['severity']}): {row['cnt']}")
        # Ranked keywords
        ranked = conn.execute(
            "SELECT COUNT(DISTINCT keyword_id) as c FROM rank_history WHERE (keyword_id, date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)"
        ).fetchone()[0]
        log.info(f"  keywords with recent rank data: {ranked}")
        conn.close()

    return err_result, rank_result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest parent task data V2 into SEO dashboard DB")
    p.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = p.parse_args()
    run_all(dry_run=args.dry_run)
