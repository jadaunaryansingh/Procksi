-- Migration: Add Analysis Columns to Teams Table
-- This SQL script adds all analysis-related columns from the projects table to the teams table
-- Run this BEFORE executing migrate_projects_to_teams.py

-- Add analysis status column
ALTER TABLE teams ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';

-- Add analysis score columns
ALTER TABLE teams ADD COLUMN IF NOT EXISTS total_score FLOAT CHECK (total_score >= 0 AND total_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS quality_score FLOAT CHECK (quality_score >= 0 AND quality_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS security_score FLOAT CHECK (security_score >= 0 AND security_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS originality_score FLOAT CHECK (originality_score >= 0 AND originality_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS architecture_score FLOAT CHECK (architecture_score >= 0 AND architecture_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS documentation_score FLOAT CHECK (documentation_score >= 0 AND documentation_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS effort_score FLOAT CHECK (effort_score >= 0 AND effort_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS implementation_score FLOAT CHECK (implementation_score >= 0 AND implementation_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS engineering_score FLOAT CHECK (engineering_score >= 0 AND engineering_score <= 100);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS organization_score FLOAT CHECK (organization_score >= 0 AND organization_score <= 100);

-- Add analysis metadata columns
ALTER TABLE teams ADD COLUMN IF NOT EXISTS total_commits INTEGER DEFAULT 0;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS verdict TEXT;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS ai_pros TEXT[];
ALTER TABLE teams ADD COLUMN IF NOT EXISTS ai_cons TEXT[];
ALTER TABLE teams ADD COLUMN IF NOT EXISTS report_json JSONB;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS report_path VARCHAR(500);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS viz_path VARCHAR(500);
ALTER TABLE teams ADD COLUMN IF NOT EXISTS description TEXT;

-- Add timestamp columns
ALTER TABLE teams ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE teams ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);
CREATE INDEX IF NOT EXISTS idx_teams_total_score ON teams(total_score DESC) WHERE total_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_teams_analyzed_at ON teams(analyzed_at DESC) WHERE analyzed_at IS NOT NULL;

-- Add comment to document the migration
COMMENT ON COLUMN teams.status IS 'Analysis status: pending, analyzing, completed, failed';
COMMENT ON COLUMN teams.total_score IS 'Overall analysis score (0-100)';
COMMENT ON COLUMN teams.analyzed_at IS 'Timestamp of last analysis completion';

-- Verify columns were added
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'teams'
AND column_name IN (
    'status', 'total_score', 'quality_score', 'security_score',
    'originality_score', 'architecture_score', 'documentation_score',
    'effort_score', 'implementation_score', 'engineering_score',
    'organization_score', 'total_commits', 'verdict', 'ai_pros',
    'ai_cons', 'report_json', 'report_path', 'viz_path',
    'description', 'analyzed_at', 'last_analyzed_at'
)
ORDER BY column_name;
