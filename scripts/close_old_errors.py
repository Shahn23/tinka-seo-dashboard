#!/usr/bin/env python3
"""Close old manual errors and show final state."""
import sqlite3
from pathlib import Path

DB = Path("C:/Users/heysh/OneDrive/Desktop/tinka-seo-dashboard/data/seo_dashboard.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# Close old manual errors
result = conn.execute("UPDATE onpage_errors SET status='fixed', fixed_at=datetime('now') WHERE batch_id LIKE 'manual%' AND status='open'")
print(f"Closed {result.rowcount} old manual errors (superseded by comprehensive audit)")
conn.commit()

# Check final state
print()
print("=== FINAL ONPAGE ERROR STATE ===")
for r in conn.execute("SELECT batch_id, status, COUNT(*) as cnt FROM onpage_errors GROUP BY batch_id, status ORDER BY batch_id").fetchall():
    print(f"  batch={r['batch_id']}, status={r['status']}: {r['cnt']}")

print()
print("=== OPEN ERRORS (by severity) ===")
for r in conn.execute("SELECT severity, COUNT(*) as cnt FROM onpage_errors WHERE status='open' GROUP BY severity ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END").fetchall():
    print(f"  {r['severity']}: {r['cnt']}")
total_open = conn.execute("SELECT COUNT(*) FROM onpage_errors WHERE status='open'").fetchone()[0]
print(f"  Total open: {total_open}")
total_err = conn.execute("SELECT COUNT(*) FROM onpage_errors").fetchone()[0]
print(f"  Total errors in DB: {total_err}")

conn.close()
