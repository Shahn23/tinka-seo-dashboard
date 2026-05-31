-- SEO Dashboard Database Schema
-- 7 tables + 5 views for keyword rankings, on-page errors, and content ideas

-- ── Domains ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS domains (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT    NOT NULL UNIQUE,
    label       TEXT    NOT NULL,
    is_primary  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z')
);

-- ── Keywords ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS keywords (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword             TEXT    NOT NULL,
    domain_id           INTEGER NOT NULL REFERENCES domains(id),
    monthly_volume      INTEGER DEFAULT 0,
    keyword_difficulty  REAL    DEFAULT 0.0,
    cpc                 REAL    DEFAULT 0.0,
    created_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    updated_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    UNIQUE(keyword, domain_id)
);

-- ── Rank History (GSC data) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rank_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id    INTEGER NOT NULL REFERENCES keywords(id),
    domain_id     INTEGER NOT NULL REFERENCES domains(id),
    date          TEXT    NOT NULL,
    position      REAL    DEFAULT NULL,
    clicks        INTEGER DEFAULT 0,
    impressions   INTEGER DEFAULT 0,
    ctr           REAL    DEFAULT 0.0,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    UNIQUE(keyword_id, domain_id, date)
);
CREATE INDEX IF NOT EXISTS idx_rank_history_keyword ON rank_history(keyword_id);
CREATE INDEX IF NOT EXISTS idx_rank_history_date ON rank_history(date);
CREATE INDEX IF NOT EXISTS idx_rank_history_domain ON rank_history(domain_id);

-- ── SEO Issues ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS seo_issues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id     INTEGER NOT NULL REFERENCES domains(id),
    keyword_id    INTEGER REFERENCES keywords(id),
    issue_type    TEXT    NOT NULL,
    severity      TEXT    NOT NULL DEFAULT 'moderate',  -- critical, high, moderate, low, info
    detail        TEXT,
    suggested_fix TEXT,
    status        TEXT    NOT NULL DEFAULT 'open',       -- open, fixed, wontfix, ignored
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    updated_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z')
);
CREATE INDEX IF NOT EXISTS idx_seo_issues_domain ON seo_issues(domain_id);
CREATE INDEX IF NOT EXISTS idx_seo_issues_status ON seo_issues(status);

-- ── Content Ideas ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_ideas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    target_keyword  TEXT    NOT NULL,
    description     TEXT,
    priority        INTEGER DEFAULT 5,       -- 1-10 scale
    source          TEXT    DEFAULT 'manual', -- manual, backlog_csv, api
    effort          TEXT    DEFAULT 'medium', -- low, medium, high
    status          TEXT    NOT NULL DEFAULT 'draft', -- draft, backlog, published, archived
    date_added      TEXT    NOT NULL DEFAULT (date('now')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    UNIQUE(title, target_keyword)
);
CREATE INDEX IF NOT EXISTS idx_content_ideas_priority ON content_ideas(priority);
CREATE INDEX IF NOT EXISTS idx_content_ideas_status ON content_ideas(status);

-- ── On-Page Errors ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onpage_errors (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    url            TEXT    NOT NULL,
    domain_id      INTEGER NOT NULL REFERENCES domains(id),
    error_type     TEXT    NOT NULL,           -- canonical type: broken_link, missing_title, etc.
    severity       TEXT    NOT NULL DEFAULT 'warning', -- critical, warning, info
    detail         TEXT,
    suggested_fix  TEXT,
    status         TEXT    NOT NULL DEFAULT 'open',    -- open, fixed, wontfix, ignored
    discovered_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    check_batch    TEXT,                      -- e.g. 'daily-2026-05-31'
    source         TEXT    DEFAULT 'crawler',  -- crawler, manual, api
    fixed_at       TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    updated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    UNIQUE(url, domain_id, error_type, check_batch)
);
CREATE INDEX IF NOT EXISTS idx_onpage_errors_url ON onpage_errors(url);
CREATE INDEX IF NOT EXISTS idx_onpage_errors_domain_status ON onpage_errors(domain_id, status);
CREATE INDEX IF NOT EXISTS idx_onpage_errors_batch ON onpage_errors(check_batch);

