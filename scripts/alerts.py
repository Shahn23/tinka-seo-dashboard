#!/usr/bin/env python3
"""SEO Alert Script — detects notable changes and generates alerts.

Checks for:
  - Significant rank drops (position loss >= threshold, default 3)
  - Critical / high-severity on-page errors
  - New broken links
  - Site health score drops (vs previous snapshot)
  - Keywords falling out of top 10 positions
  - Sync failures
  - Stale data (no recent sync)

Usage:
    python scripts/alerts.py                          # Default checks
    python scripts/alerts.py --drop-threshold 2       # Stricter rank-drop sensitivity
    python scripts/alerts.py --json                   # JSON output
    python scripts/alerts.py --min-severity high       # Only high+ severity errors
    python scripts/alerts.py --quiet                  # Exit code only (0=all clear, 1=alerts)
"""

import argparse, json, os, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta

# ── paths ─────────────────────────────────────────────────────────────────────

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "seo_dashboard.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_dicts(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_one_dict(conn: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


# ── alert severity levels ────────────────────────────────────────────────────

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}


class Alert:
    def __init__(self, severity: str, category: str, title: str, detail: str, context: dict | None = None):
        self.severity = severity
        self.category = category
        self.title = title
        self.detail = detail
        self.context = context or {}

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "context": self.context,
        }

    def __str__(self) -> str:
        icon = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "moderate": "🟡 MODERATE", "low": "🔵 LOW"}.get(self.severity, "⚪ INFO")
        return f"  {icon}  [{self.category}] {self.title}\n           {self.detail}"

    def __lt__(self, other):
        return SEVERITY_ORDER.get(self.severity, 99) < SEVERITY_ORDER.get(other.severity, 99)


# ── alert checks ──────────────────────────────────────────────────────────────


def check_rank_drops(conn: sqlite3.Connection, threshold: float = 3.0) -> list[Alert]:
    """Keywords that dropped by >=threshold positions vs the previous day."""
    alerts: list[Alert] = []

    rows = fetch_dicts(conn, """
        WITH latest AS (
            SELECT keyword_id, position, clicks, impressions,
                   date AS latest_date
            FROM rank_history rh1
            WHERE rh1.id = (SELECT MAX(id) FROM rank_history rh2 WHERE rh2.keyword_id = rh1.keyword_id)
        ),
        prev AS (
            SELECT keyword_id, position, date AS prev_date
            FROM rank_history rh1
            WHERE rh1.id = (SELECT MAX(id) FROM rank_history rh2
                            WHERE rh2.keyword_id = rh1.keyword_id
                              AND rh2.id < (SELECT MAX(id) FROM rank_history rh3 WHERE rh3.keyword_id = rh1.keyword_id))
        )
        SELECT l.keyword_id, l.position AS current_pos, p.position AS previous_pos,
               l.clicks, l.impressions, l.latest_date, p.prev_date,
               k.keyword, d.display_name AS domain,
               (p.position - l.position) AS drop_amount
        FROM latest l
        JOIN prev p ON p.keyword_id = l.keyword_id
        JOIN keywords k ON k.id = l.keyword_id
        JOIN domains d ON d.id = k.domain_id
        WHERE (p.position - l.position) <= -?
          AND l.position > 0
          AND p.position > 0
        ORDER BY drop_amount ASC
        LIMIT 30
    """, (threshold,))

    for r in rows:
        severity = "critical" if abs(r["drop_amount"]) >= 8 else "high" if abs(r["drop_amount"]) >= 5 else "moderate"
        alerts.append(Alert(
            severity=severity,
            category="rank_drop",
            title=f"Rank drop: {r['keyword']} on {r['domain']}",
            detail=(f"Dropped {abs(r['drop_amount']):.0f} positions "
                    f"(#{r['previous_pos']:.0f} → #{r['current_pos']:.0f}) "
                    f"between {r['prev_date']} and {r['latest_date']}"),
            context={"keyword": r["keyword"], "domain": r["domain"],
                     "from_pos": r["previous_pos"], "to_pos": r["current_pos"],
                     "drop": abs(r["drop_amount"])},
        ))

    return alerts


