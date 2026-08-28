-- ============================================================================
-- TRACKER SYNC — state and change log for riskrewardcharts.com
-- Date: 2026-08-23
--
-- `app/services/tracker_sync.py` was written and tested on 2026-07-26 and
-- never called: no route, no script, no scheduled task. The Green and Red
-- Lines it fetches are the two inputs the entire decision engine reads, so
-- until now every band, every deserved comparison and every 3-point trigger
-- was computed against columns nobody filled.
--
-- Two tables, mirroring the Breakout Investors pair that already works:
--   tracker_poll_state    — when the source was last reached, so the 12-hour
--                           minimum is enforced in code rather than by trust
--                           in whoever clicks the button.
--   tracker_line_changes  — what moved, and whether the owner was told. A
--                           moved line means the analyst revalued the company
--                           and every number downstream is stale; that is
--                           worth one message, and `notified_at` is what stops
--                           it being sent twice or lost when a send fails.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS tracker_poll_state (
    id SERIAL PRIMARY KEY,
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR(300),
    picks_last_read INTEGER
);

COMMENT ON TABLE tracker_poll_state IS
    'Single row: when riskrewardcharts.com was last read. Written on every attempt, successful or not.';
COMMENT ON COLUMN tracker_poll_state.last_attempt_at IS
    'Drives the 12h minimum interval. Attempt, not success — a source that is down must not be retried faster than one that is up.';
COMMENT ON COLUMN tracker_poll_state.last_success_at IS
    'NULL means we have never had a good read; the first one is a baseline, not news.';


CREATE TABLE IF NOT EXISTS tracker_line_changes (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    before_value VARCHAR(60),
    after_value VARCHAR(60),
    detail_cs TEXT NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    notified_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_tracker_changes_ticker
    ON tracker_line_changes (ticker, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_tracker_changes_unnotified
    ON tracker_line_changes (notified_at, detected_at DESC);

COMMENT ON TABLE tracker_line_changes IS
    'What moved on the Gomes tracker between two reads. A moved band invalidates every score computed before it.';
COMMENT ON COLUMN tracker_line_changes.kind IS
    'NEW_PICK | REMOVED | LINE_MOVED | PICK_TYPE. PICK_TYPE is the big one: it means he moved real money in or out.';
COMMENT ON COLUMN tracker_line_changes.notified_at IS
    'NULL until the owner was told. A failed send leaves it NULL so the next run retries instead of losing the news.';
