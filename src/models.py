"""
SEO Dashboard — Python Data Models

Defines dataclasses for all entities and JSON import helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


# ── Domain ────────────────────────────────────────────────────────────────────

@dataclass
class Domain:
    url: str
    label: str
    is_primary: bool = False
    id: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Domain:
        return cls(
            id=row["id"],
            url=row["url"],
            label=row["label"],
            is_primary=bool(row["is_primary"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Keyword ──────────────────────────────────────────────────────────────────

@dataclass
class Keyword:
    keyword: str
    domain_id: int
    monthly_volume: int = 0
    keyword_difficulty: float = 0.0
    cpc: float = 0.0
    id: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Keyword:
        return cls(
            id=row["id"],
            keyword=row["keyword"],
            domain_id=row["domain_id"],
            monthly_volume=row["monthly_volume"] or 0,
            keyword_difficulty=row["keyword_difficulty"] or 0.0,
            cpc=row["cpc"] or 0.0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Rank Record (GSC daily data) ──────────────────────────────────────────────

@dataclass
class RankRecord:
    keyword_id: int
    domain_id: int
    date: str
    position: float | None = None
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    id: int | None = None
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> RankRecord:
        return cls(
            id=row["id"],
            keyword_id=row["keyword_id"],
            domain_id=row["domain_id"],
            date=row["date"],
            position=row["position"],
            clicks=row["clicks"] or 0,
            impressions=row["impressions"] or 0,
            ctr=row["ctr"] or 0.0,
            created_at=row["created_at"],
        )

    @classmethod
    def from_gsc_row(cls, row: dict[str, Any], keyword_id: int, domain_id: int) -> RankRecord:
        """Create from a GSC API response row."""
        return cls(
            keyword_id=keyword_id,
            domain_id=domain_id,
            date=row.get("date", _today()),
            position=row.get("position"),
            clicks=row.get("clicks", 0),
            impressions=row.get("impressions", 0),
            ctr=row.get("ctr", 0.0),
        )


# ── SEO Issue ─────────────────────────────────────────────────────────────────

@dataclass
class SeoIssue:
    domain_id: int
    issue_type: str
    severity: str = "moderate"
    detail: str | None = None
    suggested_fix: str | None = None
    status: str = "open"
    keyword_id: int | None = None
    id: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SeoIssue:
        return cls(
            id=row["id"],
            domain_id=row["domain_id"],
            keyword_id=row.get("keyword_id"),
            issue_type=row["issue_type"],
            severity=row["severity"],
            detail=row["detail"],
            suggested_fix=row["suggested_fix"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── Content Idea ──────────────────────────────────────────────────────────────

@dataclass
class ContentIdea:
    title: str
    target_keyword: str
    description: str | None = None
    priority: int = 5
    source: str = "manual"
    effort: str = "medium"
    status: str = "draft"
    date_added: str = field(default_factory=_today)
    id: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ContentIdea:
        return cls(
            id=row["id"],
            title=row["title"],
            target_keyword=row["target_keyword"],
            description=row.get("description"),
            priority=row.get("priority", 5),
            source=row.get("source", "manual"),
            effort=row.get("effort", "medium"),
            status=row["status"],
            date_added=row.get("date_added", _today()),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ── On-Page Error ─────────────────────────────────────────────────────────────

@dataclass
class OnPageError:
    url: str
    domain_id: int
    error_type: str
    severity: str = "warning"
    detail: str | None = None
    suggested_fix: str | None = None
    status: str = "open"
    discovered_at: str = field(default_factory=_now)
    check_batch: str | None = None
    source: str = "crawler"
    fixed_at: str | None = None
    id: int | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> OnPageError:
        return cls(
            id=row["id"],
            url=row["url"],
            domain_id=row["domain_id"],
            error_type=row["error_type"],
            severity=row["severity"],
            detail=row.get("detail"),
            suggested_fix=row.get("suggested_fix"),
            status=row["status"],
            discovered_at=row.get("discovered_at", ""),
            check_batch=row.get("check_batch"),
            source=row.get("source", "crawler"),
            fixed_at=row.get("fixed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> OnPageError:
        """Create from a JSON/crawler response dict with flexible key names."""
        key_map = {
            "page_url": "url", "uri": "url", "path": "url",
            "type": "error_type", "issue_type": "error_type", "error": "error_type",
            "fix": "suggested_fix", "recommendation": "suggested_fix",
        }
        mapped = {}
        for k, v in d.items():
            target = key_map.get(k, k)
            mapped[target] = v
            if target != k:
                mapped.setdefault(k, v)

        return cls(
            url=mapped.get("url", ""),
            domain_id=mapped.get("domain_id", 0),
            error_type=mapped.get("error_type", "unknown"),
            severity=mapped.get("severity", "warning"),
            detail=mapped.get("detail"),
            suggested_fix=mapped.get("suggested_fix"),
            status=mapped.get("status", "open"),
            discovered_at=mapped.get("discovered_at", _now()),
            check_batch=mapped.get("check_batch"),
            source=mapped.get("source", "crawler"),
        )


# ── Error Type Registry ───────────────────────────────────────────────────────

ERROR_TYPES: dict[str, str] = {
    "broken_link": "Broken link (404 or dead URL)",
    "missing_title": "Page is missing an HTML <title> tag",
    "missing_meta": "Page is missing a meta description",
    "duplicate_title": "Duplicate title across multiple pages",
    "duplicate_meta": "Duplicate meta description across pages",
    "missing_h1": "Page is missing an H1 heading",
    "multiple_h1": "Page has more than one H1 heading",
    "broken_image": "Image with broken src or alt text missing",
    "slow_page": "Page load time exceeds threshold",
    "no_robots": "Page missing robots.txt or has restrictive rules",
    "no_sitemap": "No XML sitemap found",
    "not_indexed": "Page not indexed by search engines",
    "thin_content": "Page has very little content (< 300 words)",
    "mobile_issues": "Mobile usability issues detected",
    "https_issues": "Mixed content or HTTPS configuration issues",
    "canonical_issues": "Missing or conflicting canonical tags",
    "redirect_chain": "Excessive redirects (3+ hops)",
    "orphan_page": "Page has no internal links pointing to it",
}


# ── Sync Log Entry ───────────────────────────────────────────────────────────

@dataclass
class SyncLogEntry:
    sync_type: str
    status: str = "running"
    rows_processed: int = 0
    error_detail: str | None = None
    id: int | None = None
    started_at: str = field(default_factory=_now)
    completed_at: str | None = None


# ── Utility ──────────────────────────────────────────────────────────────────

def load_json_errors(path: str) -> list[dict[str, Any]]:
    """Load errors from a JSON file (list of dicts)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return [data]
    return data


