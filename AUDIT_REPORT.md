# Tinka SEO Dashboard — Full Codebase Audit Report
**Date:** June 8, 2026  
**Project:** `C:\Users\heysh\OneDrive\Desktop\tinka-seo-dashboard`

---

## (0) DB Schema — All Tables, Columns, Indexes, Foreign Keys

### domains
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| name | TEXT | NOT NULL, UNIQUE |
| display_name | TEXT | NOT NULL |
| gsc_site_url | TEXT | nullable |
| created_at | TEXT | DEFAULT datetime('now') |
| is_active | INTEGER | DEFAULT 1 |

**Data:** 2 rows — `giantbubbles.co.nz` (id=1), `giantbubblesau.com` (id=2)  
**Indexes:** None (beyond PK)

### keywords
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| domain_id | INTEGER | NOT NULL, REFERENCES domains(id) |
| keyword | TEXT | NOT NULL |
| category | TEXT | nullable |
| intent | TEXT | CHECK(intent IN ('informational','commercial','transactional','navigational')) |
| bid | REAL | nullable |
| volume | INTEGER | DEFAULT 0 |
| opportunity_score | REAL | DEFAULT 5.0 |
| difficulty | INTEGER | DEFAULT 50 |
| is_high_priority | INTEGER | DEFAULT 0 |
| created_at | TEXT | DEFAULT datetime('now') |
| UNIQUE(domain_id, keyword) | | |

**Data:** 187 rows  
**Indexes:** PK only. No index on domain_id (foreign key), no index on (domain_id, keyword) despite UNIQUE constraint.

### rank_history
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| keyword_id | INTEGER | NOT NULL, REFERENCES keywords(id) |
| date | TEXT | NOT NULL |
| position | REAL | DEFAULT 0 |
| clicks | INTEGER | DEFAULT 0 |
| impressions | INTEGER | DEFAULT 0 |
| ctr | REAL | DEFAULT 0 |
| UNIQUE(keyword_id, date) | | |

**Data:** 2,179 rows spanning 2026-03-04 to 2026-06-02 (91 distinct dates)  
**Indexes:** PK only. Missing index on (keyword_id, date) — the unique constraint creates an implicit index, but no index on `date` alone for time-range queries.

### onpage_errors
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| domain_id | INTEGER | NOT NULL, REFERENCES domains(id) |
| error_type | TEXT | NOT NULL |
| severity | TEXT | CHECK(severity IN ('critical','high','moderate','low')) |
| page_url | TEXT | nullable |
| description | TEXT | nullable |
| suggestion | TEXT | nullable |
| status | TEXT | CHECK(status IN ('open','in_progress','fixed')), DEFAULT 'open' |
| batch_id | TEXT | nullable |
| created_at | TEXT | DEFAULT datetime('now') |
| fixed_at | TEXT | nullable |

**Data:** 168 rows, 32 open  
**Indexes:** PK only. No index on domain_id or status.

### content_ideas
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| title | TEXT | NOT NULL |
| target_keyword | TEXT | nullable |
| category | TEXT | nullable |
| estimated_searches | INTEGER | DEFAULT 0 |
| opportunity_score | REAL | DEFAULT 5.0 |
| effort | TEXT | CHECK(effort IN ('easy','medium','hard')), DEFAULT 'medium' |
| content_type | TEXT | nullable |
| outline | TEXT | nullable |
| source | TEXT | DEFAULT 'seed' |
| status | TEXT | DEFAULT 'draft' |
| created_at | TEXT | DEFAULT datetime('now') |

**Data:** 115 rows (75 draft, 39 backlog, 1 published)  
**Issue:** 33+ distinct categories with case inconsistencies (`How-To` vs `how-to`, `party` vs `Party Planning`, `kids` vs `kids-activities`)

### published_articles
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| content_idea_id | INTEGER | REFERENCES content_ideas(id) |
| shopify_article_id | INTEGER | nullable |
| title | TEXT | NOT NULL |
| market | TEXT | NOT NULL, CHECK(market IN ('NZ','AU')) |
| target_domain | TEXT | NOT NULL |
| status | TEXT | DEFAULT 'draft', CHECK(status IN ('draft','published','failed')) |
| target_keywords | TEXT | nullable |
| word_count | INTEGER | DEFAULT 0 |
| seo_score | REAL | nullable |
| shopify_url | TEXT | nullable |
| created_at | TEXT | DEFAULT datetime('now') |
| published_at | TEXT | nullable |

