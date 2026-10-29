-- =====================================================
-- Migration: Add batches table for sequential processing
-- =====================================================
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS batches (
    id UUID PRIMARY KEY,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    total_repos INTEGER NOT NULL,
    completed_repos INTEGER DEFAULT 0,
    failed_repos INTEGER DEFAULT 0,
    current_index INTEGER DEFAULT 0,
    current_repo_url TEXT,
    current_repo_team TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Index for status queries
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_created_at ON batches(created_at DESC);

-- Add batch_id column to analysis_jobs for tracking
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS batch_id UUID REFERENCES batches(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_batch ON analysis_jobs(batch_id);
