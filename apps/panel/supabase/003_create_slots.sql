-- =====================================================
-- STEP 3: Create Slots with Different Statuses
-- =====================================================
-- 15-team distribution for Panel P01:
-- Submitted: 2, Active: 3, Upcoming: 4, Missed: 4, Unassigned: 2

-- Pre-check: run this SELECT first. If it returns any rows, run 002_create_teams_and_projects.sql before this file.
SELECT v.team_id AS missing_team_id
FROM (VALUES (101),(102),(103),(104),(105),(106),(107),(108),(109),(110),(111),(112),(113),(114),(115)) AS v(team_id)
LEFT JOIN teams t ON t.id = v.team_id
WHERE t.id IS NULL;

-- ==========================================
-- SUBMITTED TEAMS (2) - Past slots with completed evaluations
-- ==========================================

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 101, 'Lab 101', '09:00 AM - 09:15 AM', NOW() - INTERVAL '2 days' + INTERVAL '9 hours', NOW() - INTERVAL '2 days' + INTERVAL '9.25 hours', 'Submitted');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 103, 'Lab 101', '11:00 AM - 11:15 AM', NOW() - INTERVAL '2 days' + INTERVAL '11 hours', NOW() - INTERVAL '2 days' + INTERVAL '11.25 hours', 'Submitted');

-- ==========================================
-- ACTIVE TEAMS (3) - Ongoing right now
-- ==========================================

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 104, 'Table 1', 'Current Slot A', NOW() - INTERVAL '8 minutes', NOW() + INTERVAL '7 minutes', 'Active');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 105, 'Table 2', 'Current Slot B', NOW() - INTERVAL '5 minutes', NOW() + INTERVAL '10 minutes', 'Active');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 106, 'Table 3', 'Current Slot C', NOW() - INTERVAL '2 minutes', NOW() + INTERVAL '13 minutes', 'Active');

-- ==========================================
-- UPCOMING TEAMS (4) - Future windows
-- ==========================================

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 111, 'Conference Room A', '01:00 PM - 01:15 PM', NOW() + INTERVAL '35 minutes', NOW() + INTERVAL '50 minutes', 'Upcoming');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 112, 'Conference Room B', '01:20 PM - 01:35 PM', NOW() + INTERVAL '55 minutes', NOW() + INTERVAL '70 minutes', 'Upcoming');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 113, 'Lab 102', 'Tomorrow 10:00 AM - 10:15 AM', NOW() + INTERVAL '1 day' + INTERVAL '10 hours', NOW() + INTERVAL '1 day' + INTERVAL '10.25 hours', 'Upcoming');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 114, 'Lab 102', 'Tomorrow 10:20 AM - 10:35 AM', NOW() + INTERVAL '1 day' + INTERVAL '10.33 hours', NOW() + INTERVAL '1 day' + INTERVAL '10.58 hours', 'Upcoming');

-- ==========================================
-- MISSED TEAMS (4) - Past windows without submission
-- ==========================================

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 107, 'Lab 104', '10:00 AM - 10:15 AM', NOW() - INTERVAL '3 days' + INTERVAL '10 hours', NOW() - INTERVAL '3 days' + INTERVAL '10.25 hours', 'Missed');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 108, 'Lab 104', '10:20 AM - 10:35 AM', NOW() - INTERVAL '3 days' + INTERVAL '10.33 hours', NOW() - INTERVAL '3 days' + INTERVAL '10.58 hours', 'Missed');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 109, 'Conference Room C', '11:00 AM - 11:15 AM', NOW() - INTERVAL '4 days' + INTERVAL '11 hours', NOW() - INTERVAL '4 days' + INTERVAL '11.25 hours', 'Missed');

INSERT INTO slots (panel_id, team_id, venue, slot_label, window_start, window_end, status) VALUES
('P01', 110, 'Conference Room C', '11:20 AM - 11:35 AM', NOW() - INTERVAL '4 days' + INTERVAL '11.33 hours', NOW() - INTERVAL '4 days' + INTERVAL '11.58 hours', 'Missed');

-- Note: Teams 102 and 115 are intentionally left unassigned.

-- Verify slots created
SELECT
    status,
    COUNT(*) as count,
    STRING_AGG(CONCAT('Team ', team_id), ', ') as teams
FROM slots
WHERE panel_id = 'P01'
GROUP BY status
ORDER BY
    CASE status
        WHEN 'Submitted' THEN 1
        WHEN 'Upcoming' THEN 2
        WHEN 'Active' THEN 3
        WHEN 'Missed' THEN 4
    END;