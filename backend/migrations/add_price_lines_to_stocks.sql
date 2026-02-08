-- Add Price Lines and Trend Analysis Fields to Stocks Table
-- Date: 2026-01-25
-- Purpose: Enable frontend trend analysis (BULLISH/BEARISH/NEUTRAL)

-- Add price analysis columns to stocks table
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS current_price NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS green_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS red_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS grey_line NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_position_pct NUMERIC(5, 2);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_zone VARCHAR(50);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS market_cap NUMERIC(15, 2);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stocks_price_zone ON stocks (price_zone) WHERE price_zone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_stocks_current_price ON stocks (ticker, current_price) WHERE current_price IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN stocks.current_price IS 'Current market price (live or last close)';
COMMENT ON COLUMN stocks.green_line IS 'Buy zone / Support level (Gomes undervalued price)';
COMMENT ON COLUMN stocks.red_line IS 'Sell zone / Resistance level (Gomes fair/overvalued price)';
COMMENT ON COLUMN stocks.grey_line IS 'Neutral zone price level (if mentioned)';
COMMENT ON COLUMN stocks.price_position_pct IS 'Where price sits between green/red lines (0-100%)';
COMMENT ON COLUMN stocks.price_zone IS 'Price classification: DEEP_VALUE, BUY_ZONE, ACCUMULATE, FAIR_VALUE, SELL_ZONE, OVERVALUED';
COMMENT ON COLUMN stocks.market_cap IS 'Total market capitalization in millions';
