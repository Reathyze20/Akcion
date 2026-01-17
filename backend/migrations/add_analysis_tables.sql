-- Analysis Tables Migration - Production Ready
-- Adds tables for storing analyst transcripts and SWOT analysis
-- Compatible with existing Trading Intelligence Module schema

-- ==========================================
-- 1. ALTER active_watchlist - Add Gomes Score and Analysis Fields
-- ==========================================

-- Add columns to existing active_watchlist table
ALTER TABLE active_watchlist
ADD COLUMN IF NOT EXISTS gomes_score NUMERIC(4, 2) CHECK (gomes_score >= 0 AND gomes_score <= 10),
ADD COLUMN IF NOT EXISTS investment_thesis TEXT,
ADD COLUMN IF NOT EXISTS risks TEXT;

-- Create index for filtering by Gomes score
CREATE INDEX IF NOT EXISTS idx_watchlist_gomes_score 
ON active_watchlist (gomes_score DESC) 
WHERE gomes_score IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN active_watchlist.gomes_score IS 'Mark Gomes score (0-10), higher = better investment opportunity';
COMMENT ON COLUMN active_watchlist.investment_thesis IS 'Detailed investment thesis from analyst transcripts';
COMMENT ON COLUMN active_watchlist.risks IS 'Identified risks and concerns from analysis';

-- ==========================================
-- 2. CREATE analyst_transcripts - Store Raw and Processed Transcripts
-- ==========================================

CREATE TABLE IF NOT EXISTS analyst_transcripts (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,  -- e.g., 'Breakout Investors', 'Mark Gomes'
    raw_text TEXT NOT NULL,
    processed_summary TEXT,
    detected_tickers TEXT[] NOT NULL DEFAULT '{}',  -- PostgreSQL array for tickers
    date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Additional metadata
    video_url VARCHAR(500),
    transcript_quality VARCHAR(20) CHECK (transcript_quality IN ('high', 'medium', 'low')),
    is_processed BOOLEAN NOT NULL DEFAULT FALSE,
    processing_notes TEXT,
    
    CONSTRAINT check_date_not_future CHECK (date <= CURRENT_DATE)
);

-- Indexes for fast searching
CREATE INDEX IF NOT EXISTS idx_transcripts_source ON analyst_transcripts (source_name, date DESC);
CREATE INDEX IF NOT EXISTS idx_transcripts_date ON analyst_transcripts (date DESC);
CREATE INDEX IF NOT EXISTS idx_transcripts_processed ON analyst_transcripts (is_processed, created_at DESC);

-- GIN index for fast ticker array searches
CREATE INDEX IF NOT EXISTS idx_transcripts_tickers ON analyst_transcripts USING GIN (detected_tickers);

-- Full-text search index on processed_summary
CREATE INDEX IF NOT EXISTS idx_transcripts_summary_fts ON analyst_transcripts USING GIN (to_tsvector('english', COALESCE(processed_summary, '')));

-- Comments for documentation
COMMENT ON TABLE analyst_transcripts IS 'Stores raw and processed transcripts from analyst videos (e.g., Mark Gomes)';
COMMENT ON COLUMN analyst_transcripts.detected_tickers IS 'Array of stock tickers mentioned in transcript';
COMMENT ON COLUMN analyst_transcripts.processed_summary IS 'AI-generated summary of key points';

-- ==========================================
-- 3. CREATE swot_analysis - AI-Generated SWOT per Ticker
-- ==========================================

CREATE TABLE IF NOT EXISTS swot_analysis (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
    watchlist_id INTEGER REFERENCES active_watchlist(id) ON DELETE CASCADE,
    transcript_id INTEGER REFERENCES analyst_transcripts(id) ON DELETE SET NULL,
    
    -- SWOT data stored as JSONB for flexibility
    swot_data JSONB NOT NULL,
    
    -- Metadata
    ai_model_version VARCHAR(50) NOT NULL,  -- e.g., 'gemini-1.5-pro', 'gpt-4'
    confidence_score NUMERIC(5, 4) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- Optional expiry for outdated analysis
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    
    CONSTRAINT check_swot_structure CHECK (
        swot_data ? 'strengths' AND
        swot_data ? 'weaknesses' AND
        swot_data ? 'opportunities' AND
        swot_data ? 'threats'
    )
);

