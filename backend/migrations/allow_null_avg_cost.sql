-- ============================================================================
-- Migration: positions.avg_cost becomes nullable
-- ============================================================================
-- Degiro portfolio exports carry NO purchase price (only the closing price).
-- The old import silently stored the closing price as avg_cost — fabricated
-- cost basis that corrupted P/L and the doubling rule. From now on an import
-- without a real purchase price stores NULL, the app flags the position as
-- "⚠️ CHYBÍ nákupní cena", and the user fills it in via position edit.
--
-- SAFETY: additive-only constraint relaxation. No data changed.
--
--   psql "$DATABASE_URL" -f backend/migrations/allow_null_avg_cost.sql
-- ============================================================================

ALTER TABLE positions ALTER COLUMN avg_cost DROP NOT NULL;
