-- ============================================================================
-- STOCK OWNER INTENT — a standing instruction the phase gate cannot see
-- Date: 2026-08-25
--
-- ECOR is GREAT_FIND today (§31) and would pass the Buy Guard, but it is
-- queued for exit, not for another purchase. SMSI is blocked by WAIT_TIME
-- today, but for the wrong reason — it is held only for a tax-loss harvest,
-- and that block would silently lift the moment a future reading moves it
-- off WAIT_TIME. Neither belongs on `stock_lifecycle`, which is versioned by
-- every automated detection; this is its own small table, set by a human,
-- read by the daily-actions gate before it ever asks the phase.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_owner_intent (
    ticker VARCHAR(20) PRIMARY KEY,
    intent VARCHAR(30) NOT NULL,
    note VARCHAR(300),
    set_by VARCHAR(100) NOT NULL,
    set_at TIMESTAMP WITH TIME ZONE NOT NULL
);

COMMENT ON TABLE stock_owner_intent IS
    'A standing instruction for one ticker, independent of phase. Presence alone suppresses new BUY/ACCUMULATE suggestions for it.';
COMMENT ON COLUMN stock_owner_intent.intent IS
    'EXIT_PENDING | TAX_LOSS_HOLD today — free text, not an enum. Both mean the same thing to the gate; the note says why.';
