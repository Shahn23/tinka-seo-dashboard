# Tinka SEO Dashboard v0.7 - All Data Integrated 🚀

All-in-one SEO dashboard for **Giant Bubbles by Tinka** - live-syncing keyword rankings, new keyword opportunities, on-page SEO errors, and blog content ideas. Fully integrated with data from 4 research workstreams: ranking analysis, keyword discovery, blog ideation, and SEO audit. Built for the site owner (no technical skills needed).

## Live Access

**Vercel (auto-refreshing):** [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app)
- Opens in any browser, auto-refreshes every 60 seconds

**Local (Streamlit):** `http://localhost:8510` (double-click `start_dashboard.bat`)

## Features (9 Tabs)

| Tab | Features | Who It's For |
|-----|----------|-------------|
| 🔑 Rankings | Current keyword positions, rank distribution (Top 3/10/20), winners & losers over 30 days, per-keyword trend charts. **Generate new keywords via AI** and **delete unwanted keywords**. | Business owner - see which keywords are ranking and which need work |
| 📊 Competitive | Keyword gap analysis, share of voice, cluster heatmap, market coverage sunburst | Marketing - identify competitive opportunities |
| 🛠️ SEO Issues | On-page SEO problems (critical, high, moderate, low), with descriptions and fix suggestions **from latest 53-finding audit** | Developer - prioritized action list |
| 📝 Content | Blog post ideas sorted by opportunity score with target keywords. Now **97 ideas** including 15 new v2 ideas (sensory autism, city guides, eco bubbles, Montessori, gift guides, wedding exits). **Generate new ideas via AI** and **delete unwanted ones**. | Writer - pick the highest-impact topics first |
| ✍️ Content Studio | Write SEO articles from researched keywords, **generate articles with AI inline**, post drafts to Shopify, **delete unwanted articles** | Publisher - manage the whole pipeline |
| 🔍 Deep Audit | Live page analysis - 9-point on-page SEO scorechecker with meta, schema, speed, image checks | Quick technical checks |
| 🌐 AI Visibility | AI search (ChatGPT/Perplexity) visibility check, content gap analysis, Reddit opportunity search, competition radar | GEO optimization |
| 🔔 Alerts | Rank drop alerts, keyword opportunity alerts, weekly digests | Stay informed |
| 🔄 Settings | Data sync controls, API integration setup, tool recommendations | Configure integrations |

### Key Features
- **Rank distribution** - see Top 3, Top 10, Top 20 counts with percentages
- **Winners & Losers** - which keywords improved/dropped in the last 30 days
- **Quick Wins** - high-opportunity, low-difficulty keywords to target first
- **Position trend** - select any keyword to see its rank, clicks, and impressions over time
- **Auto-refresh** - page reloads every 60 seconds with latest data
- **Filters** - view by domain (NZ/AU), category, or keyword intent
- **Live GSC sync** - Google Search Console data updates daily (6 AM cron)
- **187 keywords tracked** (99 NZ, 88 AU), 32 ranked, 2,179 rank history rows
- **15 new blog post ideas integrated** (parent task t_61a55ee1) covering 30 keywords, avg opportunity 8.2

## How to Use (Non-Technical)

1. **Open the link** - [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app)
2. **Use the sidebar** - select "giantbubbles.co.nz" or "giantbubblesau.com" to see one domain at a time, or leave at "All" to see both
3. **Check the Rankings tab** - the metric cards at the top show how many keywords are in Top 3, Top 10, Top 20. The Winners & Losers section shows which keywords moved most
4. **Pick a keyword trend** - use the dropdown under "Position Trend" to see a keyword's history
5. **Explore New Keywords** - these are research-backed keywords you're not ranking for yet. High opportunity score = write content about these first
6. **Review Issues** - critical items hurt rankings most. Each issue has a description and fix suggestion
7. **Check Content Ideas** - sorted by best opportunity. Pick an easy topic for a quick win

**Pro tip:** The auto-refresh runs every 60 seconds, so just leave it open on a second monitor.

## Data Sources

- **Google Search Console** - keyword rankings, clicks, impressions (synced daily at 6 AM, or manual via `scripts/daily_sync.py --live --days 1`)
- **On-page SEO audit** (t_d57cacd6) - 53 findings (10 critical, 11 high, 20 moderate, 2 low open) including cross-site duplicate content, missing meta descriptions, overstuffed titles/meta, missing H1s, and alt text gaps
- **Keyword research** - 187 keywords (99 NZ, 88 AU) across both domains (154 original + 33 new from parent task t_23086db7)
- **Content backlog** - 97 blog post ideas with opportunity scores (82 original + 15 new v2 from parent task t_61a55ee1)
- **Ranking analysis** (t_5171c80e) - 32/187 ranked keywords (20.8% ranking rate), 14 falling, 9 rising, 8 new entrants

## How to Update Data Sources

The dashboard syncs live from the SQLite database. Updates are applied by refreshing the database and redeploying.

### Automatic Sync (Daily)
A cron job runs daily at 6 AM (set via Hermes Agent) which:
1. Pulls fresh GSC ranking data via `scripts/daily_sync.py --live --days 1`
2. Updates `rank_history` with latest positions, clicks, impressions
3. Any new keywords added to the DB are automatically reflected in the dashboard

