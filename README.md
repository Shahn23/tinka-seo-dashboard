# Tinka SEO Dashboard

Streamlit dashboard for Giant Bubbles by Tinka — tracks keyword rankings (137 keywords, 34 ranked), on-page SEO issues (47 open, 23 critical/high), content ideas (74 topics), and **v0.4 Content Studio** for writing AI-powered SEO articles and publishing to Shopify as drafts.

Live at: http://localhost:8510 (start with `start_dashboard.bat`)

## v0.4 What's New — Content Studio 🚀

- **Article Pipeline** — Pick a researched keyword, write an SEO article, post to Shopify as a draft in one command
- **Content Studio tab** — Track published articles, see which ideas need writing, select topics by opportunity score
- **First article live** — "The Ultimate Guide to Giant Bubbles" posted as Shopify draft (article ID 615913390401)
- **article_writer.py** — CLI tool for posting articles; reads content ideas from DB, posts to Shopify, records in tracking table
- **Shopify integration** — Auto-refreshed OAuth token (every 20h via cron), `write_content` scope for blog post management

### Writing a New Article

```bash
# 1. Create the HTML article in articles/
# 2. Post as draft to Shopify:
python scripts/article_writer.py --idea <ID> --body articles/your-article.html --market NZ
# 3. Review & publish from Shopify Admin → Blog Posts → Drafts
```

Live at: http://localhost:8510 (start with `start_dashboard.bat`)

## Data Sources

- **Google Search Console** — Keyword rankings, clicks, impressions (via `scripts/sync_gsc.py`)
- **Comprehensive on-page SEO audit** — 47 structured issues from the t_0136a7e9 audit (17 critical, 14 high, 16 moderate), stored in the SQLite DB with severity, error type, page URL, description, and fix suggestion
- **Keyword research** — 107-keyword AU+NZ universe with opportunity scoring, difficulty, category, and intent, sourced from multiple research rounds
- **Rank tracking** — 34 keywords with recent rank data (NZ avg position: ~4.6, AU avg position: ~5.6)
- **Content backlog** — 62 content ideas with opportunity scores, target keywords, estimated search volume, and outlines

All parent task data is integrated into the SQLite DB via `scripts/ingest_parent_data.py` (v1) and `scripts/ingest_parent_data_v2.py` (v2 — comprehensive audit + ranking data).

## Local Development

```bash
pip install -r requirements.txt
streamlit run dashboard.py --server.headless true --server.port 8510
```

Or double-click `start_dashboard.bat` from the repo root.

## Refreshing Data

### Manual refresh (from within dashboard)
Click **GSC Live Refresh** in the Settings tab (tab 6) — syncs the latest 7 days of GSC data.

### Re-ingest newest parent task data (30 new keywords + 12 blog topics)

When the latest keyword research and blog topics arrive (new CSV + markdown drops into `data/`):

```bash
python scripts/ingest_newest_parent_data.py
```

This ingests:
- **30 new keywords** from `data/new_keyword_ideas_v2.csv` into the keywords table
- **Latest ranking positions** from `data/current_keyword_rankings.csv` into rank_history
- **12 new blog topics** from `data/blog_post_topics_from_new_keywords_v2.md` into content_ideas
- Plus 10 city template locations ready for content adaptation

### Re-ingest parent task data
When new audit data lands (SEO audit, ranking CSV, keyword research):

```bash
# Step 1: Ingest on-page errors from comprehensive audit + ranking data
python scripts/ingest_parent_data_v2.py

# Step 2: Fix any unmatched keyword names (handles fuzzy matching)
python scripts/fix_unmatched_rankings.py

# Step 3: Close superseded old errors
python scripts/close_old_errors.py

# Step 4: Verify counts
python scripts/check_state.py
```

### Daily automated sync (GSC + Rank Tracker)

```bash
python scripts/daily_sync.py --live --days 1
```

This runs daily at **6 AM via Hermes cron** (`job 607bde89ba99`). It syncs GSC data, then generates a rank tracker report showing:
- Keyword ranking changes (rising/falling/stable/new/lost over 7 days)
- Average position by domain
- Gap analysis (unranked high-opportunity keywords)

### Rank Tracker

```bash
python scripts/rank_tracker.py                    # Full report
python scripts/rank_tracker.py --json             # JSON output
python scripts/rank_tracker.py --export-csv path  # Export to CSV
python scripts/rank_tracker.py --status-only       # Quick summary
```

Outputs to `data/current_keyword_rankings.csv` — the full keyword status with positions and 7-day changes.

## Data Counts (as of June 2026)

| Metric | Value |
|--------|-------|
| Keywords tracked | 137 (43 NZ, 64 AU, 30 new from research) |
| Keywords with rank data | 34 |
| Average position | 5.6 |
| Open SEO issues | 47 (17 critical, 14 high, 16 moderate) |
| Content ideas | 74 (62 original + 12 new blog post topics) |
| Blog city templates | 10 cities ready for adaptation |
| Rank history rows | 2,271 |
| Combined est. search volume (new topics) | ~3,530/mo |

## Project Structure

```
tinka-seo-dashboard/
├── dashboard.py                # Main Streamlit app (6 tabs, 1319 lines)
├── seo_dashboard.py            # Legacy FastAPI version
├── requirements.txt            # Python dependencies
├── vercel.json                 # Vercel deployment config
├── README.md                   # This file
├── start_dashboard.bat         # One-click launcher
├── data/
│   ├── seo_dashboard.db        # SQLite database (all integrated data)
│   ├── schema.sql              # DB schema (5 tables + 3 views)
│   ├── tinka_keyword_research.csv
│   ├── tinka_blog_post_ideas.md
│   ├── new_keyword_opportunities.csv    # 25 gap keywords from t_6d72ac1e
│   ├── new_blog_post_topics.md          # 10 new blog topics from t_6d72ac1e
│   ├── errors_au.json
│   └── errors_nz.json
├── scripts/
│   ├── ingest_parent_data.py           # v1 - original parent task data integration
│   ├── ingest_parent_data_v2.py        # v2 - comprehensive audit + ranking data
│   ├── ingest_newest_parent_data.py    # v3 - 30 new keywords + 12 blog topics + latest ranks
│   ├── fix_unmatched_rankings.py       # Fuzzy-matches & adds missing keywords
│   ├── close_old_errors.py             # Supersedes old manual error batches
│   ├── check_state.py                  # Quick DB state verifier
│   ├── check_old_errors.py             # Debug: compare old vs new errors
│   ├── daily_sync.py                   # GSC + rank tracker orchestrator (runs daily 6am)
│   ├── sync_gsc.py                     # GSC rankings sync
│   ├── ingest_errors.py                # On-page error ingestion
│   ├── ingest_content.py               # Content idea ingestion
│   └── init_db.py                      # Database initialization
├── api/
│   ├── index.py                  # FastAPI backend (Vercel-compatible)
│   ├── seo_dashboard.db          # Seed DB for Vercel deploy
│   └── templates/
│       └── dashboard.html        # HTML template for FastAPI rendering
└── config/
    └── seo_config.yaml
```
