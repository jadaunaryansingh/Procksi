-- =====================================================
-- STEP 1: Clear All Existing Team Data
-- =====================================================
-- Run this first to clean up existing data
-- This will preserve users and evaluation parameters

-- Delete in order to respect foreign key constraints
DELETE FROM evaluation_drafts WHERE team_id IS NOT NULL;
DELETE FROM evaluations WHERE team_id IS NOT NULL;
DELETE FROM alerts WHERE team_id IS NOT NULL;
DELETE FROM github_data;
DELETE FROM slots;
DELETE FROM projects;
DELETE FROM teams;

-- Reset auto-increment sequences if needed
-- ALTER SEQUENCE teams_id_seq RESTART WITH 101;

-- Verify cleanup
SELECT 'Teams deleted:' as step, COUNT(*) as count FROM teams
UNION ALL
SELECT 'Projects deleted:' as step, COUNT(*) as count FROM projects
UNION ALL
SELECT 'Slots deleted:' as step, COUNT(*) as count FROM slots
UNION ALL
SELECT 'Evaluations deleted:' as step, COUNT(*) as count FROM evaluations;