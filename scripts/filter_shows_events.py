"""Filter out all 'shows' and 'events' related keywords/content from the SEO dashboard DB.

User request: 'we are not looking to rank any "shows" or "events" for our giant bubbles.'
"""
import sqlite3
import os
import shutil

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'api', 'seo_dashboard.db')
MASTER_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'seo_dashboard.db')

def clean_database(db_path):
    """Remove shows/events keywords and related content from the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Find keyword IDs that contain 'show' or 'event'
    cur.execute("""
        SELECT id, keyword, domain_id FROM keywords 
        WHERE LOWER(keyword) LIKE '%show%' OR LOWER(keyword) LIKE '%event%'
        ORDER BY id
    """)
    show_event_keywords = cur.fetchall()
    keyword_ids = [row['id'] for row in show_event_keywords]
    
    print(f"=== Keywords to remove ({len(keyword_ids)}) ===")
    for k in show_event_keywords:
        print(f"  id={k['id']}: '{k['keyword']}' (domain_id={k['domain_id']})")
    
    # 2. Find content_ideas that mention 'show' or 'event' in title or target_keyword
    cur.execute("""
        SELECT id, title, target_keyword FROM content_ideas
        WHERE LOWER(title) LIKE '%show%' OR LOWER(title) LIKE '%event%' 
           OR LOWER(target_keyword) LIKE '%show%' OR LOWER(target_keyword) LIKE '%event%'
        ORDER BY id
    """)
    show_event_content = cur.fetchall()
    content_ids = [row['id'] for row in show_event_content]
    
    print(f"\n=== Content ideas to remove ({len(content_ids)}) ===")
    for c in show_event_content:
        print(f"  id={c['id']}: '{c['title']}' (keyword='{c['target_keyword']}')")
    
    # 3. Find onpage_errors referencing events pages
    cur.execute("""
        SELECT id, error_type, severity, page_url FROM onpage_errors
        WHERE LOWER(page_url) LIKE '%/events%'
        ORDER BY id
    """)
    event_errors = cur.fetchall()
    error_ids = [row['id'] for row in event_errors]
    
    print(f"\n=== On-page errors to remove ({len(error_ids)}) ===")
    for e in event_errors:
        print(f"  id={e['id']}: {e['error_type']} on {e['page_url']}")
    
    # --- Execute deletes ---
    
    # Delete rank_history for these keywords
    if keyword_ids:
        ph = ','.join('?' * len(keyword_ids))
        cur.execute(f"DELETE FROM rank_history WHERE keyword_id IN ({ph})", keyword_ids)
        print(f"\nDeleted {cur.rowcount} rank_history rows for show/event keywords")
    
    # Delete keywords
    if keyword_ids:
        ph = ','.join('?' * len(keyword_ids))
        cur.execute(f"DELETE FROM keywords WHERE id IN ({ph})", keyword_ids)
        print(f"Deleted {cur.rowcount} keywords")
    
    # Delete content_ideas
    if content_ids:
        # Also check if there are any published_articles referencing these content ideas
        ph = ','.join('?' * len(content_ids))
        cur.execute(f"SELECT COUNT(*) FROM published_articles WHERE content_idea_id IN ({ph})", content_ids)
        article_count = cur.fetchone()[0]
        if article_count > 0:
            print(f"WARNING: {article_count} published_articles reference these content ideas — NOT deleting content ideas")
        else:
            cur.execute(f"DELETE FROM content_ideas WHERE id IN ({ph})", content_ids)
            print(f"Deleted {cur.rowcount} content ideas")
    
    # Delete onpage_errors for /events pages
    if error_ids:
        ph = ','.join('?' * len(error_ids))
        cur.execute(f"DELETE FROM onpage_errors WHERE id IN ({ph})", error_ids)
        print(f"Deleted {cur.rowcount} on-page errors")
    
    conn.commit()
    
    # Show post-cleanup counts
    for table in ['keywords', 'content_ideas', 'onpage_errors', 'rank_history']:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"\n{table} count after cleanup: {cur.fetchone()[0]}")
    
    conn.close()
    print("\nCleanup complete!")

# Clean the API seed DB
print("=" * 60)
print("CLEANING API DB")
print("=" * 60)
clean_database(DB_PATH)

# Also clean the master data DB
print("\n" + "=" * 60)
print("CLEANING MASTER DATA DB")
print("=" * 60)
clean_database(MASTER_DB)