**Data:** 1 row (1 published article)

### action_queue
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| action_type | TEXT | NOT NULL |
| action_params | TEXT | nullable |
| status | TEXT | DEFAULT 'pending' |
| created_at | TEXT | DEFAULT datetime('now') |
| processed_at | TEXT | nullable |
| result | TEXT | nullable |
| error | TEXT | nullable |

**Data:** Empty (no pending actions)

### sync_log
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK AUTOINCREMENT |
| source | TEXT | NOT NULL |
| status | TEXT | CHECK(status IN ('running','success','failed')), DEFAULT 'running' |
| rows_synced | INTEGER | DEFAULT 0 |
| started_at | TEXT | DEFAULT datetime('now') |
| completed_at | TEXT | nullable |
| error | TEXT | nullable |

**Data:** 26 rows. Last successful GSC sync: June 6 with 0 rows. Last failed: June 4 (`No module named 'googleapiclient'`).

### Foreign key relationships
```
domains (1) ──→ keywords (domain_id)
keywords (1) ──→ rank_history (keyword_id)
domains (1) ──→ onpage_errors (domain_id)
content_ideas (1) ──→ published_articles (content_idea_id)
```

---

## (1) api/index.py — Complete Tab/Chart/Query/Filter Map

### Global Infrastructure (Lines 1-114)

| Line(s) | Component | Detail |
|---------|-----------|--------|
| 1-9 | Imports | sqlite3, datetime, Path, defaultdict, xml.sax.saxutils, plotly.graph_objects, FastAPI |
| 15-21 | Router import | Attempts `.actions_routes` (package) then `actions_routes` (flat) |
| 23-57 | DB init | Copies `api/seo_dashboard.db` → `/tmp/seo_dashboard.db`, sets PRAGMAs |
| 58-59 | App creation | `FastAPI(title="...")`, includes `actions_router` |
| 63-72 | Middleware | 503 guard if DB init failed |
| 74-89 | `get_conn()` / `fetch()` / `get_one()` | SQLite connection with Row factory, generic fetch helper |
| 95-100 | `fig_to_html()` | Plotly → HTML with CDN, no modebar, responsive |
| 102-113 | Helpers | `sf()` safe float, `si()` safe int, `esc()` HTML escape |
| 142-332 | HTML template | Full-page HTML with CSS + JS (auto-refresh 60s, tabs, toast notifications, interactive action helpers) |

### Tab Navigation (Lines 240-260)

| Line | Tab ID | Label | Badge |
|------|--------|-------|-------|
| 241 | `tab-kw` | 🔑 Rankings | none |
| 242 | `tab-newkw` | 🆕 New Keywords | none |
| 243 | `tab-comp` | 📊 Competitive | none |
| 244 | `tab-issues` | 🛠️ Issues | `open_issue_count` |
| 245 | `tab-content` | 📝 Content | `idea_count` |
| 246 | `tab-studio` | ✍️ Content Studio | none |
| 247 | `tab-audit` | 🔍 Deep Audit | none |
| 248 | `tab-geo` | 🌐 AI Visibility | none |
| 249 | `tab-settings` | 🔄 Settings | none |

### Sidebar Filters (Lines 231-238)

| Filter | Source | SQL Query |
|--------|--------|-----------|
| Domain (dropdown) | `SELECT name FROM domains WHERE is_active=1` (line 826) | Passed as WHERE clause to all data queries |
| Category (dropdown) | `SELECT DISTINCT category FROM keywords ORDER BY category` (line 827) | Filter on `k.category` |
| Intent (dropdown) | Hardcoded list: All, informational, commercial, transactional, navigational (line 831) | Filter on `k.intent` |

---

### Tab 1: 🔑 Keyword Rankings — `render_keywords()` (Lines 335-417)

**Data Source:** `keywords` + `domains` + `rank_history` (latest position per keyword)

