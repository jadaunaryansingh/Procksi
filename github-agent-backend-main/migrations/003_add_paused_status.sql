-- Migration: Add 'paused' status to batch_analysis_runs
-- Date: 2026-02-11
-- Description: Adds 'paused' as a valid status for batch analysis runs to support pause/resume functionality

-- Drop the existing constraint
ALTER TABLE batch_analysis_runs DROP CONSTRAINT IF EXISTS batch_analysis_runs_status_check;

-- Add the new constraint with 'paused' included
ALTER TABLE batch_analysis_runs 
ADD CONSTRAINT batch_analysis_runs_status_check 
CHECK (status IN ('pending', 'running', 'completed', 'failed', 'paused'));

-- Add metadata column if it doesn't exist (for storing pause/resume info)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batch_analysis_runs' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE batch_analysis_runs ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
        CREATE INDEX IF NOT EXISTS idx_batch_runs_metadata ON batch_analysis_runs USING gin(metadata);
    END IF;
END $$;

COMMENT ON CONSTRAINT batch_analysis_runs_status_check ON batch_analysis_runs IS 'Valid statuses: pending, running, completed, failed, paused';
