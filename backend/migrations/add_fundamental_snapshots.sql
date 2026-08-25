-- ============================================================================
-- FUNDAMENTAL SNAPSHOTS
-- Date: 2026-08-23
--
-- `yahoo_finance_cache` holds one row per ticker and rewrites it on every
-- refresh. Right for a cache, wrong for anything that wants to know whether a
-- company is getting better or worse: each read destroys the previous one, so
-- the app has never been able to see a trend in any company EDGAR cannot reach
-- — which is four of the five largest positions.
--
-- SEC gives quarterly series with real period boundaries and is the better
-- source by a wide margin. It simply does not cover the Canadian and OTC
-- names, and for those this table is the only way a year-on-year comparison
-- will ever exist.
--
-- Urgent rather than merely useful: the data is already being fetched, nothing
-- extra is downloaded, and the only difference between having a series in 2027
-- and not having one is whether these rows were written from today. The same
-- "now or never" as the decision journal.
--
-- Not audited and not period-boundaried. Everything built on these is labelled
-- YAHOO_TTM and capped away from the ends of the cylinder scale.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    revenue_ttm DOUBLE PRECISION,
    net_income_ttm DOUBLE PRECISION,
    operating_margin DOUBLE PRECISION,
    profit_margin DOUBLE PRECISION,
    total_cash DOUBLE PRECISION,
    total_debt DOUBLE PRECISION,
    shares_outstanding DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    currency VARCHAR(8)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_ticker_time
    ON fundamental_snapshots (ticker, captured_at DESC);

COMMENT ON TABLE fundamental_snapshots IS
    'Trailing figures kept over time rather than overwritten. The only path to a trend for companies EDGAR cannot see.';
COMMENT ON COLUMN fundamental_snapshots.ticker IS
    'The symbol the provider answered under, not the canonical one — two listings can differ in currency and share count, and merging them would turn a units change into a trend.';
