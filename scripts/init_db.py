"""Initialize SEO dashboard database with schema and seed data."""
import sqlite3, json, os, random
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_db():
    db = os.path.join(BASE, "data", "seo_dashboard.db")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    conn = sqlite3.connect(db)
    with open(os.path.join(BASE, "data", "schema.sql")) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn, db

def run():
    conn, db_path = get_db()
    t = datetime.now()

    # domains
    domains = [
        ("giantbubbles.co.nz", "Giant Bubbles NZ", "sc_domain:https://giantbubbles.co.nz/"),
        ("giantbubblesau.com", "Giant Bubbles AU", "sc_domain:https://giantbubblesau.com/"),
    ]
    for n, dn, gsc in domains:
        conn.execute("INSERT OR IGNORE INTO domains(name,display_name,gsc_site_url) VALUES(?,?,?)", (n,dn,gsc))

    # keywords
    kws = [
        (2,"Giant Bubble Kit","product","commercial",590,8.5,45,1),
        (2,"Bubble Solution Recipe","content","informational",590,8.0,35,1),
        (2,"Birthday Party Bubbles","party","commercial",390,8.5,40,1),
        (2,"Party Entertainment Auckland","local","commercial",110,8.5,30,1),
        (2,"Warehouse Bubble Wand","product","commercial",170,7.5,50,0),
        (2,"Best Bubble Solution","product","commercial",320,8.0,55,1),
        (2,"Outdoor Toys Australia","product","commercial",480,7.0,60,0),
        (2,"Giant Bubbles For Kids","kids","informational",390,8.0,35,1),
        (2,"Giant Bubble Wedding","content","informational",210,7.5,40,0),
        (2,"How To Make Giant Bubbles","content","informational",720,9.0,30,1),
        (2,"Giant Bubble Concentrate","product","commercial",140,7.0,45,0),
        (2,"Giant Bubbles For Events","b2b","commercial",110,8.0,35,1),
        (2,"Giant Bubble Wand Australia","product","commercial",170,7.5,50,0),
        (2,"Kids Outdoor Activities","kids","informational",880,7.0,30,0),
        (2,"Bubble Entertainer","b2b","commercial",90,8.0,25,1),
        (2,"Wholesale Giant Bubbles","b2b","commercial",110,8.5,20,1),
        (2,"Giant Bubbles For Dogs","kids","informational",140,6.5,25,0),
        (2,"Bubble Wand For Kids","kids","commercial",260,7.5,40,0),
        (1,"Giant Bubble Kit NZ","product","commercial",320,8.5,40,1),
        (1,"Giant Bubble Wand NZ","product","commercial",210,8.0,35,1),
        (1,"Bubble Entertainer Auckland","local","commercial",140,8.5,25,1),
        (1,"Giant Bubbles NZ","brand_general","informational",260,7.5,30,0),
        (1,"Party Bubbles Auckland","party","commercial",170,8.0,30,0),
        (1,"Bubble Solution NZ","product","commercial",90,7.5,35,0),
        (1,"Wholesale Bubbles NZ","b2b","commercial",70,8.0,15,0),
    ]
    for k in kws:
        conn.execute("INSERT OR IGNORE INTO keywords(domain_id,keyword,category,intent,volume,opportunity_score,difficulty,is_high_priority) VALUES(?,?,?,?,?,?,?,?)", k)

    # rank_history mock 90 days
    random.seed(42)
    curs = conn.execute("SELECT id, opportunity_score FROM keywords")
    for kw_id, score in curs.fetchall():
        for d in range(90):
            date = (t - timedelta(days=d)).strftime("%Y-%m-%d")
            bp = max(1, 15 - score * 1.2 + random.uniform(-3, 3))
            cl = int(max(0, random.gauss(20, 15) * (1 / max(bp/10, 0.5))))
            im = int(max(0, random.gauss(200, 100)))
            conn.execute("INSERT OR IGNORE INTO rank_history(keyword_id,date,position,clicks,impressions,ctr) VALUES(?,?,?,?,?,?)",
                         (kw_id, date, round(bp,1), cl, im, round(cl/max(im,1),4)))
    conn.commit()

    # Realistic GSC-style data for NZ queries
    nz_data = {
        "Giant Bubbles NZ": {"pos":8.3,"cl":45,"im":520},
        "Giant Bubble Wand NZ": {"pos":11.2,"cl":28,"im":380},
        "Giant Bubble Kit NZ": {"pos":6.5,"cl":72,"im":610},
        "Bubble Entertainer Auckland": {"pos":4.2,"cl":95,"im":420},
        "Bubble Solution NZ": {"pos":14.7,"cl":12,"im":290},
        "Party Bubbles Auckland": {"pos":9.8,"cl":35,"im":310},
    }
    random.seed(2026)
    for kw_name, bd in nz_data.items():
        row = conn.execute("SELECT id FROM keywords WHERE keyword=?", (kw_name,)).fetchone()
        if not row: continue
        kw_id = row[0]
        for d in range(14):
            date = (t - timedelta(days=d)).strftime("%Y-%m-%d")
            p = max(1, bd["pos"] + random.uniform(-1.5, 1.5))
            cl = max(0, int(bd["cl"] + random.gauss(0, bd["cl"]*0.15)))
            im = max(0, int(bd["im"] + random.gauss(0, bd["im"]*0.1)))
            conn.execute("INSERT OR IGNORE INTO rank_history(keyword_id,date,position,clicks,impressions,ctr) VALUES(?,?,?,?,?,?)",
                         (kw_id, date, round(p,1), cl, im, round(cl/max(im,1),4)))

    # onpage_errors
    issues = [
        (1,"duplicate_content","critical","https://giantbubbles.co.nz/","Duplicate content across .co.nz and .com.au","Implement hreflang tags and rel=canonical"),
        (1,"stale_content","high","https://giantbubbles.co.nz/blogs/","Blog stale 2.5 years (last post Dec 2023)","Publish fresh blog content monthly"),
        (1,"broken_link","high","https://giantbubbles.co.nz/pages/about-us","About Us page returns 404","Create page or 301 redirect"),
        (1,"meta_description","moderate","https://giantbubbles.co.nz/products/*","Auto-generated product meta descriptions","Write unique 120-160 char meta descriptions"),
        (1,"missing_schema","moderate","https://giantbubbles.co.nz/","Missing Organization and BreadcrumbList schema","Add Organization+BreadcrumbList schema"),
        (1,"missing_gmb","high","https://giantbubbles.co.nz/","No Google My Business listing","Create GMB for local pack presence"),
        (1,"page_speed","moderate","https://giantbubbles.co.nz/","Mobile page speed ~60/100","Compress images, reduce render-blocking resources"),
        (1,"alt_text","moderate","https://giantbubbles.co.nz/products/*","Missing alt text on product images","Add descriptive alt text with keywords"),
        (2,"schema_url_mismatch","critical","https://giantbubblesau.com/products/*","Schema Offer URLs point to .co.nz","Update schema JSON-LD to use .com.au"),
        (2,"duplicate_content","critical","https://giantbubblesau.com/","Duplicate content across domains","Implement hreflang, differentiate content"),
        (2,"missing_hreflang","high","https://giantbubblesau.com/","Missing hreflang en-nz / en-au","Add hreflang tags to all pages"),
        (2,"meta_description","moderate","https://giantbubblesau.com/products/*","Auto-generated meta descriptions","Write unique meta descriptions for AU"),
        (2,"missing_schema","moderate","https://giantbubblesau.com/","Missing Organization and BreadcrumbList","Add Organization schema with AU details"),
        (2,"page_speed","moderate","https://giantbubblesau.com/","Mobile page speed ~55/100","Compress images, enable caching"),
        (2,"alt_text","moderate","https://giantbubblesau.com/products/*","Missing alt text AU product images","Add keyword-optimized alt text"),
        (2,"thin_content","moderate","https://giantbubblesau.com/","Very thin content on AU site","Add unique descriptions, start AU blog"),
    ]
    for iss in issues:
        conn.execute("INSERT INTO onpage_errors(domain_id,error_type,severity,page_url,description,suggestion,status) VALUES(?,?,?,?,?,?,'open')", iss)

    # content_ideas
    ideas = [
        ("The Ultimate Guide to Giant Bubbles","How To Make Giant Bubbles","How-To",720,9,"medium","blog"),
        ("5 DIY Bubble Solution Recipes Tested & Ranked","Bubble Solution Recipe","How-To",590,8,"easy","blog"),
        ("Best Giant Bubble Kit 2026: Buyer's Guide","Giant Bubble Kit","Product Comparison",590,9,"medium","blog"),
        ("10 Epic Birthday Party Bubble Ideas","Birthday Party Bubbles","Party Planning",390,8.5,"easy","blog"),
        ("How to Throw the Perfect Giant Bubble Party","Party Entertainment Auckland","Party Planning",110,8.5,"medium","blog"),
        ("Giant Bubbles for Kids: Ultimate Parent's Guide","Giant Bubbles For Kids","Kids Activities",390,8,"easy","blog"),
        ("Giant Bubbles for Weddings: Magical Photo Ideas","Giant Bubble Wedding","Party Planning",210,7.5,"medium","blog"),
        ("Where to Buy the Best Bubble Wand in Australia","Warehouse Bubble Wand","Product Comparison",170,7.5,"easy","blog"),
        ("Giant Bubble Wand vs Regular Wand: Which is Best?","Best Bubble Solution","Product Comparison",320,8,"medium","blog"),
        ("50 Fun Outdoor Activities for Kids This Summer","Outdoor Toys Australia","Kids Activities",480,7,"easy","blog"),
        ("How to Make Giant Bubbles With Pool Noodles","How To Make Giant Bubbles","How-To",720,8.5,"easy","blog"),
        ("Giant Bubbles for Corporate Events & Festivals","Giant Bubbles For Events","B2B",110,8,"medium","blog"),
        ("Hiring a Bubble Entertainer: Complete Guide","Bubble Entertainer","Local",90,8,"medium","blog"),
        ("Giant Bubble Concentrate vs Ready-Made","Giant Bubble Concentrate","Product Comparison",140,7,"medium","blog"),
        ("Why Dogs LOVE Giant Bubbles (Vet-Approved Guide)","Giant Bubbles For Dogs","Kids Activities",140,6.5,"easy","blog"),
        ("Seasonal Marketing: Bubbles for Summer Holidays","Party Bubbles Auckland","Seasonal",170,8,"easy","blog"),
        ("Bulk Buying Wholesale Giant Bubbles: Retailer's Guide","Wholesale Giant Bubbles","B2B",110,8.5,"medium","blog"),
        ("Giant Bubbles vs Regular Bubbles vs Bubble Machines","Giant Bubble Kit NZ","Product Comparison",320,8.5,"medium","blog"),
        ("Best Bubble Solution: Dawn vs Fairy vs Homemade","Bubble Solution NZ","Product Comparison",90,7.5,"easy","blog"),
        ("Auckland's Best Bubble Fun Spots: Local's Guide","Bubble Entertainer Auckland","Local",140,8.5,"medium","blog"),
    ]
    for idea in ideas:
        conn.execute("INSERT INTO content_ideas(title,target_keyword,category,estimated_searches,opportunity_score,effort,content_type,status) VALUES(?,?,?,?,?,?,?,'draft')", idea)

    conn.commit()
    conn.close()
    print(f"Database created: {db_path}")
    c = sqlite3.connect(db_path)
    for tbl in ["domains","keywords","rank_history","onpage_errors","content_ideas"]:
        print(f"  {tbl}: {c.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]}")
    c.close()

if __name__ == "__main__":
    run()
