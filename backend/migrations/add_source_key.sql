-- ============================================================================
-- Migration: source attribution (dual-source: Gomes vs Breakout Investors)
-- ============================================================================
-- Adds a canonical source_key to stocks so two sources coexist per ticker
-- instead of overwriting each other. Backfills from the existing free-text
-- speaker column.
--
-- SAFETY: additive only. Adds one nullable column + one index. No data is
-- deleted or rewritten destructively. Still: BACK UP FIRST, then run against
-- your Neon DB deliberately (this was NOT auto-applied).
--
--   psql "$DATABASE_URL" -f backend/migrations/add_source_key.sql
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS source_key VARCHAR(50);

-- Backfill canonical source from the existing speaker text.
-- Mirrors app/core/sources.py::normalize_source.
UPDATE stocks
SET source_key = CASE
    WHEN speaker ILIKE '%gomes%' OR speaker ILIKE '%money mark%' THEN 'GOMES'
    WHEN speaker ILIKE '%breakout%' THEN 'BREAKOUT_INVESTORS'
    ELSE 'OTHER'
END
WHERE source_key IS NULL;

-- Index the two-source lookups (latest take per ticker per source).
CREATE INDEX IF NOT EXISTS idx_stocks_ticker_source ON stocks (ticker, source_key);