**SQL Query (lines 846-856):**
```sql
SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent, k.volume,
       k.opportunity_score, k.difficulty, k.is_high_priority,
       rh.position AS current_position, rh.clicks, rh.impressions
FROM keywords k JOIN domains d ON k.domain_id = d.id
LEFT JOIN (SELECT keyword_id, position, clicks, impressions, date
           FROM rank_history WHERE (keyword_id, date) IN
           (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)
          ) rh ON k.id = rh.keyword_id
WHERE ... ORDER BY k.volume DESC
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Metric cards | 351-361 | count, avg_pos, total_clicks, total_impressions, top3/10/20/outside |
| Chart: Volume by Category | 884-893 | Horizontal bar chart (go.Bar) |
| Chart: Opportunity Score Dist | 895-901 | Histogram (go.Histogram) |
| Winners & Losers | 904-931 | Computed from position delta over 30 days (SQL at 906-916) |
| Quick Wins | 933-941 | Filtered: opp_score>=7, difficulty<=40, unranked/pos>5 |
| Trend selector | 395-401 | `<select name="keyword">` form, submits on change |
| Chart: Position Trend | 946-960 | Line chart (go.Scatter), y-axis reversed |
| Chart: Clicks & Impressions | 961-969 | Dual line chart |
| Full table | 409-413 | All keywords with delete buttons |

**Winners/Losers SQL (lines 905-916):**
```sql
SELECT k.id, k.keyword, d.name AS domain,
       latest.position AS current_position,
       past.position AS past_position
FROM keywords k JOIN domains d ON k.domain_id = d.id
LEFT JOIN (SELECT keyword_id, position FROM rank_history
           WHERE (keyword_id, date) IN
           (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)
          ) latest ON k.id = latest.keyword_id
LEFT JOIN rank_history past ON k.id = past.keyword_id AND past.date = ?
WHERE ...
```
**Note:** 30-day window hardcoded (line 904: `timedelta(days=30)`). No filter parameter.

---

### Tab 2: 🆕 New Keyword Opportunities — `render_new_keywords()` (Lines 420-470)

**Data Source:** `keywords` LEFT JOIN `rank_history` WHERE rank_history is NULL

**SQL Query (lines 979-990):**
```sql
SELECT k.id, d.name AS domain, k.keyword, k.category, k.intent,
       k.volume, k.opportunity_score, k.difficulty
FROM keywords k JOIN domains d ON k.domain_id = d.id
LEFT JOIN rank_history rh ON k.id = rh.keyword_id
WHERE rh.id IS NULL
AND (d.name = ? OR ? = 'All')
AND (k.category = ? OR ? = 'All')
AND (k.intent = ? OR ? = 'All')
ORDER BY k.opportunity_score DESC, k.volume DESC
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Generate Keywords form | 430-449 | POST to `/api/queue-action` with action_type=generate_keywords |
| Metric cards | 451-455 | Untracked count, avg opportunity score, total searches |
| Top Picks (score >= 8) | 460-463 | Cards in grid |
| Full table | 465-468 | All untracked keywords with delete buttons |

---

### Tab 3: 🛠️ Technical SEO Issues — `render_issues()` (Lines 473-519)

**Data Source:** `onpage_errors` JOIN `domains`

**SQL Query (lines 1012-1020):**
```sql
SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
       e.description, e.suggestion, e.status, e.created_at, e.fixed_at
FROM onpage_errors e JOIN domains d ON e.domain_id = d.id
WHERE ...
ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
             WHEN 'moderate' THEN 2 ELSE 3 END, e.id
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Metric cards | 483-489 | Open, critical, high, moderate, fixed counts |
| Chart: Severity Pie | 1030-1037 | Pie chart (go.Pie) |
| Chart: Domain Bar | 1038-1047 | Vertical bar chart (go.Bar) |
| Severity filter dropdown | 495-504 | `sev` query param, submits on change |
| Issue cards | 506-518 | Individual issue display with Mark Fixed button |

**Note:** Severity filter re-submits the entire page, losing position in other tabs. Select `name="sev"` is not preserved across tab switches.

---

### Tab 4: 📝 Blog Content Ideas — `render_content()` (Lines 522-589)

**Data Source:** `content_ideas`

**SQL Query (lines 1055-1062):**
```sql
SELECT ci.id, ci.title, ci.target_keyword, ci.category,
       ci.estimated_searches, ci.opportunity_score, ci.effort,
       ci.content_type, ci.status
