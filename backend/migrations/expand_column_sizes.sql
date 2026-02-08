-- Migration: Expand column sizes for AI-generated content
-- Purpose: Fix "value too long" errors from AI analysis
-- Date: 2026-01-31

-- Expand action_verdict and other AI-generated columns
ALTER TABLE stocks ALTER COLUMN action_verdict TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN price_target_short TYPE VARCHAR(200);
ALTER TABLE stocks ALTER COLUMN price_target_long TYPE VARCHAR(200);
ALTER TABLE stocks ALTER COLUMN asset_class TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN inflection_status TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN current_valuation_stage TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN trading_zone_signal TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN price_zone TYPE VARCHAR(50);
ALTER TABLE stocks ALTER COLUMN insider_activity TYPE VARCHAR(200);
ALTER TABLE stocks ALTER COLUMN time_horizon TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN sentiment TYPE VARCHAR(50);

-- Also expand source fields
ALTER TABLE stocks ALTER COLUMN source_type TYPE VARCHAR(100);
ALTER TABLE stocks ALTER COLUMN speaker TYPE VARCHAR(200);

-- Verify changes
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'stocks' 
AND column_name IN ('action_verdict', 'price_target_short', 'price_target_long', 'asset_class', 'time_horizon')
ORDER BY column_name;
