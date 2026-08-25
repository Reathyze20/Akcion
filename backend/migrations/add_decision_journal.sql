-- ============================================================================
-- DECISION JOURNAL
-- Date: 2026-08-23
--
-- Why this migration is urgent rather than merely useful
-- ------------------------------------------------------
-- `conviction_score_history` records the score a MODEL produced. It does not
-- record the decision the ENGINE made: the R/R score, the deserved level, the
-- cylinders behind it, the band the price sat in, or the market alert that
-- gated it. Calibration matures 2026-09-22 (first 30-day horizon) and fully in
-- August 2027, and when it does it will be able to answer "were the nines
-- better than the fives?" — but not "did the band engine work?", because that
-- was never written down.
--
-- History cannot be reconstructed. The journal opened 2026-08-23 precisely
-- because everything before it never existed as data (see
-- docs/BACKLOG.md and app/services/score_journal.py). If the band engine ships
-- before these columns do, the same hole opens a second time and stays open.
--
-- Three additions, all for the same reason:
--   1. conviction_score_history gains the decision, not just the score.
--   2. investment_logs gains the R/R score AT ENTRY. The canon's 3-point rule
--      (docs/GOMES_METHODOLOGY_CANON.md §5) measures a move FROM the entry
--      score, so without this column the rule is uncomputable — which is why
--      `RiskRewardCalculator.should_take_profit` has never had a caller.
--   3. refused_buys records the buys the guard REFUSED. A rule that only
--      records what it allowed cannot be judged: in a year this is what says
--      whether the Buy Guard protected capital or cost it.
--
-- Every column is nullable. Existing rows stay valid and "unknown" stays
-- distinguishable from zero, which is the standing rule in this codebase.
--
-- Idempotent. Safe to re-run.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. The journal records the decision
-- ----------------------------------------------------------------------------

ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS rr_score NUMERIC(6, 3);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS deserved_score NUMERIC(6, 3);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS cylinders SMALLINT;
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS green_line NUMERIC(12, 4);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS red_line NUMERIC(12, 4);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS line_currency VARCHAR(3);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS band VARCHAR(20);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS market_alert VARCHAR(10);
ALTER TABLE conviction_score_history
    ADD COLUMN IF NOT EXISTS source_key VARCHAR(30);

COMMENT ON COLUMN conviction_score_history.rr_score IS
    'Logarithmic R/R score 0-10 at the moment of the decision (canon §4a). NULL = lines were missing, not zero.';
COMMENT ON COLUMN conviction_score_history.deserved_score IS
    'The level the company deserved: 10 - cylinders (canon §4b). NULL when cylinders were unknown.';
COMMENT ON COLUMN conviction_score_history.cylinders IS
    'Operational health 0-10 behind deserved_score. NULL = unknown, which is why no BUY could be issued.';
COMMENT ON COLUMN conviction_score_history.line_currency IS
    'Currency the green/red lines are quoted in. The tracker quotes the US OTC listing, so a CAD-priced position must be converted before scoring.';
COMMENT ON COLUMN conviction_score_history.band IS
    'Which band the price sat in: POD_ZELENOU / NAKUP / DRZET / PREPLACENO / NAD_CERVENOU / MIMO_METODIKU / NEZNAME.';
COMMENT ON COLUMN conviction_score_history.market_alert IS
    'Market alert level in force when the decision was made. It gates every buy, so a measurement without it is unreadable.';
COMMENT ON COLUMN conviction_score_history.source_key IS
    'Which source this decision came from: GOMES / BREAKOUT_INVESTORS / OTHER.';

-- Calibration groups by band and by source; both are scanned with the date.
CREATE INDEX IF NOT EXISTS idx_score_history_band
    ON conviction_score_history (band, recorded_at DESC);