FROM content_ideas ci
WHERE ... ORDER BY ci.opportunity_score DESC
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Generate Ideas form | 536-547 | POST to `/api/queue-action` with action_type=generate_ideas |
| Metric cards | 549-553 | Count, avg score, total searches |
| Chart: Opp Score vs Volume | 1072-1092 | Scatter plot (go.Scatter), color-coded by category |
| Chart: Volume by Category | 1094-1106 | Horizontal bar chart |
| Effort filter dropdown | 558-566 | `effort` query param |
| Top Picks (score >= 8) | 568-574 | Cards in grid |
| Full table | 577-587 | All ideas with Delete + Write Article buttons |

---

### Tab 5: 📊 Competitive Analysis — `render_competitive()` (Lines 592-629)

**Data Source:** `keywords` + `domains` + `rank_history` — cross-site comparison

**SQL Query (lines 1121-1132):**
```sql
SELECT k.keyword, k.volume, k.category,
       MAX(CASE WHEN d.name='giantbubbles.co.nz' THEN 1 ELSE 0 END) AS nz_kw,
       MAX(CASE WHEN d.name='giantbubblesau.com' THEN 1 ELSE 0 END) AS au_kw,
       MAX(CASE WHEN d.name='giantbubbles.co.nz' AND rh.position IS NOT NULL THEN 1 ELSE 0 END) AS nz_rank,
       MAX(CASE WHEN d.name='giantbubblesau.com' AND rh.position IS NOT NULL THEN 1 ELSE 0 END) AS au_rank
FROM keywords k JOIN domains d ON k.domain_id = d.id
LEFT JOIN (SELECT keyword_id, MAX(date) as max_d FROM rank_history GROUP BY keyword_id) rh_max ON k.id = rh_max.keyword_id
LEFT JOIN rank_history rh ON k.id = rh.keyword_id AND rh.date = rh_max.max_d
GROUP BY k.keyword
ORDER BY k.volume DESC
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Keyword coverage table | 599-606 | NZ/AU coverage status (✅=ranked, 🟡=tracked, ❌=missing) |
| Summary cards | 609-616 | Shared, NZ-only, AU-only counts |
| Gap analysis | 622-627 | Keywords where one domain has data but the other doesn't |

**Note:** No real competitor data — only compares the two Tinka domains against each other.

---

### Tab 6: ✍️ Content Studio — `render_content_studio()` (Lines 632-669)

**Data Source:** `published_articles`

**SQL Query (lines 1147-1149):**
```sql
SELECT pa.id, pa.title, pa.target_domain, pa.status, pa.target_keywords,
       pa.word_count, pa.seo_score, pa.shopify_url, pa.created_at, pa.published_at
FROM published_articles pa ORDER BY pa.created_at DESC
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Metric cards | 637-642 | Count, total words, published, drafts |
| Article table | 645-655 | All articles with delete buttons |
| Keywords used | 657-665 | Tag display per article |

---

### Tab 7: 🔍 Deep Site Audit — `render_deep_audit()` (Lines 672-705)

**Data Source:** `onpage_errors` (same table as Issues tab, different query order)

**SQL Query (lines 1152-1158):**
```sql
SELECT e.id, d.name AS domain, e.error_type, e.severity, e.page_url,
       e.description, e.suggestion, e.status, e.created_at, e.fixed_at
FROM onpage_errors e JOIN domains d ON e.domain_id = d.id
ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
             WHEN 'moderate' THEN 2 ELSE 3 END, e.id
```

| Component | Line(s) | Type |
|-----------|---------|------|
| Metric cards | 678-684 | Critical, high, moderate, low, fixed counts |
| Severity-grouped findings | 689-701 | Grouped sections with Mark Fixed buttons |

**Note:** This tab duplicates the Issues tab data but with different presentation (grouped by severity, no filtering).

---

### Tab 8: 🌐 AI & GEO Visibility — `render_geo_visibility()` (Lines 708-741)

