-- ============================================================================
-- CLAIM ATTRIBUTION
-- Date: 2026-08-22
--
-- The intake accepts any source the owner can paste: a WhatsApp excerpt from
-- the Breakout Investors group, a Mark Gomes video transcript, a company
-- earnings call, a news article. Those carry very different weight, and
-- `ticker_mentions` had no way to record which was which — every extracted
-- claim looked equally authoritative.
--
-- That distinction is not cosmetic. docs/GOMES_METHODOLOGY_CANON.md caps
-- position size by cross-source agreement (AGREE <=15% / SINGLE <=7% /
-- CONFLICT <=5%), and app/core/sources.py already splits GOMES from
-- BREAKOUT_INVESTORS. Without a speaker on the mention, one enthusiastic
-- group member reads the same as the analyst the whole method is built on.
--
-- Columns:
--   speaker        — who said it, as the source named them.
--   source_key     — GOMES | BREAKOUT_INVESTORS | COMPANY | MEDIA | OTHER.
--                    COMPANY is a primary source (an earnings call is fact,
--                    not commentary) and outranks every opinion.
--   claim_type     — FACT | OPINION | TRADE_DISCLOSURE | RR_LINES |
--                    MARKET_ALERT. Only FACT-grade claims may move a thesis;
--                    the canon is fundamental, not sentiment-driven.
--   thesis_impact  — SUPPORTS | CONTRADICTS | BREAKS | NEUTRAL.
--
-- `context_snippet` (already present) now holds the VERBATIM quote the claim
-- was drawn from. Code verifies that string actually occurs in the submitted
-- text and drops the claim otherwise — a prompt can be talked around, a
-- substring check cannot.
--
-- All nullable, idempotent, safe to re-run.
-- ============================================================================

ALTER TABLE ticker_mentions
    ADD COLUMN IF NOT EXISTS speaker VARCHAR(120);

ALTER TABLE ticker_mentions
    ADD COLUMN IF NOT EXISTS source_key VARCHAR(30);

ALTER TABLE ticker_mentions
    ADD COLUMN IF NOT EXISTS claim_type VARCHAR(30);

ALTER TABLE ticker_mentions
    ADD COLUMN IF NOT EXISTS thesis_impact VARCHAR(20);

COMMENT ON COLUMN ticker_mentions.speaker IS
    'Who made the claim, as named in the source. Never a phone number.';
COMMENT ON COLUMN ticker_mentions.source_key IS
    'GOMES | BREAKOUT_INVESTORS | COMPANY | MEDIA | OTHER — drives the dual-source position cap.';
COMMENT ON COLUMN ticker_mentions.claim_type IS
    'FACT | OPINION | TRADE_DISCLOSURE | RR_LINES | MARKET_ALERT. Only FACT may move a thesis.';
COMMENT ON COLUMN ticker_mentions.thesis_impact IS
    'SUPPORTS | CONTRADICTS | BREAKS | NEUTRAL.';
COMMENT ON COLUMN ticker_mentions.context_snippet IS
    'Verbatim quote from the source. Verified to occur in the submitted text before the row is written.';

-- The ticker timeline reads newest-first per ticker; the outlook recompute
-- filters that by source and claim type.
CREATE INDEX IF NOT EXISTS idx_ticker_mentions_ticker_date
    ON ticker_mentions (ticker, mention_date DESC);
CREATE INDEX IF NOT EXISTS idx_ticker_mentions_source
    ON ticker_mentions (source_key, claim_type);

-- ----------------------------------------------------------------------------
-- The container the mentions hang off. `analyst_transcripts` was built for
-- Gomes videos; the intake now also holds WhatsApp excerpts and earnings
-- calls, which need to be told apart when recomputing an outlook.
-- ----------------------------------------------------------------------------

ALTER TABLE analyst_transcripts
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(30);

COMMENT ON COLUMN analyst_transcripts.source_type IS
    'WHATSAPP_GROUP | GOMES_VIDEO | EARNINGS_CALL | NEWS | OTHER.';
