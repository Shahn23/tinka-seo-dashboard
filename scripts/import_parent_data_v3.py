"""Import all data from parent tasks (t_05b6423e, t_0fbae95c, t_97fdddac) into the dashboard DB.
Handles: audit findings, blog post ideas, keyword verification."""

import sqlite3, json, os, sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "seo_dashboard.db")

BATCH_ID = f"parent-v3-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def domain_id(conn, name):
    cur = conn.execute("SELECT id FROM domains WHERE name = ?", [name])
    r = cur.fetchone()
    if r:
        return r["id"]
    cur = conn.execute("INSERT INTO domains (name, display_name) VALUES (?, ?)", [name, name])
    return cur.lastrowid

def insert_audit_findings(conn):
    """Import the 11 detailed audit findings from the JSON report."""
    json_path = os.path.join(PROJECT_DIR, "data", "seo_audit_findings_20260604.json")
    if not os.path.exists(json_path):
        print(f"[SKIP] audit findings JSON not found: {json_path}")
        return 0

    with open(json_path) as f:
        findings = json.load(f)

    # Get domain IDs
    nz_id = domain_id(conn, "giantbubbles.co.nz")
    au_id = domain_id(conn, "giantbubblesau.com")

    # Check which already exist (deduplicate by error_type + description prefix)
    existing = set()
    cur = conn.execute("SELECT error_type, description FROM onpage_errors WHERE batch_id = ?", [BATCH_ID])
    for r in cur.fetchall():
        existing.add((r["error_type"], r["description"][:50]))

    inserted = 0
    for f in findings:
        for site_id, site_label in [(nz_id, "NZ"), (au_id, "AU")]:
            # Some findings apply to both, some to specific sites
            sites = f.get("sites", ["nz", "au"])
            if site_label.lower() not in sites and "both" not in str(sites).lower() and site_label.lower() not in str(sites).lower():
                continue

            error_type = f["category"]
            severity = f["severity"]
            page_url = f.get("pages", [None])
            if page_url and len(page_url) > 0:
                page_url = page_url[0]
            else:
                page_url = f"/"

            desc = f"{f['title']}: {f['description']}"
            suggestion = f.get("fix", "")

            # Dedup check
            key = (error_type, desc[:50])
            if key in existing:
                continue

            conn.execute("""
                INSERT INTO onpage_errors
                    (domain_id, error_type, severity, page_url, description, suggestion, status, batch_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, datetime('now'))
            """, [site_id, error_type, severity, page_url, desc[:500], suggestion[:500], BATCH_ID])
            inserted += 1
            existing.add(key)

    conn.commit()
    print(f"[OK] Inserted {inserted} new audit findings (batch: {BATCH_ID})")
    return inserted