def check_keywords_lost_top10(conn: sqlite3.Connection) -> list[Alert]:
    """Keywords that dropped out of the top 10."""
    alerts: list[Alert] = []

    rows = fetch_dicts(conn, """
        WITH latest AS (
            SELECT keyword_id, position, date FROM rank_history rh1
            WHERE rh1.id = (SELECT MAX(id) FROM rank_history rh2 WHERE rh2.keyword_id = rh1.keyword_id)
        ),
        prev AS (
            SELECT keyword_id, position FROM rank_history rh1
            WHERE rh1.id = (SELECT MAX(id) FROM rank_history rh2
                            WHERE rh2.keyword_id = rh1.keyword_id
                              AND rh2.id < (SELECT MAX(id) FROM rank_history rh3 WHERE rh3.keyword_id = rh1.keyword_id))
        )
        SELECT l.keyword_id, l.position AS current_pos, p.position AS previous_pos,
               k.keyword, d.display_name AS domain
        FROM latest l
        JOIN prev p ON p.keyword_id = l.keyword_id
        JOIN keywords k ON k.id = l.keyword_id
        JOIN domains d ON d.id = k.domain_id
        WHERE p.position BETWEEN 1 AND 10
          AND (l.position > 10 OR l.position = 0)
        ORDER BY p.position ASC
        LIMIT 20
    """)

    for r in rows:
        alerts.append(Alert(
            severity="high",
            category="lost_top10",
            title=f"Lost Top 10: {r['keyword']} on {r['domain']}",
            detail=(f"Fell from #{r['previous_pos']:.0f} to #{r['current_pos']:.0f} — no longer in top 10"),
            context={"keyword": r["keyword"], "domain": r["domain"],
                     "from_pos": r["previous_pos"], "to_pos": r["current_pos"]},
        ))

    return alerts


def check_critical_errors(conn: sqlite3.Connection, min_severity: str = "moderate") -> list[Alert]:
    """Critical and high-severity on-page errors still open."""
    alerts: list[Alert] = []
    sev_levels = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
    min_level = sev_levels.get(min_severity, 2)

    rows = fetch_dicts(conn, """
        SELECT oe.error_type, oe.severity, COUNT(*) AS cnt,
               d.display_name AS domain,
               GROUP_CONCAT(DISTINCT oe.page_url) AS sample_urls
        FROM onpage_errors oe
        JOIN domains d ON d.id = oe.domain_id
        WHERE oe.status IN ('open', 'in_progress')
        GROUP BY oe.error_type, oe.severity, oe.domain_id
        HAVING cnt >= 1
        ORDER BY CASE oe.severity
            WHEN 'critical' THEN 1 WHEN 'high' THEN 2
            WHEN 'moderate' THEN 3 WHEN 'low' THEN 4
        END, cnt DESC
        LIMIT 25
    """)

    for r in rows:
        level = sev_levels.get(r["severity"], 99)
        if level > min_level:
            continue

        sample = r.get("sample_urls", "")
        url_snippet = ""
        if sample:
            urls = sample.split(",")
            url_snippet = f"  e.g., {urls[0].strip()}" if urls else ""

        alerts.append(Alert(
            severity=r["severity"],
            category="onpage_error",
            title=f"{r['cnt']} × {r['error_type'].replace('_', ' ').title()} on {r['domain']}",
            detail=f"Severity: {r['severity']}. {url_snippet}" if url_snippet else f"Severity: {r['severity']}.",
            context={"error_type": r["error_type"], "severity": r["severity"],
                     "domain": r["domain"], "count": r["cnt"]},
        ))

    return alerts