### Manual Data Updates

**Adding new keywords:**
1. Use the "Generate" button in the dashboard's Rankings tab (AI-powered)
2. Or insert directly into the database via Python:
```python
import sqlite3
conn = sqlite3.connect("data/seo_dashboard.db")
# NZ domain_id=1, AU domain_id=2
conn.execute("""INSERT INTO keywords (domain_id, keyword, category, intent, volume, opportunity_score, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
             (1, "your keyword nz", "product", "commercial", 200, 8.0, 15))
conn.commit()
```

**Adding new content ideas:**
1. Use the "Generate Ideas" AI feature in the Content tab
2. Or insert via Python following the `content_ideas` table schema:
   - title, target_keyword, category, estimated_searches, opportunity_score, effort, content_type, outline, source, status
3. New v2 blog ideas can be re-ingested with: `python scripts/ingest_v2_blog_ideas.py`

**Updating SEO issues:**
New audit findings can be imported from JSON via:
```bash
python -c "
import json, sqlite3
with open('data/seo_audit_findings_20260604.json') as f:
    findings = json.load(f)
conn = sqlite3.connect('data/seo_dashboard.db')
# Each finding gets inserted as an onpage_error
# ... see scripts/ingest_parent_data.py for full pipeline
conn.close()
"
```

**Marking issues as fixed:**
In the dashboard's SEO Issues tab, use the "Mark Fixed" button for individual issues, or batch-close resolved issues via:
```sql
UPDATE onpage_errors SET status='fixed', fixed_at=datetime('now')
WHERE batch_id='your-batch-id' AND status='open';
```

### Deploying Changes
After updating the database:
```bash
# 1. Copy fresh DB to the Vercel build path
copy data\seo_dashboard.db api\seo_dashboard.db
# 2. Deploy (uses saved Vercel token)
vercel --prod --yes
```
Or double-click `deploy.bat` for a one-click deploy.

### Adding New Data Files
To add a new data source:
1. Add your data to the appropriate table in `data/seo_dashboard.db`
2. The dashboard queries dynamically from the DB - no code changes needed for new rows
3. For new chart types or tabs, edit `api/index.py` (Vercel) or `dashboard.py` (local Streamlit)

## Deployment

### Vercel (hosted - for sharing with clients)

The dashboard is already deployed at [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app).

To refresh the deployment with the latest data:
```bash
# From the dashboard project directory:
copy data\seo_dashboard.db api\seo_dashboard.db
vercel --prod --yes
```

Or double-click `deploy.bat` (first time requires Vercel login).

### Local (Streamlit - for development)

```bash
uv run streamlit run dashboard.py --server.headless true --server.port 8510
```
Or double-click `start_dashboard.bat`.

## Project Structure

```
tinka-seo-dashboard/
├── dashboard.py           # Streamlit dashboard (local, 7 tabs)
├── seo_dashboard.py       # Legacy Streamlit version
├── api/
│   ├── index.py           # FastAPI app (Vercel-compatible, 5 tabs)
│   ├── seo_dashboard.db   # Seed DB for Vercel deploy
│   └── templates/         # Legacy HTML templates
├── data/
│   ├── seo_dashboard.db   # Main SQLite database (280 KB)
│   ├── new_keyword_ideas_v4.csv      # 25 latest keyword suggestions
│   ├── new_keyword_research_report_v4.md   # Research report
│   └── ...                # Supporting data files
├── scripts/
│   ├── daily_sync.py      # Daily GSC + rank tracker orchestrator
│   ├── sync_gsc.py        # Google Search Console sync
│   ├── rank_tracker.py    # Rank change analysis
│   ├── ingest_parent_data.py  # Data import pipeline
│   └── ...                # Supporting scripts
├── requirements.txt
├── vercel.json            # Vercel deployment config
├── deploy.bat             # One-click Vercel deploy script
├── start_dashboard.bat    # One-click local launcher
└── README.md              # This file
```

## Data Counts (as of June 4, 2026)

| Metric | Value |
|--------|-------|
| Keywords tracked | 187 (99 NZ, 88 AU) |
| Keywords with rank data | 32 |
| Average position | 5.5 |
| Rank history rows | 2,179 |
| Open SEO issues | 43 (10 critical, 11 high, 20 moderate, 2 low) |
| Fixed SEO issues | 93 |
| Content ideas | 97 (82 original + 15 v2) |
| New keyword opportunities | 187 tracked + 33 untracked research |
| New blog post ideas (v2) | 15 covering 30 keywords, ~4,450/mo volume |
| SEO audit findings | 53 total from latest crawl |
| Last GSC sync | June 4, 2026 |

## Version History

- **v0.7** (current) - Full data integration: 33 new keywords, 15 blog post ideas, 53 audit findings. Content ideas at 97.
- **v0.6** - AI keyword & article idea generation, inline article writer, delete/remove keywords/ideas/articles, em dash removal
- **v0.5** - RustySEO + GEO features, Deep Site Audit, AI Visibility tracker, Reddit search
- **v0.4** - Content Studio with Shopify integration, article publishing
- **v0.3** - Competitive gap analysis, enhanced keyword filtering
- **v0.2** - Full dashboard with 6 tabs, Plotly charts, GSC sync
- **v0.1** - Initial keyword tracking dashboard
