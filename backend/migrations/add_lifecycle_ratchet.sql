-- ============================================================================
-- LIFECYCLE RATCHET + ROUGH PATCH
-- Date: 2026-08-24
--
-- GOMES_VIDEO_ADDENDUM.md §V1. The one thing Gomes tells the viewer to write
-- down is the difference between Gold Mine and a rough patch:
--
--   "The fact that you go through a rough patch -- less orders, the business
--    slows down -- does NOT mean you have shifted out of Gold Mine. You've
--    already proven your product sells in the marketplace, so you're not going
--    to go back to Wait Time."
--
-- Until now both classifiers were memoryless: `StockLifecycleClassifier`
-- votes on keywords and `propose_phase` takes an argmax, and neither knows
-- what the company was yesterday. WAIT_TIME_SIGNALS is literally the
-- vocabulary of a rough patch -- "missed guidance", "lawsuit", "delays",
-- "cfo left" -- so a proven holding with one bad quarter was relabelled
-- WAIT_TIME, and GomesGatekeeper then refused to buy it at the exact moment
-- it was cheapest. That is the setup the whole method exists to catch.
--
-- `phase_reached` is the high-water mark. `phase` may never fall below it.
-- The Wait Time reading is not discarded -- it becomes `rough_patch`, which
-- the Buy Guard reads.
--
-- `rough_patch_since` carries weight beyond bookkeeping: the Buy Guard
-- compares it with `cylinders_confirmed_at`. Quality agreed BEFORE the
-- business slowed is not evidence about the business now, so a rough patch
-- that began after the confirmation invalidates it for buying. That gate is
-- what keeps this migration from being a net loosening of safety.
--
-- Backfill: every row that already reads GOLD_MINE has, by definition,
-- reached GOLD_MINE. Rows in the other stages get their current phase as the
-- mark. UNKNOWN is left NULL -- it is the absence of a reading, not a rung,
-- and must never become a floor.
--
-- Operationally this is not optional and not only a Neon chore: the model
-- carries these columns, so until they exist every ORM query against
-- `stock_lifecycle` fails on UndefinedColumn and takes the away cycle and the
-- board down with it. A second, leaner copy of this migration was written for
-- exactly that reason and has been folded in here; if that one was already run,
-- re-running this is what adds the constraints and the index it lacked.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

ALTER TABLE stock_lifecycle
    ADD COLUMN IF NOT EXISTS phase_reached     VARCHAR(20),
    ADD COLUMN IF NOT EXISTS rough_patch       BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS rough_patch_since TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS rough_patch_until DATE,
    ADD COLUMN IF NOT EXISTS rough_patch_note  TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_lifecycle_phase_reached'
    ) THEN
        ALTER TABLE stock_lifecycle
            ADD CONSTRAINT check_lifecycle_phase_reached
            CHECK (phase_reached IS NULL
                   OR phase_reached IN ('GREAT_FIND', 'WAIT_TIME', 'GOLD_MINE'));
    END IF;
END $$;

-- Backfill the high-water mark from what is already on record.
UPDATE stock_lifecycle
   SET phase_reached = phase
 WHERE phase_reached IS NULL
   AND phase IN ('GREAT_FIND', 'WAIT_TIME', 'GOLD_MINE');

-- A rough patch is only meaningful on a company that reached Gold Mine; the
-- flag on anything else would be a stage wearing a different name.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_rough_patch_proven_only'
    ) THEN
        ALTER TABLE stock_lifecycle
            ADD CONSTRAINT check_rough_patch_proven_only
            CHECK (rough_patch = FALSE OR phase_reached = 'GOLD_MINE');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_lifecycle_rough_patch
    ON stock_lifecycle (ticker)
    WHERE rough_patch = TRUE;