def check_new_broken_links(conn: sqlite3.Connection) -> list[Alert]:
    """New broken-link errors (open, not previously fixed)."""
    rows = fetch_dicts(conn, """
        SELECT oe.id, oe.page_url, oe.description, oe.suggestion,
               d.display_name AS domain, oe.created_at
        FROM onpage_errors oe
        JOIN domains d ON d.id = oe.domain_id
        WHERE (oe.error_type LIKE '%broken%' OR oe.error_type = 'broken_link')
          AND oe.status = 'open'
          AND oe.created_at >= date('now', '-7 days')
        ORDER BY oe.created_at DESC
        LIMIT 20
    """)

    alerts: list[Alert] = []
    for r in rows:
        alerts.append(Alert(
            severity="high",
            category="broken_link",
            title=f"Broken link on {r['domain']}",
            detail=f"Page: {r['page_url'] or 'N/A'} | {r.get('description', '')[:120]}",
            context={"domain": r["domain"], "page_url": r["page_url"],
                     "description": r.get("description", ""), "created": r.get("created_at", "")},
        ))

    return alerts


def check_site_health_drop(conn: sqlite3.Connection) -> list[Alert]:
    """Compare latest 2 health snapshots for score drops."""
    snapshots = fetch_dicts(conn, """
        SELECT id, health_score, grade, timestamp
        FROM site_health_snapshots
        ORDER BY id DESC LIMIT 2
    """)

    alerts: list[Alert] = []
    if len(snapshots) < 2:
        return alerts

    latest, previous = snapshots[0], snapshots[1]
    delta = latest["health_score"] - previous["health_score"]

    if delta <= -10:
        alerts.append(Alert(
            severity="critical",
            category="health_drop",
            title="Major site health score drop",
            detail=(f"Health score dropped {abs(delta):.1f} points "
                    f"({previous['health_score']:.1f} → {latest['health_score']:.1f}) "
                    f"Grade: {previous.get('grade','?')} → {latest.get('grade','?')}"),
            context={"from_score": previous["health_score"], "to_score": latest["health_score"],
                     "delta": delta, "previous_grade": previous.get("grade"),
                     "current_grade": latest.get("grade")},
        ))
    elif delta <= -5:
        alerts.append(Alert(
            severity="high",
            category="health_drop",
            title="Site health score declined",
            detail=(f"Health score dropped {abs(delta):.1f} points "
                    f"({previous['health_score']:.1f} → {latest['health_score']:.1f})"),
            context={"from_score": previous["health_score"], "to_score": latest["health_score"],
                     "delta": delta},
        ))

    return alerts


def check_sync_failures(conn: sqlite3.Connection) -> list[Alert]:
    """Recent sync failures (last 48 hours)."""
    rows = fetch_dicts(conn, """
        SELECT source, status, rows_synced, started_at, error
        FROM sync_log
        WHERE started_at >= datetime('now', '-48 hours')
          AND status = 'failed'
        ORDER BY started_at DESC
    """)

    alerts: list[Alert] = []
    for r in rows:
        alerts.append(Alert(
            severity="critical" if r["source"] == "gsc" else "high",
            category="sync_failure",
            title=f"Sync failed: {r['source']}",
            detail=f"Error: {(r.get('error') or 'Unknown')[:200]}",
            context={"source": r["source"], "error": r.get("error"), "started_at": r.get("started_at")},
        ))

    return alerts


