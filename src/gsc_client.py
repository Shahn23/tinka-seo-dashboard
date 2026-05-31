"""
SEO Dashboard — GSC Client

Live and mock Google Search Console data fetching.
Uses service account authentication for live mode.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from typing import Any

from src.models import RankRecord


class GSCClient:
    """Google Search Console data fetcher with mock and live modes."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.gsc_config = self.config.get("gsc", {})
        self._service = None

    def is_live_available(self) -> bool:
        """Check if live GSC API is configured."""
        if not self.gsc_config.get("enabled"):
            return False
        sa_file = self.gsc_config.get("service_account_file", "")
        return bool(sa_file) and os.path.exists(os.path.expanduser(sa_file))

    def fetch_rankings(
        self,
        site_url: str,
        days: int = 7,
        live: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch ranking data from GSC.

        Args:
            site_url: The GSC site URL (e.g., 'sc-domain:giantbubbles.co.nz')
            days: Number of days of history to fetch
            live: If True, use live API; otherwise return mock data

        Returns:
            List of dicts with keys: date, query, position, clicks, impressions, ctr
        """
        if live:
            return self._fetch_live(site_url, days)
        return self._fetch_mock(site_url, days)

    def test_connection(self, site_url: str) -> dict[str, Any]:
        """Test GSC API connection. Returns connection status."""
        if self.is_live_available():
            return {"status": "ok", "mode": "live", "message": "GSC API configured"}
        return {"status": "ok", "mode": "mock", "message": "Using mock data mode"}

    def _fetch_live(self, site_url: str, days: int) -> list[dict[str, Any]]:
        """Fetch real data from GSC API."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "google-api-python-client and google-auth are required for live mode. "
                "Install with: pip install google-api-python-client google-auth"
            )

        sa_file = os.path.expanduser(self.gsc_config.get("service_account_file", ""))
        if not os.path.exists(sa_file):
            raise FileNotFoundError(f"Service account file not found: {sa_file}")

        credentials = service_account.Credentials.from_service_account_file(
            sa_file, scopes=["https://www.googleapis.com/auth/webmasters.readonly"]
        )
        service = build("searchconsole", "v1", credentials=credentials)

        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        request = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["date", "query"],
            "rowLimit": 25000,
        }

        response = service.searchanalytics().query(
            siteUrl=site_url, body=request
        ).execute()

        rows = response.get("rows", [])
        results = []
        for row in rows:
            results.append({
                "date": row["keys"][0],
                "query": row["keys"][1],
                "clicks": row["clicks"],
                "impressions": row["impressions"],
                "ctr": row["ctr"],
                "position": row["position"],
            })
        return results

    def _fetch_mock(self, site_url: str, days: int) -> list[dict[str, Any]]:
        """Generate realistic mock GSC data for testing."""
        domain_label = "AU" if "au" in site_url.lower() else "NZ"
        queries = {
            "AU": [
                "giant bubble kit", "how to make giant bubbles", "bubble party ideas",
                "giant bubbles for kids", "outdoor party entertainment",
                "birthday party bubbles", "bubble solution recipe", "giant bubble wand",
            ],
            "NZ": [
                "party entertainment auckland", "giant bubbles nz",
                "kids party entertainment auckland", "bubble show auckland",
                "outdoor party hire auckland", "giant bubble kit nz",
                "bubble entertainer auckland", "children's party entertainment",
            ],
        }
        selected_queries = queries.get(domain_label, queries["AU"])
        # Seed for reproducibility
        rng = random.Random(f"{site_url}-{days}")
        results = []
        for day_offset in range(days):
            date = (datetime.utcnow() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            for query in selected_queries:
                pos = rng.randint(3, 45)
                impressions = rng.randint(50, 2000)
                ctr = rng.uniform(0.01, 0.15)
                clicks = max(1, int(impressions * ctr))
                results.append({
                    "date": date,
                    "query": query,
                    "clicks": clicks,
                    "impressions": impressions,
                    "ctr": ctr,
                    "position": pos,
                })
        return results

    def records_for_db(
        self, results: list[dict[str, Any]], domain_id: int
    ) -> dict[str, list[RankRecord]]:
        """Convert GSC API results to RankRecord objects, keyed by keyword text."""
        from src.database import Database
        db = Database(self.config.get("database", {}).get("path", "data/seo_dashboard.db"))
        records_by_keyword: dict[str, list[RankRecord]] = {}
        for row in results:
            keyword_text = row["query"]
            keywords = db.search_keywords(keyword_text, domain_id=domain_id)
            if not keywords:
                continue
            kw = keywords[0]
            record = RankRecord.from_gsc_row(row, kw.id, domain_id)
            records_by_keyword.setdefault(keyword_text, []).append(record)
        return records_by_keyword
