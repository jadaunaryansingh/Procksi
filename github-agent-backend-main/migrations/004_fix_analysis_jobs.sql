-- ==================== FIX ANALYSIS JOBS TABLE ====================
-- Add missing columns to analysis_jobs table

-- Add metadata column (JSONB for flexible storage)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'analysis_jobs' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE analysis_jobs ADD COLUMN metadata JSONB;
        COMMENT ON COLUMN analysis_jobs.metadata IS 'Additional metadata including batch_run_id, run_number, team_id';
    END IF;
END $$;

-- Add requested_by column
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'analysis_jobs' AND column_name = 'requested_by'
    ) THEN
        ALTER TABLE analysis_jobs ADD COLUMN requested_by UUID REFERENCES users(user_id);
        COMMENT ON COLUMN analysis_jobs.requested_by IS 'User who requested the analysis';
    END IF;
END $$;

-- Add team_id column for easier querying
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'analysis_jobs' AND column_name = 'team_id'
    ) THEN
        ALTER TABLE analysis_jobs ADD COLUMN team_id UUID REFERENCES teams(id) ON DELETE CASCADE;
        COMMENT ON COLUMN analysis_jobs.team_id IS 'Team associated with this job';
    END IF;
END $$;

-- Add run_number column for tracking weekly analysis runs
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'analysis_jobs' AND column_name = 'run_number'
    ) THEN
        ALTER TABLE analysis_jobs ADD COLUMN run_number INTEGER;
        COMMENT ON COLUMN analysis_jobs.run_number IS 'Weekly analysis run number';
    END IF;
END $$;

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_team_id ON analysis_jobs(team_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_batch_id ON analysis_jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_requested_by ON analysis_jobs(requested_by);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_run_number ON analysis_jobs(run_number);

-- Add GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_metadata ON analysis_jobs USING GIN (metadata);

COMMENT ON TABLE analysis_jobs IS 'Queue for repository analysis jobs';
