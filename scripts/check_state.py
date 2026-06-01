#!/usr/bin/env python3
"""Check current DB state."""
import sqlite3
from pathlib import Path

DB = Path("C:/Users/heysh/OneDrive/Desktop/tinka-seo-dashboard/data/seo_dashboard.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

print("=== KEYWORD COUNTS ===")
for r in conn.execute("SELECT d.name, COUNT(*) as cnt FROM keywords k JOIN domains d ON k.domain_id=d.id GROUP BY d.name").fetchall():
    print(f"  {r['name']}: {r['cnt']}")
print(f"  Total: {conn.execute('SELECT COUNT(*) FROM keywords').fetchone()[0]}")

print()
print("=== ONPAGE ERRORS (by batch and status) ===")
for r in conn.execute("SELECT batch_id, status, COUNT(*) as cnt FROM onpage_errors GROUP BY batch_id, status ORDER BY batch_id").fetchall():
    print(f"  batch={r['batch_id']}, status={r['status']}: {r['cnt']}")

print()
print("=== ONPAGE ERRORS (open, by severity) ===")
total_open = conn.execute("SELECT COUNT(*) FROM onpage_errors WHERE status='open'").fetchone()[0]
for r in conn.execute("SELECT severity, COUNT(*) as cnt FROM onpage_errors WHERE status='open' GROUP BY severity ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END").fetchall():
    print(f"  {r['severity']}: {r['cnt']}")
print(f"  Total open: {total_open}")

print()
print("=== RANKINGS (recent) ===")
ranked = conn.execute("SELECT COUNT(DISTINCT keyword_id) FROM rank_history WHERE (keyword_id, date) IN (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)").fetchone()[0]
print(f"  Keywords with recent rank data: {ranked}")
total_rh = conn.execute("SELECT COUNT(*) FROM rank_history").fetchone()[0]
print(f"  Total rank_history rows: {total_rh}")

print()
print("=== CONTENT IDEAS ===")
print(f"  Total: {conn.execute('SELECT COUNT(*) FROM content_ideas').fetchone()[0]}")

conn.close()