**Data Source:** `rank_history` + `keywords` + `domains`

**SQL Query (lines 1169-1174):**
```sql
SELECT k.keyword, d.name AS domain, rh.date, rh.position, rh.clicks, rh.impressions, rh.ctr
FROM rank_history rh JOIN keywords k ON rh.keyword_id = k.id
JOIN domains d ON k.domain_id = d.id
ORDER BY rh.date DESC LIMIT 100
```

| Component | Line(s) | Type |
|-----------|---------|------|
| GSC Performance table | 715-721 | Date, domain, avg position, clicks, impressions, CTR |
| GEO Tips | 726-739 | Hardcoded static text (no data-driven content) |

**Note:** Hardcoded GEO tips — no actual AI-optimization scoring, no structured data audit, no brand mention tracking.

---

### Tab 9: 🔄 Sync & Settings — `render_settings()` (Lines 744-813)

| Component | Line(s) | Type |
|-----------|---------|------|
| Last sync status | 747-757 | From `sync_log WHERE source='gsc' ORDER BY started_at DESC LIMIT 1` |
| Auto-sync schedule | 758-760 | Hardcoded text |
| Pending Actions | 770-786 | From `action_queue ORDER BY id DESC LIMIT 20` |
| Sync History | 788-793 | From `sync_log ORDER BY started_at DESC LIMIT 10` |
| How-to guide | 795-811 | Hardcoded usage guide |

---

### Interactive JavaScript Helpers (Lines 265-329)

| Function | Lines | Endpoint |
|----------|-------|----------|
| `postAction(url, formData)` | 265-280 | Generic POST to `/api/queue-action` |
| `deleteItem(url)` | 282-296 | POST to `/api/delete/keyword/{id}`, `/api/delete/idea/{id}`, `/api/delete/article/{id}` |
| `markFixed(url)` | 298-311 | POST to `/api/mark-fixed/{error_id}` |
| `generateKeywords()` | 313 | Triggers kw-gen-form submit |
| `generateIdeas()` | 314 | Triggers idea-gen-form submit |
| `showToast(msg, type)` | 317-329 | Toast notification (success/error) |

---

## (2) api/actions_routes.py — Interactive Endpoints (185 lines)

| Endpoint | Method | Line | Action |
|----------|--------|------|--------|
| `/api/queue-action` | POST | 87-105 | Queue action (generate_keywords, generate_ideas, write_article) |
| `/api/delete/keyword/{kw_id}` | POST | 107-117 | Delete keyword + rank history from /tmp + local DB |
| `/api/delete/idea/{idea_id}` | POST | 119-128 | Delete content idea |
| `/api/delete/article/{article_id}` | POST | 130-139 | Delete published article |
| `/api/mark-fixed/{error_id}` | POST | 141-154 | Mark onpage_errors status='fixed' |
| `/api/pending-actions` | GET | 156-185 | List pending/recent actions |

**Key behavior:** Writes go to BOTH `/tmp/seo_dashboard.db` (immediate Vercel feedback) AND `api/seo_dashboard.db` (persistent). Uses `modify_tmp_db()` which iterates both paths.

---

## (3) scripts/daily_sync.py — Sync Orchestrator (400 lines)

### Pipeline Execution Order

```
daily_sync.py
├── 1. run_gsc_sync()       → scripts/sync_gsc.py
│   ├── Loads domains from DB
│   ├── Loads keyword map from DB
│   ├── Authenticates GSC via service account (~/.hermes/gsc-credentials.json)
│   ├── Iterates each domain × each day
│   ├── Matches GSC queries to tracked keywords (exact → substring)
│   └── Writes rank_history rows
├── 2. run_rank_report()    → Direct SQL queries (no subprocess)
│   ├── Keyword counts, avg position
│   ├── 7-day deltas (rising/falling/stable)
│   └── Output only to logs
└── 3. run_error_ingest()   → scripts/ingest_errors.py
    └── Reads from data/*.json files
    └── run_content_ingest() → scripts/ingest_content.py
        └── Reads from data/*.csv files
```

### Data Sources

