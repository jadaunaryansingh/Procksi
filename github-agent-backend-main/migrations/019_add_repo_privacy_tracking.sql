-- Migration: Add repository privacy tracking
-- This migration adds a field to track if a repository is private

DO $$ 
BEGIN
    -- Add is_private column to teams table
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'is_private'
    ) THEN
        ALTER TABLE teams ADD COLUMN is_private BOOLEAN DEFAULT NULL;
        COMMENT ON COLUMN teams.is_private IS 'Whether the repository is private (NULL = not checked yet, TRUE = private, FALSE = public)';
    END IF;
    
    -- Add last_privacy_check column to track when we last checked
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'last_privacy_check'
    ) THEN
        ALTER TABLE teams ADD COLUMN last_privacy_check TIMESTAMP WITH TIME ZONE;
        COMMENT ON COLUMN teams.last_privacy_check IS 'Last time we checked if the repository is private';
    END IF;
END $$;

-- Create index for querying private repos
CREATE INDEX IF NOT EXISTS idx_teams_is_private ON teams(is_private) WHERE is_private = TRUE;
