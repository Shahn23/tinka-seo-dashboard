"""
SEO Dashboard — Database Connection and CRUD Layer

SQLite-backed with WAL mode for concurrent reads, upsert semantics,
and views for common query patterns.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Iterator

from src.models import (
    ContentIdea,
    Domain,
    Keyword,
    OnPageError,
    RankRecord,
    SeoIssue,
    SyncLogEntry,
)


class Database:
    """SQLite database wrapper with upsert semantics for all entities."""

    def __init__(self, db_path: str, schema_path: str | None = None):
        self.db_path = db_path
        self._schema_path = schema_path
        if schema_path and not os.path.exists(db_path):
            self._init_schema(schema_path)

    def init_schema(self) -> None:
        """(Re)initialize the database schema. Safe to call if tables exist."""
        if self._schema_path and os.path.exists(self._schema_path):
            self._init_schema(self._schema_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self, schema_path: str) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()
        conn = self._connect()
        conn.executescript(sql)
        conn.commit()
        conn.close()

    # ── Domains ───────────────────────────────────────────────────────────

    def upsert_domain(self, domain: Domain) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO domains (url, label, is_primary, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       label=excluded.label,
                       is_primary=excluded.is_primary,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'""",
                (domain.url, domain.label, int(domain.is_primary),
                 domain.created_at, domain.updated_at),
            )
            conn.commit()
            return cur.lastrowid or self._get_domain_id(domain.url)
        finally:
            conn.close()

    def _get_domain_id(self, url: str) -> int | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM domains WHERE url = ?", (url,)).fetchone()
            return row["id"] if row else None
        finally:
            conn.close()

    def list_domains(self) -> list[Domain]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM domains ORDER BY is_primary DESC, url"
            ).fetchall()
            return [Domain.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_domain(self, domain_id: int) -> Domain | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM domains WHERE id = ?", (domain_id,)
            ).fetchone()
            return Domain.from_row(dict(row)) if row else None
        finally:
            conn.close()

    # ── Keywords ──────────────────────────────────────────────────────────

    def upsert_keyword(self, keyword: Keyword) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO keywords (keyword, domain_id, monthly_volume, keyword_difficulty, cpc, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(keyword, domain_id) DO UPDATE SET
                       monthly_volume=excluded.monthly_volume,
                       keyword_difficulty=excluded.keyword_difficulty,
                       cpc=excluded.cpc,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'""",
                (keyword.keyword, keyword.domain_id, keyword.monthly_volume,
                 keyword.keyword_difficulty, keyword.cpc,
                 keyword.created_at, keyword.updated_at),
            )
            conn.commit()
            if cur.lastrowid and cur.lastrowid > 0:
                return cur.lastrowid
            row = conn.execute(
                "SELECT id FROM keywords WHERE keyword = ? AND domain_id = ?",
                (keyword.keyword, keyword.domain_id),
            ).fetchone()
            return row["id"] if row else 0
        finally:
            conn.close()

    def list_keywords(self, domain_id: int | None = None) -> list[Keyword]:
        conn = self._connect()
        try:
            if domain_id:
                rows = conn.execute(
                    "SELECT * FROM keywords WHERE domain_id = ? ORDER BY keyword",
                    (domain_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM keywords ORDER BY keyword"
                ).fetchall()
            return [Keyword.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def get_keyword(self, keyword_id: int) -> Keyword | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM keywords WHERE id = ?", (keyword_id,)
            ).fetchone()
            return Keyword.from_row(dict(row)) if row else None
        finally:
            conn.close()

    def search_keywords(self, query: str, domain_id: int | None = None) -> list[Keyword]:
        conn = self._connect()
        try:
            if domain_id:
                rows = conn.execute(
                    "SELECT * FROM keywords WHERE keyword LIKE ? AND domain_id = ? ORDER BY keyword",
                    (f"%{query}%", domain_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM keywords WHERE keyword LIKE ? ORDER BY keyword",
                    (f"%{query}%",),
                ).fetchall()
            return [Keyword.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── Rank History ──────────────────────────────────────────────────────

    def upsert_rank(self, record: RankRecord) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO rank_history (keyword_id, domain_id, date, position, clicks, impressions, ctr, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(keyword_id, domain_id, date) DO UPDATE SET
                       position=excluded.position,
                       clicks=excluded.clicks,
                       impressions=excluded.impressions,
                       ctr=excluded.ctr""",
                (record.keyword_id, record.domain_id, record.date,
                 record.position, record.clicks, record.impressions,
                 record.ctr, record.created_at),
            )
            conn.commit()
            return cur.lastrowid or 0
        finally:
            conn.close()

    def upsert_ranks_batch(self, records: list[RankRecord]) -> int:
        """Bulk upsert rank records. Returns count of records processed."""
        conn = self._connect()
        try:
            count = 0
            for rec in records:
                conn.execute(
                    """INSERT INTO rank_history (keyword_id, domain_id, date, position, clicks, impressions, ctr, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(keyword_id, domain_id, date) DO UPDATE SET
                           position=excluded.position,
                           clicks=excluded.clicks,
                           impressions=excluded.impressions,
                           ctr=excluded.ctr""",
                    (rec.keyword_id, rec.domain_id, rec.date,
                     rec.position, rec.clicks, rec.impressions,
                     rec.ctr, rec.created_at),
                )
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def rank_records_exist_for_date(self, domain_id: int, date: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM rank_history WHERE domain_id = ? AND date = ?",
                (domain_id, date),
            ).fetchone()
            return row["cnt"] > 0
        finally:
            conn.close()

    def get_rank_history(
        self,
        keyword_id: int | None = None,
        domain_id: int | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            query = """SELECT rh.*, k.keyword, d.url AS domain_url
                       FROM rank_history rh
                       JOIN keywords k ON rh.keyword_id = k.id
                       JOIN domains d ON rh.domain_id = d.id
                       WHERE rh.date >= date('now', ?)"""
            params: list[Any] = [f"-{days} days"]
            if keyword_id:
                query += " AND rh.keyword_id = ?"
                params.append(keyword_id)
            if domain_id:
                query += " AND rh.domain_id = ?"
                params.append(domain_id)
            query += " ORDER BY rh.date ASC"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Current Rankings (via view) ───────────────────────────────────────

    def current_rankings(
        self,
        domain_id: int | None = None,
        keyword_filter: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            query = "SELECT * FROM v_current_rankings WHERE 1=1"
            params: list[Any] = []
            if domain_id:
                query += " AND domain_id = ?"
                params.append(domain_id)
            if keyword_filter:
                query += " AND keyword LIKE ?"
                params.append(f"%{keyword_filter}%")
            query += " ORDER BY opportunity_score DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── SEO Issues ────────────────────────────────────────────────────────

    def upsert_issue(self, issue: SeoIssue) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO seo_issues (domain_id, keyword_id, issue_type, severity, detail, suggested_fix, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (issue.domain_id, issue.keyword_id, issue.issue_type,
                 issue.severity, issue.detail, issue.suggested_fix,
                 issue.status, issue.created_at, issue.updated_at),
            )
            conn.commit()
            return cur.lastrowid or 0
        finally:
            conn.close()

    def list_issues(
        self,
        domain_id: int | None = None,
        status: str | None = None,
    ) -> list[SeoIssue]:
        conn = self._connect()
        try:
            query = "SELECT * FROM seo_issues WHERE 1=1"
            params: list[Any] = []
            if domain_id:
                query += " AND domain_id = ?"
                params.append(domain_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END, created_at DESC"
            rows = conn.execute(query, params).fetchall()
            return [SeoIssue.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def open_issues_summary(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM v_open_issues_summary").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Content Ideas ────────────────────────────────────────────────────

    def upsert_content_idea(self, idea: ContentIdea) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO content_ideas (title, target_keyword, description, priority, source, effort, status, date_added, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(title, target_keyword) DO UPDATE SET
                       description=excluded.description,
                       priority=excluded.priority,
                       source=excluded.source,
                       effort=excluded.effort,
                       status=excluded.status,
                       date_added=excluded.date_added,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'""",
                (idea.title, idea.target_keyword, idea.description,
                 idea.priority, idea.source, idea.effort,
                 idea.status, idea.date_added,
                 idea.created_at, idea.updated_at),
            )
            conn.commit()
            if cur.lastrowid and cur.lastrowid > 0:
                return cur.lastrowid
            row = conn.execute(
                "SELECT id FROM content_ideas WHERE title = ? AND target_keyword = ?",
                (idea.title, idea.target_keyword),
            ).fetchone()
            return row["id"] if row else 0
        finally:
            conn.close()

    def list_content_ideas(
        self,
        status: str | None = None,
        domain_id: int | None = None,
        min_priority: int | None = None,
    ) -> list[ContentIdea]:
        conn = self._connect()
        try:
            query = "SELECT * FROM content_ideas WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            if min_priority is not None:
                query += " AND priority >= ?"
                params.append(min_priority)
            query += " ORDER BY priority DESC, date_added DESC"
            rows = conn.execute(query, params).fetchall()
            return [ContentIdea.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def top_content_ideas(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM v_top_content_ideas LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_backlog_with_rankings(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM v_backlog_with_rankings ORDER BY priority DESC, opportunity_score DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def search_content_ideas(self, query: str) -> list[ContentIdea]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM content_ideas WHERE title LIKE ? OR target_keyword LIKE ? ORDER BY priority DESC",
                (f"%{query}%", f"%{query}%"),
            ).fetchall()
            return [ContentIdea.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    # ── On-Page Errors ────────────────────────────────────────────────────

    def upsert_onpage_error(self, error: OnPageError) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO onpage_errors (url, domain_id, error_type, severity, detail, suggested_fix, status, discovered_at, check_batch, source, fixed_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(url, domain_id, error_type, check_batch) DO UPDATE SET
                       severity=excluded.severity,
                       detail=excluded.detail,
                       suggested_fix=excluded.suggested_fix,
                       status=excluded.status,
                       fixed_at=excluded.fixed_at,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'""",
                (error.url, error.domain_id, error.error_type, error.severity,
                 error.detail, error.suggested_fix, error.status,
                 error.discovered_at, error.check_batch, error.source,
                 error.fixed_at, error.created_at, error.updated_at),
            )
            conn.commit()
            return cur.lastrowid or 0
        finally:
            conn.close()

    def bulk_upsert_onpage_errors(
        self, errors: list[OnPageError], close_previous_batch: bool = False
    ) -> dict[str, Any]:
        """Bulk upsert on-page errors. Optionally close errors not in this batch."""
        conn = self._connect()
        try:
            count = 0
            batch_ids = set()
            for err in errors:
                conn.execute(
                    """INSERT INTO onpage_errors (url, domain_id, error_type, severity, detail, suggested_fix, status, discovered_at, check_batch, source, fixed_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(url, domain_id, error_type, check_batch) DO UPDATE SET
                           severity=excluded.severity,
                           detail=excluded.detail,
                           suggested_fix=excluded.suggested_fix,
                           status=excluded.status,
                           fixed_at=excluded.fixed_at,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'""",
                    (err.url, err.domain_id, err.error_type, err.severity,
                     err.detail, err.suggested_fix, err.status,
                     err.discovered_at, err.check_batch, err.source,
                     err.fixed_at, err.created_at, err.updated_at),
                )
                count += 1
                if err.check_batch:
                    batch_ids.add(err.check_batch)

            closed = 0
            if close_previous_batch and batch_ids:
                for bid in batch_ids:
                    cur = conn.execute(
                        """UPDATE onpage_errors SET status = 'fixed', fixed_at = strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z',
                               updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'
                           WHERE domain_id = ? AND status = 'open' AND check_batch != ?""",
                        (errors[0].domain_id, bid),
                    )
                    closed += cur.rowcount

            conn.commit()
            return {"imported": count, "closed_previous": closed}
        finally:
            conn.close()

    def list_onpage_errors(
        self,
        domain_id: int | None = None,
        status: str | None = None,
        error_type: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[OnPageError]:
        conn = self._connect()
        try:
            query = "SELECT * FROM onpage_errors WHERE 1=1"
            params: list[Any] = []
            if domain_id:
                query += " AND domain_id = ?"
                params.append(domain_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            if error_type:
                query += " AND error_type = ?"
                params.append(error_type)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            query += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, discovered_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [OnPageError.from_row(dict(r)) for r in rows]
        finally:
            conn.close()

    def mark_onpage_error_fixed(self, error_id: int) -> bool:
        conn = self._connect()
        try:
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            cur = conn.execute(
                """UPDATE onpage_errors SET status = 'fixed', fixed_at = ?,
                       updated_at = ? WHERE id = ? AND status = 'open'""",
                (now, now, error_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_onpage_error_by_id(self, error_id: int) -> OnPageError | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM onpage_errors WHERE id = ?", (error_id,)
            ).fetchone()
            return OnPageError.from_row(dict(row)) if row else None
        finally:
            conn.close()

    def open_onpage_errors_summary(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT d.url AS domain, d.label AS domain_label, oe.error_type,
                          oe.severity, COUNT(*) AS error_count
                   FROM onpage_errors oe
                   JOIN domains d ON oe.domain_id = d.id
                   WHERE oe.status = 'open'
                   GROUP BY d.url, d.label, oe.error_type, oe.severity
                   ORDER BY
                       CASE oe.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                       error_count DESC"""
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Sync Log ──────────────────────────────────────────────────────────

    def start_sync(self, sync_type: str) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO sync_log (sync_type, status) VALUES (?, 'running')",
                (sync_type,),
            )
            conn.commit()
            return cur.lastrowid or 0
        finally:
            conn.close()

    def complete_sync(self, sync_id: int, rows_processed: int = 0, error: str | None = None) -> None:
        conn = self._connect()
        try:
            status = "failed" if error else "completed"
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            conn.execute(
                """UPDATE sync_log SET status = ?, rows_processed = ?,
                       error_detail = ?, completed_at = ?
                   WHERE id = ?""",
                (status, rows_processed, error, now, sync_id),
            )
            conn.commit()
        finally:
            conn.close()

    def check_already_synced_today(self, sync_type: str) -> bool:
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS cnt FROM sync_log
                   WHERE sync_type = ? AND status = 'completed'
                   AND date(started_at) = date('now')""",
                (sync_type,),
            ).fetchone()
            return row["cnt"] > 0
        finally:
            conn.close()

    def get_recent_syncs(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM sync_log ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Quick Wins ────────────────────────────────────────────────────────

    def get_quick_wins(self, domain_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Keywords with high opportunity but low current position."""
        conn = self._connect()
        try:
            query = """SELECT * FROM v_current_rankings
                       WHERE (current_position IS NULL OR current_position > 20)
                       AND monthly_volume > 0"""
            params: list[Any] = []
            if domain_id:
                query += " AND domain_id = ?"
                params.append(domain_id)
            query += " ORDER BY opportunity_score DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── Dashboard Aggregate ───────────────────────────────────────────────

    def dashboard_summary(self) -> dict[str, Any]:
        """Single call for dashboard overview metrics."""
        conn = self._connect()
        try:
            rank_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM rank_history"
            ).fetchone()["cnt"]
            open_issues = conn.execute(
                "SELECT COUNT(*) AS cnt FROM seo_issues WHERE status='open'"
            ).fetchone()["cnt"]
            open_errors = conn.execute(
                "SELECT COUNT(*) AS cnt FROM onpage_errors WHERE status='open'"
            ).fetchone()["cnt"]
            ideas = conn.execute(
                "SELECT COUNT(*) AS cnt FROM content_ideas"
            ).fetchone()["cnt"]
            backlog = conn.execute(
                "SELECT COUNT(*) AS cnt FROM content_ideas WHERE status IN ('backlog','draft')"
            ).fetchone()["cnt"]
            kw_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM keywords"
            ).fetchone()["cnt"]
            domains = self.list_domains()
            return {
                "rank_records": rank_count,
                "open_issues": open_issues,
                "open_onpage_errors": open_errors,
                "total_content_ideas": ideas,
                "backlog_ideas": backlog,
                "keywords_tracked": kw_count,
                "domains": [(d.url, d.label) for d in domains],
                "domains_count": len(domains),
            }
        finally:
            conn.close()
