#!/usr/bin/env python3
"""
Initialize the SEO Dashboard database.
Creates tables, views, and seeds the domains.
"""

from __future__ import annotations

import os
import sys


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, base_dir)

    from src.database import Database

    schema_path = os.path.join(base_dir, "data", "schema.sql")
    db_path = os.path.join(base_dir, "data", "seo_dashboard.db")

    # Remove existing DB for a clean init
    if os.path.exists(db_path):
        os.remove(db_path)

    db = Database(db_path, schema_path)

    # Seed domains
    from src.models import Domain

    domains = [
        Domain(url="giantbubblesau.com", label="Australia", is_primary=True),
        Domain(url="giantbubbles.co.nz", label="New Zealand", is_primary=False),
    ]
    for d in domains:
        domain_id = db.upsert_domain(d)
        print(f"[init] Domain: {d.url} → id={domain_id}")

    print(f"[init] Database created at {db_path}")
    print("[init] Done.")


if __name__ == "__main__":
    main()
