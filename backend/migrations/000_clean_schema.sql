-- ============================================================================
-- AKCION CLEAN DATABASE SCHEMA
-- Version: 2.0.0
-- Date: 2026-02-01
-- 
-- This is the consolidated schema for a clean start.
-- Run this on an EMPTY database only.
-- ============================================================================

-- ============================================================================
-- 1. STOCKS TABLE - Core Investment Analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS stocks (
    -- Primary Key & Timestamps
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP,
    
    -- Stock Identification
    ticker VARCHAR(20) NOT NULL,
    company_name VARCHAR(200),
    
    -- Source Attribution
    source_type VARCHAR(50),
    speaker VARCHAR(100),
    
    -- Analysis Metadata
    sentiment VARCHAR(50),
    conviction_score INTEGER,
    
    -- Price & Timing
    price_target TEXT,
    time_horizon VARCHAR(100),
    
    -- The Gomes Rules (Core Analysis)
    edge TEXT,
    catalysts TEXT,
    next_catalyst VARCHAR(100),
    risks TEXT,
    raw_notes TEXT,
    
    -- Trading Action Fields
    action_verdict VARCHAR(100),
    entry_zone VARCHAR(200),
    price_target_short VARCHAR(200),
    price_target_long VARCHAR(200),
    stop_loss_risk TEXT,
    moat_rating INTEGER,
    trade_rationale TEXT,
    chart_setup TEXT,
    
    -- Gomes Guardian Master Fields
    asset_class VARCHAR(100),
    cash_runway_months INTEGER,
    insider_ownership_pct FLOAT,
    fully_diluted_market_cap FLOAT,
    enterprise_value FLOAT,
    quarterly_burn_rate FLOAT,
    total_cash FLOAT,
    inflection_status VARCHAR(50),
    primary_catalyst TEXT,
    catalyst_date DATE,
    thesis_narrative TEXT,
    price_floor FLOAT,
    price_target_24m FLOAT,
    current_valuation_stage VARCHAR(50),
    price_base FLOAT,
    price_moon FLOAT,
    forward_pe_2027 FLOAT,
    max_allocation_cap FLOAT,
    stop_loss_price FLOAT,
    insider_activity VARCHAR(50),
    
    -- Price Lines & Trend Analysis
    current_price FLOAT,
    green_line FLOAT,
    red_line FLOAT,
    grey_line FLOAT,
    price_position_pct FLOAT,
    price_zone VARCHAR(50),
    market_cap FLOAT,
    
    -- Trading Zones (Calculated)
    max_buy_price FLOAT,
    start_sell_price FLOAT,
    risk_to_floor_pct FLOAT,
    upside_to_ceiling_pct FLOAT,
    trading_zone_signal VARCHAR(50),
    
    -- Thesis Monitoring
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason VARCHAR(50),
    last_review_requested TIMESTAMP,
    
    -- Version Tracking
    is_latest BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_stocks_ticker ON stocks(ticker);
CREATE INDEX IF NOT EXISTS idx_stocks_is_latest ON stocks(is_latest);
CREATE INDEX IF NOT EXISTS idx_stocks_created_at ON stocks(created_at);

-- ============================================================================
-- 2. PORTFOLIOS TABLE - Multi-Account Management
-- ============================================================================
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP,
    
    name VARCHAR(100) NOT NULL,
    owner VARCHAR(100) NOT NULL,
    broker VARCHAR(50) NOT NULL,
    cash_balance FLOAT DEFAULT 0,
    monthly_contribution FLOAT DEFAULT 0,
    
    UNIQUE(name, owner)
);

-- ============================================================================
-- 3. POSITIONS TABLE - Holdings in Portfolios
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP,
    
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    company_name VARCHAR(200),
    
    shares_count FLOAT NOT NULL DEFAULT 0,
    avg_cost FLOAT NOT NULL DEFAULT 0,
    current_price FLOAT,
    last_price_update TIMESTAMP,
    currency VARCHAR(10) DEFAULT 'USD',
    
    UNIQUE(portfolio_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_positions_portfolio_id ON positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);

-- ============================================================================
-- 4. MARKET STATUS TABLE - Traffic Light System
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_status (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    status VARCHAR(20) NOT NULL DEFAULT 'GREEN',
    note TEXT,
    
    CONSTRAINT valid_status CHECK (status IN ('GREEN', 'YELLOW', 'ORANGE', 'RED'))
);

-- Insert default GREEN status
INSERT INTO market_status (status, note) 
VALUES ('GREEN', 'Market conditions normal - offense mode allowed')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 5. CONVICTION SCORE HISTORY - Track Score Changes Over Time
-- ============================================================================
CREATE TABLE IF NOT EXISTS conviction_score_history (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    ticker VARCHAR(20) NOT NULL,
    conviction_score INTEGER NOT NULL,
    thesis_status VARCHAR(50),
    action_signal VARCHAR(50),
    price_at_analysis FLOAT,
    analysis_source VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_score_history_ticker ON conviction_score_history(ticker);
CREATE INDEX IF NOT EXISTS idx_score_history_created_at ON conviction_score_history(created_at);

-- ============================================================================
-- 6. THESIS DRIFT ALERTS - Monitor Thesis Changes
-- ============================================================================
CREATE TABLE IF NOT EXISTS thesis_drift_alerts (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    ticker VARCHAR(20) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'INFO',
    old_score INTEGER,
    new_score INTEGER,
    price_change_pct FLOAT,
    message TEXT NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_drift_alerts_ticker ON thesis_drift_alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_unack ON thesis_drift_alerts(is_acknowledged) WHERE is_acknowledged = FALSE;

-- ============================================================================
-- 7. INVESTMENT LOGS - Track All Investment Decisions
-- ============================================================================
CREATE TABLE IF NOT EXISTS investment_logs (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    portfolio_id INTEGER REFERENCES portfolios(id),
    ticker VARCHAR(20) NOT NULL,
    log_type VARCHAR(50) NOT NULL,
    amount FLOAT,
    shares FLOAT,
    price FLOAT,
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_investment_logs_ticker ON investment_logs(ticker);
CREATE INDEX IF NOT EXISTS idx_investment_logs_portfolio ON investment_logs(portfolio_id);

-- ============================================================================
-- 8. YAHOO FINANCE CACHE - Smart Price Caching
-- ============================================================================
CREATE TABLE IF NOT EXISTS yahoo_cache (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP,
    
    ticker VARCHAR(20) NOT NULL UNIQUE,
    price FLOAT,
    previous_close FLOAT,
    change_percent FLOAT,
    market_cap FLOAT,
    volume BIGINT,
    avg_volume BIGINT,
    fifty_two_week_high FLOAT,
    fifty_two_week_low FLOAT,
    currency VARCHAR(10),
    exchange VARCHAR(50),
    last_fetched TIMESTAMP NOT NULL,
    fetch_count INTEGER DEFAULT 1,
    error_count INTEGER DEFAULT 0,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_yahoo_cache_ticker ON yahoo_cache(ticker);
CREATE INDEX IF NOT EXISTS idx_yahoo_cache_last_fetched ON yahoo_cache(last_fetched);

-- ============================================================================
-- 9. NOTIFICATIONS TABLE - User Alerts
-- ============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    ticker VARCHAR(20),
    severity VARCHAR(20) DEFAULT 'INFO',
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read) WHERE is_read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_ticker ON notifications(ticker);

-- ============================================================================
-- DONE! Schema ready for Akcion v2.0.0
-- ============================================================================
