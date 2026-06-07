"""
Phase: Topical Authority Scoring
Queries the keywords table (with 'cluster' JSON column) and content_ideas table
to compute a topical authority score (0-100) per cluster.

Formula:
  authority = 0.35 × content_coverage + 0.35 × keyword_rank_coverage + 0.30 × avg_rank_score

Where:
  content_coverage      — % of keywords in cluster that have a matching content_idea (0-100)
  keyword_rank_coverage — % of keywords in cluster that have a rank position > 0 (0-100)
  avg_rank_score        — max(0, 100 - avg_position) for ranked keywords in cluster (0-100)

Stores results in the `topical_authority` table (created if not exists)
and provides a convenience view `v_topical_authority`.
"""

import sys
import os
import sqlite3
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "seo_dashboard.db",
)


def get_latest_position(conn, keyword_id: int) -> float | None:
    """Get the latest position from rank_history for a keyword."""
    c = conn.execute(
        "SELECT position FROM rank_history "
        "WHERE keyword_id = ? AND position > 0 "
        "ORDER BY date DESC LIMIT 1",
        (keyword_id,),
    )
    row = c.fetchone()
    return row[0] if row else None


def compute_topical_authority(conn) -> list[dict]:
    """
    Compute topical authority scores for all clusters.
    Returns a list of dicts, one per cluster.
    """
    # Get all keywords with cluster info
    keywords = conn.execute(
        "SELECT id, keyword, cluster FROM keywords "
        "WHERE cluster IS NOT NULL AND cluster != ''"
    ).fetchall()

    # Build cluster -> keywords mapping
    clusters: dict[int, dict] = {}
    kw_id_to_cluster: dict[int, tuple[int, str]] = {}  # kw_id -> (cluster_id, cluster_name)

    for kw_id, keyword, cluster_json in keywords:
        try:
            cl = json.loads(cluster_json)
            cid = cl["cluster_id"]
            cname = cl["cluster_name"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

        if cid not in clusters:
            clusters[cid] = {
                "cluster_id": cid,
                "cluster_name": cname,
                "keyword_ids": set(),
                "keyword_keywords": {},  # kw_id -> keyword text
            }
        clusters[cid]["keyword_ids"].add(kw_id)
        clusters[cid]["keyword_keywords"][kw_id] = keyword
        kw_id_to_cluster[kw_id] = (cid, cname)

    # Count content_ideas per keyword (case-insensitive match)
    # We map content_ideas to keywords, then to clusters
    content_ideas = conn.execute(
        "SELECT DISTINCT LOWER(TRIM(target_keyword)) FROM content_ideas "
        "WHERE target_keyword IS NOT NULL AND target_keyword != ''"
    ).fetchall()
    content_keywords_lower = {row[0] for row in content_ideas}

    # Pre-fetch latest positions for all keywords that have rank data
    # This is more efficient than N individual queries
    ranked_positions: dict[int, float] = {}
    rank_rows = conn.execute(
        "SELECT rh.keyword_id, rh.position FROM rank_history rh "
        "JOIN (SELECT keyword_id, MAX(date) AS max_date FROM rank_history "
        "       WHERE position > 0 GROUP BY keyword_id) latest "
        "ON rh.keyword_id = latest.keyword_id AND rh.date = latest.max_date"
    ).fetchall()
    for kw_id, pos in rank_rows:
        ranked_positions[kw_id] = pos

    results = []
    for cid, cluster in sorted(clusters.items(), key=lambda x: x[0]):
        total_kw = len(cluster["keyword_ids"])
        if total_kw == 0:
            continue

        # 1) Content coverage: how many keywords in this cluster have a content_idea
        kw_with_content = sum(
            1 for kw_id, kw_text in cluster["keyword_keywords"].items()
            if kw_text.lower().strip() in content_keywords_lower
        )
        content_coverage = (kw_with_content / total_kw) * 100.0

        # 2) Keyword rank coverage: how many keywords have a rank position > 0
        kw_ranked = sum(
            1 for kw_id in cluster["keyword_ids"]
            if kw_id in ranked_positions
        )
        keyword_rank_coverage = (kw_ranked / total_kw) * 100.0

        # 3) Avg rank score: based on average position of ranked keywords
        positions = [
            ranked_positions[kw_id]
            for kw_id in cluster["keyword_ids"]
            if kw_id in ranked_positions
        ]
        if positions:
            avg_position = sum(positions) / len(positions)
            avg_rank_score = max(0.0, 100.0 - avg_position)
        else:
            avg_position = None
            avg_rank_score = 0.0

        # Composite authority score (0-100)
        authority = (
            0.35 * content_coverage
            + 0.35 * keyword_rank_coverage
            + 0.30 * avg_rank_score
        )

        results.append({
            "cluster_id": cid,
            "cluster_name": cluster["cluster_name"],
            "total_keywords": total_kw,
            "keywords_with_content": kw_with_content,
            "keywords_ranked": kw_ranked,
            "avg_position": round(avg_position, 2) if avg_position is not None else None,
            "content_coverage": round(content_coverage, 2),
            "keyword_rank_coverage": round(keyword_rank_coverage, 2),
            "avg_rank_score": round(avg_rank_score, 2),
            "topical_authority": round(authority, 2),
        })

    return results


def ensure_table(conn):
    """Create topical_authority table and view if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topical_authority (
            cluster_id INTEGER PRIMARY KEY,
            cluster_name TEXT NOT NULL,
            total_keywords INTEGER DEFAULT 0,
            keywords_with_content INTEGER DEFAULT 0,
            keywords_ranked INTEGER DEFAULT 0,
            avg_position REAL,
            content_coverage REAL DEFAULT 0,
            keyword_rank_coverage REAL DEFAULT 0,
            avg_rank_score REAL DEFAULT 0,
            topical_authority REAL DEFAULT 0,
            computed_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE VIEW IF NOT EXISTS v_topical_authority AS
        SELECT
            cluster_id,
            cluster_name,
            total_keywords,
            keywords_with_content,
            keywords_ranked,
            content_coverage,
            keyword_rank_coverage,
            avg_rank_score,
            topical_authority,
            computed_at
        FROM topical_authority
        ORDER BY topical_authority DESC
    """)

    conn.commit()


