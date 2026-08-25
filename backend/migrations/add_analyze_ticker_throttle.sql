-- ============================================================================
-- ANALYZE-TICKER THROTTLE — per-ticker cooldown for POST /api/intelligence/analyze-ticker
-- Date: 2026-08-25
--
-- The route had no rate limit of its own: every call re-runs a full LLM pass.
-- IMPLEMENTATION_PLAN.md §29 point 4 found something outside this app calling
-- it 143 times in 24 hours on KUYA.V — about once every ten minutes, each time
-- getting back "no new intelligence, keeping existing thesis". This table is
-- the fix, mirroring tracker_poll_state's pattern but keyed per ticker instead
-- of a single shared row, since analyze-ticker is called per ticker rather
-- than for one shared source.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analyze_ticker_state (
    ticker VARCHAR(20) PRIMARY KEY,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE analyze_ticker_state IS
    'Per-ticker cooldown for analyze-ticker. Written on every attempt, successful or not, so a failing ticker is not retried faster than a healthy one.';
COMMENT ON COLUMN analyze_ticker_state.last_attempt_at IS
    'Drives the minimum interval. Attempt, not success.';
