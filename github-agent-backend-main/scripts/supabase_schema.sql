-- =====================================================
-- Supabase Database Schema for Repository Analysis
-- =====================================================
-- Run this in Supabase SQL Editor

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================
-- Table: projects
-- =====================================================
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_url TEXT UNIQUE NOT NULL,
    team_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    analyzed_at TIMESTAMP WITH TIME ZONE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'analyzing', 'completed', 'failed')),
    
    -- Scores (0-100)
    total_score FLOAT CHECK (total_score >= 0 AND total_score <= 100),
    originality_score FLOAT CHECK (originality_score >= 0 AND originality_score <= 100),
    quality_score FLOAT CHECK (quality_score >= 0 AND quality_score <= 100),
    security_score FLOAT CHECK (security_score >= 0 AND security_score <= 100),
    effort_score FLOAT CHECK (effort_score >= 0 AND effort_score <= 100),
    implementation_score FLOAT CHECK (implementation_score >= 0 AND implementation_score <= 100),
    engineering_score FLOAT CHECK (engineering_score >= 0 AND engineering_score <= 100),
    organization_score FLOAT CHECK (organization_score >= 0 AND organization_score <= 100),
    documentation_score FLOAT CHECK (documentation_score >= 0 AND documentation_score <= 100),
    
    -- Metadata
    total_commits INTEGER,
    verdict TEXT,
    ai_pros TEXT,
    ai_cons TEXT,
    report_json JSONB,
    viz_url TEXT
);

-- =====================================================
-- Table: analysis_jobs
-- =====================================================
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    current_stage TEXT,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- =====================================================
-- Table: tech_stack
-- =====================================================
CREATE TABLE IF NOT EXISTS tech_stack (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    technology TEXT NOT NULL,
    category TEXT CHECK (category IN ('language', 'framework', 'database', 'tool', NULL))
);

-- =====================================================
-- Table: issues
-- =====================================================
CREATE TABLE IF NOT EXISTS issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('security', 'quality', 'plagiarism', 'other')),
    severity TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
    file_path TEXT,
    description TEXT NOT NULL,
    ai_probability FLOAT CHECK (ai_probability >= 0 AND ai_probability <= 1),
    plagiarism_score FLOAT CHECK (plagiarism_score >= 0 AND plagiarism_score <= 1)
);

-- =====================================================
-- Table: team_members
-- =====================================================
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    commits INTEGER NOT NULL DEFAULT 0,
    contribution_pct FLOAT CHECK (contribution_pct >= 0 AND contribution_pct <= 100)
);

-- =====================================================
-- Indexes for Performance
-- =====================================================
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_total_score ON projects(total_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_analyzed_at ON projects(analyzed_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_projects_team_name ON projects(team_name);

CREATE INDEX IF NOT EXISTS idx_jobs_project ON analysis_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);

CREATE INDEX IF NOT EXISTS idx_tech_stack_project ON tech_stack(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_project ON issues(project_id);
CREATE INDEX IF NOT EXISTS idx_issues_severity ON issues(severity);
CREATE INDEX IF NOT EXISTS idx_team_members_project ON team_members(project_id);

-- =====================================================
-- Row Level Security (Optional - for future auth)
-- =====================================================
-- ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE tech_stack ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE issues ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;

-- =====================================================
-- Views for Common Queries
-- =====================================================

-- View: Completed projects with scores
CREATE OR REPLACE VIEW completed_projects AS
SELECT 
    p.*,
    COUNT(DISTINCT ts.id) as tech_count,
    COUNT(DISTINCT i.id) FILTER (WHERE i.severity = 'high') as high_issues_count,
    COUNT(DISTINCT tm.id) as team_size
FROM projects p
LEFT JOIN tech_stack ts ON p.id = ts.project_id
LEFT JOIN issues i ON p.id = i.project_id
LEFT JOIN team_members tm ON p.id = tm.project_id
WHERE p.status = 'completed'
GROUP BY p.id;

-- View: Leaderboard
CREATE OR REPLACE VIEW leaderboard AS
SELECT 
    ROW_NUMBER() OVER (ORDER BY total_score DESC NULLS LAST) as rank,
    id,
    repo_url,
    team_name,
    total_score,
    originality_score,
    quality_score,
    security_score,
    implementation_score,
    verdict,
    analyzed_at,
    total_commits
FROM projects
WHERE status = 'completed' AND total_score IS NOT NULL
ORDER BY total_score DESC;

-- =====================================================
-- Functions
-- =====================================================

-- Function: Calculate total score from individual scores
CREATE OR REPLACE FUNCTION calculate_total_score(
    p_originality FLOAT,
    p_quality FLOAT,
    p_security FLOAT,
    p_effort FLOAT,
    p_implementation FLOAT,
    p_engineering FLOAT,
    p_organization FLOAT,
    p_documentation FLOAT
) RETURNS FLOAT AS $$
BEGIN
    -- Weighted average (adjust weights as needed)
    RETURN (
        COALESCE(p_originality, 0) * 0.20 +
        COALESCE(p_quality, 0) * 0.15 +
        COALESCE(p_security, 0) * 0.10 +
        COALESCE(p_effort, 0) * 0.10 +
        COALESCE(p_implementation, 0) * 0.25 +
        COALESCE(p_engineering, 0) * 0.10 +
        COALESCE(p_organization, 0) * 0.05 +
        COALESCE(p_documentation, 0) * 0.05
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- =====================================================
-- Seed Data (Optional - for testing)
-- =====================================================
-- INSERT INTO projects (repo_url, team_name, status) 
-- VALUES ('https://github.com/test/repo1', 'Test Team', 'pending');

-- =====================================================
-- Database Setup Complete
-- =====================================================
-- Next steps:
-- 1. Update .env with your Supabase credentials
-- 2. Run: pip install supabase postgrest
-- 3. Test connection with backend/database.py
