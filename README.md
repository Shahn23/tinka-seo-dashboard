# Tinka SEO Dashboard

Streamlit dashboard for Giant Bubbles by Tinka — tracks keyword rankings, on-page SEO issues, and content ideas across giantbubbles.co.nz and giantbubblesau.com.

## Data Sources

- **Google Search Console** — Keyword rankings, clicks, impressions
- **On-page error scans** — Technical SEO issues by domain
- **Content backlog** — Content ideas with opportunity scoring

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
│   ├── seo_dashboard.db      # SQLite database
│   ├── schema.sql            # DB schema
│   ├── sample_onpage_errors.json
│   └── sample_content_ideas.csv
├── scripts/
│   ├── daily_sync.py         # Orchestrator for all 3 modules
│   ├── sync_gsc.py           # GSC rankings sync
│   ├── ingest_errors.py      # On-page error ingestion
│   ├── ingest_content.py     # Content idea ingestion
│   └── init_db.py            # Database initialization
└── config/
    ├── gsc_credentials.json  # GSC service account (create your own)
    └── seo_config.yaml       # SEO-specific configuration
```
