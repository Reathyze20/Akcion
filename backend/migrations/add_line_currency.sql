-- ============================================================================
-- LINE CURRENCY
-- Date: 2026-08-23
--
-- The Green and Red Lines are quoted in the currency of the listing the
-- analyst follows, which for every Gomes pick is the US OTC one. Four of the
-- five largest positions are held on a Canadian exchange and priced in
-- Canadian dollars: DBO.TO, GSI.V, IMP.V, KUYA.V. `app/core/tickers.py`
-- correctly matches those positions to their US analyses — and the R/R score
-- was then computed from a CAD price against a USD band, wrong by the whole
-- exchange rate.
--
-- It was not theoretical. The first run of the engine after cylinders were
-- confirmed produced "TRIM GSI.V" on an R/R score of 2.97; converted properly
-- the score is about 4.25. Same direction that day, different number, and no
-- reason to expect the direction to survive the next move.
--
-- `currency_mismatch` does not catch this: it compares a ticker suffix with the
-- stored currency of the POSITION, which is a different question from whether
-- the price and the band are quoted in the same money.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

ALTER TABLE stocks
    ADD COLUMN IF NOT EXISTS line_currency VARCHAR(3);

COMMENT ON COLUMN stocks.line_currency IS
    'Currency the green/red lines are quoted in. NULL = unknown, and an unknown band currency must not be assumed to match the position.';

-- Everything the tracker filled is quoted on the US OTC listing.
UPDATE stocks
   SET line_currency = 'USD'
 WHERE source_key = 'GOMES'
   AND green_line IS NOT NULL
   AND line_currency IS NULL;
