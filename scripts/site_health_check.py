#!/usr/bin/env python3
"""
Site Health Check — reads onpage_errors from the SEO dashboard DB,
computes a 0-100 health score, performs HTTP liveness checks on both
domains, and stores a snapshot in site_health_snapshots.
"""

import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── config ──────────────────────────────────────────────────────────────────
DB_PATH = r"C:\Users\heysh\OneDrive\Desktop\tinka-seo-dashboard\data\seo_dashboard.db"
DOMAINS = ["giantbubbles.co.nz", "giantbubblesau.com"]
HTTP_TIMEOUT = 15  # seconds

# Weights
W_CRITICAL  = 0.40
W_HIGH      = 0.30
W_MODERATE  = 0.15
W_FRESHNESS = 0.15


# ── helpers ─────────────────────────────────────────────────────────────────
def fmt_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def http_check(domain: str) -> dict:
    """Return {status, status_code, response_time_s, error}."""
    url = f"https://{domain}"
    result = {"domain": domain, "status": "down", "status_code": None,
              "response_time_s": None, "error": None}
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "SiteHealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            result["status_code"] = resp.status
            result["status"] = "up" if resp.status == 200 else "degraded"
    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        result["status"] = "up" if e.code == 200 else "degraded"
        result["error"] = str(e)
    except urllib.error.URLError as e:
        result["error"] = str(e.reason)
    except Exception as e:
        result["error"] = str(e)
    else:
        result["response_time_s"] = round(time.perf_counter() - start, 3)
    finally:
        if result["response_time_s"] is None:
            result["response_time_s"] = round(time.perf_counter() - start, 3)
    return result


# ── scoring ─────────────────────────────────────────────────────────────────
def score_severity(conn, severity: str) -> float:
    """Return 0-100 score for a given severity based on fix ratio."""
    cur = conn.execute("""
        SELECT status, COUNT(*) FROM onpage_errors
        WHERE severity = ?
        GROUP BY status
    """, (severity,))
    counts = dict(cur.fetchall())
    total = sum(counts.values())
    if total == 0:
        return 100.0
    fixed = counts.get("fixed", 0) + counts.get("in_progress", 0)
    return round((fixed / total) * 100, 1)


def score_freshness(conn) -> float:
    """
    Freshness score (0-100) based on how recently issues were fixed.
    - If the most recent fix was within 7  days → 100
    - If the most recent fix was within 30 days → 75
    - If the most recent fix was within 60 days → 50
    - If the most recent fix was within 90 days → 25
    - Otherwise → 0
    If there are no fixes at all, check created_at of most recent issue.
    """
    cur = conn.execute("""
        SELECT MAX(fixed_at) FROM onpage_errors
        WHERE fixed_at IS NOT NULL AND status = 'fixed'
    """)
    row = cur.fetchone()
    latest = row[0] if row and row[0] else None

    # Fallback: most recently created issue (any status)
    if not latest:
        cur = conn.execute("SELECT MAX(created_at) FROM onpage_errors")
        row = cur.fetchone()
        latest = row[0] if row and row[0] else None

    if not latest:
        return 100.0  # no data → assume healthy

    try:
        if "T" in latest:  # ISO format
            dt = datetime.fromisoformat(latest)
        else:
            dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 50.0

    days_ago = (datetime.now(timezone.utc) - dt.replace(tzinfo=timezone.utc)
                if dt.tzinfo is None
                else (datetime.now(timezone.utc) - dt)).days
    days_ago = max(0, days_ago)

    if days_ago <= 7:
        return 100.0
    elif days_ago <= 30:
        return 75.0
    elif days_ago <= 60:
        return 50.0
    elif days_ago <= 90:
        return 25.0
    else:
        return 0.0


