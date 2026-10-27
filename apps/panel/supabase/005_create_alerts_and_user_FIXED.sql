-- =====================================================
-- STEP 5: Create Alerts for Missed Teams & Panel User (FIXED)
-- =====================================================
-- Creates alerts for missed evaluations and ensures panel user exists

-- ==========================================
-- ALERTS FOR MISSED TEAMS (114-117)
-- ==========================================

-- Team 114 - Xi Programmers (Missed)
INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 114, 'missed_evaluation', 'Missed Evaluation - Xi Programmers', 'Team Xi Programmers missed their evaluation slot scheduled for 10:00 AM - 10:30 AM. Please contact the administrator for rescheduling options.', NOW() - INTERVAL '5 days' + INTERVAL '10.5 hours' + INTERVAL '5 minutes');

-- Team 115 - Omicron Labs (Missed)
INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 115, 'missed_evaluation', 'Missed Evaluation - Omicron Labs', 'Team Omicron Labs missed their evaluation slot scheduled for 11:00 AM - 11:30 AM. Please contact the administrator for rescheduling options.', NOW() - INTERVAL '4 days' + INTERVAL '11.5 hours' + INTERVAL '5 minutes');

-- Team 116 - Pi Solutions (Missed)
INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 116, 'missed_evaluation', 'Missed Evaluation - Pi Solutions', 'Team Pi Solutions missed their evaluation slot scheduled for 01:00 PM - 01:30 PM. Please contact the administrator for rescheduling options.', NOW() - INTERVAL '6 days' + INTERVAL '13.5 hours' + INTERVAL '5 minutes');

-- Team 117 - Rho Innovators (Missed)
INSERT INTO alerts (panel_id, team_id, alert_type, title, body, created_at) VALUES
('P01', 117, 'missed_evaluation', 'Missed Evaluation - Rho Innovators', 'Team Rho Innovators missed their evaluation slot scheduled for 02:00 PM - 02:30 PM. Please contact the administrator for rescheduling options.', NOW() - INTERVAL '7 days' + INTERVAL '14.5 hours' + INTERVAL '5 minutes');

-- ==========================================
-- CREATE EVALUATION PARAMETERS (if table exists)
-- ==========================================
-- Check if evaluation_parameters table exists and has data

DO $$
BEGIN
    -- Only insert if table is empty
    IF NOT EXISTS (SELECT 1 FROM evaluation_parameters LIMIT 1) THEN
        INSERT INTO evaluation_parameters (category, criterion_name, max_marks) VALUES
        ('Project Understanding', 'Conceptual Clarity', 10),
        ('Project Understanding', 'Problem Analysis', 10),
        ('Technical Implementation', 'Code Quality', 10),
        ('Technical Implementation', 'System Architecture', 10),
        ('Presentation Skills', 'Communication', 10),
        ('Presentation Skills', 'Demo Quality', 10),
        ('Documentation', 'Completeness', 10),
        ('Documentation', 'Clarity', 10);
    END IF;
END $$;

-- ==========================================
-- CREATE/UPDATE PANEL USER
-- ==========================================
-- First try to update, then insert if not exists

DO $$
BEGIN
    -- Try to update existing user
    UPDATE users SET
        role = 'panel',
        panel_id = 'P01'
    WHERE email = 'panel01@example.edu';

    -- If no rows were affected, insert new user
    IF NOT FOUND THEN
        -- Password hash for 'panel123' - you may need to adjust this
        INSERT INTO users (email, hashed_password, role, panel_id) VALUES
        ('panel01@example.edu', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBdXwtO8ZjPEPG', 'panel', 'P01');
    END IF;
END $$;

-- ==========================================
-- VERIFICATION QUERIES
-- ==========================================

-- Check alerts created
SELECT
    'Alerts for missed teams:' as info,
    COUNT(*) as count
FROM alerts
WHERE alert_type = 'missed_evaluation' AND panel_id = 'P01';

-- Check evaluation parameters (if table exists)
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