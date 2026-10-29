-- ============================================================
-- OPTION 1: SIMPLE CLEANUP (Fastest - Just Delete Old JSON)
-- ============================================================
-- Use this if you DON'T need old report data preserved
-- This immediately frees up 300-400MB of database space
-- New analyses will save to storage automatically

-- Check current size first
SELECT 
    COUNT(*) as total_teams,
    COUNT(*) FILTER (WHERE report_json IS NOT NULL) as teams_with_json,
    COUNT(*) FILTER (WHERE report_path IS NOT NULL) as teams_with_storage_path
FROM teams;

-- Option 1A: Just NULL out report_json (FASTEST)
-- Keeps all scores, columns, etc. - only removes the large JSON blob
UPDATE teams 
SET report_json = NULL 
WHERE report_json IS NOT NULL;

-- Verify
SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;


-- ============================================================
-- OPTION 2: EXTRACT KEY DATA THEN DELETE (Recommended)
-- ============================================================
-- Extracts important fields to columns BEFORE deleting JSON
-- Run this if columns don't have data yet

-- Step 1: Backfill columns from report_json
UPDATE teams 
SET 
    ai_percentage = COALESCE(
        (report_json->'judge'->>'aiGeneratedPercentage')::float,
        ai_percentage,
        0
    ),
    security_issues_count = COALESCE(
        jsonb_array_length(report_json->'security'->'issues'),
        security_issues_count,
        0
    ),
    branch_count = COALESCE(
        (report_json->'commit_details'->>'branch_count')::int,
        jsonb_array_length(report_json->'commit_details'->'branches'),
        branch_count,
        0
    )
WHERE report_json IS NOT NULL 
  AND report_json != 'null'::jsonb;

-- Step 2: Now safely delete report_json
UPDATE teams 
SET report_json = NULL 
WHERE report_json IS NOT NULL;

-- Step 3: Verify columns have data
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE ai_percentage > 0) as with_ai_pct,
    COUNT(*) FILTER (WHERE security_issues_count > 0) as with_security,
    COUNT(*) FILTER (WHERE branch_count > 0) as with_branches
FROM teams;


-- ============================================================
-- OPTION 3: VACUUM (After any deletion - reclaim space)
-- ============================================================
-- Run AFTER deleting report_json to reclaim disk space

VACUUM FULL teams;
-- OR for less locking:
VACUUM teams;

-- Check new size
SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;


-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================

-- Check database size before/after
SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;

-- Check table sizes
SELECT 
    relname as table_name,
    pg_size_pretty(pg_total_relation_size(relid)) as total_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;

-- Check teams table specifically
SELECT 
    pg_size_pretty(pg_total_relation_size('teams')) as teams_total_size,
    pg_size_pretty(pg_relation_size('teams')) as teams_data_size;

-- Check how many teams still have report_json
SELECT 
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE report_json IS NOT NULL) as with_json,
    COUNT(*) FILTER (WHERE report_json IS NULL) as without_json
FROM teams;