# ── main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"  Site Health Check — {fmt_now()}")
    print("=" * 60)

    # ── DB connectivity ──────────────────────────────────────────────────
    db = Path(DB_PATH)
    if not db.exists():
        print(f"\n  ERROR: database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    # ── Severity scores ──────────────────────────────────────────────────
    print("\n  ┌─ On-Page Issues ──────────────────────────────────┐")
    crit = score_severity(conn, "critical")
    high = score_severity(conn, "high")
    mod  = score_severity(conn, "moderate")
    print(f"  │  Critical fix rate: {crit:>5.1f}%  (weight 40%) │")
    print(f"  │  High     fix rate: {high:>5.1f}%  (weight 30%) │")
    print(f"  │  Moderate fix rate: {mod:>5.1f}%  (weight 15%) │")
    fresh = score_freshness(conn)
    print(f"  │  Freshness score:   {fresh:>5.1f}%  (weight 15%) │")
    print(f"  └──────────────────────────────────────────────────┘")

    # ── Weighted total ───────────────────────────────────────────────────
    raw_score = (
        crit   * W_CRITICAL +
        high   * W_HIGH +
        mod    * W_MODERATE +
        fresh  * W_FRESHNESS
    )
    health_score = round(raw_score, 1)

    # ── Domain counts (for report detail) ────────────────────────────────
    counts_by_domain = {}
    for domain_id, name in conn.execute(
        "SELECT d.id, d.name FROM domains d WHERE d.is_active = 1"
    ):
        cur = conn.execute("""
            SELECT severity, status, COUNT(*)
            FROM onpage_errors WHERE domain_id = ?
            GROUP BY severity, status
        """, (domain_id,))
        counts_by_domain[name] = {}
        for sev, sts, cnt in cur.fetchall():
            counts_by_domain[name][(sev, sts)] = cnt

    total_open = conn.execute(
        "SELECT COUNT(*) FROM onpage_errors WHERE status IN ('open', 'in_progress')"
    ).fetchone()[0]
    total_fixed = conn.execute(
        "SELECT COUNT(*) FROM onpage_errors WHERE status = 'fixed'"
    ).fetchone()[0]

    # ── HTTP checks ──────────────────────────────────────────────────────
    print("\n  ┌─ HTTP Liveness ───────────────────────────────────┐")
    http_results = []
    for domain in DOMAINS:
        result = http_check(domain)
        http_results.append(result)
        status_icon = "✓" if result["status"] == "up" else "✗"
        print(f"  │  {status_icon} {domain:<25s}", end="")
        if result["status"] == "up":
            print(f"  {result['response_time_s']:.3f}s  {result['status_code']}  │")
        else:
            print(f"  {'DOWN':>8s}  {result.get('error','')[:30]}  │")
    print(f"  └──────────────────────────────────────────────────┘")

    # ── Summary ──────────────────────────────────────────────────────────
    grade = "A" if health_score >= 90 else \
            "B" if health_score >= 75 else \
            "C" if health_score >= 50 else \
            "D" if health_score >= 25 else "F"

    print(f"\n  ╔══════════════════════════════════════════════════╗")
    print(f"  ║  Overall Site Health:  {health_score:>5.1f} / 100  ({grade})         ║")
    print(f"  ╠══════════════════════════════════════════════════╣")
    print(f"  ║  Breakdown:                                     ║")
    print(f"  ║    Critical fix rate × 40%  → {crit * W_CRITICAL:>6.1f} pts         ║")
    print(f"  ║    High fix rate × 30%      → {high * W_HIGH:>6.1f} pts         ║")
    print(f"  ║    Moderate fix rate × 15%  → {mod * W_MODERATE:>6.1f} pts         ║")
    print(f"  ║    Freshness × 15%           → {fresh * W_FRESHNESS:>6.1f} pts         ║")
    print(f"  ╠──────────────────────────────────────────────────╣")
    print(f"  ║  Open issues: {total_open:<3d}  |  Fixed: {total_fixed:<3d}              ║")
    for name, cc in counts_by_domain.items():
        open_c = sum(v for k, v in cc.items() if k[1] in ("open", "in_progress"))
        print(f"  ║    {name:<25s}  {open_c:>3d} open                  ║")
    up_count = sum(1 for r in http_results if r["status"] == "up")
    print(f"  ║  Sites up: {up_count}/{len(http_results)}                              ║")
    print(f"  ╚══════════════════════════════════════════════════╝")

    # ── Store snapshot ───────────────────────────────────────────────────
    snapshot = {
        "timestamp": fmt_now(),
        "health_score": health_score,
        "critical_score": crit,
        "high_score": high,
        "moderate_score": mod,
        "freshness_score": fresh,
        "critical_weight": W_CRITICAL,
        "high_weight": W_HIGH,
        "moderate_weight": W_MODERATE,
        "freshness_weight": W_FRESHNESS,
        "total_open": total_open,
        "total_fixed": total_fixed,
        "grade": grade,
    }
    # Add HTTP results as JSON columns
    for i, r in enumerate(http_results):
        snapshot[f"domain_{i+1}_name"] = r["domain"]
        snapshot[f"domain_{i+1}_status"] = r["status"]
        snapshot[f"domain_{i+1}_code"] = r["status_code"]
        snapshot[f"domain_{i+1}_response_time"] = r["response_time_s"]

    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_health_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            health_score REAL NOT NULL,
            critical_score  REAL,
            high_score      REAL,
            moderate_score  REAL,
            freshness_score REAL,
            critical_weight  REAL,
            high_weight      REAL,
            moderate_weight  REAL,
            freshness_weight REAL,
            total_open  INTEGER,
            total_fixed INTEGER,
            grade       TEXT,
            domain_1_name        TEXT,
            domain_1_status      TEXT,
            domain_1_code        INTEGER,
            domain_1_response_time REAL,
            domain_2_name        TEXT,
            domain_2_status      TEXT,
            domain_2_code        INTEGER,
            domain_2_response_time REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        INSERT INTO site_health_snapshots (
            timestamp, health_score,
            critical_score, high_score, moderate_score, freshness_score,
            critical_weight, high_weight, moderate_weight, freshness_weight,
            total_open, total_fixed, grade,
            domain_1_name, domain_1_status, domain_1_code, domain_1_response_time,
            domain_2_name, domain_2_status, domain_2_code, domain_2_response_time
        ) VALUES (
            :timestamp, :health_score,
            :critical_score, :high_score, :moderate_score, :freshness_score,
            :critical_weight, :high_weight, :moderate_weight, :freshness_weight,
            :total_open, :total_fixed, :grade,
            :domain_1_name, :domain_1_status, :domain_1_code, :domain_1_response_time,
            :domain_2_name, :domain_2_status, :domain_2_code, :domain_2_response_time
        )
    """, snapshot)
    conn.commit()

    print(f"\n  ✓ Snapshot saved to site_health_snapshots table.\n")

    conn.close()


if __name__ == "__main__":
    main()
