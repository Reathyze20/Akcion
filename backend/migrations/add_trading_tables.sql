-- Trading Intelligence Module - Database Migration
-- Create tables for ML-driven trading (PostgreSQL compatible)

-- 1. OHLCV Time Series Data
CREATE TABLE IF NOT EXISTS ohlcv_data (
    id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    open NUMERIC(12, 4) NOT NULL,
    high NUMERIC(12, 4) NOT NULL,
    low NUMERIC(12, 4) NOT NULL,
    close NUMERIC(12, 4) NOT NULL,
    volume BIGINT NOT NULL,
    vwap NUMERIC(12, 4),
    UNIQUE (time, ticker)
);

-- Create indexes for fast ticker lookups
CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_time ON ohlcv_data (ticker, time DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_time ON ohlcv_data (time DESC);

-- 2. Active Watchlist (tickers from analyst recommendations)
CREATE TABLE IF NOT EXISTS active_watchlist (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) UNIQUE NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    action_verdict VARCHAR(20),
    confidence_score NUMERIC(3, 2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_watchlist_active ON active_watchlist (is_active, last_updated DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON active_watchlist (ticker);

-- 3. ML Predictions (output from PatchTST model)
CREATE TABLE IF NOT EXISTS ml_predictions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    prediction_type VARCHAR(10) NOT NULL CHECK (prediction_type IN ('UP', 'DOWN', 'NEUTRAL')),
    confidence NUMERIC(5, 4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    predicted_price NUMERIC(12, 4) NOT NULL,
    current_price NUMERIC(12, 4) NOT NULL,
    kelly_position_size NUMERIC(5, 4) CHECK (kelly_position_size >= 0 AND kelly_position_size <= 1),
    model_version VARCHAR(50),
    horizon_days INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE SET NULL,
    watchlist_id INTEGER REFERENCES active_watchlist(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_predictions_ticker_time ON ml_predictions (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_valid ON ml_predictions (ticker, valid_until);
CREATE INDEX IF NOT EXISTS idx_predictions_type ON ml_predictions (prediction_type, created_at DESC);

-- 4. Trading Signals (final actionable output)
CREATE TABLE IF NOT EXISTS trading_signals (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    signal_type VARCHAR(10) NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    ml_prediction_id INTEGER REFERENCES ml_predictions(id) ON DELETE SET NULL,
    analyst_source_id INTEGER REFERENCES stocks(id) ON DELETE SET NULL,
    confidence NUMERIC(5, 4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    kelly_size NUMERIC(5, 4) NOT NULL CHECK (kelly_size >= 0 AND kelly_size <= 1),
    entry_price NUMERIC(12, 4),
    target_price NUMERIC(12, 4),
    stop_loss NUMERIC(12, 4),
    risk_reward_ratio NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    executed BOOLEAN DEFAULT FALSE,
    execution_price NUMERIC(12, 4),
    execution_time TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_active ON trading_signals (ticker, is_active, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_type ON trading_signals (signal_type, is_active);
CREATE INDEX IF NOT EXISTS idx_signals_expires ON trading_signals (expires_at);

-- 5. Model Performance Tracking
CREATE TABLE IF NOT EXISTS model_performance (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    prediction_id INTEGER REFERENCES ml_predictions(id) ON DELETE CASCADE,
    predicted_direction VARCHAR(10),
    actual_direction VARCHAR(10),
    predicted_price NUMERIC(12, 4),
    actual_price NUMERIC(12, 4),
    accuracy NUMERIC(5, 4),
    prediction_date DATE NOT NULL,
    evaluation_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_ticker ON model_performance (ticker, evaluation_date DESC);
CREATE INDEX IF NOT EXISTS idx_performance_accuracy ON model_performance (accuracy DESC);

-- 6. Data Sync Log (track background job status)
CREATE TABLE IF NOT EXISTS data_sync_log (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    sync_type VARCHAR(20) NOT NULL, -- 'daily', 'manual', 'initial'
    records_synced INTEGER DEFAULT 0,
    from_date DATE,
    to_date DATE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed', 'partial')),
    error_message TEXT,
    duration_seconds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_log_ticker ON data_sync_log (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON data_sync_log (status, created_at DESC);

-- 8. Views for easier querying

-- Active signals with analyst context
CREATE OR REPLACE VIEW v_active_signals AS
SELECT 
    ts.id,
    ts.ticker,
    ts.signal_type,
    ts.confidence,
    ts.kelly_size,
    ts.entry_price,
    ts.target_price,
    ts.stop_loss,
    ts.risk_reward_ratio,
    mp.prediction_type as ml_prediction,
    mp.predicted_price,
    s.action_verdict as analyst_verdict,
    s.sentiment as analyst_sentiment,
    s.company_name,
    ts.created_at,
    ts.expires_at
FROM trading_signals ts
LEFT JOIN ml_predictions mp ON ts.ml_prediction_id = mp.id
LEFT JOIN stocks s ON ts.analyst_source_id = s.id
WHERE ts.is_active = TRUE
ORDER BY ts.created_at DESC;

-- Watchlist with latest predictions
CREATE OR REPLACE VIEW v_watchlist_signals AS
SELECT 
    aw.ticker,
    aw.action_verdict,
    aw.confidence_score,
    aw.last_updated,
    mp.prediction_type,
    mp.confidence as ml_confidence,
    mp.predicted_price,
    mp.current_price,
    mp.kelly_position_size,
    mp.created_at as prediction_time
FROM active_watchlist aw
LEFT JOIN LATERAL (
    SELECT * FROM ml_predictions
    WHERE ticker = aw.ticker
    ORDER BY created_at DESC
    LIMIT 1
) mp ON TRUE
WHERE aw.is_active = TRUE
ORDER BY mp.kelly_position_size DESC NULLS LAST;

-- Model accuracy by ticker
CREATE OR REPLACE VIEW v_model_accuracy AS
SELECT 
    ticker,
    model_version,
    COUNT(*) as total_predictions,
    AVG(accuracy) as avg_accuracy,
    MIN(accuracy) as min_accuracy,
    MAX(accuracy) as max_accuracy,
    MAX(evaluation_date) as last_evaluation
FROM model_performance
GROUP BY ticker, model_version
ORDER BY avg_accuracy DESC;

-- 9. Functions

-- Function to automatically expire old signals
CREATE OR REPLACE FUNCTION expire_old_signals()
RETURNS void AS $$
BEGIN
    UPDATE trading_signals
    SET is_active = FALSE
    WHERE is_active = TRUE
    AND (
        expires_at < NOW() OR
        created_at < NOW() - INTERVAL '7 days'
    );
END;
$$ LANGUAGE plpgsql;

-- Function to calculate signal accuracy
CREATE OR REPLACE FUNCTION calculate_signal_accuracy()
RETURNS TABLE(
    ticker VARCHAR,
    total_signals BIGINT,
    correct_predictions BIGINT,
    accuracy NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        mp.ticker,
        COUNT(*)::BIGINT as total_signals,
        SUM(CASE WHEN perf.accuracy > 0.5 THEN 1 ELSE 0 END)::BIGINT as correct_predictions,
        ROUND(AVG(perf.accuracy), 4) as accuracy
    FROM ml_predictions mp
    LEFT JOIN model_performance perf ON mp.id = perf.prediction_id
    WHERE mp.created_at > NOW() - INTERVAL '90 days'
    GROUP BY mp.ticker
    HAVING COUNT(*) >= 5
    ORDER BY accuracy DESC;
END;
$$ LANGUAGE plpgsql;

-- 7. Triggers

-- Auto-update last_updated on watchlist
CREATE OR REPLACE FUNCTION update_watchlist_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_watchlist_update
BEFORE UPDATE ON active_watchlist
FOR EACH ROW
EXECUTE FUNCTION update_watchlist_timestamp();

-- 8. Initial data
-- Populate watchlist from existing stocks with BUY verdict
INSERT INTO active_watchlist (ticker, stock_id, action_verdict, confidence_score)
SELECT 
    ticker,
    id,
    action_verdict,
    0.7 -- default confidence
FROM stocks
WHERE action_verdict IN ('BUY', 'STRONG BUY', 'ACCUMULATE')
ON CONFLICT (ticker) DO NOTHING;
COMMENT ON TABLE model_performance IS 'Track prediction accuracy over time';
COMMENT ON TABLE data_sync_log IS 'Background job execution log';
