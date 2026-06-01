# Tinka SEO Dashboard

Streamlit dashboard for Giant Bubbles by Tinka — tracks keyword rankings, on-page SEO issues, and content ideas across giantbubbles.co.nz and giantbubblesau.com.

## Data Sources

- **Google Search Console** — Keyword rankings, clicks, impressions (via `scripts/sync_gsc.py`)
- **On-page error scans** — Technical SEO issues by domain (from `data/errors_au.json`, `data/errors_nz.json`)
- **Keyword research** — 72-keyword AU+NZ universe with opportunity scoring (from `data/tinka_keyword_research.csv`)
- **Content backlog** — Content ideas with opportunity scoring (in DB seed + `data/tinka_blog_post_ideas.md`)

All parent task data is integrated into the SQLite DB via `scripts/ingest_parent_data.py`.

## Local Development

```bash
pip install -r requirements.txt
streamlit run seo_dashboard.py --server.headless true --server.port 8510
```

## Daily Data Sync

The ingestion pipeline runs daily at 6 AM via Hermes cron:

```bash
cd scripts/
python daily_sync.py --live --days 1
```

## Deployment

### Option A: Hugging Face Spaces (Recommended)

```bash
# 1. Login (get token from https://huggingface.co/settings/tokens)
huggingface-cli login

# 2. Create Space
huggingface-cli repo create tinka-seo-dashboard --type space --space-sdk streamlit

# 3. Upload files
cd /path/to/project
git init && git add . && git commit -m "Initial commit"
git remote add space https://huggingface.co/spaces/<USERNAME>/tinka-seo-dashboard
git push --force space main
```

### Option B: Streamlit Community Cloud

1. Push this repo to GitHub
2. Go to https://streamlit.io/cloud
3. Connect repo and deploy

### Option C: Vercel

```bash
npm i -g vercel
vercel login
cd /path/to/project
vercel --prod
```

## Project Structure

```
tinka-seo-dashboard/
├── seo_dashboard.py          # Main dashboard app
├── requirements.txt          # Python dependencies
├── vercel.json               # Vercel deployment config
├── README.md                 # This file
├── data/
│   ├── seo_dashboard.db      # SQLite database (integrated data)
│   ├── schema.sql            # DB schema
│   ├── tinka_keyword_research.csv  # 72-keyword AU+NZ universe
│   ├── tinka_blog_post_ideas.md    # 10 blog post ideas with outlines
│   ├── errors_au.json        # Real on-page errors — giantbubblesau.com
│   ├── errors_nz.json        # Real on-page errors — giantbubbles.co.nz
│   ├── sample_onpage_errors.json
│   └── sample_content_ideas.csv
├── scripts/
│   ├── ingest_parent_data.py # Parent task data integration script
│   ├── daily_sync.py         # Orchestrator for all 3 modules
│   ├── sync_gsc.py           # GSC rankings sync
│   ├── ingest_errors.py      # On-page error ingestion
│   ├── ingest_content.py     # Content idea ingestion
│   └── init_db.py            # Database initialization
└── config/
    ├── gsc_credentials.json  # GSC service account (create your own)
    └── seo_config.yaml       # SEO-specific configuration
```
