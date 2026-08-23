-- ============================================================================
-- TRADE LEDGER FIELDS
-- Date: 2026-08-22
--
-- The `investment_logs` table already existed with log_type/ticker/shares/
-- price/emotion_tag, but nothing ever wrote a trade into it — every exit was
-- recorded as an unpriced share-count decrement on `positions`, so realized
-- P/L was unrecoverable.
--
-- These three columns make a recorded trade self-contained and auditable:
--   cost_basis  — the position's avg_cost AT THE MOMENT of the trade. Without
--                 it, realized_pl cannot be re-derived later (avg_cost moves).
--   realized_pl — profit/loss actually locked in on a SELL. NULL (never 0)
--                 when cost_basis is unknown, e.g. a Degiro-imported position
--                 whose purchase price was never filled in.
--   currency    — positions are not all USD. An `amount` without a currency
--                 is not a number you can trust.
--
-- All nullable: existing rows stay valid, and "unknown" stays distinguishable
-- from "zero" (see docs/EFFICIENT_INVESTING_PLAYBOOK.md — never fake a number).
--
-- Idempotent. Safe to re-run.
-- ============================================================================

ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS cost_basis DOUBLE PRECISION;

ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS realized_pl DOUBLE PRECISION;

ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS currency VARCHAR(3);

COMMENT ON COLUMN investment_logs.cost_basis IS
    'Position avg_cost at the moment of the trade. NULL = purchase price was unknown.';
COMMENT ON COLUMN investment_logs.realized_pl IS
    'Realized P/L on a SELL, in `currency`. NULL = not computable (unknown cost basis). Never 0 as a stand-in.';
COMMENT ON COLUMN investment_logs.currency IS
    'ISO code of `price`, `amount`, `cost_basis` and `realized_pl` for this row.';

-- Cooldown-after-loss and revenge-trading detection both scan recent losing
-- trades for one ticker; this is the index that query needs.
CREATE INDEX IF NOT EXISTS idx_investment_logs_ticker_created
    ON investment_logs (ticker, created_at DESC);
