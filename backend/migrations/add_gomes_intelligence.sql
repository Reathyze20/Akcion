-- Gomes Intelligence Module - Database Migration
-- Adds Gomes-specific tables for investment gatekeeping
-- Author: GitHub Copilot with Claude Opus 4.5
-- Date: 2026-01-17

-- ============================================================================
-- 1. MARKET ALERT SYSTEM (Semafor / Traffic Light)
-- ============================================================================

CREATE TABLE IF NOT EXISTS market_alerts (
    id SERIAL PRIMARY KEY,
    alert_level VARCHAR(10) NOT NULL CHECK (alert_level IN ('GREEN', 'YELLOW', 'ORANGE', 'RED')),
    
    -- Allocation percentages
    stocks_pct NUMERIC(5, 2) NOT NULL DEFAULT 100.00 CHECK (stocks_pct >= 0 AND stocks_pct <= 100),
    cash_pct NUMERIC(5, 2) NOT NULL DEFAULT 0.00 CHECK (cash_pct >= 0 AND cash_pct <= 100),
    hedge_pct NUMERIC(5, 2) NOT NULL DEFAULT 0.00 CHECK (hedge_pct >= 0 AND hedge_pct <= 100),
    
    -- Metadata
    reason TEXT,
    source VARCHAR(100), -- 'transcript', 'manual', 'system'
    transcript_id INTEGER REFERENCES analyst_transcripts(id) ON DELETE SET NULL,
    
    -- Timestamps
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_until TIMESTAMPTZ, -- NULL = still active
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'system',
    
    -- Ensure percentages sum to 100
    CONSTRAINT check_allocation_sum CHECK (stocks_pct + cash_pct + hedge_pct = 100.00)
);

CREATE INDEX IF NOT EXISTS idx_market_alerts_active ON market_alerts (effective_from DESC) WHERE effective_until IS NULL;
CREATE INDEX IF NOT EXISTS idx_market_alerts_level ON market_alerts (alert_level, effective_from DESC);