-- Indexes for fast ticker lookups
CREATE INDEX IF NOT EXISTS idx_swot_ticker ON swot_analysis (ticker, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_swot_active ON swot_analysis (ticker, is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_swot_watchlist ON swot_analysis (watchlist_id, generated_at DESC);

-- GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_swot_data_gin ON swot_analysis USING GIN (swot_data);

-- Unique constraint: one active SWOT per ticker at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_swot_ticker_active_unique 
ON swot_analysis (ticker) 
WHERE is_active = TRUE;

-- Comments for documentation
COMMENT ON TABLE swot_analysis IS 'AI-generated SWOT analysis per ticker from analyst transcripts';
COMMENT ON COLUMN swot_analysis.swot_data IS 'JSONB format: {"strengths": [...], "weaknesses": [...], "opportunities": [...], "threats": [...]}';
COMMENT ON COLUMN swot_analysis.ai_model_version IS 'AI model used for generation (e.g., gemini-1.5-pro)';

-- ==========================================
-- 4. VIEWS for Easier Querying
-- ==========================================

-- View: Complete watchlist with Gomes scores and latest SWOT
CREATE OR REPLACE VIEW v_watchlist_analysis AS
SELECT 
    aw.id AS watchlist_id,
    aw.ticker,
    aw.action_verdict,
    aw.confidence_score,
    aw.gomes_score,
    aw.investment_thesis,
    aw.risks,
    aw.last_updated,
    s.company_name,
    swot.swot_data,
    swot.ai_model_version AS swot_model,
    swot.generated_at AS swot_generated_at
FROM active_watchlist aw
LEFT JOIN stocks s ON aw.stock_id = s.id
LEFT JOIN LATERAL (
    SELECT * FROM swot_analysis
    WHERE ticker = aw.ticker AND is_active = TRUE
    ORDER BY generated_at DESC
    LIMIT 1
) swot ON TRUE
WHERE aw.is_active = TRUE
ORDER BY aw.gomes_score DESC NULLS LAST;

-- View: Recent analyst transcripts with ticker counts
CREATE OR REPLACE VIEW v_recent_transcripts AS
SELECT 
    id,
    source_name,
    date,
    array_length(detected_tickers, 1) AS ticker_count,
    detected_tickers,
    LEFT(processed_summary, 200) AS summary_preview,
    is_processed,
    created_at
FROM analyst_transcripts
ORDER BY date DESC, created_at DESC
LIMIT 50;

-- View: SWOT analysis by ticker with watchlist info
CREATE OR REPLACE VIEW v_swot_with_context AS
SELECT 
    sa.id,
    sa.ticker,
    s.company_name,
    sa.swot_data,
    sa.confidence_score,
    sa.ai_model_version,
    sa.generated_at,
    aw.gomes_score,
    aw.action_verdict,
    t.source_name AS transcript_source,
    t.date AS transcript_date
FROM swot_analysis sa
LEFT JOIN stocks s ON sa.stock_id = s.id
LEFT JOIN active_watchlist aw ON sa.watchlist_id = aw.id
LEFT JOIN analyst_transcripts t ON sa.transcript_id = t.id
WHERE sa.is_active = TRUE
ORDER BY sa.generated_at DESC;

-- ==========================================
-- 5. FUNCTIONS for Data Management
-- ==========================================

-- Function: Auto-update updated_at timestamp for analyst_transcripts
CREATE OR REPLACE FUNCTION update_transcript_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_transcript_update
BEFORE UPDATE ON analyst_transcripts
FOR EACH ROW
EXECUTE FUNCTION update_transcript_timestamp();

-- Function: Search transcripts by ticker (exact or partial match)
CREATE OR REPLACE FUNCTION search_transcripts_by_ticker(search_ticker VARCHAR)
RETURNS TABLE(
    transcript_id INTEGER,
    source_name VARCHAR,
    date DATE,
    processed_summary TEXT,
    detected_tickers TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        id,
        at.source_name,
        at.date,
        at.processed_summary,
        at.detected_tickers
    FROM analyst_transcripts at
    WHERE search_ticker = ANY(at.detected_tickers)
    ORDER BY at.date DESC, at.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Function: Get latest SWOT for ticker
CREATE OR REPLACE FUNCTION get_latest_swot(ticker_symbol VARCHAR)
RETURNS TABLE(
    id INTEGER,
    swot_data JSONB,
    confidence_score NUMERIC,
    generated_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sa.id,
        sa.swot_data,
        sa.confidence_score,
        sa.generated_at
    FROM swot_analysis sa
    WHERE sa.ticker = ticker_symbol 
    AND sa.is_active = TRUE
    ORDER BY sa.generated_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function: Expire old SWOT analyses (older than 90 days)
CREATE OR REPLACE FUNCTION expire_old_swot_analyses()
RETURNS INTEGER AS $$
DECLARE
    expired_count INTEGER;
BEGIN
    UPDATE swot_analysis
    SET is_active = FALSE
    WHERE is_active = TRUE
    AND generated_at < NOW() - INTERVAL '90 days';
    
    GET DIAGNOSTICS expired_count = ROW_COUNT;
    RETURN expired_count;
END;
$$ LANGUAGE plpgsql;

-- Function: Get top tickers by Gomes score
CREATE OR REPLACE FUNCTION get_top_gomes_tickers(limit_count INTEGER DEFAULT 10)
RETURNS TABLE(
    ticker VARCHAR,
    gomes_score NUMERIC,
    company_name VARCHAR,
    action_verdict VARCHAR,
    investment_thesis TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        aw.ticker,
        aw.gomes_score,
        s.company_name,
        aw.action_verdict,
        aw.investment_thesis
    FROM active_watchlist aw
    LEFT JOIN stocks s ON aw.stock_id = s.id
    WHERE aw.is_active = TRUE 
    AND aw.gomes_score IS NOT NULL
    ORDER BY aw.gomes_score DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- 6. EXAMPLE SWOT STRUCTURE (for documentation)
-- ==========================================

COMMENT ON COLUMN swot_analysis.swot_data IS 
'Expected JSONB structure:
{
  "strengths": [
    "Strong market position in semiconductor manufacturing",
    "Consistent revenue growth of 25% YoY",
    "Experienced management team"
  ],
  "weaknesses": [
    "High debt-to-equity ratio of 1.8",
    "Limited product diversification"
  ],
  "opportunities": [
    "Expanding AI chip market",
    "Potential government subsidies for domestic chip production"
  ],
  "threats": [
    "Intense competition from established players",
    "Supply chain vulnerabilities",
    "Regulatory risks in international markets"
  ]
}';

-- ==========================================
-- 7. VALIDATION QUERIES (for testing after migration)
-- ==========================================

-- Query to verify migration success:
-- SELECT COUNT(*) FROM analyst_transcripts;
-- SELECT COUNT(*) FROM swot_analysis;
-- SELECT ticker, gomes_score, investment_thesis FROM active_watchlist WHERE gomes_score IS NOT NULL;

-- ==========================================
-- MIGRATION COMPLETE
-- ==========================================

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Analysis tables migration completed successfully at %', NOW();
    RAISE NOTICE 'Created tables: analyst_transcripts, swot_analysis';
    RAISE NOTICE 'Altered table: active_watchlist (added gomes_score, investment_thesis, risks)';
    RAISE NOTICE 'Created views: v_watchlist_analysis, v_recent_transcripts, v_swot_with_context';
    RAISE NOTICE 'Created functions: search_transcripts_by_ticker, get_latest_swot, expire_old_swot_analyses, get_top_gomes_tickers';
END $$;
