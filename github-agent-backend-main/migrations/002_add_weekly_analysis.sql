-- Migration: Add weekly batch analysis tracking
-- Date: 2026-01-18
-- Description: Adds repo_url to teams, batch_analysis_runs, analysis_snapshots tables

-- ==================== ADD REPO_URL TO TEAMS ====================
ALTER TABLE teams ADD COLUMN IF NOT EXISTS repo_url VARCHAR(500);
CREATE INDEX IF NOT EXISTS idx_teams_repo_url ON teams(repo_url);

-- ==================== ADD MENTOR METADATA TO USERS ====================
ALTER TABLE users ADD COLUMN IF NOT EXISTS max_teams INTEGER DEFAULT 5;
ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(100);

-- ==================== BATCH ANALYSIS RUNS TABLE ====================
-- Tracks each weekly analysis run for a batch
CREATE TABLE IF NOT EXISTS batch_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    total_teams INTEGER DEFAULT 0,
    completed_teams INTEGER DEFAULT 0,
    failed_teams INTEGER DEFAULT 0,
    avg_score FLOAT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT unique_batch_run UNIQUE (batch_id, run_number)
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_batch_runs_batch_id ON batch_analysis_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_analysis_runs(status);
CREATE INDEX IF NOT EXISTS idx_batch_runs_run_number ON batch_analysis_runs(run_number);

-- ==================== ANALYSIS SNAPSHOTS TABLE ====================
-- Stores weekly analysis results per team
CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    batch_run_id UUID NOT NULL REFERENCES batch_analysis_runs(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_number INTEGER NOT NULL,
    
    -- Scores from analysis
    total_score FLOAT,
    originality_score FLOAT,
    quality_score FLOAT,
    security_score FLOAT,
    effort_score FLOAT,
    implementation_score FLOAT,
    engineering_score FLOAT,
    organization_score FLOAT,
    documentation_score FLOAT,
    
    -- Metadata
    commit_count INTEGER,
    file_count INTEGER,
    lines_of_code INTEGER,
    tech_stack_count INTEGER,
    issue_count INTEGER,
    
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_team_run UNIQUE (team_id, run_number)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_snapshots_team_id ON analysis_snapshots(team_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON analysis_snapshots(batch_run_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_run_number ON analysis_snapshots(run_number);
CREATE INDEX IF NOT EXISTS idx_snapshots_project_id ON analysis_snapshots(project_id);

-- ==================== UPDATE EXISTING TABLES ====================

-- Add batch_id to projects if not exists (for filtering)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'batch_id'
    ) THEN
        ALTER TABLE projects ADD COLUMN batch_id UUID REFERENCES batches(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_projects_batch_id ON projects(batch_id);
    END IF;
END $$;

-- ==================== HELPER FUNCTIONS ====================

-- Function to get current week number for a batch
CREATE OR REPLACE FUNCTION get_batch_current_week(batch_uuid UUID)
RETURNS INTEGER AS $$
DECLARE
    batch_start TIMESTAMP WITH TIME ZONE;
    weeks_elapsed INTEGER;
BEGIN
    SELECT start_date INTO batch_start FROM batches WHERE id = batch_uuid;
    
    IF batch_start IS NULL THEN
        RETURN 0;
    END IF;
    
    weeks_elapsed := EXTRACT(EPOCH FROM (NOW() - batch_start))::INTEGER / 604800; -- seconds in a week
    RETURN weeks_elapsed + 1; -- Week 1, 2, 3...
END;
$$ LANGUAGE plpgsql;

-- Function to calculate team improvement from previous week
CREATE OR REPLACE FUNCTION get_team_improvement(team_uuid UUID, current_run INTEGER)
RETURNS FLOAT AS $$
DECLARE
    current_score FLOAT;
    previous_score FLOAT;
BEGIN
    SELECT total_score INTO current_score 
    FROM analysis_snapshots 
    WHERE team_id = team_uuid AND run_number = current_run;
    
    SELECT total_score INTO previous_score 
    FROM analysis_snapshots 
    WHERE team_id = team_uuid AND run_number = current_run - 1;
    
    IF current_score IS NULL OR previous_score IS NULL THEN
        RETURN 0;
    END IF;
    
    RETURN current_score - previous_score;
END;
$$ LANGUAGE plpgsql;

-- ==================== COMMENTS ====================
COMMENT ON TABLE batch_analysis_runs IS 'Weekly analysis runs for batches';
COMMENT ON TABLE analysis_snapshots IS 'Historical snapshots of team analysis results';
COMMENT ON COLUMN teams.repo_url IS 'GitHub repository URL for the team';
COMMENT ON COLUMN users.max_teams IS 'Maximum teams a mentor can handle';
COMMENT ON COLUMN users.department IS 'Department/area of the mentor';
