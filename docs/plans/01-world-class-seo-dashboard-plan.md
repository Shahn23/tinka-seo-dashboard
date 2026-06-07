# Tinka SEO Dashboard — World-Class Upgrade Plan

> Goal: Transform the existing FastAPI + Plotly SEO dashboard into a world-class
> SEO intelligence platform for Giant Bubbles by Tinka (2 domains, 187 keywords,
> ecommerce bubble-toy store). DataForSEO API now available via shared account.
>
> Current state: 9 tabs, 32 ranked keywords, GSC dead for 6 days, synthetic volume
> estimates, no competitor data, content pipeline stalled at 75 drafts.
>
> Budget: ~$30-90/mo DataForSEO API costs (vs $129-249/mo for equivalent
> commercial tool like Ahrefs/SE Ranking)

---

## Phase 0: Foundation — Data Plumbing (1 week)

**Fix what's broken before building new things.**

### 0.1 DataForSEO Python client

- **Step:** Write `scripts/dataforseo_client.py` — Python equivalent of the TypeScript client in rank-rent-v2
- **Endpoints to wrap:**
  - `POST /v3/serp/google/organic/live/regular` — live rank check
  - `POST /v3/serp/google/organic/live/advanced` — SERP features
  - `POST /v3/keywords_data/google_ads/search_volume/live` — real volume/CPC
  - `POST /v3/dataforseo_labs/google/keyword_ideas/live` — keyword discovery
  - `POST /v3/dataforseo_labs/google/keyword_difficulty/live` — difficulty scoring
  - `POST /v3/dataforseo_labs/google/related_keywords/live` — related terms
  - `POST /v3/backlinks/summary/live` — backlink summary stats
  - `POST /v3/backlinks/backlinks/live` — individual backlinks
  - `POST /v3/backlinks/referring_domains/live` — referring domains
- **Auth:** Basic auth (healing4happiness@gmail.com:password), store creds in Vercel env vars
- **Config:** Store credentials in `config.yaml` + Vercel env vars (`DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`)

### 0.2 Fix GSC sync

- **Step 1:** Diagnose why `sync_gsc.py` returns 0 rows since June 4
  - Read sync_gsc.py (7091 bytes) — was the `googleapiclient` import fixed?
  - Test against the actual GSC API with a curl/debug call
- **Step 2:** Patch sync_gsc.py to output debug info (number of rows returned, date range)
- **Step 3:** Run a manual backfill for the 6 missing days (June 2-8)
- **Step 4:** Set up a cron job to run daily at 6 AM (existing cron should work if the script fix works)
- **Deliverable:** Rank history updated to today, cron keeps it fresh

### 0.3 Real keyword volume + difficulty ingestion

- **Step 1:** Write `scripts/enrich_keywords.py` — for all 187 keywords:
  - Call DataForSEO `getKeywordVolume()` batch (100 at a time, ~2 calls)
  - Call `getKeywordDifficulty()` batch
  - Update `keywords` table: `volume`, `difficulty`, `cpc`, `competition`
- **Step 2:** Add location_code mapping for NZ (2076) and AU (2036)
- **Step 3:** Also run on any keyword inserted in the future (hook into daily_sync.py)
- **Deliverable:** Every keyword has real DataForSEO volume + difficulty, not synthetic

### 0.4 Add DB indexes

- **Step 1:** Write migration `migration_001_indexes.sql`
  - `CREATE INDEX idx_kw_domain ON keywords(domain_id)`
  - `CREATE INDEX idx_rank_kw_date ON rank_history(keyword_id, date)`
  - `CREATE INDEX idx_rank_date ON rank_history(date)`
  - `CREATE INDEX idx_ci_status ON content_ideas(status)`
  - `CREATE INDEX idx_oe_severity ON onpage_errors(severity, status)`
- **Deliverable:** All common queries use index lookups (should be <50ms each)

---

## Phase 1: Live Rank Tracking + Keyword Intel (1-2 weeks)

**Replaces stale GSC data with real-time DataForSEO rank checks.**

### 1.1 Daily rank check script

- **Step 1:** Write `scripts/daily_rank_check.py`
  - Reads all 187 keywords + their target domains from DB
  - For each keyword+domain pair, calls `lookupRankForDomain()` via DataForSEO
  - Inserts result into `rank_history` (keyword_id, date, position, url, title)
  - Rate limit: max 100 calls/min, spread across 2-3 min batch
  - Cost: 187 × 2 domains = 374 calls/day × $0.002 = $0.75/day = **$22.50/mo**