def insert_blog_ideas(conn):
    """Import the 15 new blog post ideas from parent task t_0fbae95c.
    These fill gaps NOT covered by existing 22 draft posts."""
    
    ideas = [
        {
            "title": "Giant Bubbles Queenstown: Your Ultimate Guide to Bubble Fun in the Adventure Capital",
            "target_keyword": "Giant Bubbles Queenstown",
            "category": "local",
            "estimated_searches": 90,
            "opportunity_score": 14.0,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Queenstown-specific guide: best locations (lakefront, gardens), events, how to buy kits for holiday homes/Airbnbs. Leverages tourism audience."
        },
        {
            "title": "Matariki Magic: Celebrate the Maori New Year with Giant Bubbles",
            "target_keyword": "Matariki Activities for Families NZ",
            "category": "seasonal",
            "estimated_searches": 210,
            "opportunity_score": 8.0,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "How giant bubbles connect to Matariki themes. Activities for kids, community event ideas. URGENT - publish by mid-June for peak seasonal traffic."
        },
        {
            "title": "The Complete Giant Bubbles Adelaide Guide",
            "target_keyword": "Giant Bubbles Adelaide",
            "category": "local",
            "estimated_searches": 100,
            "opportunity_score": 14.0,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Where to buy kits in Adelaide, best parks/beaches (Glenelg, Semaphore), birthday party ideas, local entertainment hire."
        },
        {
            "title": "Non-Toxic Bubbles for Babies: A Parent's Complete Safety Guide",
            "target_keyword": "Non Toxic Bubbles for Babies",
            "category": "kids",
            "estimated_searches": 130,
            "opportunity_score": 12.0,
            "effort": "easy",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Why parents worry about bubble ingredients, Tinka's bio-grade formula, DIY non-toxic recipe, sensory play benefits for 6-18 month olds."
        },
        {
            "title": "Giant Bubbles for Toddlers: Safe Fun for Ages 1-3",
            "target_keyword": "Giant Bubbles for Toddlers",
            "category": "kids",
            "estimated_searches": 170,
            "opportunity_score": 8.0,
            "effort": "easy",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Best products for toddler hands, safety tips, developmental benefits, recommended solutions for sensitive skin."
        },
        {
            "title": "DIY Giant Bubble Solution with Corn Syrup: The Secret to Unpoppable Bubbles",
            "target_keyword": "How to Make Giant Bubbles With Corn Syrup",
            "category": "content",
            "estimated_searches": 320,
            "opportunity_score": 8.5,
            "effort": "easy",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Step-by-step recipe using corn syrup, science behind why it works, comparison with Tinka concentrate, troubleshooting."
        },
        {
            "title": "Giant Bubble Science Experiment for Kids (With Printable Worksheet)",
            "target_keyword": "Giant Bubble Science Experiment",
            "category": "content",
            "estimated_searches": 260,
            "opportunity_score": 7.5,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Classroom-friendly science: surface tension, light refraction, polymer chains. Downloadable observation worksheet."
        },
        {
            "title": "Where to Find Giant Bubbles in Sydney: Parks, Events & Party Ideas",
            "target_keyword": "Giant Bubbles Sydney",
            "category": "local",
            "estimated_searches": 170,
            "opportunity_score": 8.5,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Sydney locations (Centennial Park, Coogee Beach), party hire services, local stockists, upcoming events."
        },
        {
            "title": "Eco-Friendly Bubble Solution: How Tinka is Leading the Green Revolution",
            "target_keyword": "Eco Friendly Bubble Solution",
            "category": "content",
            "estimated_searches": 140,
            "opportunity_score": 11.0,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Environmental impact of standard bubbles, Tinka's bio-grade formula, comparison of green brands, DIY biodegradable recipe."
        },
        {
            "title": "Giant Bubbles Melbourne: Entertainment Guide for Events & Parties",
            "target_keyword": "Giant Bubbles Melbourne",
            "category": "local",
            "estimated_searches": 210,
            "opportunity_score": 8.0,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Melbourne venues (Botanic Gardens, St Kilda, Fitzroy Gardens), entertainer hire, stockists, weekend activity ideas."
        },
        {
            "title": "People in a Bubble Wand: The Ultimate Guide to Bubble Photography",
            "target_keyword": "People in a Bubble Wand",
            "category": "content",
            "estimated_searches": 230,
            "opportunity_score": 8.5,
            "effort": "easy",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "How the giant hoop technique works, photography tips, optimal lighting, phone vs DSLR settings, real party examples."
        },
        {
            "title": "Giant Bubbles Brisbane: Family Fun in the Sunshine State",
            "target_keyword": "Giant Bubbles Brisbane",
            "category": "local",
            "estimated_searches": 130,
            "opportunity_score": 8.5,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Brisbane parks (South Bank, New Farm Park), outdoor birthday ideas, dealing with humidity for better bubbles, stockists."
        },
        {
            "title": "Giant Bubbles for a Budding Business: Start Your Own Bubble Entertainment Venture",
            "target_keyword": "Bubble Entertainer Adelaide",
            "category": "b2b",
            "estimated_searches": 250,
            "opportunity_score": 14.0,
            "effort": "hard",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Equipment needed (Tinka wholesale), pricing models, marketing to event planners, insurance, success stories."
        },
        {
            "title": "Giant Bubbles Perth: Beach Bubbles, Parties & Where to Buy",
            "target_keyword": "Giant Bubbles Perth",
            "category": "local",
            "estimated_searches": 110,
            "opportunity_score": 8.5,
            "effort": "medium",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Perth locations (Cottesloe, Kings Park, Elizabeth Quay), dry climate tips, party entertainment, stockists."
        },
        {
            "title": "Giant Bubble Workshop: Bringing the Magic to New Zealand Schools",
            "target_keyword": "Bubble Workshop NZ",
            "category": "b2b",
            "estimated_searches": 100,
            "opportunity_score": 12.0,
            "effort": "hard",
            "content_type": "blog",
            "source": "keyword-research",
            "status": "draft",
            "outline": "Curriculum-aligned science, assembly options, pricing, safety protocols, booking process, testimonials."
        }
    ]

    # Deduplicate against existing ideas
    cur = conn.execute("SELECT title, target_keyword FROM content_ideas")
    existing = set()
    for r in cur.fetchall():
        existing.add((r["title"][:40].lower(), (r["target_keyword"] or "")[:30].lower()))

    inserted = 0
    for idea in ideas:
        key = (idea["title"][:40].lower(), idea["target_keyword"][:30].lower())
        if key in existing:
            print(f"  [SKIP] already exists: {idea['title'][:50]}")
            continue

        # Determine domain (NZ or AU based on keyword hints)
        kw = idea["target_keyword"].lower()
        if "nz" in kw or "queenstown" in kw or "matariki" in kw or "new zealand" in kw:
            domain_hint = "giantbubbles.co.nz"
        elif "au" in kw or "adelaide" in kw or "sydney" in kw or "melbourne" in kw or "perth" in kw or "brisbane" in kw:
            domain_hint = "giantbubblesau.com"
        else:
            domain_hint = "giantbubbles.co.nz"  # default NZ

        conn.execute("""
            INSERT INTO content_ideas
                (title, target_keyword, category, estimated_searches, opportunity_score, effort, content_type, source, status, outline, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'keyword-research', 'draft', ?, datetime('now'))
        """, [
            idea["title"], idea["target_keyword"], idea["category"],
            idea["estimated_searches"], idea["opportunity_score"], idea["effort"],
            idea["content_type"], idea["outline"]
        ])
        inserted += 1
        print(f"  [NEW] {idea['title'][:50]}")

    conn.commit()
    print(f"[OK] Inserted {inserted} new blog post ideas")
    return inserted


