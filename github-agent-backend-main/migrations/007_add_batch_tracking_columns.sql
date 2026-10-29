-- Migration: Add batch tracking columns for progress monitoring
-- Date: 2026-01-19
-- Purpose: Add columns for tracking batch analysis progress in real-time

-- Add tracking columns to batches table
DO $$
BEGIN
    -- Add current_index for tracking which repo is being processed
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'current_index'
    ) THEN
        ALTER TABLE batches ADD COLUMN current_index INTEGER DEFAULT 0;
        COMMENT ON COLUMN batches.current_index IS 'Current repository index being processed (0-based)';
    END IF;

    -- Add completed_repos counter
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'completed_repos'
    ) THEN
        ALTER TABLE batches ADD COLUMN completed_repos INTEGER DEFAULT 0;
        COMMENT ON COLUMN batches.completed_repos IS 'Number of repositories successfully analyzed';
    END IF;

    -- Add failed_repos counter
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'failed_repos'
    ) THEN
        ALTER TABLE batches ADD COLUMN failed_repos INTEGER DEFAULT 0;
        COMMENT ON COLUMN batches.failed_repos IS 'Number of repositories that failed analysis';
    END IF;
END $$;

-- Add metadata column to batch_analysis_runs for storing run-specific data
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batch_analysis_runs' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE batch_analysis_runs ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
        COMMENT ON COLUMN batch_analysis_runs.metadata IS 'Additional run metadata (celery task IDs, timing info, etc.)';
        
        -- Create GIN index for JSONB queries
        CREATE INDEX IF NOT EXISTS idx_batch_runs_metadata ON batch_analysis_runs USING GIN (metadata);
    END IF;
END $$;

-- Verify additions
DO $$
DECLARE
    missing_cols TEXT[] := ARRAY[]::TEXT[];
BEGIN
    -- Check batches table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'batches' AND column_name = 'current_index') THEN
        missing_cols := array_append(missing_cols, 'batches.current_index');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'batches' AND column_name = 'completed_repos') THEN
        missing_cols := array_append(missing_cols, 'batches.completed_repos');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'batches' AND column_name = 'failed_repos') THEN
        missing_cols := array_append(missing_cols, 'batches.failed_repos');
    END IF;
    
    -- Check batch_analysis_runs table
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'batch_analysis_runs' AND column_name = 'metadata') THEN
        missing_cols := array_append(missing_cols, 'batch_analysis_runs.metadata');
    END IF;
    
    IF array_length(missing_cols, 1) > 0 THEN
        RAISE WARNING 'Migration incomplete. Missing columns: %', array_to_string(missing_cols, ', ');
    ELSE
        RAISE NOTICE '✅ Migration 007 completed successfully. All batch tracking columns added.';
    END IF;
END $$;