- **Step 2:** Update daily cron to call this AFTER the GSC sync
- **Deliverable:** Every keyword has a real, fresh rank position daily

### 1.2 Real keyword data in dashboard UI

- **Step 1:** Patch `api/index.py` keywords tab — replace synthetic volume/difficulty with DataForSEO values from `keywords` table
- **Step 2:** Add color-coded difficulty badges:
  - <30 = Easy (green)
  - 30-60 = Medium (amber)
  - \>60 = Hard (red)
- **Step 3:** Add CPC column to keyword table with dollar formatting
- **Step 4:** Add "Competition" bar indicator (0.0-1.0 scale)
- **Deliverable:** All 9 tabs show real keyword metrics

### 1.3 Rank change indicators

- **Step 1:** Add a `position_change` column to the keyword table query — compare today's rank vs yesterday's
- **Step 2:** Render colored arrows in the ranking tab:
  - Green ▲ +N = improved N positions
  - Red ▼ -N = dropped N positions
  - Gray — = unchanged
  - Blue ✦ = new (first time ranking)
- **Step 3:** Add a "Winners & Losers" section at the top of the keywords tab — top 5 up movers, top 5 down movers
- **Deliverable:** Every keyword row shows change indicator at a glance

### 1.4 Rank trend sparklines

- **Step 1:** For each keyword, pull last 30 days of rank history
- **Step 2:** Generate a tiny Plotly line chart (200×40px) using `go.Scatter`
- **Step 3:** Embed as inline SVG in the keyword table
- **Alternative:** Use a CSS-based sparkline (pure HTML/CSS, no Plotly overhead)
- **Deliverable:** Every keyword row has a mini trend chart

### 1.5 Rank position heatmap

- **Step 1:** Write a new query: pivot of keyword (rows) × date (columns) × position (value)
- **Step 2:** Render with `go.Heatmap`:
  - Green = position 1-3
  - Amber = 4-10
  - Orange = 11-20
  - Red = 21+
  - Gray = no data
- **Step 3:** Add as a new section in the Rankings tab (collapsible)
- **Deliverable:** 30-day heatmap showing rank movements at a glance

---

## Phase 2: Keyword Discovery Engine (1-2 weeks)

**Your idea — research good keywords before generating articles.**

### 2.1 Seed keyword enrichment

- **Step 1:** Write `scripts/keyword_discovery.py`
  - Takes a seed keyword (e.g., "giant bubbles") + location (NZ/AU)
  - Calls DataForSEO `getKeywordIdeas()` — returns 20+ related keywords with volume/difficulty/CPC
  - Calls `getRelatedKeywords()` — returns "people also search for" terms
  - Deduplicates against existing tracked keywords
  - Saves results to a new `keyword_discoveries` table
- **Step 2:** Add keyword discovery table to DB:
  ```sql
  CREATE TABLE keyword_discoveries (
    id INTEGER PRIMARY KEY,
    domain_id INTEGER REFERENCES domains(id),
    seed_keyword TEXT NOT NULL,
    discovered_keyword TEXT NOT NULL,
    search_volume INTEGER,
    difficulty REAL,
    cpc REAL,
    competition REAL,
    source TEXT,  -- 'keyword_ideas' or 'related_keywords'
    already_tracked INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
  );
  ```
- **Deliverable:** A script that finds 20-100 new keyword opportunities from any seed

### 2.2 Keyword Discovery tab in dashboard

- **Step 1:** Add tab "🔍 Keyword Discovery" in the dashboard nav
- **Step 2:** Show:
  - Input field: enter a seed keyword
  - Dropdown: select location (NZ/AU)
  - Button: "Discover Keywords"
  - Results table: keyword | volume | difficulty | CPC | competition | already tracked (Y/N) | "Add to Tracked" button
- **Step 3:** The "Add to Tracked" button inserts into `keywords` table and triggers an immediate DataForSEO volume/difficulty enrich
- **Deliverable:** Interactive keyword research panel — type a seed, get 20+ suggestions with real metrics

### 2.3 Keyword clustering

- **Step 1:** Write `scripts/keyword_clustering.py`
  - Groups keywords by semantic similarity using DataForSEO Labs `keywords_for_categories` or simple prefix matching
  - Assigns each keyword a `cluster_id` and `cluster_name`
  - Updates `keywords` table with a `cluster` column
