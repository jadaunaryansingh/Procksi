-- Migration: Update mentor max_teams default from 5 to 15
-- Date: 2026-02-16
-- Description: Increases default max_teams capacity for mentors from 5 to 15

-- Update the default value for new users
ALTER TABLE users ALTER COLUMN max_teams SET DEFAULT 15;

-- Update existing users who have the old default of 5
UPDATE users SET max_teams = 15 WHERE max_teams = 5 OR max_teams IS NULL;
