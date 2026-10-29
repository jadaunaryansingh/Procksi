-- RUN THIS IN SUPABASE DASHBOARD SQL EDITOR
-- Go to: https://supabase.com/dashboard/project/[your-project]/sql/new

-- Add metadata column (JSONB for flexible storage)
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Add requested_by column
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS requested_by UUID REFERENCES users(id);

-- Add team_id column for easier querying
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS team_id UUID REFERENCES teams(id) ON DELETE CASCADE;

-- Add run_number column for tracking weekly analysis runs
ALTER TABLE analysis_jobs ADD COLUMN IF NOT EXISTS run_number INTEGER;

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_team_id ON analysis_jobs(team_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_batch_id ON analysis_jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_requested_by ON analysis_jobs(requested_by);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_run_number ON analysis_jobs(run_number);

-- Add GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_metadata ON analysis_jobs USING GIN (metadata);

-- Verify the columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'analysis_jobs'
ORDER BY ordinal_position;
