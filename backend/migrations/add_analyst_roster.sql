-- ============================================================================
-- ANALYST ROSTER
-- Date: 2026-08-23
--
-- `normalize_source` decided attribution by keyword: a name containing "gomes"
-- was GOMES, one containing "breakout" was BREAKOUT_INVESTORS, everything else
-- was OTHER. Since OTHER does not enter `evaluate_dual_source_buy`, an analyst
-- writing under his own name had his work stored and silently not used — and
-- the agreement matrix that sets position caps at 15 / 7 / 5 percent was being
-- fed by one source instead of two.
--
-- The mirror image sat in `claim_extraction.resolve_source_key`, which mapped
-- EVERY speaker in the WhatsApp group to BREAKOUT_INVESTORS. Around a hundred
-- and thirty people, any of whom carried the authority of the research desk.
--
-- Both are answered here, by name. Nobody is on the list by default; a speaker
-- who is not listed keeps their name on the record and counts toward nothing,
-- which is the right treatment for a crowd and not a judgement about anyone.
--
-- Explicit rather than inferred, for the same reason as app/core/tickers.py:
-- matching people by resemblance is a quiet mistake, and the cost of a wrong
-- match is a position sized against somebody else's opinion.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS analyst_roster (
    id SERIAL PRIMARY KEY,
    name_key VARCHAR(120) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    source_key VARCHAR(30) NOT NULL,
    note TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_roster_source
    ON analyst_roster (source_key, active);

COMMENT ON TABLE analyst_roster IS
    'Whose word is attributed to a source. Nobody is listed by default; an unlisted speaker is recorded and counts toward nothing.';
COMMENT ON COLUMN analyst_roster.name_key IS
    'Lower-cased display name. Matching is exact — fuzzy matching a person is how one analyst''s conviction gets sized against another''s.';
COMMENT ON COLUMN analyst_roster.note IS
    'Why this person is on the list. A roster without reasons cannot be audited a year later.';
COMMENT ON COLUMN analyst_roster.active IS
    'Deactivated rather than deleted, so claims already recorded keep their attribution.';

-- Mark Gomes himself, so the roster is the single answer from the first row.
-- The keyword fallback still catches his other spellings; this makes the
-- primary source explicit rather than implied by a substring.
ALTER TABLE analyst_roster ALTER COLUMN active SET DEFAULT TRUE;
ALTER TABLE analyst_roster ALTER COLUMN added_at SET DEFAULT NOW();

INSERT INTO analyst_roster (name_key, display_name, source_key, note, active, added_at)
VALUES
    ('mark gomes', 'Mark Gomes', 'GOMES',
     'Autor metodiky. Jeho zelené a červené čáry jsou primární ocenění a jeho valuační veto platí i proti souhlasu ostatních.',
     TRUE, NOW()),
    ('money mark', 'Money Mark', 'GOMES',
     'Přezdívka Marka Gomese na StockTwits a ve streamech.', TRUE, NOW())
ON CONFLICT (name_key) DO NOTHING;