def normalize_error_type(raw: str) -> str:
    """Map raw error type strings to canonical types."""
    mapping = {
        "404": "broken_link", "dead_link": "broken_link", "dead": "broken_link",
        "no_title": "missing_title", "no title": "missing_title", "missing title": "missing_title",
        "no_meta": "missing_meta", "no meta": "missing_meta", "missing meta": "missing_meta",
        "dup_title": "duplicate_title", "duplicate title": "duplicate_title",
        "dup_meta": "duplicate_meta", "duplicate meta": "duplicate_meta",
        "no_h1": "missing_h1", "missing h1": "missing_h1",
        "multi_h1": "multiple_h1", "multiple h1": "multiple_h1",
        "img_broken": "broken_image", "broken image": "broken_image",
        "slow": "slow_page", "slow page": "slow_page",
        "no_robots.txt": "no_robots",
        "no sitemap": "no_sitemap",
        "not indexed": "not_indexed",
        "thin": "thin_content", "thin content": "thin_content",
        "mobile": "mobile_issues", "mobile issues": "mobile_issues",
        "https": "https_issues", "https issues": "https_issues",
        "canonical": "canonical_issues", "canonical issues": "canonical_issues",
        "redirect": "redirect_chain", "redirect chain": "redirect_chain",
        "orphan": "orphan_page", "orphan page": "orphan_page",
    }
    return mapping.get(raw.strip().lower(), raw.strip().replace(" ", "_").lower())
