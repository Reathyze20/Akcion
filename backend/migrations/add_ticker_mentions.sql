-- Migration: Add Ticker Mentions Table
-- Purpose: Track individual ticker mentions across transcripts for historical analysis
-- Author: GitHub Copilot with Claude Opus 4.5
-- Date: 2026-01-17

-- ============================================================================
-- CREATE TICKER_MENTIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS ticker_mentions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    transcript_id INTEGER NOT NULL REFERENCES analyst_transcripts(id) ON DELETE CASCADE,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE SET NULL,
    
    -- Datum zmínky (z transcriptu)
    mention_date DATE NOT NULL,
    
    -- Kontext zmínky
    sentiment VARCHAR(20) NOT NULL DEFAULT 'NEUTRAL',
    action_mentioned VARCHAR(30),
    
    -- Extrahovaný kontext
    context_snippet TEXT,
    key_points JSONB,
    
    -- Číselné hodnoty
    price_target NUMERIC(12, 2),
    conviction_level VARCHAR(20),
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ai_extracted BOOLEAN DEFAULT TRUE,
    is_current BOOLEAN DEFAULT TRUE,
    
    -- Constraints
    CONSTRAINT check_mention_sentiment CHECK (
        sentiment IN ('BULLISH', 'BEARISH', 'NEUTRAL', 'VERY_BULLISH', 'VERY_BEARISH')
    ),
    CONSTRAINT check_mention_action CHECK (
        action_mentioned IS NULL OR 
        action_mentioned IN ('BUY', 'SELL', 'HOLD', 'ACCUMULATE', 'TRIM', 'WATCH', 'AVOID', 'BUY_NOW')
    ),
    CONSTRAINT check_mention_conviction CHECK (
        conviction_level IS NULL OR 
        conviction_level IN ('HIGH', 'MEDIUM', 'LOW')
    )
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Primary lookup: ticker + date
CREATE INDEX IF NOT EXISTS idx_mentions_ticker_date ON ticker_mentions(ticker, mention_date DESC);

-- Find current mentions per ticker
CREATE INDEX IF NOT EXISTS idx_mentions_current ON ticker_mentions(ticker, is_current) WHERE is_current = TRUE;

-- Sentiment analysis
CREATE INDEX IF NOT EXISTS idx_mentions_sentiment ON ticker_mentions(ticker, sentiment, mention_date DESC);

-- Transcript relationship
CREATE INDEX IF NOT EXISTS idx_mentions_transcript ON ticker_mentions(transcript_id);

-- Stock relationship
CREATE INDEX IF NOT EXISTS idx_mentions_stock ON ticker_mentions(stock_id) WHERE stock_id IS NOT NULL;

-- Key points GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_mentions_key_points ON ticker_mentions USING GIN(key_points);

-- ============================================================================
-- HELPER FUNCTION: Update is_current flag
-- ============================================================================

-- When new mention is added, mark previous mentions as not current
CREATE OR REPLACE FUNCTION update_current_mention()
RETURNS TRIGGER AS $$
BEGIN
    -- Mark all previous mentions for this ticker as not current
    UPDATE ticker_mentions 
    SET is_current = FALSE 
    WHERE ticker = NEW.ticker 
      AND id != NEW.id 
      AND is_current = TRUE;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update is_current
DROP TRIGGER IF EXISTS trigger_update_current_mention ON ticker_mentions;
CREATE TRIGGER trigger_update_current_mention
    AFTER INSERT ON ticker_mentions
    FOR EACH ROW
    EXECUTE FUNCTION update_current_mention();

-- ============================================================================
-- VIEW: Latest mention per ticker with full context
-- ============================================================================

CREATE OR REPLACE VIEW v_latest_ticker_mentions AS
SELECT 
    tm.id,
    tm.ticker,
    tm.mention_date,
    tm.sentiment,
    tm.action_mentioned,
    tm.context_snippet,
    tm.key_points,
    tm.price_target,
    tm.conviction_level,
    tm.created_at,
    at.source_name,
    at.video_url,
    s.company_name,
    s.gomes_score,
    -- Calculate weight (exponential decay, 30-day half-life)
    EXP(-0.023 * (CURRENT_DATE - tm.mention_date)) as weight
FROM ticker_mentions tm
JOIN analyst_transcripts at ON tm.transcript_id = at.id
LEFT JOIN stocks s ON tm.stock_id = s.id AND s.is_latest = TRUE
WHERE tm.is_current = TRUE
ORDER BY tm.mention_date DESC;

-- ============================================================================
-- VIEW: Ticker history timeline
-- ============================================================================

CREATE OR REPLACE VIEW v_ticker_timeline AS
SELECT 
    tm.ticker,
    tm.mention_date,
    tm.sentiment,
    tm.action_mentioned,
    tm.context_snippet,
    tm.key_points,
    tm.price_target,
    tm.conviction_level,
    at.source_name,
    at.video_url,
    -- Weight for this mention
    EXP(-0.023 * (CURRENT_DATE - tm.mention_date)) as weight,
    -- Row number for ranking
    ROW_NUMBER() OVER (PARTITION BY tm.ticker ORDER BY tm.mention_date DESC) as mention_rank
FROM ticker_mentions tm
JOIN analyst_transcripts at ON tm.transcript_id = at.id
ORDER BY tm.ticker, tm.mention_date DESC;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE ticker_mentions IS 'Individual ticker mentions from analyst transcripts for historical tracking';
COMMENT ON COLUMN ticker_mentions.mention_date IS 'Date when the mention was made (from video/transcript date)';
COMMENT ON COLUMN ticker_mentions.sentiment IS 'Overall sentiment: BULLISH, BEARISH, NEUTRAL, VERY_BULLISH, VERY_BEARISH';
COMMENT ON COLUMN ticker_mentions.action_mentioned IS 'Recommended action: BUY, SELL, HOLD, ACCUMULATE, TRIM, WATCH, AVOID, BUY_NOW';
COMMENT ON COLUMN ticker_mentions.context_snippet IS 'Relevant excerpt from transcript about this ticker';
COMMENT ON COLUMN ticker_mentions.key_points IS 'JSON array of key points: catalysts, risks, price targets, etc.';
COMMENT ON COLUMN ticker_mentions.is_current IS 'Flag for the most recent mention per ticker (auto-updated by trigger)';

COMMENT ON VIEW v_latest_ticker_mentions IS 'Current/latest mention for each ticker with full context';
COMMENT ON VIEW v_ticker_timeline IS 'Complete mention history per ticker, ordered by date';

-- ============================================================================
-- DROP the date constraint on analyst_transcripts (allow historical imports)
-- ============================================================================

ALTER TABLE analyst_transcripts DROP CONSTRAINT IF EXISTS check_date_not_future;

COMMIT;