- **Step 2:** Add cluster filter to the Rankings tab sidebar
- **Step 3:** Add cluster summary cards:
  - Cluster name | keywords count | avg rank | total volume | avg difficulty | top opportunity
- **Deliverable:** Keywords organized into 8-15 topical clusters with aggregate metrics

### 2.4 Content gap analysis

- **Step 1:** Write `scripts/content_gap_analysis.py`
  - For each keyword cluster, check which top-20 ranking competitors have content
  - Compare against the site's existing content (from `content_ideas` + Shopify blog)
  - Flag keywords where competitors rank but Tinka has no dedicated content
- **Step 2:** "Content Gap" section in the Keyword Discovery tab:
  - Keyword | volume | difficulty | competitor count | your rank (if any) | "Create Content" button
- **Deliverable:** A prioritized list of keywords where content would fill a gap

---

## Phase 3: Competitive Intelligence (1-2 weeks)

**Your domain vs. top 5 competitors on every meaningful metric.**

### 3.1 Competitor identification

- **Step 1:** Write `scripts/identify_competitors.py`
  - For each top-10 ranked keyword, extract the top 5 domains from DataForSEO SERP results
  - Aggregate to find the most frequently appearing competitors
  - Store in a new `competitors` table
- **Step 2:** Competitor table schema:
  ```sql
  CREATE TABLE competitors (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL UNIQUE,
    display_name TEXT,
    first_seen TEXT,
    shared_keyword_count INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1
  );
  ```
- **Deliverable:** 3-10 real competitors identified from live SERP data

### 3.2 Competitive rank comparison

- **Step 1:** Extend `daily_rank_check.py` to also check competitor positions for shared keywords
- **Step 2:** Add "Competitive" tab that shows:
  - Side-by-side table: keyword | your rank | competitor 1 rank | competitor 2 rank | ...
  - Colored cells: green where you're ahead, red where you're behind
  - "Total Wins / Losses" counter
- **Step 3:** Competitive rank trend chart — your position vs. competitors over time
- **Deliverable:** Real competitor comparison, not the current NZ-vs-AU fake

### 3.3 Share of Voice (SOV)

- **Step 1:** Calculate SOV per keyword cluster:
  - For each keyword, estimate traffic = volume × CTR(position)
  - Your traffic share = your est. traffic / total est. traffic for top 10
  - SOV = your traffic / (your traffic + sum(competitor traffic))
- **Step 2:** SOV gauge chart in Competitive tab (`go.Indicator` with gauge mode)
- **Step 3:** SOV breakdown donut chart showing you vs. top 3 competitors
- **Deliverable:** Real SOV metrics — the most executive-friendly SEO metric

### 3.4 Backlink profile

- **Step 1:** Write `scripts/backlink_sync.py`
  - Calls DataForSEO `getBacklinkSummary()` for each domain
  - Calls `getBacklinks()` for top-50 backlinks
  - Calls `getReferringDomains()` for referring domains
  - Stores in new `backlinks` and `backlink_snapshots` tables
- **Step 2:** Backlinks tab:
  - KPI cards: total backlinks | referring domains | dofollow % | domain authority
  - New/lost backlinks chart (last 30 days)
  - Top 10 backlinks by authority table
  - Anchor text distribution word cloud (Plotly word cloud or bar chart)
- **Step 3:** Backlink gap analysis — domains linking to competitors but not to you
- **Deliverable:** Full backlink profile for both domains

---

## Phase 4: Content Pipeline — From Research to Published (1-2 weeks)

**Fix the stalled pipeline — 75 drafts sitting idle.**

### 4.1 Content brief generation

- **Step 1:** Write `scripts/content_brief_generator.py`
  - Takes a target keyword
  - Fetches SERP top 10 for that keyword via DataForSEO
  - Analyzes top pages: avg word count, headings structure, keyword density, readability
  - Generates a content brief (markdown):
    ```
    # Content Brief: [Keyword]
    Target Volume: [volume]
    Difficulty: [difficulty]
    Recommended Word Count: [avg of top 5 + 20%]
    Suggested H2s: [from top 3 articles' headings]
    Target Terms: [related keywords to include]
    SERP Features: [featured snippet? local pack?]
    ```
  - Stores in a new `content_briefs` table
- **Step 2:** "Generate Brief" button on each content idea in the Content Studio tab
- **Deliverable:** One-click content brief generation from live SERP analysis

