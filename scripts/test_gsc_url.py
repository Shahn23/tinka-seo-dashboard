"""Test GSC connection with proper URLs"""
import sys, os, json

sys.path.insert(0, r'C:\Users\heysh\OneDrive\Desktop\tinka-seo-dashboard')
CREDENTIALS = os.path.join(os.path.expanduser('~'), '.hermes', 'gsc-credentials.json')

from google.oauth2 import service_account
from googleapiclient.discovery import build

creds = service_account.Credentials.from_service_account_file(
    CREDENTIALS, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
)
service = build("searchconsole", "v1", credentials=creds)

# Get the correct site URL from the API
sites = service.sites().list().execute()
for s in sites.get("siteEntry", []):
    proper_url = s['siteUrl']
    print(f"Correct GSC URL: {proper_url}")
    
    # Query with the proper URL
    request = {"startDate": "2026-06-01", "endDate": "2026-06-07", "dimensions": ["query"], "rowLimit": 30}
    response = service.searchanalytics().query(siteUrl=proper_url, body=request).execute()
    rows = response.get("rows", [])
    print(f"  Queries found: {len(rows)}")
    for row in rows[:15]:
        print(f"    {row['keys'][0]:40s} clicks={row.get('clicks',0):3d} pos={row.get('position',0):.1f}")
    print()

# Also check what the DB has
import sqlite3
conn = sqlite3.connect(r'C:\Users\heysh\OneDrive\Desktop\tinka-seo-dashboard\data\seo_dashboard.db')
conn.row_factory = sqlite3.Row
doms = conn.execute('SELECT id, name, gsc_site_url FROM domains WHERE is_active=1').fetchall()
for d in doms:
    print(f"DB has: name={d['name']}, gsc_site_url={d['gsc_site_url']}")
conn.close()
