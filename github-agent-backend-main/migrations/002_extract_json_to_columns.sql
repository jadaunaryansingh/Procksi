-- Migration: Add Additional Columns for JSON Field Extraction
-- Purpose: Extract frequently accessed fields from report_json to columns
-- Expected Impact: Eliminate JSON parsing for common queries

-- ============================================================
-- ADD NEW COLUMNS TO TEAMS TABLE
-- ============================================================

-- AI percentage (frequently queried in reports)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS ai_percentage FLOAT DEFAULT 0;

-- Security issues count (for quick filtering)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS security_issues_count INT DEFAULT 0;

-- Commit count (already exists as total_commits, but ensure it's there)
-- ALTER TABLE teams ADD COLUMN IF NOT EXISTS total_commits INT DEFAULT 0;

-- Last commit date (for activity tracking)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS last_commit_date TIMESTAMP;

-- Report storage path (for new storage system)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS report_path TEXT;

-- Report size (for monitoring)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS report_size INT;

-- Frameworks as array (for quick access)
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS frameworks TEXT[];

-- High severity security issues count
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS high_severity_issues INT DEFAULT 0;

-- Medium severity security issues count
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS medium_severity_issues INT DEFAULT 0;

-- Branch count
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS branch_count INT DEFAULT 0;

-- ============================================================
-- CREATE INDEXES ON NEW COLUMNS
-- ============================================================

-- Index for AI percentage queries (e.g., teams with high AI usage)
CREATE INDEX IF NOT EXISTS idx_teams_ai_percentage 
ON teams(ai_percentage) 
WHERE ai_percentage > 0;

-- Index for security issues (e.g., teams with security problems)
CREATE INDEX IF NOT EXISTS idx_teams_security_issues 
ON teams(security_issues_count) 
WHERE security_issues_count > 0;

-- Index for last commit date (for activity queries)
CREATE INDEX IF NOT EXISTS idx_teams_last_commit_date 
ON teams(last_commit_date DESC NULLS LAST);

-- Index for high severity issues
CREATE INDEX IF NOT EXISTS idx_teams_high_severity 
ON teams(high_severity_issues) 
WHERE high_severity_issues > 0;

-- ============================================================
-- BACKFILL DATA FROM EXISTING REPORT_JSON
-- ============================================================

-- This script extracts data from report_json and populates the new columns
-- Run after adding columns to populate existing data

-- Update AI percentage
UPDATE teams 
SET ai_percentage = (report_json->>'aiGeneratedPercentage')::float
WHERE report_json IS NOT NULL 
  AND report_json->>'aiGeneratedPercentage' IS NOT NULL;

-- Update security issues count
UPDATE teams 
SET security_issues_count = jsonb_array_length(
    COALESCE(report_json->'securityIssues', '[]'::jsonb)
)
WHERE report_json IS NOT NULL 
  AND report_json->'securityIssues' IS NOT NULL;

-- Update frameworks array
UPDATE teams 
SET frameworks = ARRAY(
    SELECT jsonb_array_elements_text(report_json->'frameworks')
)
WHERE report_json IS NOT NULL 
  AND report_json->'frameworks' IS NOT NULL;

-- Update last commit date (from commit_details if available)
UPDATE teams 
SET last_commit_date = (report_json->'commit_details'->>'last_commit_date')::timestamp
WHERE report_json IS NOT NULL 
  AND report_json->'commit_details'->>'last_commit_date' IS NOT NULL;

-- Update branch count
UPDATE teams 
SET branch_count = (report_json->'commit_details'->>'branch_count')::int
WHERE report_json IS NOT NULL 
  AND report_json->'commit_details'->>'branch_count' IS NOT NULL;

-- ============================================================
-- VERIFY MIGRATION
-- ============================================================

-- Check how many rows were updated
SELECT 
    COUNT(*) FILTER (WHERE ai_percentage > 0) as teams_with_ai_data,
    COUNT(*) FILTER (WHERE security_issues_count > 0) as teams_with_security_issues,
    COUNT(*) FILTER (WHERE frameworks IS NOT NULL) as teams_with_frameworks,
    COUNT(*) FILTER (WHERE last_commit_date IS NOT NULL) as teams_with_commit_dates,
    COUNT(*) FILTER (WHERE report_path IS NOT NULL) as teams_migrated_to_storage,
    COUNT(*) as total_teams
FROM teams;

-- Sample query showing new columns
SELECT 
    team_name,
    total_score,
    ai_percentage,
    security_issues_count,
    high_severity_issues,
    branch_count,
    last_commit_date,
    report_path
FROM teams 
WHERE status = 'completed'
LIMIT 10;

-- ============================================================
-- NOTES
-- ============================================================
-- 1. Run backfill queries during low-traffic hours
-- 2. Monitor query performance before/after
-- 3. After migration, update data_mapper.py to populate these columns
-- 4. Eventually remove report_json column after confirming storage migration works
