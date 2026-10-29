-- ============================================================
-- EXPORT REPORT_JSON TO FILE FOR BACKUP
-- ============================================================
-- Run this in Supabase SQL Editor to export data
-- Then you can save it as a JSON file for backup

-- Option 1: Get all teams with report_json as JSON array
SELECT json_agg(
    json_build_object(
        'team_id', id,
        'team_name', team_name,
        'report_json', report_json
    )
) as all_reports
FROM teams 
WHERE report_json IS NOT NULL;

-- Option 2: Export one team at a time (safer for large data)
-- Change the team_id to export specific teams
SELECT 
    id as team_id,
    team_name,
    report_json
FROM teams 
WHERE report_json IS NOT NULL
LIMIT 10;

-- Option 3: Get count and size estimate
SELECT 
    COUNT(*) as teams_with_json,
    SUM(pg_column_size(report_json)) / 1024 / 1024 as total_json_size_mb
FROM teams 
WHERE report_json IS NOT NULL;


-- ============================================================
-- BACKUP TO SEPARATE TABLE (PRESERVES DATA IN DATABASE)
-- ============================================================
-- Creates a backup table before migration
-- This keeps old data in database as backup

-- Step 1: Create backup table
CREATE TABLE IF NOT EXISTS teams_report_backup (
    team_id UUID PRIMARY KEY,
    team_name TEXT,
    report_json JSONB,
    backed_up_at TIMESTAMP DEFAULT NOW()
);

-- Step 2: Copy all report_json to backup
INSERT INTO teams_report_backup (team_id, team_name, report_json)
SELECT id, team_name, report_json
FROM teams
WHERE report_json IS NOT NULL
ON CONFLICT (team_id) DO UPDATE SET
    report_json = EXCLUDED.report_json,
    backed_up_at = NOW();

-- Step 3: Verify backup
SELECT 
    COUNT(*) as backed_up_teams,
    SUM(pg_column_size(report_json)) / 1024 / 1024 as backup_size_mb
FROM teams_report_backup;

-- Step 4: NOW you can safely clear report_json from teams table
-- (Only after verifying backup exists)
UPDATE teams SET report_json = NULL WHERE report_json IS NOT NULL;

-- Step 5: Reclaim space
VACUUM teams;


-- ============================================================
-- RESTORE FROM BACKUP (If needed)
-- ============================================================
-- Use this to restore report_json if something goes wrong

UPDATE teams t
SET report_json = b.report_json
FROM teams_report_backup b
WHERE t.id = b.team_id;
