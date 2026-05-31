#!/usr/bin/env python3
"""
Seed the database with sample data based on actual SEO research.
Loads real keyword, issue, and content idea data matching the
Giant Bubbles by Tinka SEO dashboard outputs.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta


# ── Seed Data ────────────────────────────────────────────────────────────────

DOMAINS = [
    ("giantbubblesau.com", "Australia", True),
    ("giantbubbles.co.nz", "New Zealand", False),
]

# AU keywords with realistic SEO metrics
AU_KEYWORDS = [
    ("giant bubble kit", 590, 42, 2.50),
    ("how to make giant bubbles", 880, 35, 1.80),
    ("giant bubbles for kids", 390, 48, 2.10),
    ("bubble party ideas", 320, 38, 2.80),
    ("giant bubble wand", 260, 45, 1.90),
    ("bubble solution recipe", 480, 30, 1.50),
    ("outdoor party entertainment", 210, 55, 3.20),
    ("birthday party bubbles", 170, 52, 2.40),
    ("bubble machine australia", 140, 58, 1.60),
    ("giant bubbles australia", 120, 40, 2.00),
    ("bubble entertainer hire", 90, 65, 3.50),
    ("kids party activities", 720, 50, 2.90),
    ("outdoor games for kids", 590, 45, 2.30),
    ("party hire melbourne", 480, 60, 4.00),
    ("childrens entertainment sydney", 320, 55, 3.80),
]

# NZ keywords (Auckland-focused)
NZ_KEYWORDS = [
    ("party entertainment auckland", 390, 52, 3.00),
    ("kids party entertainment auckland", 260, 48, 2.80),
    ("giant bubbles nz", 140, 35, 1.50),
    ("bubble show auckland", 110, 40, 2.20),
    ("outdoor party hire auckland", 170, 55, 3.50),
    ("children's party entertainment", 320, 50, 2.60),
    ("bubble entertainer auckland", 90, 45, 2.00),
    ("giant bubble kit nz", 80, 38, 1.80),
    ("school holiday activities auckland", 210, 58, 2.40),
    ("family fun auckland", 590, 45, 2.10),
]

# SEO Issues
SEO_ISSUES = [
    # AU - Critical
    ("AU", "missing_title", "critical", "Homepage missing meta title", "Add descriptive title tag with primary keyword"),
    ("AU", "slow_page", "critical", "Mobile page load > 4s on product pages", "Optimize images and enable caching"),
    ("AU", "no_sitemap", "critical", "No XML sitemap detected", "Generate and submit sitemap to GSC"),
    # AU - High
    ("AU", "duplicate_title", "high", "3 product pages share same title", "Write unique titles for each product page"),
    ("AU", "broken_link", "high", "2 broken internal links found", "Fix or redirect broken URLs"),
    ("AU", "missing_meta", "high", "5 pages missing meta descriptions", "Write unique meta descriptions"),
    # AU - Moderate
    ("AU", "thin_content", "moderate", "About page has only 150 words", "Expand to 500+ words with relevant keywords"),
    ("AU", "missing_h1", "moderate", "Blog category pages missing H1", "Add descriptive H1 tags"),
    ("AU", "not_indexed", "moderate", "4 blog posts not indexed after 2 weeks", "Check noindex tags and submit to GSC"),
    ("AU", "broken_image", "moderate", "3 images with broken alt text", "Add descriptive alt text to all images"),
    ("AU", "mobile_issues", "moderate", "Text too small on mobile product pages", "Increase base font size to 16px"),
    # NZ - High
    ("NZ", "missing_title", "high", "Auckland landing page missing title", "Add location-specific title tag"),
    ("NZ", "thin_content", "high", "Services page < 200 words", "Add detailed service descriptions"),
    ("NZ", "no_robots", "high", "Robots.txt blocking /blog/", "Fix robots.txt to allow blog indexing"),
    # NZ - Moderate
    ("NZ", "canonical_issues", "moderate", "Duplicate www/non-www versions", "Set canonical domain and 301 redirect"),
    ("NZ", "missing_meta", "moderate", "Contact page missing meta description", "Add meta description"),
]

# Content Ideas
CONTENT_IDEAS = [
    ("Ultimate Guide to Giant Bubbles: Recipes, Wands & Tips for Australia", "giant bubble kit", 10, "high"),
    ("Giant Bubble Kit Buyer's Guide: Australia 2026", "giant bubble kit", 9, "medium"),
    ("10 Best Birthday Party Entertainment Ideas for Kids", "birthday party bubbles", 9, "medium"),
    ("Giant Bubbles for Kids: A Safe & Fun Outdoor Activity Guide", "giant bubbles for kids", 9, "medium"),
    ("How to Make Giant Bubbles: The Complete DIY Recipe Guide", "how to make giant bubbles", 9, "low"),
    ("Hire a Bubble Entertainer in Auckland: Complete Guide", "bubble entertainer auckland", 8, "medium"),
    ("The Best Kids Party Entertainment in Auckland for 2026", "kids party entertainment auckland", 8, "medium"),
    ("6 Amazing Outdoor Party Games for Kids Birthday Parties", "outdoor party entertainment", 8, "medium"),
    ("Bubble Solution Recipe: How to Make the Best Giant Bubbles", "bubble solution recipe", 8, "low"),
    ("Top 10 Party Entertainment Ideas for Kids in Melbourne", "party entertainment auckland", 7, "medium"),
    ("Best Giant Bubble Wand: Reviews and Buying Guide", "giant bubble wand", 7, "low"),
    ("Why Giant Bubbles Are the Perfect Kids' Party Activity", "giant bubbles for kids", 7, "low"),
    ("How to Choose the Right Bubble Machine for Your Event", "bubble machine australia", 7, "medium"),
    ("Family Fun in Auckland: Top 10 Activities for School Holidays", "family fun auckland", 7, "medium"),
    ("School Holiday Activities Auckland: Ultimate Parent's Guide", "school holiday activities auckland", 7, "medium"),
    ("Giant Bubbles Sydney: Events, Shows and Parties", "giant bubbles australia", 6, "medium"),
    ("Children's Party Entertainment Ideas That Kids Actually Love", "childrens entertainment sydney", 6, "medium"),
    ("Outdoor Party Hire Auckland: Everything You Need to Know", "outdoor party hire auckland", 6, "medium"),
    ("Bubble Show Auckland: The Ultimate Family Entertainment", "bubble show auckland", 6, "medium"),
    ("Giant Bubble Kit NZ: Where to Buy and How to Use", "giant bubble kit nz", 6, "low"),
]

# Backlog Content Ideas
BACKLOG_IDEAS = [
    ("DIY Giant Bubble Wand: Build Your Own for Under $10", "giant bubble wand", 5, "low"),
    ("How to Organize a Bubble-Themed Birthday Party", "birthday party bubbles", 6, "medium"),
    ("The Science of Giant Bubbles: Why They Pop & How to Keep Them Bigger", "how to make giant bubbles", 5, "medium"),
    ("Giant Bubbles vs Bubble Machines: Which Is Better for Your Event?", "giant bubble kit", 5, "medium"),
    ("Best Outdoor Games for Kids Ages 3-10: Complete List", "outdoor party entertainment", 6, "low"),
    ("Giant Bubble Photography Tips: Capture the Perfect Bubble Shot", "giant bubble kit", 4, "low"),
    ("How Much Does a Bubble Entertainer Cost in Auckland?", "bubble entertainer auckland", 5, "low"),
    ("Auckland Kids Parties: The Ultimate Planning Guide", "kids party entertainment auckland", 6, "medium"),
    ("Giant Bubbles for School Events: Ideas for Fairs & Fundraisers", "giant bubbles for kids", 5, "medium"),
    ("The Complete Guide to Outdoor Kids' Parties in Auckland", "outdoor party hire auckland", 5, "medium"),
    ("Best Party Entertainers in Auckland for 2026", "party entertainment auckland", 4, "medium"),
    ("Giant Bubble Recipe Without Glycerin: 3 Easy Alternatives", "bubble solution recipe", 5, "low"),
    ("Children's Birthday Party Trends Australia 2026", "birthday party bubbles", 4, "medium"),
    ("How to Price Your Bubble Entertainment Business", "bubble entertainer auckland", 4, "low"),
    ("SEO for Event Businesses: How to Rank for Local Search", "party entertainment auckland", 4, "medium"),
    ("Case Study: How a Bubble Business Grew Traffic by 300%", "giant bubbles nz", 4, "medium"),
    ("Giant Bubbles for Weddings: Creative Ideas for Photographers", "giant bubbles nz", 4, "low"),
    ("The Ultimate Guide to Children's Party Entertainment in NZ", "children's party entertainment", 5, "medium"),
    ("10 Ways to Make Your School Holiday Program Stand Out", "school holiday activities auckland", 5, "medium"),
    ("Giant Bubbles for Corporate Events: Team Building Ideas", "giant bubbles nz", 3, "medium"),
]

# On-Page Errors (sample data)
AU_ONPAGE_ERRORS = [
    ("https://giantbubblesau.com/", "missing_title", "critical", "Homepage missing meta title", "Add <title>Giant Bubbles Australia | Giant Bubble Kits & Party Entertainment</title>"),
    ("https://giantbubblesau.com/", "missing_meta", "critical", "Missing meta description", "Add meta description with primary keywords"),
    ("https://giantbubblesau.com/shop/giant-bubble-kit", "duplicate_title", "warning", "Title duplicates other product pages", "Write unique title for this product"),
    ("https://giantbubblesau.com/shop/bubble-wand", "broken_link", "warning", "Product image returns 404", "Fix image URL or upload replacement"),
    ("https://giantbubblesau.com/about", "thin_content", "critical", "About page has only 150 words", "Expand to 500+ words"),
    ("https://giantbubblesau.com/blog/", "missing_h1", "warning", "Blog index missing H1 tag", "Add H1 with keyword-rich title"),
    ("https://giantbubblesau.com/shop/", "slow_page", "critical", "Page load time exceeds 4s", "Optimize product images and enable caching"),
    ("https://giantbubblesau.com/contact", "missing_meta", "info", "Contact page missing meta description", "Add meta description"),
    ("https://giantbubblesau.com/blog/giant-bubble-recipes", "not_indexed", "warning", "Post not indexed after 2 weeks", "Check noindex tags"),
]

NZ_ONPAGE_ERRORS = [
    ("https://giantbubbles.co.nz/", "missing_title", "critical", "Auckland landing page missing title tag", "Add <title>Giant Bubbles NZ | Bubble Entertainment Auckland</title>"),
    ("https://giantbubbles.co.nz/", "missing_meta", "warning", "Missing meta description", "Add meta description with location keywords"),
    ("https://giantbubbles.co.nz/services", "thin_content", "warning", "Services page has only 180 words", "Add detailed service descriptions"),
    ("https://giantbubbles.co.nz/blog", "no_robots", "critical", "Robots.txt is blocking /blog/", "Update robots.txt to allow blog indexing"),
    ("https://giantbubbles.co.nz/contact", "canonical_issues", "info", "Canonical tag points to giantbubblesau.com", "Fix canonical tag for NZ domain"),
    ("https://giantbubbles.co.nz/gallery", "broken_image", "warning", "Gallery image missing alt text", "Add descriptive alt text to all images"),
    ("https://giantbubbles.co.nz/pricing", "missing_meta", "info", "Pricing page missing meta description", "Add meta description"),
]


def seed_db(db_path: str):
    """Seed the database with all sample data."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.database import Database
    from src.models import (
        ContentIdea,
        Domain,
        Keyword,
        OnPageError,
        RankRecord,
        SeoIssue,
    )

    schema_path = os.path.join(os.path.dirname(db_path), "schema.sql")
    db = Database(db_path, schema_path)

    # 1. Init DB (domains already exist from init_db.py)
    domains = {d.label: d.id for d in db.list_domains()}
    print(f"[seed] Domains: {domains}")

    # 2. Keywords & rank history
    domain_map = {}
    for url, label, primary in DOMAINS:
        d = Domain(url=url, label=label, is_primary=primary)
        domain_id = db.upsert_domain(d)
        if "au" in url.lower():
            domain_map["AU"] = domain_id
        if "nz" in url.lower():
            domain_map["NZ"] = domain_id

    import random as rng_mod
    kw_count = 0
    rank_count = 0

    today = datetime.utcnow()
    for region, kw_list in [("AU", AU_KEYWORDS), ("NZ", NZ_KEYWORDS)]:
        dom_id = domain_map[region]
        rng = rng_mod.Random(f"seed-{region}")
        for kw_text, vol, diff, cpc in kw_list:
            kw = Keyword(keyword=kw_text, domain_id=dom_id,
                         monthly_volume=vol, keyword_difficulty=diff, cpc=cpc)
            kw_id = db.upsert_keyword(kw)
            kw_count += 1

            # Generate 90 days of rank history (mock GSC data)
            for day_offset in range(90):
                date = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                pos = rng.randint(3, 45)
                impressions = rng.randint(50, 2000)
                ctr_val = rng.uniform(0.01, 0.15)
                clicks = max(1, int(impressions * ctr_val))
                rr = RankRecord(
                    keyword_id=kw_id,
                    domain_id=dom_id,
                    date=date,
                    position=pos,
                    clicks=clicks,
                    impressions=impressions,
                    ctr=ctr_val,
                )
                db.upsert_rank(rr)
                rank_count += 1

    print(f"[seed] Keywords: {kw_count}")
    print(f"[seed] Rank history: {rank_count} records")

    # 3. SEO Issues
    issue_count = 0
    for region, issue_type, severity, detail, fix in SEO_ISSUES:
        dom_id = domain_map[region]
        si = SeoIssue(
            domain_id=dom_id,
            issue_type=issue_type,
            severity=severity,
            detail=detail,
            suggested_fix=fix,
            status="open",
        )
        db.upsert_issue(si)
        issue_count += 1
    print(f"[seed] Issues: {issue_count}")

    # 4. Content Ideas
    idea_count = 0
    for title, kw, priority, effort in CONTENT_IDEAS:
        ci = ContentIdea(
            title=title,
            target_keyword=kw,
            priority=priority,
            effort=effort,
            source="manual",
            status="draft",
        )
        db.upsert_content_idea(ci)
        idea_count += 1

    # Backlog ideas
    for title, kw, priority, effort in BACKLOG_IDEAS:
        ci = ContentIdea(
            title=title,
            target_keyword=kw,
            priority=priority,
            effort=effort,
            source="backlog_csv",
            status="backlog",
        )
        db.upsert_content_idea(ci)
        idea_count += 1
    print(f"[seed] Content ideas: {idea_count}")

    # 5. On-Page Errors (seed some open + some fixed)
    import json

    # AU errors
    for url, err_type, severity, detail, fix in AU_ONPAGE_ERRORS:
        oe = OnPageError(
            url=url,
            domain_id=domain_map["AU"],
            error_type=err_type,
            severity=severity,
            detail=detail,
            suggested_fix=fix,
            status="open",
            check_batch="seed-2026-05-31",
        )
        db.upsert_onpage_error(oe)

    # NZ errors
    for url, err_type, severity, detail, fix in NZ_ONPAGE_ERRORS:
        oe = OnPageError(
            url=url,
            domain_id=domain_map["NZ"],
            error_type=err_type,
            severity=severity,
            detail=detail,
            suggested_fix=fix,
            status="open",
            check_batch="seed-2026-05-31",
        )
        db.upsert_onpage_error(oe)

    # Also seed a few fixed errors to show the lifecycle
    for url, err_type, _, detail, fix in AU_ONPAGE_ERRORS[:2]:
        from datetime import datetime as dt
        fixed = dt.utcnow().isoformat(timespec="seconds") + "Z"
        oe = OnPageError(
            url=url,
            domain_id=domain_map["AU"],
            error_type=err_type,
            severity="warning",
            detail=detail,
            suggested_fix=fix,
            status="fixed",
            check_batch="seed-fixed",
            fixed_at=fixed,
        )
        db.upsert_onpage_error(oe)

    print(f"[seed] On-page errors: {len(AU_ONPAGE_ERRORS) + len(NZ_ONPAGE_ERRORS) + 2}")
    print("[seed] Done.")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "seo_dashboard.db")
    seed_db(db_path)
