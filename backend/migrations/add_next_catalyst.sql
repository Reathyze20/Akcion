-- Migration: Add next_catalyst column to stocks table
-- Date: 2026-01-24
-- Purpose: Store the next upcoming catalyst for quick reference in portfolio view
-- Format: "EVENT / DATE" (e.g., "Q1 EARNINGS / MAY 26", "AMTRAK DECISION / H2 26")

ALTER TABLE stocks ADD COLUMN IF NOT EXISTS next_catalyst VARCHAR(100);

COMMENT ON COLUMN stocks.next_catalyst IS 'Next upcoming catalyst event with date';
