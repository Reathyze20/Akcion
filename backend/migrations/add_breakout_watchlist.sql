-- Migration: Breakout Investors watchlist
-- Purpose: store the second source's published watchlist — conviction count
--          and target price — for the names we hold or watch
-- Date: 2026-08-23
--
-- Three tables because a snapshot alone answers the wrong question. The
-- snapshot says what the list is; `breakout_watchlist_changes` says what moved,
-- which is the only part worth a notification; `breakout_poll_state` says
-- whether the source was reachable at all, so an outage cannot pass for an
-- unchanged list and trigger a retry loop against someone else's server.
--
-- The CHECK on implied_target is the point of the first table. The app's
-- recurring defect is an absent input turning into a confident number, and a
-- target price is exactly that kind of number: it is derived from a quote and
-- an upside ratio, and if either is missing there is no target — not a zero,
-- not a stale one. The schema refuses to store one.

CREATE TABLE IF NOT EXISTS breakout_watchlist (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(200),

    -- how many members back the name
    endorsements INTEGER NOT NULL DEFAULT 0,

    -- expected gain as a ratio, as published: 0.62 means +62 %
    upside_ratio NUMERIC(12, 6),

    -- their quote at the moment upside was read, and the target it implies
    price_at_read NUMERIC(12, 4),
    implied_target NUMERIC(12, 4),

    -- when THEY added the name (source's created_at)
    added_at TIMESTAMP WITH TIME ZONE,
    -- when WE first saw it; differs for everything present at the first poll
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT target_has_its_inputs CHECK (
        implied_target IS NULL
        OR (price_at_read IS NOT NULL AND upside_ratio IS NOT NULL)
    ),
    CONSTRAINT price_at_read_is_a_price CHECK (
        price_at_read IS NULL OR price_at_read > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_breakout_watchlist_symbol
    ON breakout_watchlist (symbol);


CREATE TABLE IF NOT EXISTS breakout_watchlist_changes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    kind VARCHAR(20) NOT NULL
        CHECK (kind IN ('ADDED', 'REMOVED', 'ENDORSEMENTS', 'UPSIDE')),

    -- NULL on ADDED (before) and REMOVED (after) — the absence is the fact
    before_value NUMERIC(12, 6),
    after_value NUMERIC(12, 6),

    detail_cs TEXT NOT NULL,

    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    notified_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_breakout_changes_symbol
    ON breakout_watchlist_changes (symbol);
CREATE INDEX IF NOT EXISTS idx_breakout_changes_unsent
    ON breakout_watchlist_changes (notified_at, detected_at);


CREATE TABLE IF NOT EXISTS breakout_poll_state (
    id SERIAL PRIMARY KEY,
    -- written on EVERY attempt: a source that is down must not be retried
    -- faster than one that is up
    last_attempt_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_error VARCHAR(300),
    entries_last_read INTEGER
);