| Source | Type | Details |
|--------|------|---------|
| Google Search Console | API | Via service account → googleapiclient, 25K row limit per day per site |
| On-page errors | JSON files | `data/sample_onpage_errors.json`, `errors.json`, `onpage_errors.json` |
| Content ideas | CSV files | `data/sample_content_ideas.csv`, `content_ideas.csv`, `backlog.csv` |

### Schedule

- **GSC:** Daily 6 AM cron (Hermes cron job)
- **Errors:** Daily (same cron)
- **Content:** Daily (same cron)
- **Action processing:** Every 30 min (separate `process_actions.py`)

### Staleness Issue (CRITICAL)

| Metric | Value |
|--------|-------|
| Latest rank data | **2026-06-02** (6 days stale as of June 8) |
| Recent syncs | All reporting "success" with **0 rows synced** |
| June 4 failure | `No module named 'googleapiclient'` |
| Root cause | GSC sync runs but produces 0 matched rows. Likely because keyword-to-query matching is too loose/too strict, OR GSC credentials are not set up in the serverless environment where the cron runs. |

**Keyword match rate:** Only 32/187 keywords (17%) have any rank history data.

---

## (4) scripts/article_writer.py + ai_generator.py — Content Pipeline

### ai_generator.py (255 lines)

| Function | Line | Purpose |
|----------|------|---------|
| `get_openrouter_key()` | 24-38 | Reads OPENROUTER_API_KEY from `~/.hermes/.env` or `~/open-brain/.env.secrets` |
| `ask_ai()` | 40-71 | Calls OpenRouter API (`deepseek/deepseek-chat`), 60s timeout, 4K max tokens |
| `generate_keywords()` | 75-123 | Generates keyword ideas from topic seed → returns JSON array |
| `generate_article_ideas()` | 127-173 | Generates article/blog ideas from keywords → returns JSON array |
| `generate_article_body()` | 177-216 | Generates full SEO-optimized HTML article body |

**CLI Modes:**
| Flag | Purpose |
|------|---------|
| `--generate-keywords <topic>` | Generate keyword ideas |
| `--generate-articles <topic>` | Generate article ideas |
| `--generate-body <title>` | Generate article body HTML |
| `--market NZ\|AU` | Market target |
| `--count N` | Number of results |
| `--json` | Raw JSON output |

### article_writer.py (304 lines)

| Component | Line | Purpose |
|-----------|------|---------|
| `get_shopify_token()` | 69-80 | Reads SHOPIFY_ADMIN_TOKEN from `~/.hermes/.env` |
| `post_to_shopify()` | 94-143 | Creates draft article on Shopify blog (BLOG_ID=106785898817) |
| `record_article()` | 145-170 | Records article in `published_articles` table |
| `list_ideas()` | 197-219 | Lists unpublished content ideas sorted by opportunity |

**CLI Usage:**
```
python scripts/article_writer.py --idea 5 --body articles/rotorua.html
python scripts/article_writer.py --idea 5 --generate       # placeholder — not implemented
python scripts/article_writer.py --list-ideas
```

**NOTE:** The `--generate` flag is documented but `generate_article_html()` returns `None` (line 194). Full AI generation goes through `process_actions.py` → `article_writer.py --idea X --body <file>` — the --generate pipeline is incomplete.

---

## (5) scripts/process_actions.py — Action Queue Processor (247 lines)

### Supported Action Types

| Action Type | Lines | Behavior |
|-------------|-------|----------|
| `generate_keywords` | 90-131 | Calls `ai_generator.py --generate-keywords`, inserts into `keywords` table |
| `generate_ideas` | 133-166 | Calls `ai_generator.py --generate-articles`, inserts into `content_ideas` |
| `write_article` | 168-179 | Calls `article_writer.py --idea X --generate` (NOTE: --generate not implemented yet) |
| `delete_keyword` | 181 | Skips — "Already applied to /tmp" |
| `delete_idea` | 181 | Same skip |
| `delete_article` | 181 | Same skip |
| `mark_fixed` | 181 | Same skip |

### Processing Flow
1. Reads pending actions from `data/seo_dashboard.db`
2. Processes each action (AI generation subprocess or skip)
3. Updates action_queue status to `completed` or `failed`
4. Copies updated DB to `api/seo_dashboard.db` (line 232)
5. Optionally deploys to Vercel via `npx vercel --prod --yes` (lines 236-243)

