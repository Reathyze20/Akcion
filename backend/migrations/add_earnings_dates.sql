-- ============================================================================
-- EARNINGS DATES
-- Date: 2026-08-23
--
-- The canon's fourteen-day blackout — do not be holding into a print you
-- cannot predict — has been fully implemented since the app was written and
-- has never once fired. `GomesGatekeeper.EARNINGS_DANGER_DAYS` is honoured by
-- every path that receives a date, and nothing ever supplied one:
-- `gomes_analyzer._get_earnings_date` returns None under a TODO, so every
-- `investment_verdicts.days_to_earnings` ever written is NULL.
--
-- One row per COMPANY, keyed canonically, so a position held as KUYA.V finds
-- the date filed under KUYAF.
--
-- `confirmed` is the column that matters. Yahoo answers with either a single
-- day (announced) or a two-day window (inferred from past cadence), and the
-- SEC fallback is our own arithmetic on filing periods. All three block a
-- purchase — buying two days before a print is what the canon forbids, and a
-- delayed purchase is cheaper than a surprise — but a block on a guess must
-- never be shown as a block on a fact.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS earnings_dates (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,

    next_date DATE,
    window_end DATE,
    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(20) NOT NULL DEFAULT 'YAHOO',

    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    note TEXT
);

CREATE INDEX IF NOT EXISTS idx_earnings_next ON earnings_dates (next_date);

COMMENT ON TABLE earnings_dates IS
    'When each company next reports. One row per company, keyed by the canonical symbol.';
COMMENT ON COLUMN earnings_dates.confirmed IS
    'True only for a single announced day. False = a window or our own cadence arithmetic — an estimate, and shown as one.';
COMMENT ON COLUMN earnings_dates.window_end IS
    'Set only when the provider gave a range, which means it inferred the timing rather than reading an announcement.';
COMMENT ON COLUMN earnings_dates.note IS
    'Why there is no date, when there is none. An absence that names itself is one the owner can act on.';
