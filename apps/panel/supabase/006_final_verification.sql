-- =====================================================
-- FINAL: Verification and Summary Queries
-- =====================================================
-- Run these queries to verify everything is set up correctly

-- ==========================================
-- COMPLETE DATA SUMMARY
-- ==========================================

SELECT
    '=== TEAMS BY STATUS ===' as section,
    '' as team_id,
    '' as team_name,
    '' as status,
    '' as slot_time
UNION ALL
SELECT
    'SUBMITTED (2 teams)' as section,
    CAST(t.id AS TEXT) as team_id,
    t.name as team_name,
    s.status,
    s.slot_label as slot_time
FROM teams t
JOIN slots s ON t.id = s.team_id
WHERE s.status = 'Submitted' AND s.panel_id = 'P01'
UNION ALL
SELECT '', '', '', '', ''
UNION ALL
SELECT
    'UPCOMING (4 teams)' as section,
    CAST(t.id AS TEXT) as team_id,
    t.name as team_name,
    s.status,
    s.slot_label as slot_time
FROM teams t
JOIN slots s ON t.id = s.team_id
WHERE s.status = 'Upcoming' AND s.panel_id = 'P01'
UNION ALL
SELECT '', '', '', '', ''
UNION ALL
SELECT
    'ACTIVE (3 teams)' as section,
    CAST(t.id AS TEXT) as team_id,
    t.name as team_name,
    s.status,
    s.slot_label as slot_time
FROM teams t
JOIN slots s ON t.id = s.team_id
WHERE s.status = 'Active' AND s.panel_id = 'P01'
UNION ALL
SELECT '', '', '', '', ''
UNION ALL
SELECT
    'MISSED (4 teams)' as section,
    CAST(t.id AS TEXT) as team_id,
    t.name as team_name,
    s.status,
    s.slot_label as slot_time
FROM teams t
JOIN slots s ON t.id = s.team_id
WHERE s.status = 'Missed' AND s.panel_id = 'P01'
UNION ALL
SELECT '', '', '', '', ''
UNION ALL
SELECT
    'UNASSIGNED (2 teams)' as section,
    CAST(t.id AS TEXT) as team_id,
    t.name as team_name,
    'No slot assigned' as status,
    '' as slot_time
FROM teams t
WHERE t.id NOT IN (SELECT team_id FROM slots WHERE panel_id = 'P01')
ORDER BY section, team_id;

-- ==========================================
-- DASHBOARD STATISTICS
-- ==========================================

SELECT
    'PANEL DASHBOARD STATS' as metric,
    '' as value
UNION ALL
SELECT 'Total Teams:', CAST(COUNT(*) AS TEXT) FROM teams
UNION ALL
SELECT 'Teams with Slots:', CAST(COUNT(DISTINCT team_id) AS TEXT) FROM slots WHERE panel_id = 'P01'
UNION ALL
SELECT 'Completed Evaluations:', CAST(COUNT(*) AS TEXT) FROM evaluations WHERE panel_id = 'P01'
UNION ALL
SELECT 'Active Slots:', CAST(COUNT(*) AS TEXT) FROM slots WHERE status = 'Active' AND panel_id = 'P01'
UNION ALL
SELECT 'Upcoming Slots:', CAST(COUNT(*) AS TEXT) FROM slots WHERE status = 'Upcoming' AND panel_id = 'P01'
UNION ALL
SELECT 'Missed Evaluations:', CAST(COUNT(*) AS TEXT) FROM slots WHERE status = 'Missed' AND panel_id = 'P01'
UNION ALL
SELECT 'Unassigned Teams:', CAST(COUNT(*) AS TEXT) FROM teams WHERE id NOT IN (SELECT team_id FROM slots WHERE panel_id = 'P01');

-- ==========================================
-- LOGIN CREDENTIALS
-- ==========================================

SELECT
    '=== LOGIN INFORMATION ===' as info,
    '' as value
UNION ALL
SELECT 'Email:', 'panel01@gla.ac.in'
UNION ALL
SELECT 'Password:', 'panel123'
UNION ALL
SELECT 'Panel ID:', 'P01'
UNION ALL
SELECT 'Role:', 'panel'
UNION ALL
SELECT '', ''
UNION ALL
SELECT '=== TESTING SCENARIOS ===' as info, '' as value
UNION ALL
SELECT '1. Dashboard:', 'Should show 3 active slots, progress tracker'
UNION ALL
SELECT '2. My Slots:', 'List all teams with status badges'
UNION ALL
SELECT '3. Active Evaluation:', 'Try evaluating teams 111, 112, or 113'
UNION ALL
SELECT '4. Missed Submissions:', 'See 4 teams, test reschedule requests'
UNION ALL
SELECT '5. Parameters:', 'View evaluation rubric and scoring criteria';