### 4.2 Content scoring

- **Step 1:** Write `scripts/content_scorer.py`
  - Takes text content + target keyword
  - Scores 0-100 based on:
    - Keyword in title (20 pts)
    - Keyword in H1 (15 pts)
    - Keyword in first 100 words (10 pts)
    - Keyword in meta description (10 pts)
    - Keyword density (1-3% = 15 pts, else sliding scale)
    - Word count relative to top 10 avg (10 pts)
    - Internal links count (10 pts)
    - Readability score (10 pts)
  - Returns a report with specific recommendations
- **Step 2:** "Score Content" button in Content Studio — paste article text, get score + recommendations
- **Deliverable:** Surfer-like content optimization scoring

### 4.3 Pipeline funnel

- **Step 1:** Add `pipeline_stage` column to `content_ideas`:
  - `idea` → `researching` → `briefing` → `writing` → `editing` → `queued` → `published`
- **Step 2:** Pipeline funnel chart in the Content tab:
  - X-axis: stages, Y-axis: count
  - Bars colored from gray (idea) → green (published)
  - Shows exactly where the bottleneck is
- **Step 3:** "Promote" button to move a content idea forward in the pipeline
- **Deliverable:** Visual content pipeline with stage progression

### 4.4 Auto-publish workflow

- **Step 1:** Fix `article_writer.py` — it currently returns `None` when called with `--generate`
  - Debug the OpenRouter API call, fix the response parsing
  - Ensure it outputs valid article JSON
- **Step 2:** Wire the action queue (`process_actions.py`) to actually trigger article generation
- **Step 3:** Add "Publish to Shopify" button that:
  - Generates article via OpenRouter
  - Posts to Shopfiy blog API
  - Updates `published_articles` with shopify_url
  - Updates `content_ideas` pipeline_stage to `published`
- **Deliverable:** Working end-to-end article pipeline — keyword → content → published

---

## Phase 5: Site Health + Technical SEO (1 week)

**Turn your 168 onpage issues into a proactive monitoring system.**

### 5.1 Live crawl integration

- **Step 1:** Write `scripts/live_crawl_check.py`
  - For each domain, crawl top 20 pages (homepage, category pages, product pages, blog)
  - Check: page speed (via requests timing), meta tags, hreflang, schema.org validation
  - Use DataForSEO On-Page API if available, otherwise simple HTTP checks
- **Step 2:** Issue auto-detection:
  - Missing meta descriptions
  - Missing/duplicate title tags
  - Broken internal links (404 check)
  - Missing hreflang (for .co.nz vs .com.au)
  - Schema.org validation (URLs pointing to correct domain)
  - Page load time
- **Step 3:** Store results in `onpage_errors` with `auto_detected=1` flag
- **Deliverable:** Automated weekly crawl detecting technical SEO issues

### 5.2 Site health score

- **Step 1:** Calculate a 0-100 site health score:
  - 40% — open critical issues (penalty: -10 per issue)
  - 30% — open high issues (penalty: -5 per issue)
  - 15% — average page speed
  - 15% — last crawl freshness
- **Step 2:** Render with `go.Indicator` gauge chart — top of the Issues tab
- **Step 3:** Show trend arrow (up/down since last week)
- **Deliverable:** At-a-glance site health metric

### 5.3 Issue resolution tracking

- **Step 1:** Add a "Mark as Fixed" button to each open issue
- **Step 2:** Issue trend chart — new issues vs. resolved issues per week
- **Step 3:** "Time to Fix" average metric
- **Deliverable:** Proactive issue management with resolution tracking

---

## Phase 6: Reports + Automation (1 week)

**Make the dashboard push insights to you, not the other way around.**

### 6.1 Monday morning email digest

- **Step 1:** Write `scripts/weekly_digest.py`
  - Template sections:
    - **Rank Changes:** Top 5 winners, top 5 losers
    - **New Issues:** How many new issues found since last week, top 3 by severity
    - **Content Pipeline:** How many drafts moved forward, how many published
    - **Quick Wins:** 3 keywords ranked 11-20 that are closest to cracking page 1
  - Renders as HTML email (styled inline)
- **Step 2:** Set up cron job — every Monday at 8 AM
- **Step 3:** Send via smtplib or SendGrid
- **Deliverable:** Automated weekly insights email

### 6.2 Export to CSV

