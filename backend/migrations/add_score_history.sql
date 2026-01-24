-- Migration: Add Gomes Score History Table
-- Purpose: Track score evolution for Thesis Drift detection
-- Date: 2026-01-24

-- Score History Table
CREATE TABLE IF NOT EXISTS gomes_score_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Score data
    gomes_score INTEGER NOT NULL CHECK (gomes_score >= 0 AND gomes_score <= 10),
    thesis_status VARCHAR(20) CHECK (thesis_status IN ('IMPROVED', 'STABLE', 'DETERIORATED', 'BROKEN')),
    action_signal VARCHAR(20),
    
    -- Context
    price_at_analysis NUMERIC(12, 4),
    analysis_source VARCHAR(100),  -- 'deep_dd', 'transcript', 'manual'
    
    -- Timestamps
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT valid_score UNIQUE (ticker, recorded_at)
);

CREATE INDEX idx_score_history_ticker ON gomes_score_history(ticker);
CREATE INDEX idx_score_history_recorded_at ON gomes_score_history(recorded_at);
CREATE INDEX idx_score_history_ticker_time ON gomes_score_history(ticker, recorded_at DESC);

-- Thesis Drift Alerts Table
CREATE TABLE IF NOT EXISTS thesis_drift_alerts (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    
    -- Alert data
    alert_type VARCHAR(50) NOT NULL,  -- 'HYPE_AHEAD_OF_FUNDAMENTALS', 'THESIS_BREAKING', 'ACCUMULATE_SIGNAL'
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    
    -- Context
    old_score INTEGER,
    new_score INTEGER,
    price_change_pct NUMERIC(8, 2),  -- Price change since last analysis
    message TEXT NOT NULL,
    
    -- Status
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_drift_alerts_ticker ON thesis_drift_alerts(ticker);
CREATE INDEX idx_drift_alerts_unacked ON thesis_drift_alerts(is_acknowledged) WHERE is_acknowledged = FALSE;

COMMENT ON TABLE gomes_score_history IS 'Historical record of Gomes scores for thesis drift analysis';
COMMENT ON TABLE thesis_drift_alerts IS 'Alerts generated when thesis drift is detected';
