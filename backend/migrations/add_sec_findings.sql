-- ============================================================================
-- SEC FINDINGS
-- Date: 2026-08-23
--
-- `analyze_outlook` already extracts red flags with a severity and a verbatim
-- quote — going concern, controls not effective, restatements, concentration,
-- dilution. All of it is rendered into one Czech markdown blob in
-- `sec_filings.analysis` and that is where it stays.
--
-- Which means the cylinder rubric, which most needs those findings, cannot
-- read them. SMSI and ECOR both carry going-concern warnings and both were
-- assessed without either one, because reading a severity back out of prose is
-- what this codebase refuses to do.
--
-- Now or never, again: re-reading past filings to structure them would spend
-- API credit on work the subscription already covers, so the past stays in
-- markdown. What is not optional is that every filing analysed FROM TODAY also
-- writes its findings here. Without this table, a quarter from now the app has
-- no structured findings at all and no way to catch up but to pay to read
-- everything twice.
--
-- Both severity and quote are kept because neither is sufficient. A severity
-- with no quote cannot be checked; a quote with no severity leaves every
-- finding competing equally for attention on a screen with room for three.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS sec_findings (
    id SERIAL PRIMARY KEY,

    ticker VARCHAR(20) NOT NULL,
    accession VARCHAR(25) NOT NULL,
    form VARCHAR(20),
    filed_date DATE,
    period_date DATE,

    severity VARCHAR(12) NOT NULL,
    category VARCHAR(60),
    fact_cs TEXT NOT NULL,
    quote TEXT,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_finding_per_filing UNIQUE (accession, fact_cs)
);

CREATE INDEX IF NOT EXISTS idx_findings_ticker_severity
    ON sec_findings (ticker, severity);
CREATE INDEX IF NOT EXISTS idx_findings_ticker_filed
    ON sec_findings (ticker, filed_date DESC);

COMMENT ON TABLE sec_findings IS
    'Material warnings a filing made about itself, in a form the decision engine can query. Written from 2026-08-23; earlier filings remain only as markdown.';
COMMENT ON COLUMN sec_findings.quote IS
    'Verbatim from the filing. Without it the finding cannot be checked, and an unverifiable warning about real money is worse than none.';
COMMENT ON COLUMN sec_findings.accession IS
    'Which filing said it. Findings are superseded by a newer filing rather than edited — a warning later dropped is still a fact about its quarter.';
