-- SEO Dashboard Schema
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    gsc_site_url TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL REFERENCES domains(id),
    keyword TEXT NOT NULL,
    category TEXT,
    intent TEXT CHECK(intent IN ('informational','commercial','transactional','navigational')),
    bid REAL, volume INTEGER DEFAULT 0,
    opportunity_score REAL DEFAULT 5.0,
    difficulty INTEGER DEFAULT 50,
    is_high_priority INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(domain_id, keyword)
);

CREATE TABLE IF NOT EXISTS rank_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    date TEXT NOT NULL, position REAL DEFAULT 0,
    clicks INTEGER DEFAULT 0, impressions INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0,
    UNIQUE(keyword_id, date)
);

CREATE TABLE IF NOT EXISTS onpage_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL REFERENCES domains(id),
    error_type TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('critical','high','moderate','low')) DEFAULT 'moderate',
    page_url TEXT, description TEXT, suggestion TEXT,
    status TEXT CHECK(status IN ('open','in_progress','fixed')) DEFAULT 'open',
    batch_id TEXT, created_at TEXT DEFAULT (datetime('now')), fixed_at TEXT
);

CREATE TABLE IF NOT EXISTS content_ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, target_keyword TEXT, category TEXT,
    estimated_searches INTEGER DEFAULT 0, opportunity_score REAL DEFAULT 5.0,
    effort TEXT CHECK(effort IN ('easy','medium','hard')) DEFAULT 'medium',
    content_type TEXT, outline TEXT, source TEXT DEFAULT 'seed',
    status TEXT DEFAULT 'draft', created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL, status TEXT CHECK(status IN ('running','success','failed')) DEFAULT 'running',
    rows_synced INTEGER DEFAULT 0, started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT, error TEXT
);

CREATE VIEW IF NOT EXISTS v_keywords_with_latest AS
SELECT k.id AS keyword_id, d.name AS domain, k.keyword, k.category, k.intent,
       k.volume, k.opportunity_score, k.difficulty, k.is_high_priority,
       rh.position AS current_position, rh.clicks AS last_7d_clicks,
       rh.impressions AS last_7d_impressions, rh.date AS last_updated
FROM keywords k JOIN domains d ON k.domain_id = d.id
LEFT JOIN (SELECT keyword_id, position, clicks, impressions, date
    FROM rank_history WHERE (keyword_id, date) IN
    (SELECT keyword_id, MAX(date) FROM rank_history GROUP BY keyword_id)) rh ON k.id = rh.keyword_id;

CREATE VIEW IF NOT EXISTS v_open_onpage_errors AS
SELECT d.name AS domain, e.error_type, e.severity, e.page_url, e.description, e.suggestion, e.created_at
FROM onpage_errors e JOIN domains d ON e.domain_id = d.id WHERE e.status = 'open'
ORDER BY CASE e.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END;

CREATE VIEW IF NOT EXISTS v_backlog_with_rankings AS
SELECT ci.id AS idea_id, ci.title, ci.target_keyword, ci.category, ci.estimated_searches,
       ci.opportunity_score, ci.effort, ci.status, kw.current_position, kw.domain
FROM content_ideas ci LEFT JOIN v_keywords_with_latest kw ON LOWER(ci.target_keyword) = LOWER(kw.keyword);
