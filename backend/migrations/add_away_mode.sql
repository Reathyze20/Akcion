-- ============================================================================
-- AWAY MODE
-- Date: 2026-08-23
--
-- One row: whether nobody is reading the app, and what was last pushed.
--
-- The two `last_push_*` columns are not bookkeeping. Away mode's promise is
-- that a week of the app not being opened produces a handful of messages, not
-- two hundred, and that promise is enforced by a quiet period between pushes.
-- A quiet period held only in memory ends at every restart — and the scheduler
-- this feeds is a process on a laptop that gets closed. So it lives here.
--
-- `until` in the past turns away mode off on its own. A window set before a
-- hospital stay must not silence the app for a year because nobody remembered
-- to switch it back.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS away_mode_state (
    id                 SERIAL PRIMARY KEY,
    is_away            BOOLEAN NOT NULL DEFAULT FALSE,
    since              TIMESTAMP WITH TIME ZONE,
    until              TIMESTAMP WITH TIME ZONE,
    reason             VARCHAR(255),
    last_push_at       TIMESTAMP WITH TIME ZONE,
    last_push_urgency  INTEGER NOT NULL DEFAULT 0,
    last_push_subject  VARCHAR(255),
    last_digest_reason TEXT,
    updated_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON COLUMN away_mode_state.until IS
    'End of the window. NULL = open-ended. A window in the past turns away mode off by itself.';
COMMENT ON COLUMN away_mode_state.last_push_at IS
    'When the last away-mode message went out. Persisted so the quiet period survives a restart.';
COMMENT ON COLUMN away_mode_state.last_push_urgency IS
    'Urgency of the last message. A new one must beat it by ESCALATION_MARGIN to interrupt the quiet period.';

-- Exactly one row. Everything reads row 1 and writes row 1; a second row would
-- mean two disagreeing answers to "is he away".
CREATE UNIQUE INDEX IF NOT EXISTS idx_away_mode_singleton
    ON away_mode_state ((TRUE));

INSERT INTO away_mode_state (is_away)
SELECT FALSE
WHERE NOT EXISTS (SELECT 1 FROM away_mode_state);
