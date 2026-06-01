#!/usr/bin/env python3
"""Compare old manual errors vs new audit errors."""
import sqlite3
from pathlib import Path

DB = Path("C:/Users/heysh/OneDrive/Desktop/tinka-seo-dashboard/data/seo_dashboard.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

print("=== OLD MANUAL ERRORS (open) ===")
for r in conn.execute("SELECT e.id, d.name as domain, e.error_type, e.severity, e.page_url FROM onpage_errors e JOIN domains d ON e.domain_id=d.id WHERE e.batch_id LIKE 'manual%' AND e.status='open' ORDER BY e.severity, d.name").fetchall():
    print(f"  [{r['id']}] {r['severity']} | {r['domain']} | {r['error_type']} @ {r['page_url']}")

print()
print("=== NEW AUDIT ERRORS (parent-task-audit-v2, open) ===")
for r in conn.execute("SELECT e.id, d.name as domain, e.error_type, e.severity, e.page_url FROM onpage_errors e JOIN domains d ON e.domain_id=d.id WHERE e.batch_id='parent-task-audit-v2' AND e.status='open' ORDER BY e.severity, d.name").fetchall():
    print(f"  [{r['id']}] {r['severity']} | {r['domain']} | {r['error_type']} @ {r['page_url']}")

conn.close()
