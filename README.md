# Tinka SEO Dashboard v0.5 — Live Syncing 🚀

All-in-one SEO dashboard for **Giant Bubbles by Tinka** — live-syncing keyword rankings, new keyword opportunities, on-page SEO errors, and blog content ideas. Built for the site owner (no technical skills needed).

## Live Access

**Vercel (auto-refreshing):** [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app)
— Opens in any browser, auto-refreshes every 60 seconds

**Local (Streamlit):** `http://localhost:8510` (double-click `start_dashboard.bat`)

## What's Inside

| Tab | What It Shows | For Whom |
|-----|---------------|----------|
| 🔑 Rankings | Current keyword positions, rank distribution (Top 3/10/20), winners & losers over 30 days, per-keyword trend charts | Business owner — see which keywords are ranking and which need work |
| 🆕 New Keywords | Research-backed untracked keywords with opportunity scores | Marketing — know which keywords to write content for next |
| 🛠️ Issues | On-page SEO problems (critical → moderate), with descriptions and fix suggestions | Developer — prioritized action list |
| 📝 Content | Blog post ideas sorted by opportunity score with target keywords | Writer — pick the highest-impact topics first |
| 🔄 Settings | Sync history, dashboard info, and usage guide | Everyone |

### Key Features
- **Rank distribution** — see Top 3, Top 10, Top 20 counts with percentages
- **Winners & Losers** — which keywords improved/dropped in the last 30 days
- **Quick Wins** — high-opportunity, low-difficulty keywords to target first
- **Position trend** — select any keyword to see its rank, clicks, and impressions over time
- **Auto-refresh** — page reloads every 60 seconds with latest data
- **Filters** — view by domain (NZ/AU), category, or keyword intent
- **Live GSC sync** — Google Search Console data updates daily (6 AM cron)
- **154 keywords tracked** (72 NZ, 82 AU), 34 ranked, 2,179 historical data points

## How to Use (Non-Technical)

1. **Open the link** — [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app)
2. **Use the sidebar** — select "giantbubbles.co.nz" or "giantbubblesau.com" to see one domain at a time, or leave at "All" to see both
3. **Check the Rankings tab** — the metric cards at the top show how many keywords are in Top 3, Top 10, Top 20. The Winners & Losers section shows which keywords moved most
4. **Pick a keyword trend** — use the dropdown under "Position Trend" to see a keyword's history
5. **Explore New Keywords** — these are research-backed keywords you're not ranking for yet. High opportunity score = write content about these first
6. **Review Issues** — critical items hurt rankings most. Each issue has a description and fix suggestion
7. **Check Content Ideas** — sorted by best opportunity. Pick an easy topic for a quick win

**Pro tip:** The auto-refresh runs every 60 seconds, so just leave it open on a second monitor.

## Data Sources

- **Google Search Console** — keyword rankings, clicks, impressions (synced daily at 6 AM, or manual via `scripts/daily_sync.py --live --days 1`)
- **On-page SEO audit** — 127 structured issues (32 open: 6 critical, 8 high, 18 moderate)
- **Keyword research** — 154 keywords (72 NZ, 82 AU) across both domains
- **Content backlog** — 67 blog post ideas with opportunity scores

## Deployment

### Vercel (hosted — for sharing with clients)

The dashboard is already deployed at [tinka-seo-dashboard.vercel.app](https://tinka-seo-dashboard.vercel.app).

To refresh the deployment with the latest data:
```bash
# From the dashboard project directory:
copy data\seo_dashboard.db api\seo_dashboard.db
vercel --prod --yes
```

Or double-click `deploy.bat` (first time requires Vercel login).

### Local (Streamlit — for development)

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
| Keywords tracked | 154 (72 NZ, 82 AU) |
| Keywords with rank data | 34 |
| Average position | 5.5 |
| Rank history rows | 2,179 |
| Open SEO issues | 32 (6 critical, 8 high, 18 moderate) |
| Fixed SEO issues | 95 |
| Content ideas | 67 |
| New keyword opportunities | 120 untracked |
| Last GSC sync | June 3, 2026 |

## Version History

- **v0.5** (current) — Live syncing, 5 tabs, auto-refresh every 60s, winners/losers, rank distribution, Vercel deployment
- **v0.4** — Content Studio with Shopify integration, article publishing
- **v0.3** — Competitive gap analysis, enhanced keyword filtering
- **v0.2** — Full dashboard with 6 tabs, Plotly charts, GSC sync
- **v0.1** — Initial keyword tracking dashboard
