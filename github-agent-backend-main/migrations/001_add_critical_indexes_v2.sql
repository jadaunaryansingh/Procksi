-- Migration: Add Critical Database Indexes (TRANSACTION-SAFE VERSION)
-- Purpose: Fix missing indexes causing full table scans
-- Expected Impact: 90-95% query speedup on filtered queries
-- Run with: psql $DATABASE_URL -f migrations/001_add_critical_indexes_v2.sql

-- NOTE: This version removes CONCURRENTLY to allow transaction execution
-- Safe for small-medium tables (<10,000 rows)
-- For large tables, use the individual commands version (001_add_critical_indexes_separate.sql)

BEGIN;

-- ============================================================
-- CRITICAL INDEXES FOR TEAMS TABLE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_teams_mentor_id 
ON teams(mentor_id)
WHERE mentor_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_teams_batch_id 
ON teams(batch_id)
WHERE batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_teams_status 
ON teams(status);

CREATE INDEX IF NOT EXISTS idx_teams_batch_status 
ON teams(batch_id, status)
WHERE batch_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_teams_last_analyzed 
ON teams(last_analyzed_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_teams_created_at 
ON teams(created_at DESC);

-- ============================================================
-- INDEXES FOR ANALYSIS_JOBS TABLE
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_team_id 
ON analysis_jobs(team_id);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status 
ON analysis_jobs(status);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_team_status 
ON analysis_jobs(team_id, status);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_started_at 
ON analysis_jobs(started_at DESC);

-- ============================================================
-- INDEXES FOR RELATED TABLES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_tech_stack_team_id 
ON tech_stack(team_id);

CREATE INDEX IF NOT EXISTS idx_issues_team_id 
ON issues(team_id);

CREATE INDEX IF NOT EXISTS idx_issues_severity 
ON issues(severity);

CREATE INDEX IF NOT EXISTS idx_issues_type 
ON issues(type);

CREATE INDEX IF NOT EXISTS idx_team_members_team_id 
ON team_members(team_id);

CREATE INDEX IF NOT EXISTS idx_students_team_id 
ON students(team_id);

CREATE INDEX IF NOT EXISTS idx_students_email 
ON students(email);

CREATE INDEX IF NOT EXISTS idx_mentor_assignments_mentor_id 
ON mentor_team_assignments(mentor_id);

CREATE INDEX IF NOT EXISTS idx_mentor_assignments_team_id 
ON mentor_team_assignments(team_id);

CREATE INDEX IF NOT EXISTS idx_batches_status 
ON batches(status);

COMMIT;

-- ============================================================
-- VERIFY INDEXES CREATED
-- ============================================================

SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public' 
    AND tablename IN ('teams', 'analysis_jobs', 'tech_stack', 'issues', 'team_members', 'students', 'mentor_team_assignments', 'batches')
ORDER BY tablename, indexname;
