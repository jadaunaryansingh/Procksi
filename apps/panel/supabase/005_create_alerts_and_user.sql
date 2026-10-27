-- =====================================================
-- STEP 5: Create Alerts for Missed Teams & Panel User
-- =====================================================
-- Creates alerts for missed evaluations and ensures panel user exists

-- ==========================================
-- ALERTS FOR MISSED TEAMS (107-110)
-- ==========================================

INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 107, 'missed_evaluation', 'Missed Evaluation - Gridline AI', 'Team Gridline AI missed their scheduled evaluation window. Please coordinate a reschedule with administration.', NOW() - INTERVAL '3 days' + INTERVAL '10.3 hours');

INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 108, 'missed_evaluation', 'Missed Evaluation - Helix Coders', 'Team Helix Coders missed their scheduled evaluation window. Please coordinate a reschedule with administration.', NOW() - INTERVAL '3 days' + INTERVAL '10.6 hours');

INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 109, 'missed_evaluation', 'Missed Evaluation - Ion Innovators', 'Team Ion Innovators missed their scheduled evaluation window. Please coordinate a reschedule with administration.', NOW() - INTERVAL '4 days' + INTERVAL '11.3 hours');

INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 110, 'missed_evaluation', 'Missed Evaluation - Jupiter Labs', 'Team Jupiter Labs missed their scheduled evaluation window. Please coordinate a reschedule with administration.', NOW() - INTERVAL '4 days' + INTERVAL '11.6 hours');

-- ==========================================
-- CREATE EVALUATION PARAMETERS (if not exists)
-- ==========================================
-- Note: Run this only if evaluation_parameters table is empty

INSERT INTO evaluation_parameters (category, criterion_name, max_marks)
SELECT v.category, v.criterion_name, v.max_marks
FROM (
    VALUES
    ('Project Understanding', 'Conceptual Clarity', 10),
    ('Project Understanding', 'Problem Analysis', 10),
    ('Technical Implementation', 'Code Quality', 10),
    ('Technical Implementation', 'System Architecture', 10),
    ('Presentation Skills', 'Communication', 10),
    ('Presentation Skills', 'Demo Quality', 10),
    ('Documentation', 'Completeness', 10),
    ('Documentation', 'Clarity', 10)
) AS v(category, criterion_name, max_marks)
WHERE NOT EXISTS (
    SELECT 1
    FROM evaluation_parameters ep
    WHERE ep.category = v.category
      AND ep.criterion_name = v.criterion_name
);

-- ==========================================
-- CREATE/UPDATE PANEL USER
-- ==========================================
-- Note: Password hash for 'panel123' using bcrypt
-- You may need to adjust this based on your authentication system

INSERT INTO users (email, hashed_password, role, panel_id) VALUES
('panel01@example.edu', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBdXwtO8ZjPEPG', 'panel', 'P01')
ON CONFLICT (email) DO UPDATE SET
    role = EXCLUDED.role,
    panel_id = EXCLUDED.panel_id;

-- ==========================================
-- VERIFICATION QUERIES
-- ==========================================

-- Check alerts created
SELECT
    'Alerts for missed teams:' as info,
    COUNT(*) as count
FROM alerts
WHERE alert_type = 'missed_evaluation' AND panel_id = 'P01';

-- Check evaluation parameters
SELECT
    'Evaluation parameters:' as info,
    COUNT(*) as count
FROM evaluation_parameters;

-- Check panel user
SELECT
    'Panel user created:' as info,
    email,
    role,
    panel_id
FROM users
WHERE email = 'panel01@example.edu';

-- Final summary of all data
SELECT 'Data Summary' as category, '' as detail
UNION ALL
SELECT 'Teams created:', CAST(COUNT(*) AS TEXT) FROM teams
UNION ALL
SELECT 'Projects created:', CAST(COUNT(*) AS TEXT) FROM projects
UNION ALL
SELECT 'Slots created:', CAST(COUNT(*) AS TEXT) FROM slots
UNION ALL
SELECT 'Evaluations completed:', CAST(COUNT(*) AS TEXT) FROM evaluations
UNION ALL
SELECT 'Alerts created:', CAST(COUNT(*) AS TEXT) FROM alerts WHERE alert_type = 'missed_evaluation'
UNION ALL
SELECT 'GitHub data entries:', CAST(COUNT(*) AS TEXT) FROM github_data;