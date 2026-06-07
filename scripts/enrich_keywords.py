"""Phase 0.3: Enrich keywords with real DataForSEO volume & difficulty."""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATAFORSEO_LOGIN'] = 'hey@giantbubbles.co.nz'
os.environ['DATAFORSEO_PASSWORD'] = 'a4b3bbc3c8c6df19'

from scripts.dataforseo_client import get_keyword_volume, get_keyword_difficulty

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'seo_dashboard.db')
LOCATION_MAP = {1: 'New Zealand', 2: 'Australia'}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
keywords = conn.execute('SELECT id, keyword, domain_id, volume, difficulty FROM keywords ORDER BY domain_id, id').fetchall()
print(f"Total keywords: {len(keywords)}")

updated_vol = 0
updated_diff = 0

for domain_id, loc in [(1, 'New Zealand'), (2, 'Australia')]:
    domain_kws = [k for k in keywords if k['domain_id'] == domain_id]
    kw_texts = [k['keyword'] for k in domain_kws]
    kw_map = {k['keyword'].lower(): k['id'] for k in domain_kws}
    domain_name = conn.execute('SELECT name FROM domains WHERE id=?', (domain_id,)).fetchone()['name']
    print(f"\n{domain_name} ({loc}) — {len(domain_kws)} keywords")

    if kw_texts:
        # Volume
        try:
            vol_results = get_keyword_volume(kw_texts, location_name=loc)
            for vr in vol_results:
                kid = kw_map.get(vr['keyword'].lower())
                if kid:
                    conn.execute("UPDATE keywords SET volume=? WHERE id=?", (vr['search_volume'], kid))
                    updated_vol += 1
            print(f"  Volume: {len(vol_results)} results, cost tracked by API")
        except Exception as e:
            print(f"  Volume failed: {e}")

        # Difficulty
        try:
            diff_results = get_keyword_difficulty(kw_texts, location_name=loc)
            for dr in diff_results:
                kid = kw_map.get(dr['keyword'].lower())
                if kid:
                    conn.execute("UPDATE keywords SET difficulty=? WHERE id=?", (dr['difficulty'], kid))
                    updated_diff += 1
            print(f"  Difficulty: {len(diff_results)} results")
        except Exception as e:
            print(f"  Difficulty failed: {e}")

        conn.commit()

conn.close()

print(f"\nUpdated volumes: {updated_vol} | Updated difficulties: {updated_diff}")