- **Step 1:** Add `/api/export/keywords.csv` endpoint
- **Step 2:** Add `/api/export/rank_history.csv` endpoint
- **Step 3:** Add `/api/export/content_ideas.csv` endpoint
- **Step 4:** Add download buttons in the dashboard for each table
- **Deliverable:** One-click CSV export from every data table

### 6.3 PDF snapshot report

- **Step 1:** Write `/api/report/snapshot` endpoint
  - Generates an HTML report (styled, print-friendly)
  - Uses weasyprint or pdfkit to convert to PDF
  - Includes: site health score, top 10 keywords, top 5 movers, issue summary, content pipeline
- **Step 2:** "Download PDF Report" button in Settings tab
- **Deliverable:** One-click PDF report generation

### 6.4 Alert thresholds

- **Step 1:** Add alert configuration:
  - Keyword drops below position 10 (was in top 3)
  - New critical issue detected
  - Site goes down (HTTP 5xx >10% of checks)
- **Step 2:** Alert delivery: email notification + dashboard badge
- **Deliverable:** Proactive alerting for critical changes

---

## Phase 7: Advanced Analytics + AI (2-3 weeks, ongoing)

**The differentiating features that make this better than any off-the-shelf tool.**

### 7.1 AI content suggestions

- **Step 1:** Use existing OpenRouter API (already in `article_writer.py`) to generate content suggestions
- **Step 2:** "AI Suggest" button on the Content tab — given a target keyword, generates:
  - 3 article title options
  - Suggested H2 outline
  - Key points to cover based on SERP analysis
  - Target word count
- **Deliverable:** AI-assisted content planning

### 7.2 SERP feature tracking

- **Step 1:** Switch daily rank check from `/regular` to `/advanced` endpoint
- **Step 2:** Parse additional SERP features:
  - Featured snippet (type=`featured_snippet`)
  - Local pack (type=`local_pack`)
  - People Also Ask (type=`people_also_ask`)
  - Image pack (type=`images`)
  - Shopping results (type=`shopping`)
- **Step 3:** Store in `keyword_serp_features` table
- **Step 4:** "SERP Features" section on each keyword:
  - Badges showing which features are present
  - "You appear in: featured snippet ✅" indicator
- **Deliverable:** Full SERP feature tracking for every keyword

### 7.3 Topical authority scoring

- **Step 1:** Calculate per-cluster topical authority:
  - Formula: 0.35 × Content Coverage + 0.30 × Interlinking Density + 0.35 × Keyword Cluster Coverage
- **Step 2:** Display as a gauge per cluster
- **Step 3:** "Improvement Suggestions" — what to write next to increase authority
- **Deliverable:** Topic-level authority metrics

### 7.4 AI visibility tracking

- **Step 1:** Track whether the brand appears in AI-generated search results:
  - AI Overviews (Google SGE) — check SERP for `ai_overview` type
  - Perplexity, ChatGPT citations — manual check until APIs available
- **Step 2:** "AI Visibility" tab showing where/how the brand appears in AI results
- **Deliverable:** AI search presence monitoring

---

## Cost Estimation Summary

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| DataForSEO rank checks (374/day) | ~$22.50 | $0.002/call × 374 × 30 |
| DataForSEO keyword enrichment (once) | ~$5.00 | One-time, 2-3 calls |
| DataForSEO keyword discovery (weekly) | ~$3.00 | ~50 calls/week |
| DataForSEO SERP advanced (daily) | ~$22.50 | Same volume, $0.002/call |
| DataForSEO backlinks (monthly) | ~$2.00 | One call/month per domain |
| OpenRouter AI (content gen) | ~$10-20 | Already in use |
| Vercel hosting | $0-20 | Hobby or Pro |
| **Total monthly** | **~$55-95** | |

vs. $129/mo (Ahrefs Lite) for fewer features with a dashboard you can't customize.

---

## Implementation Order

The phases are designed in dependency order:
- **Phase 0** first — fix broken foundation, get DataForSEO working
- **Phase 1** second — live rank tracking is the highest-ROI feature
- **Phase 2** third — keyword discovery powers content decisions
- **Phase 3** fourth — competitor data makes everything contextual
- **Phase 4** fifth — content pipeline needs live data to be useful
- **Phase 5** sixth — site health monitoring
- **Phase 6** seventh — reports and automation
- **Phase 7** ongoing — the differentiators

Total: **8-12 weeks** to world-class, with usable improvements shipping every 1-2 weeks.
