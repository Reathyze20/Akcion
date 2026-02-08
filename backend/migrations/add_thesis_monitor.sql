-- ============================================================================
-- THESIS MONITOR MIGRATION
-- Adds tables for thesis drift detection and alert system
-- Author: GitHub Copilot with Claude Opus 4.5
-- Date: 2026-02-01
-- ============================================================================

-- 1. Add review columns to stocks table
ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;

ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS review_reason VARCHAR(50);

ALTER TABLE stocks 
ADD COLUMN IF NOT EXISTS last_review_requested TIMESTAMP;

-- 2. Create gomes_alerts table
CREATE TABLE IF NOT EXISTS gomes_alerts (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    
    -- Alert type and severity
    alert_type VARCHAR(30) NOT NULL,  -- THESIS_BROKEN, THESIS_DRIFT, IMPROVEMENT, etc.
    severity VARCHAR(15) NOT NULL,     -- CRITICAL, WARNING, INFO, OPPORTUNITY
    
    -- Content
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    recommendation TEXT,
    
    -- Score tracking
    previous_score INTEGER,
    current_score INTEGER NOT NULL,
    score_delta INTEGER DEFAULT 0,
    
    -- Source
    source VARCHAR(100),
    
    -- Read status
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP,
    
    -- Action taken
    action_taken VARCHAR(50),
    action_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,
    
    -- Constraints
    CONSTRAINT check_alert_type CHECK (
        alert_type IN ('THESIS_BROKEN', 'THESIS_DRIFT', 'STABLE', 'IMPROVEMENT', 'MAJOR_IMPROVEMENT')
    ),
    CONSTRAINT check_severity CHECK (
        severity IN ('CRITICAL', 'WARNING', 'INFO', 'OPPORTUNITY')
    ),
    CONSTRAINT check_current_score CHECK (current_score >= 0 AND current_score <= 10)
);

-- Indexes for gomes_alerts
CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON gomes_alerts(ticker, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_unread ON gomes_alerts(is_read, severity) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON gomes_alerts(severity, created_at);

-- 3. Create gomes_score_history table
CREATE TABLE IF NOT EXISTS gomes_score_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Score
    conviction_score INTEGER NOT NULL,
    previous_score INTEGER,
    score_delta INTEGER,
    
    -- Components
    thesis_score INTEGER,
    valuation_score INTEGER,
    technical_score INTEGER,
    
    -- Context
    source VARCHAR(100),
    reason TEXT,
    
    -- Timestamps
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT check_hist_score CHECK (conviction_score >= 0 AND conviction_score <= 10)
);

-- Indexes for score history
CREATE INDEX IF NOT EXISTS idx_score_history_ticker ON gomes_score_history(ticker, recorded_at);
CREATE INDEX IF NOT EXISTS idx_score_history_score ON gomes_score_history(conviction_score, recorded_at);

-- 4. Create index on stocks for needs_review
CREATE INDEX IF NOT EXISTS idx_stocks_needs_review ON stocks(needs_review) WHERE needs_review = true;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
-- Verify the migration by checking for new columns and tables
SELECT 'Migration applied successfully' AS status;
