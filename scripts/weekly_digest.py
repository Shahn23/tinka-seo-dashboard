#!/usr/bin/env python3
"""Weekly SEO Digest — generates a comprehensive week-in-review report.

Queries the SEO dashboard database and prints a formatted summary of:
  - Domain health & site status
  - Keyword rank movement (risers, fallers, new entrants)
  - Traffic / clicks / impressions trends
  - On-page error status by severity
  - Site health score evolution
  - Content idea pipeline & published articles
  - Top-opportunity content ideas

Usage:
    python scripts/weekly_digest.py                         # Last 7 days
    python scripts/weekly_digest.py --days 14               # Custom window
    python scripts/weekly_digest.py --json                   # JSON output
    python scripts/weekly_digest.py --email                  # Email-friendly (plain text)
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


# ── query helpers ─────────────────────────────────────────────────────────────


def fetch_dicts(conn: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_one_dict(conn: sqlite3.Connection, sql: str, params=()) -> dict | None:
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


# ── report sections ───────────────────────────────────────────────────────────


def section_domains(conn: sqlite3.Connection) -> list[dict]:
    """List active domains and their basic info."""
    return fetch_dicts(conn, "SELECT id, name, display_name, gsc_site_url, created_at FROM domains WHERE is_active=1")


def section_keyword_summary(conn: sqlite3.Connection, days: int) -> dict:
    """Aggregate keyword stats: totals, tracked, ranked, latest avg position."""
    row = fetch_one_dict(conn, """
        SELECT COUNT(*) AS total_keywords,
               COUNT(DISTINCT keyword_id) AS tracked_keywords,
               ROUND(AVG(position), 1) AS avg_position,
               SUM(clicks) AS total_clicks,
               SUM(impressions) AS total_impressions,
               ROUND(AVG(ctr)*100, 2) AS avg_ctr_pct
        FROM rank_history
        WHERE date = (SELECT MAX(date) FROM rank_history)
    """)
    return row or {}


def section_rank_movers(conn: sqlite3.Connection, days: int) -> dict:
    """Compare latest positions with N-days ago to find risers / fallers / new."""
    today = fetch_dicts(conn, """
        SELECT rh.keyword_id, k.keyword, d.display_name AS domain, k.cluster,
               rh.position, rh.clicks, rh.impressions
        FROM rank_history rh
        JOIN keywords k ON k.id = rh.keyword_id
        JOIN domains d ON d.id = k.domain_id
        WHERE rh.date = (SELECT MAX(date) FROM rank_history)
    """)

    past_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    past = fetch_dicts(conn, """
        SELECT keyword_id, position
        FROM rank_history
        WHERE date = ?
    """, (past_date,))

    today_map = {r["keyword_id"]: r for r in today}
    past_map = {r["keyword_id"]: r["position"] for r in past}

    risers, fallers, stable, new_entrants = [], [], [], []
    for kw_id, t in today_map.items():
        p = past_map.get(kw_id)
        if p is None:
            new_entrants.append(t)
            continue
        diff = p - t["position"]  # positive = improved (higher rank = lower number)
        if diff >= 1.0:
            risers.append({**t, "change": round(diff, 1)})
        elif diff <= -1.0:
            fallers.append({**t, "change": round(diff, 1)})
        else:
            stable.append(t)

    risers.sort(key=lambda x: -x["change"])
    fallers.sort(key=lambda x: x["change"])

    return {
        "risers": risers[:15],
        "fallers": fallers[:15],
        "new_entrants": new_entrants[:15],
        "stable_count": len(stable),
        "riser_count": len(risers),
        "faller_count": len(fallers),
        "new_count": len(new_entrants),
    }


def section_trend(conn: sqlite3.Connection, days: int) -> dict:
    """Daily clicks, impressions, avg position over the period."""
    rows = fetch_dicts(conn, """
        SELECT date,
               ROUND(AVG(position), 1) AS avg_position,
               SUM(clicks) AS total_clicks,
               SUM(impressions) AS total_impressions,
               ROUND(AVG(ctr)*100, 2) AS avg_ctr_pct
        FROM rank_history
        WHERE date >= date('now', ?)
        GROUP BY date
        ORDER BY date
    """, (f"-{days} days",))
    return {"daily": rows}


def section_errors(conn: sqlite3.Connection) -> dict:
    """On-page errors grouped by severity + type."""
    by_severity = fetch_dicts(conn, """
        SELECT severity, COUNT(*) AS cnt
        FROM onpage_errors
        WHERE status IN ('open', 'in_progress')
        GROUP BY severity
        ORDER BY CASE severity
            WHEN 'critical'  THEN 1
            WHEN 'high'      THEN 2
            WHEN 'moderate'  THEN 3
            WHEN 'low'       THEN 4
        END
    """)

    by_type = fetch_dicts(conn, """
        SELECT error_type, severity, COUNT(*) AS cnt
        FROM onpage_errors
        WHERE status IN ('open', 'in_progress')
        GROUP BY error_type, severity
        ORDER BY cnt DESC
        LIMIT 20
    """)

    total_open = conn.execute(
        "SELECT COUNT(*) FROM onpage_errors WHERE status IN ('open', 'in_progress')"
    ).fetchone()[0]

    total_fixed = conn.execute("SELECT COUNT(*) FROM onpage_errors WHERE status='fixed'").fetchone()[0]

    return {
        "total_open": total_open,
        "total_fixed": total_fixed,
        "by_severity": by_severity,
        "by_type": by_type,
    }


def section_site_health(conn: sqlite3.Connection) -> dict:
    """Latest health snapshot + score deltas vs previous snapshot."""
    latest = fetch_one_dict(conn, """
        SELECT * FROM site_health_snapshots
        ORDER BY id DESC LIMIT 1
    """)

    previous = fetch_one_dict(conn, """
        SELECT * FROM site_health_snapshots
        ORDER BY id DESC LIMIT 1 OFFSET 1
    """)

    return {"latest": latest, "previous": previous}


def section_content_ideas(conn: sqlite3.Connection) -> dict:
    """Content idea pipeline summary + top picks."""
    by_status = fetch_dicts(conn, """
        SELECT status, COUNT(*) AS cnt FROM content_ideas
        GROUP BY status ORDER BY cnt DESC
    """)

    top_picks = fetch_dicts(conn, """
        SELECT id, title, target_keyword, category, estimated_searches,
               opportunity_score, effort, status, created_at
        FROM content_ideas
        WHERE opportunity_score >= 7.0 AND status IN ('draft', 'backlog')
        ORDER BY opportunity_score DESC, estimated_searches DESC
        LIMIT 10
    """)

    total = conn.execute("SELECT COUNT(*) FROM content_ideas").fetchone()[0]

    return {"total": total, "by_status": by_status, "top_picks": top_picks}


def section_articles(conn: sqlite3.Connection) -> dict:
    """Published / draft articles from last N days."""
    articles = fetch_dicts(conn, """
        SELECT pa.id, pa.title, pa.market, pa.target_domain, pa.status,
               pa.target_keywords, pa.word_count, pa.seo_score,
               pa.shopify_url, pa.created_at, pa.published_at
        FROM published_articles pa
        ORDER BY pa.created_at DESC
        LIMIT 20
    """)

    by_status = fetch_dicts(conn, """
        SELECT status, COUNT(*) AS cnt FROM published_articles
        GROUP BY status
    """)

    return {"articles": articles, "by_status": by_status}


def section_sync_status(conn: sqlite3.Connection, days: int) -> dict:
    """Recent sync log summary."""
    syncs = fetch_dicts(conn, """
        SELECT source, status, rows_synced, started_at, completed_at, error
        FROM sync_log
        WHERE started_at >= date('now', ?)
        ORDER BY started_at DESC
    """, (f"-{days} days",))
    return {"syncs": syncs}


# ── formatters ────────────────────────────────────────────────────────────────


def format_header(text: str, char: str = "=", width: int = 68) -> str:
    return f"\n{char * width}\n  {text}\n{char * width}\n"


def format_section(title: str, lines: list[str]) -> str:
    out = [format_header(title, "─")]
    out.extend(lines)
    out.append("")
    return "\n".join(out)


def build_digest(conn: sqlite3.Connection, days: int, fmt: str = "text") -> str | dict:
    """Assemble full digest and return as formatted string or dict."""
    if fmt == "json":
        data = {
            "generated_at": datetime.now().isoformat(),
            "period_days": days,
            "period_end": datetime.now().strftime("%Y-%m-%d"),
            "period_start": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
        }
    else:
        lines = []

    # ── domains ───────────────────────────────────────────────────────────
    domains = section_domains(conn)
    if fmt == "json":
        data["domains"] = domains
    else:
        lines.append(format_header("WEEKLY SEO DIGEST"))
        lines.append(f"  Period: last {days} days  ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        lines.append(f"  Domains: {', '.join(d['display_name'] for d in domains)}")

    # ── keyword snapshot ──────────────────────────────────────────────────
    ks = section_keyword_summary(conn, days)
    if fmt == "json":
        data["keyword_snapshot"] = ks
    else:
        lines.append(format_section("KEYWORD SNAPSHOT", [
            f"  Tracked keywords : {ks.get('tracked_keywords', 0)}",
            f"  Latest avg pos   : {ks.get('avg_position', 'N/A')}",
            f"  Total clicks     : {ks.get('total_clicks', 0):,}",
            f"  Total impressions: {ks.get('total_impressions', 0):,}",
            f"  Avg CTR          : {ks.get('avg_ctr_pct', 'N/A')}%",
        ]))

    # ── rank movers ───────────────────────────────────────────────────────
    rm = section_rank_movers(conn, days)
    if fmt == "json":
        data["rank_movers"] = rm
    else:
        r_lines = [
            f"  Rising  : {rm['riser_count']}  (+{'>='}1 position improvement)",
            f"  Falling : {rm['faller_count']}  ({'<='}-1 position drop)",
            f"  Stable  : {rm['stable_count']}",
            f"  New     : {rm['new_count']}  (newly ranked keywords)",
            "",
        ]
        if rm["risers"]:
            r_lines.append("  ── Top Risers ──")
            for r in rm["risers"][:8]:
                r_lines.append(f"    +{r['change']:>5.1f}  {r['keyword']:<40s} ({r['domain']}) — pos {r['position']}")
            r_lines.append("")
        if rm["fallers"]:
            r_lines.append("  ── Top Fallers ──")
            for r in rm["fallers"][:8]:
                r_lines.append(f"    {r['change']:>6.1f}  {r['keyword']:<40s} ({r['domain']}) — pos {r['position']}")
            r_lines.append("")
        if rm["new_entrants"]:
            r_lines.append("  ── New Entrants ──")
            for r in rm["new_entrants"][:5]:
                r_lines.append(f"    NEW  {r['keyword']:<40s} ({r['domain']}) — pos {r['position']}")
        lines.append(format_section("RANK MOVEMENT (vs {}-day-ago)".format(days), r_lines))

    # ── daily trend ───────────────────────────────────────────────────────
    tr = section_trend(conn, days)
    if fmt == "json":
        data["daily_trend"] = tr
    else:
        tr_lines = []
        for d in tr.get("daily", []):
            tr_lines.append(
                f"  {d['date']}  avg pos {d['avg_position']:>6.1f}  "
                f"clicks {d['total_clicks']:>5,}  "
                f"impressions {d['total_impressions']:>7,}  "
                f"CTR {d['avg_ctr_pct']:>5.2f}%"
            )
        # Summarise week-over-week
        if len(tr.get("daily", [])) >= 2:
            first = tr["daily"][0]
            last = tr["daily"][-1]
            pos_delta = last["avg_position"] - first["avg_position"]
            click_delta = last["total_clicks"] - first["total_clicks"]
            imp_delta = last["total_impressions"] - first["total_impressions"]
            tr_lines.append("")
            tr_lines.append(f"  ── Week-over-week ──")
            tr_lines.append(f"  Avg position : {first['avg_position']} → {last['avg_position']}  ({'+' if pos_delta>=0 else ''}{pos_delta:+.1f})")
            tr_lines.append(f"  Clicks       : {first['total_clicks']:,} → {last['total_clicks']:,}  ({'+' if click_delta>=0 else ''}{click_delta:,})")
            tr_lines.append(f"  Impressions  : {first['total_impressions']:,} → {last['total_impressions']:,}  ({'+' if imp_delta>=0 else ''}{imp_delta:,})")
        lines.append(format_section("DAILY TREND (last {} days)".format(days), tr_lines))

    # ── on-page errors ────────────────────────────────────────────────────
    err = section_errors(conn)
    if fmt == "json":
        data["onpage_errors"] = err
    else:
        e_lines = [
            f"  Open: {err['total_open']}  |  Fixed: {err['total_fixed']}",
            "",
        ]
        if err["by_severity"]:
            e_lines.append("  ── By Severity ──")
            sev_icons = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "🔵"}
            for s in err["by_severity"]:
                icon = sev_icons.get(s["severity"], "⚪")
                e_lines.append(f"    {icon} {s['severity'].upper():<10s}: {s['cnt']}")
            e_lines.append("")
        if err["by_type"]:
            e_lines.append("  ── By Type (top 10) ──")
            for t in err["by_type"][:10]:
                sev_icon = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "🔵"}.get(t["severity"], "⚪")
                e_lines.append(f"    {sev_icon} {t['error_type']:<30s} ({t['severity']:>8s}) : {t['cnt']}")
        lines.append(format_section("ON-PAGE ERRORS", e_lines))

    # ── site health ───────────────────────────────────────────────────────
    sh = section_site_health(conn)
    if fmt == "json":
        data["site_health"] = sh
    else:
        sh_lines = []
        lat = sh.get("latest")
        if lat:
            sh_lines.append(f"  Health Score : {lat['health_score']}  (Grade: {lat.get('grade', 'N/A')})")
            sh_lines.append(f"  Critical     : {lat.get('critical_score', 'N/A')}")
            sh_lines.append(f"  High         : {lat.get('high_score', 'N/A')}")
            sh_lines.append(f"  Moderate     : {lat.get('moderate_score', 'N/A')}")
            sh_lines.append(f"  Freshness    : {lat.get('freshness_score', 'N/A')}")
            sh_lines.append(f"  Total Open   : {lat.get('total_open', 0)}  |  Fixed: {lat.get('total_fixed', 0)}")
            if lat.get("domain_1_name"):
                sh_lines.append(f"  {lat['domain_1_name']:>25s} : {lat.get('domain_1_status','?')} ({lat.get('domain_1_code','?')}) {lat.get('domain_1_response_time',0):.2f}s")
            if lat.get("domain_2_name"):
                sh_lines.append(f"  {lat['domain_2_name']:>25s} : {lat.get('domain_2_status','?')} ({lat.get('domain_2_code','?')}) {lat.get('domain_2_response_time',0):.2f}s")

            # Delta vs previous
            prev = sh.get("previous")
            if prev:
                delta = lat["health_score"] - prev["health_score"]
                direction = "▲" if delta > 0 else "▼" if delta < 0 else "─"
                sh_lines.append(f"  Since last snapshot : {direction} {delta:+.1f} points")
        lines.append(format_section("SITE HEALTH", sh_lines))

    # ── content ideas & articles ──────────────────────────────────────────
    ci = section_content_ideas(conn)
    arts = section_articles(conn)

    if fmt == "json":
        data["content_ideas"] = ci
        data["articles"] = arts
    else:
        ci_lines = [f"  Total content ideas : {ci['total']}"]
        if ci["by_status"]:
            ci_lines.append("  ── By Status ──")
            for s in ci["by_status"]:
                ci_lines.append(f"    {s['status']:<15s}: {s['cnt']}")
        if ci["top_picks"]:
            ci_lines.append("")
            ci_lines.append("  ── Top Opportunity Ideas (score ≥ 7) ──")
            for p in ci["top_picks"]:
                ci_lines.append(
                    f"    ⭐ {p['title'][:55]:<55s} score={p['opportunity_score']:.1f} "
                    f"searches={p['estimated_searches']:,} effort={p['effort']}"
                )
        lines.append(format_section("CONTENT PIPELINE", ci_lines))

        art_lines = []
        if arts["by_status"]:
            art_lines.append("  ── By Status ──")
            for s in arts["by_status"]:
                art_lines.append(f"    {s['status']:<15s}: {s['cnt']}")
        if arts["articles"]:
            art_lines.append("")
            art_lines.append("  ── Recent Articles ──")
            for a in arts["articles"][:8]:
                status_icon = "✅" if a["status"] == "published" else "📝" if a["status"] == "draft" else "❌"
                art_lines.append(
                    f"    {status_icon} {a['title'][:55]:<55s} {a['market']:>3s} "
                    f"{a['word_count']}w {'(live)' if a.get('shopify_url') else '(draft)'}"
                )
        lines.append(format_section("PUBLISHED ARTICLES", art_lines))

    # ── recent syncs ──────────────────────────────────────────────────────
    sync = section_sync_status(conn, days)
    if fmt == "json":
        data["sync_log"] = sync
    else:
        sync_lines = []
        for s in sync.get("syncs", [])[:10]:
            icon = "✅" if s["status"] == "success" else "❌" if s["status"] == "failed" else "⏳"
            sync_lines.append(
                f"    {icon} {s['source']:<10s} {s['status']:<10s} "
                f"rows={s['rows_synced']}  {s.get('started_at','')[:16]}"
            )
        if sync_lines:
            lines.append(format_section("RECENT SYNCS (last {} days)".format(days), sync_lines))

    # ── final ─────────────────────────────────────────────────────────────
    if fmt == "json":
        return data
    else:
        lines.append("\n" + "=" * 68)
        lines.append("  END OF WEEKLY DIGEST")
        lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 68)
        return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description="Generate weekly SEO digest report")
    p.add_argument("--days", type=int, default=7, help="Number of days to analyse (default: 7)")
    p.add_argument("--json", action="store_true", help="Output as JSON instead of formatted text")
    p.add_argument("--db", default=DB, help=f"Path to database (default: {DB})")
    args = p.parse_args()

    conn = get_conn()
    try:
        output = build_digest(conn, days=args.days, fmt="json" if args.json else "text")
        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(output)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