-- ============================================================================
-- 2. STOCK LIFECYCLE PHASES (Great Find / Wait Time / Gold Mine)
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_lifecycle (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Lifecycle phase
    phase VARCHAR(20) NOT NULL CHECK (phase IN ('GREAT_FIND', 'WAIT_TIME', 'GOLD_MINE', 'UNKNOWN')),
    
    -- Phase indicators
    is_investable BOOLEAN NOT NULL DEFAULT TRUE, -- FALSE for WAIT_TIME
    firing_on_all_cylinders BOOLEAN, -- NULL = unknown
    cylinders_count INTEGER CHECK (cylinders_count >= 0 AND cylinders_count <= 10),
    
    -- Detection signals
    phase_signals JSONB, -- {"delays": true, "profitable": false, ...}
    phase_reasoning TEXT,
    
    -- Confidence
    confidence VARCHAR(10) CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    
    -- Source
    source VARCHAR(100), -- 'transcript', 'manual', 'ai_analysis'
    transcript_id INTEGER REFERENCES analyst_transcripts(id) ON DELETE SET NULL,
    
    -- Timestamps
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ, -- NULL = still valid
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint per ticker (only one active phase per ticker)
    CONSTRAINT unique_active_phase UNIQUE (ticker) WHERE valid_until IS NULL
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_ticker ON stock_lifecycle (ticker, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_phase ON stock_lifecycle (phase, is_investable);
CREATE INDEX IF NOT EXISTS idx_lifecycle_active ON stock_lifecycle (ticker) WHERE valid_until IS NULL;

-- ============================================================================
-- 3. PRICE LINES (Green Line / Red Line / Grey Line)
-- ============================================================================

CREATE TABLE IF NOT EXISTS price_lines (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Price targets
    green_line NUMERIC(12, 4), -- Buy zone (undervalued)
    red_line NUMERIC(12, 4),   -- Sell zone (fair/overvalued)
    grey_line NUMERIC(12, 4),  -- Neutral zone (if mentioned)
    
    -- Current context
    current_price NUMERIC(12, 4),
    is_undervalued BOOLEAN, -- TRUE if current < green_line
    is_overvalued BOOLEAN,  -- TRUE if current > red_line
    
    -- Score impact
    gomes_score_at_green INTEGER CHECK (gomes_score_at_green >= 0 AND gomes_score_at_green <= 10),
    gomes_score_at_red INTEGER CHECK (gomes_score_at_red >= 0 AND gomes_score_at_red <= 10),
    
    -- Source
    source VARCHAR(100), -- 'transcript', 'image', 'manual'
    source_reference TEXT, -- transcript quote or image filename
    transcript_id INTEGER REFERENCES analyst_transcripts(id) ON DELETE SET NULL,
    image_path TEXT, -- Path to screenshot with lines
    
    -- Timestamps
    effective_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ, -- NULL = still valid
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_price_lines_ticker ON price_lines (ticker, effective_from DESC);
CREATE INDEX IF NOT EXISTS idx_price_lines_active ON price_lines (ticker) WHERE valid_until IS NULL;
CREATE INDEX IF NOT EXISTS idx_price_lines_undervalued ON price_lines (is_undervalued, ticker) WHERE valid_until IS NULL;

-- ============================================================================
-- 4. POSITION SIZING TIERS (Primary / Secondary / Tertiary)
-- ============================================================================

CREATE TABLE IF NOT EXISTS position_tiers (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Position tier
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('PRIMARY', 'SECONDARY', 'TERTIARY')),
    
    -- Size limits
    max_portfolio_pct NUMERIC(5, 2) NOT NULL CHECK (max_portfolio_pct > 0 AND max_portfolio_pct <= 20),
    recommended_pct NUMERIC(5, 2) CHECK (recommended_pct > 0 AND recommended_pct <= 20),
    
    -- Constraints
    allowed_in_yellow_alert BOOLEAN NOT NULL DEFAULT TRUE,
    allowed_in_orange_alert BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_in_red_alert BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Reasoning
    tier_reasoning TEXT,
    
    -- Source
    source VARCHAR(100),
    transcript_id INTEGER REFERENCES analyst_transcripts(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_position_tiers_ticker ON position_tiers (ticker);
CREATE INDEX IF NOT EXISTS idx_position_tiers_tier ON position_tiers (tier, max_portfolio_pct);

-- ============================================================================
-- 5. INVESTMENT VERDICTS (Final Combined Decision)
-- ============================================================================

CREATE TABLE IF NOT EXISTS investment_verdicts (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    
    -- Final verdict
    verdict VARCHAR(20) NOT NULL CHECK (verdict IN (
        'STRONG_BUY', 'BUY', 'ACCUMULATE', 'HOLD', 
        'TRIM', 'SELL', 'AVOID', 'BLOCKED'
    )),
    
    -- Gatekeeper checks
    passed_gomes_filter BOOLEAN NOT NULL,
    blocked_reason TEXT, -- If blocked, why?
    
    -- Component scores
    gomes_score INTEGER CHECK (gomes_score >= 0 AND gomes_score <= 10),
    ml_prediction_score NUMERIC(5, 2), -- 0-100%
    ml_prediction_direction VARCHAR(10), -- UP, DOWN, NEUTRAL
    
    -- Lifecycle
    lifecycle_phase VARCHAR(20),
    lifecycle_investable BOOLEAN,
    
    -- Market context
    market_alert_level VARCHAR(10),
    position_tier VARCHAR(20),
    max_position_size NUMERIC(5, 2),
    
    -- Price context
    current_price NUMERIC(12, 4),
    green_line NUMERIC(12, 4),
    red_line NUMERIC(12, 4),
    price_vs_green_pct NUMERIC(8, 2), -- % above/below green line
    
    -- Risk factors (JSONB array)
    risk_factors JSONB DEFAULT '[]'::JSONB,
    
    -- Bull/Bear case
    bull_case TEXT,
    bear_case TEXT,
    
    -- Catalyst info
    has_catalyst BOOLEAN,
    catalyst_type VARCHAR(50),
    catalyst_description TEXT,
    
    -- Earnings risk
    days_to_earnings INTEGER,
    earnings_blocked BOOLEAN DEFAULT FALSE,
    
    -- Source synthesis
    data_sources JSONB DEFAULT '{}'::JSONB, -- {"transcript": true, "ml": true, "swot": false}
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ, -- NULL = current verdict
    
    -- Confidence
    confidence VARCHAR(10) CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW'))
);

CREATE INDEX IF NOT EXISTS idx_verdicts_ticker ON investment_verdicts (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verdicts_active ON investment_verdicts (ticker) WHERE valid_until IS NULL;
CREATE INDEX IF NOT EXISTS idx_verdicts_verdict ON investment_verdicts (verdict, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verdicts_blocked ON investment_verdicts (passed_gomes_filter, verdict) WHERE valid_until IS NULL;

-- ============================================================================
-- 6. IMAGE ANALYSIS LOG (For line extraction from screenshots)
-- ============================================================================

CREATE TABLE IF NOT EXISTS image_analysis_log (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    image_path TEXT NOT NULL,
    
    -- Extracted data
    extracted_green_line NUMERIC(12, 4),
    extracted_red_line NUMERIC(12, 4),
    extracted_grey_line NUMERIC(12, 4),
    extracted_current_price NUMERIC(12, 4),
    
    -- Analysis metadata
    analysis_method VARCHAR(50), -- 'manual', 'ocr', 'vision_ai'
    confidence_score NUMERIC(3, 2),
    raw_extraction_data JSONB,
    
    -- Status
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'verified')),
    verified_by VARCHAR(100),
    verified_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_image_analysis_ticker ON image_analysis_log (ticker);
CREATE INDEX IF NOT EXISTS idx_image_analysis_status ON image_analysis_log (status);

-- ============================================================================
-- 7. GOMES RULES LOG (Audit trail for rule applications)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gomes_rules_log (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    verdict_id INTEGER REFERENCES investment_verdicts(id) ON DELETE CASCADE,
    
    -- Rule application
    rule_name VARCHAR(100) NOT NULL, -- 'earnings_14_day', 'wait_time_block', 'market_alert_constraint'
    rule_result VARCHAR(20) NOT NULL, -- 'PASSED', 'BLOCKED', 'WARNING', 'ADJUSTED'
    rule_impact TEXT, -- What changed due to this rule
    
    -- Context
    rule_input JSONB, -- Input data used for rule evaluation
    
    -- Timestamps
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rules_log_ticker ON gomes_rules_log (ticker, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_rules_log_verdict ON gomes_rules_log (verdict_id);
CREATE INDEX IF NOT EXISTS idx_rules_log_rule ON gomes_rules_log (rule_name, rule_result);

-- ============================================================================
-- 8. ADD GOMES COLUMNS TO EXISTING TABLES
-- ============================================================================

-- Add lifecycle fields to stocks table
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS lifecycle_phase VARCHAR(20);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS is_gomes_investable BOOLEAN DEFAULT TRUE;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS green_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS red_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS grey_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS position_tier VARCHAR(20);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS image_path TEXT;

-- Add gomes fields to active_watchlist
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS gomes_score NUMERIC(4, 2);
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS investment_thesis TEXT;
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS risks TEXT;
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS lifecycle_phase VARCHAR(20);
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS green_line NUMERIC(12, 4);
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS red_line NUMERIC(12, 4);
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS position_tier VARCHAR(20);
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS is_gomes_blocked BOOLEAN DEFAULT FALSE;
ALTER TABLE active_watchlist ADD COLUMN IF NOT EXISTS blocked_reason TEXT;

-- ============================================================================
-- 9. INSERT DEFAULT MARKET ALERT (GREEN)
-- ============================================================================

INSERT INTO market_alerts (alert_level, stocks_pct, cash_pct, hedge_pct, reason, source)
VALUES ('GREEN', 100.00, 0.00, 0.00, 'Default initial state - all systems go', 'system')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 10. VIEWS FOR QUICK ACCESS
-- ============================================================================

-- Current market alert view
CREATE OR REPLACE VIEW current_market_alert AS
SELECT *
FROM market_alerts
WHERE effective_until IS NULL
ORDER BY effective_from DESC
LIMIT 1;

-- Investable stocks view (passes all Gomes filters)
CREATE OR REPLACE VIEW gomes_investable_stocks AS
SELECT 
    s.id,
    s.ticker,
    s.company_name,
    s.gomes_score,
    s.lifecycle_phase,
    s.green_line,
    s.red_line,
    s.position_tier,
    sl.is_investable,
    sl.firing_on_all_cylinders,
    ma.alert_level as market_alert
FROM stocks s
LEFT JOIN stock_lifecycle sl ON s.ticker = sl.ticker AND sl.valid_until IS NULL
LEFT JOIN market_alerts ma ON ma.effective_until IS NULL
WHERE s.is_latest = TRUE
  AND (sl.is_investable IS NULL OR sl.is_investable = TRUE)
  AND s.gomes_score >= 5;

-- Blocked stocks view (failed Gomes filter)
CREATE OR REPLACE VIEW gomes_blocked_stocks AS
SELECT 
    s.id,
    s.ticker,
    s.company_name,
    sl.phase as lifecycle_phase,
    sl.phase_reasoning as blocked_reason,
    sl.detected_at
FROM stocks s
JOIN stock_lifecycle sl ON s.ticker = sl.ticker AND sl.valid_until IS NULL
WHERE s.is_latest = TRUE
  AND sl.is_investable = FALSE;

-- ============================================================================
-- DONE
-- ============================================================================