### Schedule
- Every 30 min via Hermes cron

---

## (6) vercel.json — Deployment Config

```json
{
    "builds": [{
        "src": "api/index.py",
        "use": "@vercel/python",
        "config": {
            "includeFiles": [
                "api/seo_dashboard.db",
                "api/actions_routes.py",
                "api/templates/**"
            ]
        }
    }],
    "routes": [{
        "src": "/(.*)",
        "dest": "api/index.py"
    }]
}
```

**Notable:**
- Catch-all route (`/(.*)`) — no static files, no API prefix routing
- `api/templates/**` included but no Jinja2 templates exist (all inline HTML)
- Bundle includes both DB file and actions_routes.py

---

## (7) Data Sources Feeding the Dashboard

| Source | Method | Freshness | Status |
|--------|--------|-----------|--------|
| **Google Search Console** | API via googleapiclient service account | Daily | ⚠️ Syncing 0 rows since June 4 |
| **On-page errors (JSON files)** | `data/sample_onpage_errors.json` and variants | Static / manual | ⚠️ File-based, not live crawl |
| **Content ideas (CSV files)** | `data/sample_content_ideas.csv` and variants | Static / AI-generated | ✅ Working but AI estimates are synthetic |
| **AI-generated keywords** | OpenRouter → DeepSeek, via action queue | On-demand | ✅ Working |
| **AI-generated article bodies** | OpenRouter → DeepSeek, via action queue | On-demand | ⚠️ `--generate` pipeline incomplete |
| **Shopify** | Admin API via curl subprocess | On publish | ✅ Working |
| **Competitive data** | None — only compares NZ vs AU | N/A | ❌ No external competitor data |

---

## (8) Gaps and Pain Points

### Critical

| # | Issue | Impact |
|---|-------|--------|
| 1 | **Rank data 6 days stale** (latest: June 2) | All ranking KPIs, trends, winners/losers are inaccurate |
| 2 | **GSC sync produces 0 rows** since June 4 | No new rank data flowing in; 83% of keywords (155/187) have zero rank history |
| 3 | **No error ingestion data** — runs from static JSON files | Errors tab data doesn't reflect current site state |
| 4 | **Competitive tab has no real competitors** — only compares two Tinka domains | Tab is misleading; users expect competitor intelligence |

### High

| # | Issue | Impact |
|---|-------|--------|
| 5 | **No real keyword volume/difficulty data** — all AI-generated estimates | Metrics are synthetic, can't prioritize accurately |
| 6 | **Content categories are a mess** — 33+ inconsistent categories (`How-To` vs `how-to`, `party` vs `Party Planning`) | Content tab filters break, analytics unreliable |
| 7 | **Deep Audit tab duplicates Issues tab** with different presentation | Confusing; same data, different layout |
| 8 | **AI Visibility tab has hardcoded GEO tips** — no actual data | Fully static content, no actionable insights |
| 9 | `write_article` action type's `--generate` flag returns `None` (line 194 of article_writer.py) | Article pipeline broken; must supply HTML file path |
| 10 | **No DB indexes** on foreign keys (domain_id, keyword_id) | Performance will degrade with scale; no date index on rank_history |
| 11 | **Filters are not preserved across tab switches** | User must re-apply after tab change |

### Medium

| # | Issue | Impact |
|---|-------|--------|
| 12 | No error boundaries in action queue processing | Silent failures when AI generation errors |
| 13 | DB writes go to /tmp first, copied back on deploy | Race condition: in-flight actions can be lost between deploys |
| 14 | No rate limiting on generate endpoints | Could be abused to trigger many AI calls |
| 15 | 30-day hardcoded window for winners/losers (line 904) | Cannot customize comparison period |
| 16 | Content Studio shows SEO Score as `-` for all articles (line 652) | seo_score column is always NULL |
| 17 | Only 1 published article in production | Content pipeline is barely utilized |

---

## (9) Top 5 Highest-Impact Improvements with DataForSEO Integration

Ranked by effort-to-value ratio for a DataForSEO integration:

