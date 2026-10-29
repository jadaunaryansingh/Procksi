-- Add is_mentor flag to allow admin+mentor users
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'is_mentor'
    ) THEN
        ALTER TABLE users ADD COLUMN is_mentor BOOLEAN DEFAULT false;
    END IF;
END $$;

-- Backfill: mentors should be marked as is_mentor
UPDATE users
SET is_mentor = true
WHERE role = 'mentor' AND (is_mentor IS NULL OR is_mentor = false);