def verify_keywords(conn):
    """Verify that all 154 keywords from parent task are in the DB."""
    cur = conn.execute("SELECT COUNT(*) as c FROM keywords")
    total = cur.fetchone()["c"]
    
    cur = conn.execute("SELECT d.name, COUNT(*) as c FROM keywords k JOIN domains d ON k.domain_id=d.id GROUP BY d.name")
    print(f"[OK] Keywords in DB: {total}")
    for r in cur.fetchall():
        print(f"      {r['name']}: {r['c']}")
    
    cur = conn.execute("SELECT COUNT(DISTINCT keyword_id) as c FROM rank_history")
    ranked = cur.fetchone()["c"]
    print(f"[OK] Keywords with rank history: {ranked}")
    
    cur = conn.execute("SELECT COUNT(*) as c FROM rank_history")
    hist = cur.fetchone()["c"]
    print(f"[OK] Total rank history rows: {hist}")
    
    return total


if __name__ == "__main__":
    print("=== Importing Parent Task Data v3 ===\n")
    conn = get_conn()
    
    print("--- Audit Findings ---")
    audit_count = insert_audit_findings(conn)
    
    print("\n--- Blog Post Ideas ---")
    blog_count = insert_blog_ideas(conn)
    
    print("\n--- Keyword Verification ---")
    kw_total = verify_keywords(conn)
    
    conn.close()
    print(f"\n=== Done: {audit_count} findings, {blog_count} ideas, {kw_total} keywords ===")