### 1. 🔥 Real Keyword Rankings API (Replaces GSC Sync)  — **Value: 10/10, Effort: Medium**

**What it replaces:** `scripts/sync_gsc.py` and the stale GSC pipeline.

**Implementation:**
- Use DataForSEO `/v3/serp/google/organic/live/advanced` API to get real-time rank positions for all 187 tracked keywords
- Run daily (cost: ~$0.003 per keyword ≈ $0.56/day for 187 keywords)
- Populate `rank_history` with real position, URL, title, snippet data
- No more GSC credential issues, no more 0-row syncs, no more 6-day staleness

**Impact:** Fixes the #1 issue. All ranking tabs, trends, winners/losers become accurate. Real-time, not 6-days stale.

### 2. 📊 Real Keyword Research Data (Keyword Difficulty & Volume) — **Value: 9/10, Effort: Low**

**What it replaces:** AI-generated (synthetic) volume and difficulty estimates.

**Implementation:**
- Use DataForSEO `/v3/keywords_data/google/search_volume/live` batch endpoint
- Send all keywords at once to get real monthly search volume, competition, and difficulty scores
- Update `keywords.volume` and `keywords.difficulty` columns with real data
- Enrich the `keywords` table with `cpc` and `competition` columns

**Impact:** Prioritization becomes trustworthy. The "Quick Wins" and "Top Picks" sections become actionable instead of misleading.

### 3. 🏆 Real Competitor Analysis — **Value: 8/10, Effort: Low-Medium**

**What it replaces:** The current "Competitive" tab which only compares NZ vs AU (both Tinka sites).

**Implementation:**
- Use DataForSEO `/v3/serp/google/organic/live/advanced` to identify actual competitors ranking for Tinka's keywords
- Create a `competitors` table: `domain TEXT, keyword_id INT, position INT, serp_features TEXT`
- Populate by running SERP queries for top 50 keywords and extracting competitor domains from organic results
- New tab shows real competitors with keyword overlap, gap analysis, and share of voice

**Impact:** Transforms a misleading tab into a genuinely useful competitive intelligence dashboard.

### 4. 🕵️ Real On-Page SEO Audit via Live Crawl — **Value: 7/10, Effort: Medium**

**What it replaces:** Static JSON file-based error ingestion.

**Implementation:**
- Use DataForSEO `/v3/on_page/lighthouse/task_post` or on-page summary endpoint
- Trigger crawl of both domains weekly (cost: ~$0.006 per page)
- Populate `onpage_errors` with real technical findings (meta tags, headings, schema, load time, mobile usability)
- Add columns for DataForSEO-specific metrics (lighthouse score, performance, accessibility, best practices)

**Impact:** Errors tab becomes live and actionable instead of static sample data.

### 5. 🔍 Content Gap & Topic Cluster Analysis — **Value: 7/10, Effort: Low**

**What it adds:** Data-driven content strategy instead of AI-generated guesswork.

**Implementation:**
- Use DataForSEO `/v3/keywords_data/google/ads/search_volume_for_keywords/live` and `/v3/keywords_data/google/keywords_for_site/live`
- For each competitor from (3), identify keywords they rank for that Tinka doesn't
- Create a `content_gaps` table: `keyword TEXT, competitor TEXT, volume INT, difficulty INT`
- Feed gaps into the content ideas generator as real data-backed suggestions

**Impact:** Transforms the Content tab from AI-generated ideas to actual market-backed content opportunities.

### Effort/Value Summary

| Rank | Improvement | Value | Effort | Cost/Day (est.) |
|------|-------------|-------|--------|----------------|
| 1 | Real SERP Rankings | 10/10 | Medium | ~$0.56 |
| 2 | Real Keyword Volume & Difficulty | 9/10 | Low | ~$0.08 |
| 3 | Real Competitor Analysis | 8/10 | Low-Medium | ~$0.25 |
| 4 | Live On-Page Audit | 7/10 | Medium | ~$1.00 |
| 5 | Content Gap Analysis | 7/10 | Low | ~$0.15 |

**Total estimated DataForSEO daily spend for all 5:** ~$2.04/day

**Total estimated dev effort:** 3-5 days for a developer familiar with DataForSEO API and the existing codebase.
