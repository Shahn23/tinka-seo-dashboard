# Tinka SEO Dashboard

Live SEO monitoring dashboard for Giant Bubbles by Tinka — tracking keyword rankings, on-page errors, and content ideas for both Australian and New Zealand domains.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize the database (creates tables + seed domains)
python scripts/init_db.py

# Seed with sample data
python scripts/seed_data.py

# Launch dashboard
streamlit run dashboard.py
```

## Dashboard Sections

1. **Overview** — Key metrics at a glance (rankings tracked, open issues, content backlog)
2. **Keyword Rankings** — Historical trend charts, filterable by domain and keyword
3. **On-Page Errors** — Error table with severity, status tracking, and fix progress
4. **Content Ideas** — Backlog with priority scoring, keyword ranking context
5. **Data Sync** — Manual sync trigger and sync history log

## Data Sources

- **Google Search Console** — Live GSC API for NZ domain (giantbubbles.co.nz), 833 rows synced
- **Manual input** — Keyword research and SEO audit findings
- **Backlog CSV** — Content idea backlog with priority scoring

## Deployment

### Streamlit Community Cloud
1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo and deploy
4. Set `requirements.txt` as the dependency file

### Render
1. Create a new Web Service
2. Set the build command: `pip install -r requirements.txt`
3. Set the start command: `streamlit run dashboard.py --server.port $PORT`

## Project Structure

```
├── dashboard.py              # Main Streamlit dashboard
├── requirements.txt          # Python dependencies
├── config/
│   ├── config.example.yaml   # Config template
│   └── config.yaml           # Local config (gitignored)
├── data/
│   ├── schema.sql            # Database schema (7 tables, 5 views)
│   └── seo_dashboard.db      # SQLite database (gitignored)
├── docs/
├── scripts/
│   ├── init_db.py            # Initialize database
│   └── seed_data.py          # Seed with sample data
├── src/
│   ├── config.py             # YAML config loader
│   ├── database.py           # SQLite CRUD layer
│   ├── gsc_client.py         # GSC API client
│   ├── models.py             # Python data models
│   └── onpage_ingestion.py   # On-page error ingestion
└── tests/
    └── test_models.py        # Unit tests
```
