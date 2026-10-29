-- Migration: Add dynamic mentor marks configuration and general feedback
-- Date: 2026-03-01
-- Description:
--   1. Adds mentor_max_marks to batches (admin sets max marks mentors can give, default 100)
--   2. Adds mentor_feedback to teams (general mentor feedback at team level)

-- 1. Add mentor_max_marks to batches table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'batches' AND column_name = 'mentor_max_marks'
    ) THEN
        ALTER TABLE batches ADD COLUMN mentor_max_marks INTEGER NOT NULL DEFAULT 100;
        COMMENT ON COLUMN batches.mentor_max_marks IS 'Maximum marks a mentor can assign per student. Configured by admin.';
    END IF;
END $$;

-- 2. Add mentor_feedback to teams table (general suggestion/feedback from mentor)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'teams' AND column_name = 'mentor_feedback'
    ) THEN
        ALTER TABLE teams ADD COLUMN mentor_feedback TEXT DEFAULT NULL;
        COMMENT ON COLUMN teams.mentor_feedback IS 'General feedback/suggestions from the assigned mentor for this team.';
    END IF;
END $$;
