"""
Migration: Complete Gomes Guardian Master Table

Implements full Mark Gomes investment framework:
- Identity & Classification
- Financial Fortress (Hard Data)
- Thesis & Catalysts (Soft Data) 
- Valuation Reality
- Risk Control

Author: GitHub Copilot with Claude Sonnet 4.5
Date: 2026-01-25
"""

-- ============================================================================
-- IDENTITY & CLASSIFICATION
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS asset_class TEXT 
  CHECK (asset_class IN ('ANCHOR', 'HIGH_BETA_ROCKET', 'TURNAROUND', 'VALUE_TRAP', 'BIOTECH_BINARY'));

COMMENT ON COLUMN stocks.asset_class IS 'Gomes Asset Classification: Anchor (stable grower), High Beta Rocket (miner/leveraged), Biotech Binary (binary outcome), Turnaround (recovery play)';

-- ============================================================================
-- FINANCE (HARD DATA) - The Survival Metrics
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS cash_runway_months INTEGER;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS insider_ownership_pct FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS fully_diluted_market_cap FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS enterprise_value FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS quarterly_burn_rate FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS total_cash FLOAT;

COMMENT ON COLUMN stocks.cash_runway_months IS 'Months of cash remaining at current burn rate (Cash / Monthly Burn)';
COMMENT ON COLUMN stocks.insider_ownership_pct IS 'Percentage of shares held by management (skin in the game)';
COMMENT ON COLUMN stocks.fully_diluted_market_cap IS 'True market cap including warrants and options';
COMMENT ON COLUMN stocks.enterprise_value IS 'Market Cap + Debt - Cash (real valuation)';
COMMENT ON COLUMN stocks.quarterly_burn_rate IS 'Average quarterly cash burn (for runway calculation)';
COMMENT ON COLUMN stocks.total_cash IS 'Cash & equivalents on balance sheet';

-- ============================================================================
-- THESIS (SOFT DATA) - The Narrative
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS gomes_score INTEGER CHECK (gomes_score >= 0 AND gomes_score <= 10);
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS inflection_status TEXT 
  CHECK (inflection_status IN ('WAIT_TIME', 'UPCOMING', 'ACTIVE_GOLD_MINE'));
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS primary_catalyst TEXT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS catalyst_date DATE;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS thesis_narrative TEXT;

COMMENT ON COLUMN stocks.gomes_score IS 'Gomes conviction score 0-10 (AI generated from Deep DD)';
COMMENT ON COLUMN stocks.inflection_status IS 'Business stage: WAIT_TIME (red), UPCOMING (yellow), ACTIVE_GOLD_MINE (green)';
COMMENT ON COLUMN stocks.primary_catalyst IS 'Next major event (e.g., Amtrak Contract Decision)';
COMMENT ON COLUMN stocks.catalyst_date IS 'Estimated date of catalyst event';
COMMENT ON COLUMN stocks.thesis_narrative IS 'One-sentence investment thesis (The Setup)';

-- ============================================================================
-- VALUATION - Price Targets
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_floor FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_target_24m FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS current_valuation_stage TEXT
  CHECK (current_valuation_stage IN ('UNDERVALUED', 'FAIR', 'OVERVALUED', 'BUBBLE'));
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_base FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS price_moon FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS forward_pe_2027 FLOAT;

COMMENT ON COLUMN stocks.price_floor IS 'Liquidation value (Cash/Share) - absolute downside';
COMMENT ON COLUMN stocks.price_target_24m IS 'Target price in 24 months based on operational model';
COMMENT ON COLUMN stocks.current_valuation_stage IS 'Valuation assessment: UNDERVALUED (<50% of target), FAIR, OVERVALUED, BUBBLE';
COMMENT ON COLUMN stocks.price_base IS 'Base case realistic target';
COMMENT ON COLUMN stocks.price_moon IS 'Bull case moon shot target';
COMMENT ON COLUMN stocks.forward_pe_2027 IS 'Forward P/E ratio (2027 earnings estimate)';

-- ============================================================================
-- RISK CONTROL - Position Discipline
-- ============================================================================

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS max_allocation_cap FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS stop_loss_price FLOAT;
ALTER TABLE stocks ADD COLUMN IF NOT EXISTS insider_activity TEXT
  CHECK (insider_activity IN ('BUYING', 'HOLDING', 'SELLING'));

COMMENT ON COLUMN stocks.max_allocation_cap IS 'Maximum portfolio allocation % (dynamically calculated by Gomes Logic)';
COMMENT ON COLUMN stocks.stop_loss_price IS 'Hard exit price (technical support or -20% from entry)';
COMMENT ON COLUMN stocks.insider_activity IS 'Recent insider trading activity';

-- ============================================================================
-- INDEXES for Performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_stocks_asset_class ON stocks(asset_class);
CREATE INDEX IF NOT EXISTS idx_stocks_inflection_status ON stocks(inflection_status);
CREATE INDEX IF NOT EXISTS idx_stocks_gomes_score ON stocks(gomes_score DESC);
CREATE INDEX IF NOT EXISTS idx_stocks_cash_runway ON stocks(cash_runway_months);
CREATE INDEX IF NOT EXISTS idx_stocks_catalyst_date ON stocks(catalyst_date);
CREATE INDEX IF NOT EXISTS idx_stocks_valuation_stage ON stocks(current_valuation_stage);

-- ============================================================================
-- LEGACY FIELD CLEANUP (optional - can be removed after migration)
-- ============================================================================

-- If you had old fields with different names, drop them here:
-- ALTER TABLE stocks DROP COLUMN IF EXISTS old_field_name;
