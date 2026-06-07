"""
Phase: Keyword Clustering
Groups keywords into topical clusters using prefix matching (first 2-4 words)
combined with the category column. No external APIs.
"""

import sys
import os
import sqlite3
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "seo_dashboard.db",
)


def normalize_category(cat: str) -> str:
    """Normalize category to lowercase for consistent grouping."""
    if cat is None:
        return "uncategorized"
    return cat.lower().strip()


def keyword_prefix(keyword: str, n_words: int) -> str:
    """Return the first N words of a keyword as a normalized prefix string."""
    words = keyword.strip().lower().split()
    if len(words) < n_words:
        return " ".join(words)
    return " ".join(words[:n_words])


def cluster_keywords(keywords):
    """
    Group keywords into clusters by prefix (first 2-4 words) + category.
    
    Returns dict: {cluster_id: {'name': str, 'keyword_ids': [int]}}
    """
    # Phase 1: generate candidate groupings
    # For each keyword, generate (prefix, category) keys at word lengths 4, 3, 2
    # and collect all keywords that share the same key.
    
    candidates_by_key = defaultdict(set)  # (prefix, cat) -> set of keyword ids
    kw_info = {}
    
    for kw_id, keyword, cat in keywords:
        cat_norm = normalize_category(cat)
        kw_info[kw_id] = {"keyword": keyword, "category": cat_norm}
        
        words = keyword.strip().split()
        # Generate prefixes of length 4, 3, 2 (only if keyword has enough words)
        for n in [4, 3, 2]:
            if len(words) >= n:
                prefix = keyword_prefix(keyword, n)
                candidates_by_key[(prefix, cat_norm)].add(kw_id)
    
    # Phase 2: build clusters from candidate groups
    # - Prefer 4-word prefixes, fall back to 3, then 2
    # - A group needs at least 2 keywords to form a cluster
    # - If a keyword matches multiple groups at the same word-length,
    #   assign it to the largest group
    
    assigned = set()  # keyword ids already assigned
    clusters = []
    cluster_id_counter = 1
    
    # Process by word length (4 -> 3 -> 2), within each length process groups
    for n in [4, 3, 2]:
        # Collect groups at this word length, sorted by size descending
        groups_at_n = []
        for (prefix, cat), kw_ids in candidates_by_key.items():
            # Only consider groups where prefix is exactly N words
            if len(prefix.split()) != n:
                continue
            # Filter to unassigned keywords only
            unassigned = kw_ids - assigned
            # Skip groups that only partially overlap (at higher word lengths,
            # a keyword may have already been assigned by a previous pass)
            if len(unassigned) < 2:
                continue
            groups_at_n.append((prefix, cat, unassigned))
        
        # Sort by group size descending for greedy assignment
        groups_at_n.sort(key=lambda x: len(x[2]), reverse=True)
        
        for prefix, cat, kw_ids in groups_at_n:
            # Filter to still-unassigned keywords
            still_unassigned = kw_ids - assigned
            if len(still_unassigned) < 2:
                continue
            
            # Build a clean cluster name
            cluster_name = prefix.title()
            # Append category suffix if it's meaningful (not a generic catch-all)
            if cat and cat not in ("uncategorized", "untracked", "content"):
                cluster_name += f" ({cat.title()})"
            
            clusters.append({
                "id": cluster_id_counter,
                "name": cluster_name,
                "keyword_ids": still_unassigned,
            })
            assigned.update(still_unassigned)
            cluster_id_counter += 1
    
    # Phase 3: remaining unassigned keywords become their own singleton clusters
    for kw_id, keyword, cat in keywords:
        if kw_id not in assigned:
            cat_norm = normalize_category(cat)
            prefix = keyword_prefix(keyword, 2)
            if not prefix:
                prefix = keyword.strip().lower()
            cluster_name = prefix.title()
            if cat_norm and cat_norm not in ("uncategorized", "untracked"):
                cluster_name += f" ({cat_norm.title()})"
            clusters.append({
                "id": cluster_id_counter,
                "name": cluster_name,
                "keyword_ids": {kw_id},
            })
            assigned.add(kw_id)
            cluster_id_counter += 1
    
    return clusters


def main():
    print("=" * 60)
    print("Keyword Clustering")
    print("=" * 60)
    
    # 1. Connect & read keywords
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    
    # Check if `cluster` column already exists; if not, add it
    cursor = conn.execute("PRAGMA table_info(keywords)")
    cols = {row["name"] for row in cursor.fetchall()}
    
    if "cluster" not in cols:
        print("Adding `cluster` TEXT column to keywords table...")
        conn.execute("ALTER TABLE keywords ADD COLUMN cluster TEXT")
        conn.commit()
        print("  Done.")
    else:
        print("`cluster` column already exists — will overwrite values.")
    
    keywords = conn.execute(
        "SELECT id, keyword, category FROM keywords ORDER BY id"
    ).fetchall()
    kw_rows = [(k["id"], k["keyword"], k["category"]) for k in keywords]
    print(f"Total keywords loaded: {len(kw_rows)}\n")
    
    # 2. Run clustering
    clusters = cluster_keywords(kw_rows)
    print(f"Generated {len(clusters)} clusters\n")
    
    # 3. Write results back to DB
    kw_to_cluster = {}  # kw_id -> {"cluster_id": int, "cluster_name": str}
    for cl in clusters:
        for kw_id in cl["keyword_ids"]:
            kw_to_cluster[kw_id] = {
                "cluster_id": cl["id"],
                "cluster_name": cl["name"],
            }
    
    # Store as JSON string in the cluster column
    import json
    
    updated = 0
    for kw_id, cluster_info in kw_to_cluster.items():
        conn.execute(
            "UPDATE keywords SET cluster=? WHERE id=?",
            (json.dumps(cluster_info), kw_id),
        )
        updated += 1
    
    conn.commit()
    print(f"Updated {updated} keyword rows in DB\n")
    
    # 4. Summary
    print("=" * 60)
    print("CLUSTER SUMMARY")
    print("=" * 60)
    
    # Sort clusters by size descending
    clusters_sorted = sorted(clusters, key=lambda c: len(c["keyword_ids"]), reverse=True)
    
    for cl in clusters_sorted:
        kw_count = len(cl["keyword_ids"])
        # Show first few keywords as examples
        kw_examples = []
        for k in kw_rows:
            if k[0] in cl["keyword_ids"]:
                kw_examples.append(k[1])
                if len(kw_examples) >= 3:
                    break
        examples_str = ", ".join(f'"{e}"' for e in kw_examples)
        print(f"  Cluster #{cl['id']:3d} ({kw_count:3d} keywords): {cl['name']}")
        print(f"    e.g. {examples_str}")
        print()
    
    # Print distribution stats
    sizes = [len(c["keyword_ids"]) for c in clusters]
    print(f"Total clusters:     {len(clusters)}")
    print(f"Max cluster size:   {max(sizes)}")
    print(f"Min cluster size:   {min(sizes)}")
    print(f"Avg cluster size:   {sum(sizes) / len(sizes):.1f}")
    
    singletons = sum(1 for s in sizes if s == 1)
    small = sum(1 for s in sizes if 2 <= s <= 3)
    medium = sum(1 for s in sizes if 4 <= s <= 8)
    large = sum(1 for s in sizes if s >= 9)
    print(f"  - {singletons} singletons (1 keyword)")
    print(f"  - {small} small clusters (2-3 keywords)")
    print(f"  - {medium} medium clusters (4-8 keywords)")
    print(f"  - {large} large clusters (9+ keywords)")
    
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
