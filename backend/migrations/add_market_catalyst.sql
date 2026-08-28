-- ============================================================================
-- MARKET CATALYST (semafor: valuation x knowledge of cause)
-- Date: 2026-08-24
--
-- GOMES_VIDEO_ADDENDUM.md §V3. The four grades are not four levels of
-- expensive. Gomes separates them by what he KNOWS:
--
--   YELLOW  "I don't know what's going to cause the market to drop, but
--            something's going to, because the market's too expensive right
--            now. Most of my alerts are going to be yellow."
--   ORANGE  COVID. "I knew it was bad. I just didn't know HOW bad."
--   RED     "when I know exactly what's happening, why it's happening, and how
--            severe it is."  Twice in thirty years.
--
-- So ORANGE and RED are claims about a CAUSE, and `market_gauge` -- which
-- measures price against a 41-year trend and admits it missed the 2007 top --
-- cannot make them. Its range is now capped at YELLOW, and the escalation it
-- used to perform automatically (AT_UPPER_LINE -> ORANGE, which moves the
-- target allocation to 25/35/40 and sells most of a portfolio) now needs
-- somebody to write down what is happening.
--
-- The other half is de-escalation, which this app has never had at all.
-- `market_watch` may tighten the semafor and may never loosen it, by design,
-- and the owner returned to this app after three and a half months of
-- dormancy. An ORANGE set during a scare and then forgotten keeps the Buy
-- Guard refusing every purchase indefinitely, and the failure is silent
-- because a refusal looks exactly like caution working. A dated cause can be
-- shown as stale and questioned.
--
-- `catalyst_severity_known` is a boolean and not a scale on purpose. Gomes'
-- own distinction is binary -- either he knows how bad it is or he does not.
-- A five-point severity would invite a 3, and a 3 is exactly the judgement he
-- refuses to make.
--
-- No backfill. A cause nobody wrote is a cause nobody had, and inventing one
-- for whatever the semafor happens to say today would manufacture the
-- justification this migration exists to require.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

ALTER TABLE market_status
    ADD COLUMN IF NOT EXISTS catalyst_description     TEXT,
    ADD COLUMN IF NOT EXISTS catalyst_identified_at   TIMESTAMP,
    ADD COLUMN IF NOT EXISTS catalyst_severity_known  BOOLEAN NOT NULL DEFAULT FALSE;

-- A description with no date cannot be aged, and an age is the whole point.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_catalyst_dated'
    ) THEN
        ALTER TABLE market_status
            ADD CONSTRAINT check_catalyst_dated
            CHECK ((catalyst_description IS NULL) = (catalyst_identified_at IS NULL));
    END IF;
END $$;
