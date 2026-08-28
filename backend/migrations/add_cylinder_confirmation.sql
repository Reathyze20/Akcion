-- ============================================================================
-- CYLINDER CONFIRMATION
-- Date: 2026-08-23
--
-- `stock_lifecycle.cylinders_count` has existed since the Gomes intelligence
-- module was written and has never held a value: its only writer took the
-- number from `StockLifecycleClassifier.classify()`, which hardcodes None.
-- Since `GomesGatekeeper` refuses a purchase when cylinders are unknown, the
-- app has been structurally incapable of ever saying "buy".
--
-- `app/services/cylinders.py` now proposes a number from named, dated facts.
-- These three columns are what separates a PROPOSAL from a CONFIRMATION, and
-- the Buy Guard reads only the second. Without that line the rubric would be
-- the same invented input as before, moved one storey up.
--
--   cylinders_confirmed_at   — when the owner agreed. NULL = a proposal only,
--                              and a proposal authorises nothing.
--   cylinders_confirmed_by   — who agreed. Two people use this app and their
--                              positions differ; so may their judgement.
--   cylinders_valid_until    — when the agreement lapses. A cylinder count
--                              describes how a company is operating, and the
--                              next quarterly report is exactly the event that
--                              can make it wrong.
--
-- An expired confirmation is NOT deleted. The selling side keeps reading it,
-- because stale data may make this app more cautious and never less — an
-- expired quality reading blocks new purchases while leaving the trim and
-- de-risk rules armed.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

ALTER TABLE stock_lifecycle
    ADD COLUMN IF NOT EXISTS cylinders_confirmed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE stock_lifecycle
    ADD COLUMN IF NOT EXISTS cylinders_confirmed_by VARCHAR(100);
ALTER TABLE stock_lifecycle
    ADD COLUMN IF NOT EXISTS cylinders_valid_until TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN stock_lifecycle.cylinders_confirmed_at IS
    'When the owner agreed to this cylinder count. NULL = proposal only; the Buy Guard will not accept it.';
COMMENT ON COLUMN stock_lifecycle.cylinders_confirmed_by IS
    'Who agreed. Two people use this app and their judgement may differ.';
COMMENT ON COLUMN stock_lifecycle.cylinders_valid_until IS
    'When the agreement lapses — the next report can contradict it. Expired blocks buying but never disarms selling.';

CREATE INDEX IF NOT EXISTS idx_lifecycle_confirmed
    ON stock_lifecycle (ticker, cylinders_confirmed_at DESC)
    WHERE cylinders_confirmed_at IS NOT NULL;
