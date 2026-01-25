-- Add Trading Zones fields to Stocks Table
-- Date: 2026-01-25
-- Purpose: Enable GOMES TRADING ZONES display (BUY/HOLD/SELL limits)

-- Add trading zone columns to stocks table
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS max_buy_price NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS start_sell_price NUMERIC(12, 4);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS risk_to_floor_pct NUMERIC(6, 2);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS upside_to_ceiling_pct NUMERIC(6, 2);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS trading_zone_signal VARCHAR(50);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stocks_trading_signal ON stocks (trading_zone_signal) WHERE trading_zone_signal IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN stocks.max_buy_price IS 'Maximum buy price = green_line + 5% (Above this: HOLD only)';
COMMENT ON COLUMN stocks.start_sell_price IS 'Start selling price = red_line - 5% (Sell into strength)';
COMMENT ON COLUMN stocks.risk_to_floor_pct IS 'Risk percentage to green line: (current - green) / current * 100';
COMMENT ON COLUMN stocks.upside_to_ceiling_pct IS 'Upside percentage to red line: (red - current) / current * 100';
COMMENT ON COLUMN stocks.trading_zone_signal IS 'Trading recommendation: AGGRESSIVE_BUY, BUY, HOLD, SELL, STRONG_SELL';
