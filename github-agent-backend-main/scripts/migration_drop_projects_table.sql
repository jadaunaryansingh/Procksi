-- Migration: Drop Projects Table
-- This SQL script drops the projects table after successful data migration
-- Run this AFTER executing migrate_projects_to_teams.py and verifying data integrity

-- First, drop all foreign key constraints that reference the projects table
-- Note: CASCADE will automatically drop dependent objects

-- Drop the projects table and all its dependencies
DROP TABLE IF EXISTS projects CASCADE;

-- Verify the table was dropped
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name = 'projects';

-- This should return no rows if the table was successfully dropped

-- Optional: Clean up any remaining project_id columns in other tables
-- (These should have been migrated to team_id by the Python script)

-- Check for any remaining project_id columns
SELECT 
    table_name,
    column_name
FROM information_schema.columns
WHERE table_schema = 'public'
AND column_name = 'project_id'
ORDER BY table_name;

-- If any tables still have project_id columns, you may want to drop them:
-- ALTER TABLE team_members DROP COLUMN IF EXISTS project_id;
-- ALTER TABLE analysis_jobs DROP COLUMN IF EXISTS project_id;
-- ALTER TABLE tech_stack DROP COLUMN IF EXISTS project_id;
-- ALTER TABLE issues DROP COLUMN IF EXISTS project_id;
-- ALTER TABLE project_comments DROP COLUMN IF EXISTS project_id;
-- ALTER TABLE analysis_snapshots DROP COLUMN IF EXISTS project_id;

-- Note: Uncomment the above ALTER TABLE statements only after verifying
-- that all data has been successfully migrated to use team_id instead
