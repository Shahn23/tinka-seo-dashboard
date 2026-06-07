-- Phase 0.4: DB indexes for query performance
-- Run: sqlite3 data/seo_dashboard.db < migration_001_indexes.sql

-- Keywords: filter by domain, sort by volume/difficulty
CREATE INDEX IF NOT EXISTS idx_kw_domain ON keywords(domain_id);
CREATE INDEX IF NOT EXISTS idx_kw_volume ON keywords(volume DESC);
CREATE INDEX IF NOT EXISTS idx_kw_difficulty ON keywords(difficulty DESC);

-- Rank history: keyword trending, date-range queries
CREATE INDEX IF NOT EXISTS idx_rank_kw_date ON rank_history(keyword_id, date);
CREATE INDEX IF NOT EXISTS idx_rank_date ON rank_history(date);
CREATE INDEX IF NOT EXISTS idx_rank_kw_pos ON rank_history(keyword_id, position);

-- Content pipeline: stage filtering, status queries
CREATE INDEX IF NOT EXISTS idx_ci_status ON content_ideas(status);
CREATE INDEX IF NOT EXISTS idx_ci_domain_status ON content_ideas(domain_id, status);

-- Onpage errors: severity + status filters
CREATE INDEX IF NOT EXISTS idx_oe_severity ON onpage_errors(severity, status);
CREATE INDEX IF NOT EXISTS idx_oe_domain ON onpage_errors(domain_id);

-- Sync log: recent status lookups
CREATE INDEX IF NOT EXISTS idx_sync_source_date ON sync_log(source, started_at DESC);

-- Rank changes: latest rank per keyword
CREATE INDEX IF NOT EXISTS idx_rank_domain_date ON rank_history(keyword_id, date DESC);

.print "All indexes created successfully."
