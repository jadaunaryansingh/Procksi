-- =====================================================
-- STEP 4: Create Evaluations for Submitted Teams
-- =====================================================
-- Creates evaluation records for 2 submitted teams: 101 and 103.

INSERT INTO evaluations (panel_id, team_id, scores_json, remarks, submitted_at, receipt_id, locked) VALUES
('P01', 101, '{"q1": 9, "q2": 8, "q3": 8, "q4": 9}', 'Apollo Web Services presented a mature cloud operations workflow with strong architectural decisions and clean implementation.', NOW() - INTERVAL '2 days' + INTERVAL '9.25 hours' + INTERVAL '5 minutes', 'RCPT-P01-101-' || EXTRACT(EPOCH FROM (NOW() - INTERVAL '2 days' + INTERVAL '9.25 hours')), true);

INSERT INTO evaluations (panel_id, team_id, scores_json, remarks, submitted_at, receipt_id, locked) VALUES
('P01', 103, '{"q1": 8, "q2": 8, "q3": 9, "q4": 8}', 'Beta Blockers delivered a reliable real-time monitoring pipeline, with well-structured code and practical demo coverage.', NOW() - INTERVAL '2 days' + INTERVAL '11.25 hours' + INTERVAL '5 minutes', 'RCPT-P01-103-' || EXTRACT(EPOCH FROM (NOW() - INTERVAL '2 days' + INTERVAL '11.25 hours')), true);

-- Verify evaluations created
SELECT
    e.team_id,
    t.name as team_name,
    e.receipt_id,
    e.submitted_at,
    e.locked,
    LENGTH(e.remarks) as remarks_length
FROM evaluations e
JOIN teams t ON e.team_id = t.id
WHERE e.panel_id = 'P01'
ORDER BY e.team_id;