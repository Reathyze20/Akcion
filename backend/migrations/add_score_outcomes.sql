-- Migration: Score Outcomes
-- Purpose: measure each journaled conviction score against what the price did
-- Date: 2026-08-23
--
-- One row per (journal entry, horizon). Immutable once evaluated: a measured
-- outcome is a fact about a past prediction and must not be quietly restated.
--
-- The two CHECK constraints are the point of this table, not decoration. The
-- app's recurring defect is absent data turning into a confident number, so
-- the schema itself refuses to store an 'evaluated' row without the prices it
-- was supposedly computed from, and refuses an 'unable' row that does not say
-- why.

CREATE TABLE IF NOT EXISTS score_outcomes (
    id SERIAL PRIMARY KEY,
    history_id INTEGER NOT NULL
        REFERENCES conviction_score_history(id) ON DELETE CASCADE,
    horizon_days INTEGER NOT NULL,

    -- evaluated = both prices real; pending = horizon has not elapsed;
    -- unable = the horizon passed but the measurement cannot be made
    eval_status VARCHAR(20) NOT NULL
        CHECK (eval_status IN ('evaluated', 'pending', 'unable')),
    unable_reason VARCHAR(50),

    -- Where the baseline came from: 'journal' (the quote captured when the
    -- score was issued) or 'close_on_record_date' (the actual close that day,
    -- recovered from bars — the more accurate of the two)
    baseline_price NUMERIC(12, 4),
    baseline_source VARCHAR(30),

    end_price NUMERIC(12, 4),
    end_date DATE,

    return_pct NUMERIC(10, 4),
    benchmark_return_pct NUMERIC(10, 4),
    excess_return_pct NUMERIC(10, 4),

    evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_score_outcome_horizon UNIQUE (history_id, horizon_days),

    -- "Evaluated" may never mean "we had no data"
    CONSTRAINT evaluated_has_its_numbers CHECK (
        eval_status <> 'evaluated'
        OR (baseline_price IS NOT NULL
            AND end_price IS NOT NULL
            AND return_pct IS NOT NULL)
    ),

    -- An unmeasurable outcome has to name the gap
    CONSTRAINT unable_names_its_reason CHECK (
        eval_status <> 'unable' OR unable_reason IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_score_outcomes_history
    ON score_outcomes(history_id);
CREATE INDEX IF NOT EXISTS idx_score_outcomes_pending
    ON score_outcomes(eval_status) WHERE eval_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_score_outcomes_horizon
    ON score_outcomes(horizon_days, eval_status);

COMMENT ON TABLE score_outcomes IS
    'Forward returns of each journaled conviction score, per horizon';
