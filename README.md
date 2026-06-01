# Tinka SEO Dashboard

Streamlit dashboard for Giant Bubbles by Tinka — tracks keyword rankings (107 keywords, 34 ranked), on-page SEO issues (47 open, 23 critical/high), and content ideas (62 topics) across **giantbubbles.co.nz** (43 keywords) and **giantbubblesau.com** (64 keywords).

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

### Daily automated sync (GSC)
```bash
python scripts/daily_sync.py --live --days 1
```

Runs daily at 6 AM via Hermes cron.

## Data Counts (as of June 2026)

| Metric | Value |
|--------|-------|
| Keywords tracked | 107 (43 NZ, 64 AU) |
| Keywords with rank data | 34 |
| Average position | 5.6 |
| Open SEO issues | 47 (17 critical, 14 high, 16 moderate) |
| Content ideas | 62 |
| Rank history rows | 2,271 |

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
│   ├── ingest_parent_data.py     # v1 - original parent task data integration
│   ├── ingest_parent_data_v2.py  # v2 - comprehensive audit + ranking data
│   ├── fix_unmatched_rankings.py # Fuzzy-matches & adds missing keywords
│   ├── close_old_errors.py       # Supersedes old manual error batches
│   ├── check_state.py            # Quick DB state verifier
│   ├── check_old_errors.py       # Debug: compare old vs new errors
│   ├── daily_sync.py             # GSC orchestrator
│   ├── sync_gsc.py               # GSC rankings sync
│   ├── ingest_errors.py          # On-page error ingestion
│   ├── ingest_content.py         # Content idea ingestion
│   └── init_db.py                # Database initialization
├── api/
│   ├── index.py                  # FastAPI backend (Vercel-compatible)
│   ├── seo_dashboard.db          # Seed DB for Vercel deploy
│   └── templates/
│       └── dashboard.html        # HTML template for FastAPI rendering
└── config/
    └── seo_config.yaml
```
