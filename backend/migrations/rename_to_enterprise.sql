-- Migration: Rename Gomes to Enterprise naming convention
-- Purpose: Align database with enterprise application naming
-- Date: 2026-01-31
-- WARNING: This will DROP and recreate tables - data will be lost!

-- ============================================================================
-- DROP OLD TABLES (with CASCADE to remove dependencies)
-- ============================================================================

DROP TABLE IF EXISTS gomes_score_history CASCADE;
DROP TABLE IF EXISTS thesis_drift_alerts CASCADE;
DROP TABLE IF EXISTS gomes_rules_log CASCADE;

-- Also drop index if exists
DROP INDEX IF EXISTS idx_score_history_ticker;
DROP INDEX IF EXISTS idx_score_history_recorded_at;
DROP INDEX IF EXISTS idx_score_history_ticker_time;

-- ============================================================================
-- CREATE NEW TABLES WITH ENTERPRISE NAMING
-- ============================================================================

-- Conviction Score History (formerly gomes_score_history)
CREATE TABLE IF NOT EXISTS conviction_score_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Score data (renamed from gomes_score)
    conviction_score INTEGER NOT NULL CHECK (conviction_score >= 0 AND conviction_score <= 10),
    thesis_status VARCHAR(20) CHECK (thesis_status IN ('IMPROVED', 'STABLE', 'DETERIORATED', 'BROKEN')),
    action_signal VARCHAR(20),
    
    -- Context
    price_at_analysis NUMERIC(12, 4),
    analysis_source VARCHAR(100),
    
    -- Timestamps
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for conviction_score_history
CREATE INDEX idx_conviction_score_history_ticker ON conviction_score_history(ticker);
CREATE INDEX idx_conviction_score_history_recorded_at ON conviction_score_history(recorded_at);
CREATE INDEX idx_conviction_score_history_ticker_time ON conviction_score_history(ticker, recorded_at DESC);

-- Thesis Drift Alerts (same name, just recreate clean)
CREATE TABLE IF NOT EXISTS thesis_drift_alerts (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    
    -- Alert data
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    
    -- Context
    old_score INTEGER,
    new_score INTEGER,
    price_change_pct NUMERIC(8, 2),
    message TEXT NOT NULL,
    
    -- Status
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_thesis_drift_alerts_ticker ON thesis_drift_alerts(ticker);
CREATE INDEX idx_thesis_drift_alerts_created ON thesis_drift_alerts(created_at);

-- Investment Rules Log (formerly gomes_rules_log)
CREATE TABLE IF NOT EXISTS investment_rules_log (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    rule_passed BOOLEAN NOT NULL,
    reason TEXT,
    context JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investment_rules_log_ticker ON investment_rules_log(ticker);
CREATE INDEX idx_investment_rules_log_created ON investment_rules_log(created_at);

-- ============================================================================
-- RENAME COLUMN IN stocks TABLE (gomes_score -> conviction_score)
-- ============================================================================

-- Check if gomes_score column exists and rename it (skip if already done)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'stocks' AND column_name = 'gomes_score') THEN
        -- Drop the old column if conviction_score already exists
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'stocks' AND column_name = 'conviction_score') THEN
            ALTER TABLE stocks DROP COLUMN gomes_score;
            RAISE NOTICE 'Dropped old stocks.gomes_score column (conviction_score already exists)';
        ELSE
            ALTER TABLE stocks RENAME COLUMN gomes_score TO conviction_score;
            RAISE NOTICE 'Renamed stocks.gomes_score to conviction_score';
        END IF;
    ELSE
        RAISE NOTICE 'Column stocks.gomes_score not found - already migrated';
    END IF;
END $$;

-- ============================================================================
-- ADD COMMENTS
-- ============================================================================

COMMENT ON TABLE conviction_score_history IS 'Historical record of Conviction Scores for thesis drift analysis';
COMMENT ON TABLE thesis_drift_alerts IS 'Alerts generated when price/score divergence detected';
COMMENT ON TABLE investment_rules_log IS 'Log of investment rule evaluations';

COMMENT ON COLUMN conviction_score_history.conviction_score IS 'Investment thesis strength score (0-10)';
COMMENT ON COLUMN stocks.conviction_score IS 'Current investment thesis strength score (0-10)';

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Show all tables with 'conviction' or 'investment' in name
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND (table_name LIKE '%conviction%' OR table_name LIKE '%investment%' OR table_name LIKE '%thesis%')
ORDER BY table_name;