-- ── Sync Log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type       TEXT    NOT NULL,           -- gsc, onpage_crawl, backlog_import
    status          TEXT    NOT NULL DEFAULT 'running', -- running, completed, failed
    rows_processed  INTEGER DEFAULT 0,
    error_detail    TEXT,
    started_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now') || 'Z'),
    completed_at    TEXT
);

-- ── Views ──────────────────────────────────────────────────────────────────

-- Current keyword rankings (latest date per keyword per domain)
CREATE VIEW IF NOT EXISTS v_current_rankings AS
SELECT
    k.id AS keyword_id,
    k.keyword,
    d.id AS domain_id,
    d.url AS domain_url,
    d.label AS domain_label,
    rh.position AS current_position,
    rh.clicks AS total_clicks,
    rh.impressions AS total_impressions,
    rh.ctr,
    k.monthly_volume,
    k.keyword_difficulty,
    -- Opportunity score: lower position + higher volume = higher opportunity
    CASE
        WHEN rh.position IS NULL THEN 10.0
        WHEN rh.position = 0 THEN 10.0
        ELSE ROUND((1.0 - (rh.position / 100.0)) * (k.monthly_volume / 1000.0 + 1.0) * 5.0 + 3.0, 1)
    END AS opportunity_score,
    rh.date AS last_updated
FROM keywords k
JOIN domains d ON k.domain_id = d.id
LEFT JOIN rank_history rh ON rh.keyword_id = k.id
    AND rh.date = (SELECT MAX(rh2.date) FROM rank_history rh2 WHERE rh2.keyword_id = k.id AND rh2.domain_id = d.id);

-- Open SEO issues summary
CREATE VIEW IF NOT EXISTS v_open_issues_summary AS
SELECT
    d.url AS domain,
    d.label AS domain_label,
    si.severity,
    COUNT(*) AS issue_count
FROM seo_issues si
JOIN domains d ON si.domain_id = d.id
WHERE si.status = 'open'
GROUP BY d.url, d.label, si.severity;

-- Top content ideas by opportunity
CREATE VIEW IF NOT EXISTS v_top_content_ideas AS
SELECT
    ci.id,
    ci.title,
    ci.target_keyword,
    COALESCE(k.monthly_volume, 0) AS monthly_volume,
    ci.priority,
    ci.status,
    ci.date_added,
    ci.effort,
    ROUND(
        (ci.priority / 10.0) * (COALESCE(k.monthly_volume, 0) / 1000.0 + 1.0) * 5.0, 1
    ) AS opportunity_score
FROM content_ideas ci
LEFT JOIN keywords k ON k.keyword = ci.target_keyword AND k.domain_id = (SELECT id FROM domains LIMIT 1)
ORDER BY opportunity_score DESC;

-- Open on-page errors summary
CREATE VIEW IF NOT EXISTS v_open_onpage_errors AS
SELECT
    oe.id,
    oe.url,
    d.url AS domain_url,
    d.label AS domain_label,
    oe.error_type,
    oe.severity,
    oe.detail,
    oe.suggested_fix,
    oe.discovered_at,
    oe.check_batch
FROM onpage_errors oe
JOIN domains d ON oe.domain_id = d.id
WHERE oe.status = 'open'
ORDER BY
    CASE oe.severity
        WHEN 'critical' THEN 0
        WHEN 'warning' THEN 1
        WHEN 'info' THEN 2
        ELSE 3
    END,
    oe.discovered_at DESC;

-- Backlog content ideas with keyword rankings
CREATE VIEW IF NOT EXISTS v_backlog_with_rankings AS
SELECT
    ci.id,
    ci.title,
    ci.target_keyword,
    ci.priority,
    ci.status,
    ci.date_added,
    ci.effort,
    k.id AS keyword_id,
    COALESCE(k.monthly_volume, 0) AS monthly_volume,
    COALESCE(k.keyword_difficulty, 0) AS keyword_difficulty,
    vcr.current_position,
    vcr.opportunity_score
FROM content_ideas ci
LEFT JOIN keywords k ON LOWER(k.keyword) = LOWER(ci.target_keyword)
LEFT JOIN v_current_rankings vcr ON vcr.keyword_id = k.id
WHERE ci.status IN ('backlog', 'draft')
ORDER BY ci.priority DESC, vcr.current_position ASC NULLS LAST;
