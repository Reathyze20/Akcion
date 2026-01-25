-- ==========================================
-- Yahoo Finance Smart Cache
-- ==========================================
-- Purpose: Minimize Yahoo API calls with intelligent caching
-- Author: Gomes Guardian Team
-- Date: 2026-01-25

-- Cache tabulka pro Yahoo Finance data
CREATE TABLE IF NOT EXISTS yahoo_finance_cache (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    
    -- Market Data (denní aktualizace během market hours)
    current_price NUMERIC(12, 4),
    previous_close NUMERIC(12, 4),
    day_low NUMERIC(12, 4),
    day_high NUMERIC(12, 4),
    volume BIGINT,
    
    -- Fundamental Data (týdenní aktualizace)
    market_cap BIGINT,
    pe_ratio NUMERIC(8, 2),
    forward_pe NUMERIC(8, 2),
    pb_ratio NUMERIC(8, 2),
    dividend_yield NUMERIC(6, 4),
    beta NUMERIC(6, 3),
    shares_outstanding BIGINT,
    
    -- Financial Statement Data (čtvrtletní aktualizace)
    revenue_ttm BIGINT,
    net_income_ttm BIGINT,
    operating_margin NUMERIC(6, 4),
    profit_margin NUMERIC(6, 4),
    total_cash BIGINT,
    total_debt BIGINT,
    
    -- Meta informace
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    exchange VARCHAR(20),
    currency VARCHAR(10) DEFAULT 'USD',
    
    -- Cache management
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    market_data_updated TIMESTAMPTZ,     -- Poslední update cenových dat
    fundamental_data_updated TIMESTAMPTZ, -- Poslední update fundamentálních dat
    financial_data_updated TIMESTAMPTZ,   -- Poslední update účetních dat
    
    -- Error tracking
    last_fetch_error TEXT,
    error_count INTEGER DEFAULT 0,
    last_successful_fetch TIMESTAMPTZ,
    
    -- Raw data storage (pro budoucí analýzy)
    raw_data JSONB,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexy pro rychlé vyhledávání
CREATE INDEX IF NOT EXISTS idx_yahoo_cache_ticker ON yahoo_finance_cache (ticker);
CREATE INDEX IF NOT EXISTS idx_yahoo_cache_last_updated ON yahoo_finance_cache (last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_yahoo_cache_market_data_age ON yahoo_finance_cache (market_data_updated DESC) WHERE market_data_updated IS NOT NULL;

-- GIN index pro JSONB dotazy
CREATE INDEX IF NOT EXISTS idx_yahoo_cache_raw_data ON yahoo_finance_cache USING GIN (raw_data);

-- Funkce pro smazání starých dat (starší než 30 dní bez updatu)
CREATE OR REPLACE FUNCTION cleanup_stale_yahoo_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM yahoo_finance_cache
    WHERE last_updated < NOW() - INTERVAL '30 days';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Comments pro dokumentaci
COMMENT ON TABLE yahoo_finance_cache IS 'Smart cache pro Yahoo Finance API - minimalizuje API calls podle Gomes pravidel';
COMMENT ON COLUMN yahoo_finance_cache.market_data_updated IS 'Timestamp posledního update market dat (cena, volume) - aktualizovat každých 15 min během market hours';
COMMENT ON COLUMN yahoo_finance_cache.fundamental_data_updated IS 'Timestamp posledního update fundamentálů (PE, market cap) - aktualizovat max 1x týdně';
COMMENT ON COLUMN yahoo_finance_cache.financial_data_updated IS 'Timestamp posledního update účetních dat (revenue, earnings) - aktualizovat max 1x čtvrtletí';

-- ==========================================
-- Refresh Log Table (Audit trail)
-- ==========================================
CREATE TABLE IF NOT EXISTS yahoo_refresh_log (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    refresh_type VARCHAR(20) NOT NULL CHECK (refresh_type IN ('auto', 'manual', 'scheduled')),
    data_types VARCHAR[] NOT NULL, -- ['market', 'fundamental', 'financial']
    success BOOLEAN NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,
    triggered_by VARCHAR(50), -- 'system', 'user', 'cron'
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_log_ticker ON yahoo_refresh_log (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_log_type ON yahoo_refresh_log (refresh_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_log_created ON yahoo_refresh_log (created_at DESC);

COMMENT ON TABLE yahoo_refresh_log IS 'Audit log všech Yahoo API volání - pro monitoring a debug rate limits';
