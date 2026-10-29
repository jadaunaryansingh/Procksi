-- Migration: Add missing columns to batches table
-- Date: 2026-02-11
-- Purpose: Add columns needed for batch processing tracking

-- Add completed_at column to batches table
ALTER TABLE batches 
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Add current_repo_url column to batches table (for tracking current processing)
ALTER TABLE batches 
ADD COLUMN IF NOT EXISTS current_repo_url TEXT;

-- Add current_repo_team column to batches table (for tracking current team)
ALTER TABLE batches 
ADD COLUMN IF NOT EXISTS current_repo_team TEXT;

-- Add error_message column to batches table
ALTER TABLE batches 
ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Add comment
COMMENT ON COLUMN batches.completed_at IS 'Timestamp when the batch was completed';
COMMENT ON COLUMN batches.current_repo_url IS 'Currently processing repository URL';
COMMENT ON COLUMN batches.current_repo_team IS 'Currently processing team name';
COMMENT ON COLUMN batches.error_message IS 'Error message if batch processing failed';
