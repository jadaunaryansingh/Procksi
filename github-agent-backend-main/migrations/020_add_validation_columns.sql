-- Migration: Add enhanced repository privacy validation columns
-- This migration adds columns for proactive validation, confidence scoring, and fix suggestions

-- Add validation_status column to track validation state
ALTER TABLE teams ADD COLUMN IF NOT EXISTS validation_status VARCHAR(50);
COMMENT ON COLUMN teams.validation_status IS 'Validation status: valid, invalid_url, private, not_found, missing_url, pending';

-- Add validation_confidence column for confidence scoring
ALTER TABLE teams ADD COLUMN IF NOT EXISTS validation_confidence FLOAT;
COMMENT ON COLUMN teams.validation_confidence IS 'Confidence score for classification (0.0-1.0)';

-- Add validation_reason column for human-readable explanation
ALTER TABLE teams ADD COLUMN IF NOT EXISTS validation_reason TEXT;
COMMENT ON COLUMN teams.validation_reason IS 'Human-readable reason for classification';

-- Add suggested_fixes column for fix suggestions
ALTER TABLE teams ADD COLUMN IF NOT EXISTS suggested_fixes JSONB;
COMMENT ON COLUMN teams.suggested_fixes IS 'Array of suggested fix URLs: ["https://github.com/user1/repo", "https://github.com/user2/repo"]';

-- Add last_validation_check column to track proactive validation
ALTER TABLE teams ADD COLUMN IF NOT EXISTS last_validation_check TIMESTAMP WITH TIME ZONE;
COMMENT ON COLUMN teams.last_validation_check IS 'Timestamp of last proactive validation (separate from last_privacy_check)';

-- Add url_change_history column for audit trail
ALTER TABLE teams ADD COLUMN IF NOT EXISTS url_change_history JSONB;
COMMENT ON COLUMN teams.url_change_history IS 'Array of URL changes: [{"old_url": "...", "new_url": "...", "changed_by": "...", "changed_at": "..."}]';

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_teams_validation_status ON teams(validation_status);
CREATE INDEX IF NOT EXISTS idx_teams_validation_confidence ON teams(validation_confidence) WHERE validation_confidence IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_teams_last_validation_check ON teams(last_validation_check) WHERE last_validation_check IS NOT NULL;

-- Add constraint to ensure confidence is in valid range [0.0, 1.0]
ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_validation_confidence_range;
ALTER TABLE teams ADD CONSTRAINT teams_validation_confidence_range 
CHECK (validation_confidence IS NULL OR (validation_confidence >= 0.0 AND validation_confidence <= 1.0));
