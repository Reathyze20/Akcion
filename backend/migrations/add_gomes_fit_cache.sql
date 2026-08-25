-- ============================================================================
-- GOMES FIT CACHE — cached `fit_candidate()` output for the FIT layer in Nálezy
-- Date: 2026-08-25
--
-- `fit_candidate()` (app/services/gomes_fit.py) needs a live price-bar fetch
-- and the market gauge — the one thing `find_dossier.build()` promises never
-- to do. So `enrich()` computes and caches it here, same as Yahoo/SEC/Finnhub
-- above it, and `build()` only ever reads this table.
--
-- Idempotent. Safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS gomes_fit_cache (
    ticker VARCHAR(20) PRIMARY KEY,
    as_of DATE NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    summary_cs TEXT NOT NULL,
    fits_json JSONB NOT NULL,
    uncomputable_json JSONB NOT NULL
);

COMMENT ON TABLE gomes_fit_cache IS
    'Cached gomes_fit.fit_candidate() result per ticker. Never a verdict — see gomes_fit.py CAVEAT_CS.';
