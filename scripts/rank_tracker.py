#!/usr/bin/env python3
"""Rank Tracker - analyzes GSC position data for changes, trends, and gap analysis.

Produces a structured report showing:
- Keywords with position changes (up, down, new entrants, lost rankings)
- Trend analysis (7-day / 30-day moving averages)
- Keyword gap analysis (tracked vs untracked keywords)
- Cross-domain comparison (NZ vs AU)

Usage:
    python scripts/rank_tracker.py                    # Full report to stdout
    python scripts/rank_tracker.py --json             # JSON output for dashboard
    python scripts/rank_tracker.py --status-only      # Just status counts
    python scripts/rank_tracker.py --export-csv       # Export full keyword status CSV
"""

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("rank-tracker")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "seo_dashboard.db"


# ── helpers ───────────────────────────────────────────────────────────────────


def get_conn():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def date_range_str(days: int) -> str:
    return f"{(date.today() - timedelta(days=days - 1)).isoformat()}/{date.today().isoformat()}"


# ── core analysis ─────────────────────────────────────────────────────────────


def get_latest_rankings(conn) -> list[dict]:
    """Get the most recent rank for each keyword (GSC data only)."""
    rows = conn.execute("""
        SELECT
            k.id AS kw_id,
            d.id AS domain_id,
            d.name AS domain,
            d.display_name,
            k.keyword,
            k.category,
            k.intent,
            k.volume,
            k.opportunity_score,
            k.difficulty,
            k.is_high_priority,
            rh.position,
            rh.clicks,
            rh.impressions,
            rh.ctr,
            rh.date AS rank_date,
            k.created_at
        FROM keywords k
        JOIN domains d ON k.domain_id = d.id
        LEFT JOIN (
            SELECT keyword_id, position, clicks, impressions, ctr, date, id
            FROM rank_history rh1
            WHERE id = (
                SELECT MAX(rh2.id)
                FROM rank_history rh2
                WHERE rh2.keyword_id = rh1.keyword_id
            )
        ) rh ON k.id = rh.keyword_id
        WHERE d.is_active = 1
        ORDER BY d.name, rh.position NULLS LAST, k.volume DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_prior_rankings(conn, lookback_days: int = 7) -> dict:
    """Get rankings from N days ago for comparison.
    Returns {keyword_id: {'position': X, 'date': 'YYYY-MM-DD'}}."""
    target_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    rows = conn.execute("""
        SELECT rh.keyword_id, rh.position, rh.date
        FROM rank_history rh
        WHERE rh.date = ?
        AND rh.id = (
            SELECT MAX(rh2.id) FROM rank_history rh2
            WHERE rh2.keyword_id = rh.keyword_id AND rh2.date = ?
        )
    """, (target_date, target_date)).fetchall()
    return {r["keyword_id"]: {"position": r["position"], "date": r["date"]} for r in rows}


def get_earliest_ranking(conn, kw_id: int) -> dict | None:
    """Get the first-ever recorded ranking for a keyword."""
    r = conn.execute("""
        SELECT position, date FROM rank_history
        WHERE keyword_id = ?
        ORDER BY date ASC LIMIT 1
    """, (kw_id,)).fetchone()
    return dict(r) if r else None


def get_rank_history(kw_id: int, days: int = 30) -> list[dict]:
    """Get time series of rankings for a keyword."""
    conn = get_conn()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT date, position, clicks, impressions
        FROM rank_history
        WHERE keyword_id = ? AND date >= ?
        ORDER BY date
    """, (kw_id, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_change(latest: float | None, prior: float | None) -> dict:
    """Compute rank change. Negative = improved (lower is better in ranking)."""
    if latest is None and prior is None:
        return {"direction": "none", "change": 0, "label": "No data"}
    if latest is not None and prior is None:
        return {"direction": "new", "change": 0, "label": "New entrant"}
    if latest is None and prior is not None:
        return {"direction": "lost", "change": 0, "label": "Lost ranking"}
    diff = prior - latest  # positive = improved (rank went up)
    if abs(diff) < 0.5:
        return {"direction": "stable", "change": round(diff, 1), "label": "Stable"}
    if diff > 0:
        return {"direction": "up", "change": round(diff, 1), "label": f"▲ +{diff:.1f}"}
    return {"direction": "down", "change": round(diff, 1), "label": f"▼ {diff:.1f}"}


# ── report generators ────────────────────────────────────────────────────────


def generate_status_report(conn) -> dict:
    """Generate a full status report of all keywords."""
    rankings = get_latest_rankings(conn)
    prior_7d = get_prior_rankings(conn, 7)
    
    total = len(rankings)
    ranked = [r for r in rankings if r["position"] is not None]
    unranked = [r for r in rankings if r["position"] is None]
    
    # Group by domain
    by_domain = defaultdict(list)
    for r in rankings:
        by_domain[r["domain"]].append(r)
    
    # Compute summary stats
    rising = []
    falling = []
    stable = []
    new_entrants = []
    lost = []
    
    for r in rankings:
        kw_id = r["kw_id"]
        prior = prior_7d.get(kw_id)
        change_info = compute_change(r["position"], prior["position"] if prior else None)
        r["change"] = change_info
        
        if change_info["direction"] == "up":
            rising.append(r)
        elif change_info["direction"] == "down":
            falling.append(r)
        elif change_info["direction"] == "stable":
            stable.append(r)
        elif change_info["direction"] == "new":
            new_entrants.append(r)
        elif change_info["direction"] == "lost":
            lost.append(r)
    
    # Domain breakdown
    domain_report = {}
    for name, kws in by_domain.items():
        ranked_kws = [k for k in kws if k["position"] is not None]
        domain_report[name] = {
            "total": len(kws),
            "ranked": len(ranked_kws),
            "unranked": len(kws) - len(ranked_kws),
            "avg_position": round(sum(k["position"] for k in ranked_kws if k["position"]) / len(ranked_kws), 1) if ranked_kws else None,
            "rising": len([k for k in kws if k.get("change", {}).get("direction") == "up"]),
            "falling": len([k for k in kws if k.get("change", {}).get("direction") == "down"]),
            "new": len([k for k in kws if k.get("change", {}).get("direction") == "new"]),
            "total_volume": sum(k.get("volume") or 0 for k in kws),
            "opportunity_kws": len([k for k in unranked if k["domain"] == name and (k.get("opportunity_score") or 0) >= 7]),
        }
    
    # High-opportunity unranked keywords (quick wins)
    high_opp_unranked = [r for r in unranked if (r.get("opportunity_score") or 0) >= 7]
    high_opp_unranked.sort(key=lambda x: -(x.get("volume") or 0))
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "date_range_7d": date_range_str(7),
        "summary": {
            "total_keywords": total,
            "ranked": len(ranked),
            "unranked": len(unranked),
            "ranking_rate": round(len(ranked) / total * 100, 1) if total else 0,
            "rising": len(rising),
            "falling": len(falling),
            "stable": len(stable),
            "new_entrants": len(new_entrants),
            "lost_rankings": len(lost),
            "avg_position_all_domains": round(
                sum(r["position"] for r in ranked if r["position"]) / len(ranked), 1
            ) if ranked else None,
        },
        "by_domain": domain_report,
        "rising_keywords": [
            {
                "domain": r["domain"],
                "keyword": r["keyword"],
                "current_pos": r["position"],
                "change": r["change"]["change"],
                "volume": r["volume"],
            }
            for r in sorted(rising, key=lambda x: -x["change"]["change"])[:10]
        ],
        "falling_keywords": [
            {
                "domain": r["domain"],
                "keyword": r["keyword"],
                "current_pos": r["position"],
                "change": abs(r["change"]["change"]),
                "volume": r["volume"],
            }
            for r in sorted(falling, key=lambda x: -abs(x["change"]["change"]))[:10]
        ],
        "new_entrants_list": [
            {
                "domain": r["domain"],
                "keyword": r["keyword"],
                "position": r["position"],
                "volume": r["volume"],
            }
            for r in new_entrants
        ],
        "high_opportunity_unranked": [
            {
                "domain": r["domain"],
                "keyword": r["keyword"],
                "volume": r["volume"],
                "opportunity_score": r["opportunity_score"],
                "difficulty": r["difficulty"],
            }
            for r in high_opp_unranked[:15]
        ],
        "keyword_details": rankings,
    }
    
    return report


def export_csv(report: dict, path: str):
    """Export keyword ranking data to CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Domain", "Keyword", "Category", "Intent", "Volume",
            "Opportunity_Score", "Difficulty", "Current_Position",
            "Rank_Status", "Change_7d", "Clicks", "Impressions",
            "Last_Checked", "Priority"
        ])
        for kw in report["keyword_details"]:
            writer.writerow([
                kw["domain"],
                kw["keyword"],
                kw.get("category", ""),
                kw.get("intent", ""),
                kw.get("volume", ""),
                kw.get("opportunity_score", ""),
                kw.get("difficulty", ""),
                round(kw["position"], 1) if kw["position"] else "",
                "Ranked" if kw["position"] else "Unranked",
                kw.get("change", {}).get("label", ""),
                kw.get("clicks", ""),
                kw.get("impressions", ""),
                kw.get("rank_date", ""),
                "High" if kw.get("is_high_priority") else "",
            ])


# ── main ─────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(description="Keyword rank tracking analysis")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--status-only", action="store_true", help="Print summary only")
    p.add_argument("--export-csv", type=str, help="Export full status to CSV path")
    args = p.parse_args()

    conn = get_conn()
    report = generate_status_report(conn)
    conn.close()

    if args.json:
        # Strip keyword_details for JSON mode to keep output manageable
        output = {k: v for k, v in report.items() if k != "keyword_details"}
        print(json.dumps(output, indent=2, default=str))
        return

    if args.export_csv:
        export_csv(report, args.export_csv)
        log.info(f"✅ CSV exported to {args.export_csv}")
        return

    # Human-readable output
    s = report["summary"]
    print("=" * 60)
    print(f"  KEYWORD RANK TRACKER - {report['generated_at'][:10]}")
    print(f"  Period: {report['date_range_7d']}")
    print("=" * 60)
    print(f"\n📊 OVERVIEW")
    print(f"  Keywords tracked:   {s['total_keywords']}")
    print(f"  Ranked (GSC data):  {s['ranked']} ({s['ranking_rate']}%)")
    print(f"  Unranked (no data): {s['unranked']}")
    print(f"  Average position:   {s['avg_position_all_domains'] or 'N/A'}")
    print(f"\n🔄 7-DAY CHANGES")
    print(f"  Rising:   ▲ {s['rising']}")
    print(f"  Falling:  ▼ {s['falling']}")
    print(f"  Stable:   - {s['stable']}")
    print(f"  New:      ✨ {s['new_entrants']}")
    print(f"  Lost:     💀 {s['lost_rankings']}")

    print(f"\n🌐 BY DOMAIN")
    for name, info in report["by_domain"].items():
        arrow = "▲" if info["rising"] > info["falling"] else ("▼" if info["falling"] > info["rising"] else "-")
        print(f"  {name}:")
        print(f"    Tracked: {info['total']} | Ranked: {info['ranked']} | Unranked: {info['unranked']}")
        print(f"    Avg Pos: {info['avg_position'] or 'N/A'} | {arrow} {info['rising']}↑ {info['falling']}↓ {info['new']}✨")
        print(f"    Total Volume: {info['total_volume']:,}/mo | Opp. Gaps: {info['opportunity_kws']}")

    if report["rising_keywords"]:
        print(f"\n📈 TOP RISING KEYWORDS")
        for kw in report["rising_keywords"]:
            print(f"  ▲ {kw['keyword']:40s} [{kw['domain']}] → pos {kw['current_pos']:.0f} (+{kw['change']:.0f})")

    if report["falling_keywords"]:
        print(f"\n📉 FALLING KEYWORDS")
        for kw in report["falling_keywords"]:
            print(f"  ▼ {kw['keyword']:40s} [{kw['domain']}] → pos {kw['current_pos']:.0f} (-{kw['change']:.0f})")

    if report["high_opportunity_unranked"]:
        print(f"\n🎯 HIGH-OPPORTUNITY UNRANKED KEYWORDS (Quick Wins)")
        for kw in report["high_opportunity_unranked"]:
            print(f"  💡 {kw['keyword']:40s} [{kw['domain']}] vol={kw['volume']:,} score={kw['opportunity_score']:.0f}/diff={kw['difficulty']}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
