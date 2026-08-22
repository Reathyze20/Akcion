-- ============================================================================
-- SEC EDGAR FILINGS + INSIDER TRANSACTIONS
-- Date: 2026-08-22
--
-- Stores what the regulator says about held positions: 10-K / 10-Q filings and
-- Form 4 insider transactions, read straight from EDGAR.
--
-- Two design points are load-bearing, both verified against live SEC data on
-- 2026-08-22, and both exist to stop a confident signal being manufactured out
-- of something that is not one.
--
-- 1. `sec_coverage.status` separates "this company files nothing this quarter"
--    from "this company does not file with the SEC at all". Five of fourteen
--    holdings (GSI.V, KUYA.V, IMP.V, QIPT, UMD) trade on TSX Venture and other
--    non-US venues and file with their own regulators. Storing both as an
--    absence of rows would turn a fact about an exchange into a fact about a
--    company.
--
-- 2. `insider_transactions.signal` is NOT derived from the acquired/disposed
--    flag. The first Form 4 fetched (TPCS, 2026-08-20) was a bona fide gift:
--    code G, price $0.00, flagged disposed. Read naively that is "an insider
--    sold 8,000 shares". Only codes P and S involve a decision to transact at
--    a market price; every other code is administrative or non-discretionary
--    and is stored with signal = 'NO_SIGNAL'.
--
-- `price_per_share` is deliberately nullable and is NULL — not 0 — for grants
-- and gifts. Zero is a price; the absence of one is not.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_coverage (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20) NOT NULL UNIQUE,
    cik             VARCHAR(10),
    company_name    VARCHAR(255),
    status          VARCHAR(32) NOT NULL,
    note            VARCHAR(500),
    last_checked_at TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON COLUMN sec_coverage.status IS
    'COVERED | NOT_AN_SEC_FILER | LOOKUP_FAILED. NOT_AN_SEC_FILER is a fact about the listing venue, not about the company.';
COMMENT ON COLUMN sec_coverage.last_checked_at IS
    'When EDGAR was last read for this ticker. NULL = never checked, which is not the same as "nothing found".';


CREATE TABLE IF NOT EXISTS sec_filings (
    id             SERIAL PRIMARY KEY,
    ticker         VARCHAR(20) NOT NULL,
    cik            VARCHAR(10) NOT NULL,
    form           VARCHAR(20) NOT NULL,
    filed_date     DATE NOT NULL,
    period_date    DATE,
    accession      VARCHAR(25) NOT NULL,
    document       VARCHAR(255) NOT NULL,
    url            VARCHAR(500),
    analysis       TEXT,
    analyzed_at    TIMESTAMP WITH TIME ZONE,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_sec_filing_accession UNIQUE (accession, document)
);

COMMENT ON COLUMN sec_filings.analysis IS
    'Czech summary produced from the filing text. NULL = not analysed yet, which the UI must show as such rather than as "nothing notable".';

CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker_filed
    ON sec_filings (ticker, filed_date DESC);


CREATE TABLE IF NOT EXISTS insider_transactions (
    id                  SERIAL PRIMARY KEY,
    ticker              VARCHAR(20) NOT NULL,
    accession           VARCHAR(25) NOT NULL,
    insider_name        VARCHAR(255) NOT NULL,
    is_director         BOOLEAN DEFAULT FALSE,
    is_officer          BOOLEAN DEFAULT FALSE,
    officer_title       VARCHAR(255),
    is_ten_percent      BOOLEAN DEFAULT FALSE,
    transaction_date    DATE,
    filed_date          DATE,
    code                VARCHAR(2) NOT NULL,
    code_label          VARCHAR(100),
    signal              VARCHAR(12) NOT NULL,
    shares              DOUBLE PRECISION,
    price_per_share     DOUBLE PRECISION,
    acquired            BOOLEAN,
    shares_owned_after  DOUBLE PRECISION,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_insider_tx UNIQUE (accession, insider_name, transaction_date, code, shares)
);

COMMENT ON COLUMN insider_transactions.signal IS
    'BUY | SELL | NO_SIGNAL. Derived from the SEC transaction code, never from acquired/disposed: a gift (G) and a tax withholding (F) are disposals that mean nothing.';
COMMENT ON COLUMN insider_transactions.price_per_share IS
    'NULL for grants and gifts. Zero is a price; the absence of one is not.';

CREATE INDEX IF NOT EXISTS idx_insider_tx_ticker_date
    ON insider_transactions (ticker, transaction_date DESC);

-- The query that matters: real market decisions, newest first.
CREATE INDEX IF NOT EXISTS idx_insider_tx_signal
    ON insider_transactions (ticker, signal, transaction_date DESC)
    WHERE signal <> 'NO_SIGNAL';


-- ---------------------------------------------------------------------------
-- 2026-08-22, same day: FOREIGN_PRIVATE_ISSUER is 22 characters and the column
-- was VARCHAR(20), so RADCOM — a real holding — failed to store at all.
-- Idempotent widen for databases created before the constant existed.
-- ---------------------------------------------------------------------------
ALTER TABLE sec_coverage ALTER COLUMN status TYPE VARCHAR(32);