def store_results(conn, results: list[dict]):
    """Upsert results into the topical_authority table."""
    conn.execute("DELETE FROM topical_authority")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in results:
        conn.execute(
            """INSERT INTO topical_authority (
                cluster_id, cluster_name, total_keywords,
                keywords_with_content, keywords_ranked, avg_position,
                content_coverage, keyword_rank_coverage, avg_rank_score,
                topical_authority, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r["cluster_id"],
                r["cluster_name"],
                r["total_keywords"],
                r["keywords_with_content"],
                r["keywords_ranked"],
                r["avg_position"],
                r["content_coverage"],
                r["keyword_rank_coverage"],
                r["avg_rank_score"],
                r["topical_authority"],
                now,
            ),
        )
    conn.commit()


def main():
    print("=" * 60)
    print("Topical Authority Scoring")
    print("=" * 60)

    conn = sqlite3.connect(DB)

    # 1. Compute scores
    print("Computing topical authority scores...")
    results = compute_topical_authority(conn)
    print(f"  Found {len(results)} clusters with keywords.")
    print()

    # 2. Ensure table + view exist
    print("Ensuring topical_authority table and v_topical_authority view...")
    ensure_table(conn)
    print("  Done.")
    print()

    # 3. Store results
    print("Storing results...")
    store_results(conn, results)
    print(f"  Stored {len(results)} cluster scores.")
    print()

    # 4. Summary report
    print("=" * 60)
    print("TOPICAL AUTHORITY SUMMARY")
    print("=" * 60)
    print(f"{'Rank':<6} {'Cluster':<40} {'Auth Score':<12} {'Coverage':<10} {'Rank Cov':<10} {'Rank Sc':<10}")
    print("-" * 92)

    sorted_results = sorted(results, key=lambda r: r["topical_authority"], reverse=True)
    for rank, r in enumerate(sorted_results[:30], 1):
        name = r["cluster_name"][:38]
        print(
            f"{rank:<6} {name:<40} "
            f"{r['topical_authority']:<12.2f} "
            f"{r['content_coverage']:<10.2f} "
            f"{r['keyword_rank_coverage']:<10.2f} "
            f"{r['avg_rank_score']:<10.2f}"
        )

    if len(sorted_results) > 30:
        print(f"  ... and {len(sorted_results) - 30} more clusters.")

    print()
    print("Distribution of authority scores:")
    buckets = [
        ("90-100 (Excellent)", 90),
        ("70-89  (Strong)", 70),
        ("50-69  (Developing)", 50),
        ("25-49  (Emerging)", 25),
        ("0-24   (Needs Work)", 0),
    ]
    for label, threshold in buckets:
        upper = next((t for l, t in buckets if buckets.index((l, t)) == buckets.index((label, threshold)) - 1), 101)
        count = sum(1 for r in sorted_results if threshold <= r["topical_authority"] < upper)
        print(f"  {label}: {count} clusters")

    lowest = sorted_results[-1] if sorted_results else None
    highest = sorted_results[0] if sorted_results else None
    if highest:
        print(f"\n  Highest: #{highest['cluster_id']} \"{highest['cluster_name']}\" = {highest['topical_authority']:.2f}")
    if lowest:
        print(f"  Lowest:  #{lowest['cluster_id']} \"{lowest['cluster_name']}\" = {lowest['topical_authority']:.2f}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