def check_stale_sync(conn: sqlite3.Connection) -> list[Alert]:
    """Check if any source hasn't synced in 24+ hours."""
    alerts: list[Alert] = []
    sources = fetch_dicts(conn, """
        SELECT s1.source, s1.status, s1.started_at
        FROM sync_log s1
        WHERE s1.id = (SELECT MAX(s2.id) FROM sync_log s2 WHERE s2.source = s1.source)
          AND s1.started_at < datetime('now', '-24 hours')
    """)

    for s in sources:
        if s["status"] == "failed":
            continue  # already reported above
        hours_ago = (datetime.now() - datetime.strptime(s["started_at"][:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
        alerts.append(Alert(
            severity="moderate",
            category="stale_sync",
            title=f"No recent sync: {s['source']}",
            detail=f"Last sync was {hours_ago:.0f} hours ago ({s['started_at'][:16]})",
            context={"source": s["source"], "last_sync": s["started_at"], "hours_ago": round(hours_ago)},
        ))

    return alerts


def check_content_stale(conn: sqlite3.Connection) -> list[Alert]:
    """Articles stuck in draft for >7 days with no publication."""
    rows = fetch_dicts(conn, """
        SELECT id, title, market, target_domain, target_keywords,
               word_count, created_at
        FROM published_articles
        WHERE status = 'draft'
          AND created_at < datetime('now', '-7 days')
        ORDER BY created_at ASC
        LIMIT 10
    """)

    alerts: list[Alert] = []
    for r in rows:
        alerts.append(Alert(
            severity="low",
            category="stale_article",
            title=f"Stale draft: {r['title'][:50]}",
            detail=f"Created {r['created_at'][:10]} on {r['market']} — {r['word_count']} words, not published",
            context={"article_id": r["id"], "title": r["title"], "market": r["market"],
                     "created_at": r["created_at"], "word_count": r["word_count"]},
        ))

    return alerts


# ── orchestrator ──────────────────────────────────────────────────────────────


def run_all_checks(conn: sqlite3.Connection, drop_threshold: float = 3.0,
                   min_severity: str = "moderate") -> list[Alert]:
    """Run all alert checks and return sorted list."""
    alerts: list[Alert] = []

    alerts.extend(check_rank_drops(conn, threshold=drop_threshold))
    alerts.extend(check_keywords_lost_top10(conn))
    alerts.extend(check_critical_errors(conn, min_severity=min_severity))
    alerts.extend(check_new_broken_links(conn))
    alerts.extend(check_site_health_drop(conn))
    alerts.extend(check_sync_failures(conn))
    alerts.extend(check_stale_sync(conn))
    alerts.extend(check_content_stale(conn))

    alerts.sort()
    return alerts


def format_alerts(alerts: list[Alert], quiet: bool = False) -> str | None:
    """Format alert list as human-readable string."""
    if not alerts:
        if quiet:
            return None
        return "✅  All clear — no alerts triggered.\n"

    by_severity: dict[str, list[Alert]] = defaultdict(list)
    for a in alerts:
        by_severity[a.severity].append(a)

    parts = [f"\n{'=' * 68}"]
    parts.append(f"  SEO ALERTS — {len(alerts)} issue(s) detected")
    parts.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append("=" * 68)

    for sev in ("critical", "high", "moderate", "low"):
        items = by_severity.get(sev, [])
        if not items:
            continue
        icon = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "🔵"}[sev]
        parts.append(f"\n  {icon} {sev.upper()} ({len(items)})")
        parts.append("  " + "─" * 64)
        for a in items:
            parts.append(str(a))
        parts.append("")

    parts.append("=" * 68)
    parts.append(f"  {len(alerts)} total alert(s)  |  "
                 f"Critical: {len(by_severity.get('critical', []))}  "
                 f"High: {len(by_severity.get('high', []))}  "
                 f"Moderate: {len(by_severity.get('moderate', []))}  "
                 f"Low: {len(by_severity.get('low', []))}")
    parts.append("=" * 68)

    return "\n".join(parts)


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description="SEO alert checker — detect notable changes")
    p.add_argument("--drop-threshold", type=float, default=3.0,
                   help="Position drop threshold for rank-drop alerts (default: 3.0)")
    p.add_argument("--min-severity", choices=["critical", "high", "moderate", "low"],
                   default="moderate", help="Minimum error severity to alert on (default: moderate)")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--quiet", action="store_true",
                   help="Quiet mode: only exit code 0 (clear) or 1 (alerts)")
    p.add_argument("--db", default=DB, help=f"Path to database (default: {DB})")
    args = p.parse_args()

    conn = get_conn()
    try:
        alerts = run_all_checks(
            conn,
            drop_threshold=args.drop_threshold,
            min_severity=args.min_severity,
        )

        if args.json:
            print(json.dumps([a.to_dict() for a in alerts], indent=2))
        elif args.quiet:
            # No output; exit code indicates result
            pass
        else:
            output = format_alerts(alerts, quiet=args.quiet)
            if output:
                print(output)

        sys.exit(1 if alerts else 0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