-- ----------------------------------------------------------------------------
-- 2. A trade records the valuation it was made at
-- ----------------------------------------------------------------------------
-- The band tells you whether a stock is cheap NOW. The 3-point rule needs to
-- know how far it has moved SINCE YOU BOUGHT, and the two are different
-- questions. `avg_cost` answers it in price space, but price space shifts every
-- time the analyst moves a line — the score does not, which is why the score is
-- what gets stored.

ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS rr_score_at_entry NUMERIC(6, 3);
ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS green_line_at_entry NUMERIC(12, 4);
ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS red_line_at_entry NUMERIC(12, 4);
ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS cylinders_at_entry SMALLINT;
ALTER TABLE investment_logs
    ADD COLUMN IF NOT EXISTS line_currency VARCHAR(3);

COMMENT ON COLUMN investment_logs.rr_score_at_entry IS
    'R/R score when this trade was made. The 3-point rule (canon §5) measures from here. NULL = lines unknown at the time; the rule then stays silent rather than guessing.';
COMMENT ON COLUMN investment_logs.green_line_at_entry IS
    'Green Line used for rr_score_at_entry, kept so the score can be re-derived after the analyst moves the band.';
COMMENT ON COLUMN investment_logs.red_line_at_entry IS
    'Red Line used for rr_score_at_entry.';
COMMENT ON COLUMN investment_logs.cylinders_at_entry IS
    'Cylinders at the time of the trade — what the position was judged to deserve when it was opened.';
COMMENT ON COLUMN investment_logs.line_currency IS
    'Currency of green_line_at_entry / red_line_at_entry, which need not be the currency of `price`.';


-- ----------------------------------------------------------------------------
-- 3. The buys that were refused
-- ----------------------------------------------------------------------------
-- `GomesGatekeeper.evaluate_buy_guard` returns (False, reason) and every caller
-- throws the reason away. A discipline engine that keeps no record of what it
-- blocked cannot be evaluated, and "the rules protected us" stays an article of
-- faith instead of a measurement.
--
-- One row per (ticker, day, gate): a daily job re-evaluating the same unchanged
-- refusal must not fill the table with duplicates, but a refusal that changes
-- gate — from "market not green" to "not cheap enough" — is new information.

CREATE TABLE IF NOT EXISTS refused_buys (
    id SERIAL PRIMARY KEY,

    ticker VARCHAR(20) NOT NULL,
    refused_on DATE NOT NULL,
    refused_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Which gate said no. Codes come from GomesGatekeeper.BuyGate so the
    -- string in this column is never parsed back out of a sentence.
    failed_gate VARCHAR(40) NOT NULL,
    reason TEXT,

    -- The state the refusal was computed from, so it can be re-checked
    source_key VARCHAR(30),
    price NUMERIC(12, 4),
    green_line NUMERIC(12, 4),
    red_line NUMERIC(12, 4),
    line_currency VARCHAR(3),
    rr_score NUMERIC(6, 3),
    deserved_score NUMERIC(6, 3),
    cylinders SMALLINT,
    lifecycle_phase VARCHAR(20),
    market_alert VARCHAR(10),

    CONSTRAINT uq_refused_buy_day UNIQUE (ticker, refused_on, failed_gate)
);

CREATE INDEX IF NOT EXISTS idx_refused_buys_ticker
    ON refused_buys (ticker, refused_at DESC);
CREATE INDEX IF NOT EXISTS idx_refused_buys_gate
    ON refused_buys (failed_gate, refused_at DESC);

COMMENT ON TABLE refused_buys IS
    'Every buy the Gomes Buy Guard refused, with the gate that refused it. Read back later to measure whether the discipline earned its keep.';
COMMENT ON COLUMN refused_buys.failed_gate IS
    'MARKET_NOT_GREEN | ALERT_UNKNOWN | CYLINDERS_UNKNOWN | WAIT_TIME | SCORE_MISSING | NOT_CHEAP_ENOUGH';
COMMENT ON COLUMN refused_buys.refused_on IS
    'Date part of refused_at, carried separately because the uniqueness rule is per day.';
