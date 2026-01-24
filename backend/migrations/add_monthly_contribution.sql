-- Migration: Add monthly_contribution column to portfolios table
-- Date: 2026-01-24
-- Purpose: Allow individual monthly contribution settings per portfolio

ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS monthly_contribution FLOAT DEFAULT 20000.0;

COMMENT ON COLUMN portfolios.monthly_contribution IS 'Monthly contribution amount in CZK for allocation planning';
