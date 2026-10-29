-- Migration: Add per-student inactivity streak tracking
-- Description: Track consecutive inactive weeks and accumulated mark penalty for individual students

DO $$
BEGIN
    -- Number of consecutive weeks the student has had zero personal commits
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'students' AND column_name = 'inactive_weeks'
    ) THEN
        ALTER TABLE students ADD COLUMN inactive_weeks INTEGER DEFAULT 0;
    END IF;

    -- Cumulative mark penalty applied due to continued inactivity (positive integer, e.g. 5 = -5 marks)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'students' AND column_name = 'inactivity_penalty'
    ) THEN
        ALTER TABLE students ADD COLUMN inactivity_penalty INTEGER DEFAULT 0;
    END IF;

    -- Timestamp of last inactive-member alert sent to this student
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'students' AND column_name = 'last_inactivity_alert'
    ) THEN
        ALTER TABLE students ADD COLUMN last_inactivity_alert TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_students_inactive_weeks ON students(inactive_weeks);

COMMENT ON COLUMN students.inactive_weeks      IS 'Consecutive weeks with zero personal commits; reset to 0 when student makes commits';
COMMENT ON COLUMN students.inactivity_penalty  IS 'Accumulated mark deduction due to inactivity (e.g. 10 means -10 marks applied)';
COMMENT ON COLUMN students.last_inactivity_alert IS 'Timestamp of the last inactivity alert email sent to this student';
