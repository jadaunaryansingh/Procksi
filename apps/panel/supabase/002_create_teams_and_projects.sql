-- =====================================================
-- STEP 2: Create 15 Teams with Projects
-- =====================================================
-- Creates teams with IDs 101-115 and their related projects

-- Insert 15 teams
INSERT INTO teams (id, name) VALUES
(101, 'Apollo Web Services'),
(102, 'Gamma Rayburst'),
(103, 'Beta Blockers'),
(104, 'Delta Force'),
(105, 'Echo Systems'),
(106, 'Falcon Stack'),
(107, 'Gridline AI'),
(108, 'Helix Coders'),
(109, 'Ion Innovators'),
(110, 'Jupiter Labs'),
(111, 'Kernel Knights'),
(112, 'Lambda Crew'),
(113, 'Matrix Minds'),
(114, 'Nova Nerds'),
(115, 'Omega Builders')
ON CONFLICT (id) DO UPDATE SET
name = EXCLUDED.name;

-- Insert corresponding projects
INSERT INTO projects (team_id, title, description) VALUES
(101, 'Cloud Operations Suite', 'A cloud operations platform for automated monitoring and incident handling.'),
(102, 'Particle Visualization', 'A data visualization suite for high-dimensional particle behavior analysis.'),
(103, 'Real-time Vital Monitoring System', 'An IoT-backed health vitals dashboard with alerting and trends.'),
(104, 'Campus Logistics', 'A route and demand management tool for campus transport and deliveries.'),
(105, 'Peer Learning Network', 'A collaborative mentoring and knowledge-sharing network for students.'),
(106, 'Smart Attendance Analytics', 'Attendance tracking with anomaly detection and performance insights.'),
(107, 'Adaptive Timetable Optimizer', 'Constraint-based scheduling engine for dynamic academic timetables.'),
(108, 'Lab Equipment Tracker', 'Asset lifecycle and booking platform for lab infrastructure.'),
(109, 'Digital Noticeboard Engine', 'A targeted notification and announcement publishing system.'),
(110, 'Automated Exam Invigilation', 'Computer-vision-assisted invigilation workflow for assessments.'),
(111, 'Student Mentoring CRM', 'A mentor-student engagement tracker with progress pipelines.'),
(112, 'Placement Readiness Platform', 'Skill and interview readiness tracker for placement preparation.'),
(113, 'Transport Route Optimizer', 'Real-time route planner for reducing wait time and fuel usage.'),
(114, 'Hostel Complaint Resolver', 'Issue-ticketing workflow for hostel maintenance requests.'),
(115, 'Research Paper Recommender', 'A semantic recommendation engine for academic literature discovery.')
ON CONFLICT (team_id) DO UPDATE SET
title = EXCLUDED.title,
description = EXCLUDED.description;

-- Insert GitHub data for all teams
INSERT INTO github_data (team_id, repository_url, default_branch, open_pull_requests, commit_count_30d, last_commit_at) VALUES
(101, 'https://github.com/gla-university/team-101', 'main', 1, 28, NOW() - INTERVAL '1 day'),
(102, 'https://github.com/gla-university/team-102', 'main', 3, 19, NOW() - INTERVAL '2 days'),
(103, 'https://github.com/gla-university/team-103', 'main', 2, 24, NOW() - INTERVAL '1 day'),
(104, 'https://github.com/gla-university/team-104', 'main', 1, 21, NOW() - INTERVAL '3 days'),
(105, 'https://github.com/gla-university/team-105', 'main', 0, 22, NOW() - INTERVAL '2 days'),
(106, 'https://github.com/gla-university/team-106', 'main', 2, 20, NOW() - INTERVAL '4 days'),
(107, 'https://github.com/gla-university/team-107', 'main', 4, 16, NOW() - INTERVAL '5 days'),
(108, 'https://github.com/gla-university/team-108', 'main', 1, 14, NOW() - INTERVAL '6 days'),
(109, 'https://github.com/gla-university/team-109', 'main', 2, 15, NOW() - INTERVAL '7 days'),
(110, 'https://github.com/gla-university/team-110', 'main', 3, 13, NOW() - INTERVAL '8 days'),
(111, 'https://github.com/gla-university/team-111', 'main', 0, 18, NOW() - INTERVAL '2 days'),
(112, 'https://github.com/gla-university/team-112', 'main', 1, 17, NOW() - INTERVAL '3 days'),
(113, 'https://github.com/gla-university/team-113', 'main', 2, 19, NOW() - INTERVAL '1 day'),
(114, 'https://github.com/gla-university/team-114', 'main', 1, 16, NOW() - INTERVAL '2 days'),
(115, 'https://github.com/gla-university/team-115', 'main', 0, 11, NOW() - INTERVAL '5 days')
ON CONFLICT (team_id) DO UPDATE SET
repository_url = EXCLUDED.repository_url,
default_branch = EXCLUDED.default_branch,
open_pull_requests = EXCLUDED.open_pull_requests,
commit_count_30d = EXCLUDED.commit_count_30d,
last_commit_at = EXCLUDED.last_commit_at;

-- Verify teams and projects created
SELECT 'Teams created:' as step, COUNT(*) as count FROM teams
UNION ALL
SELECT 'Projects created:' as step, COUNT(*) as count FROM projects
UNION ALL
SELECT 'GitHub data created:' as step, COUNT(*) as count FROM github_data;