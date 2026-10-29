-- Migration: Add mentor activity tracking columns to users table
-- Date: 2026-02-28
-- Description: Adds last_login, last_logout, is_online, and total_time_spent columns to users table for mentor activity tracking

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'last_login'
    ) THEN
        ALTER TABLE users ADD COLUMN last_login TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'last_logout'
    ) THEN
        ALTER TABLE users ADD COLUMN last_logout TIMESTAMPTZ;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'is_online'
    ) THEN
        ALTER TABLE users ADD COLUMN is_online BOOLEAN DEFAULT false;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'total_time_spent'
    ) THEN
        ALTER TABLE users ADD COLUMN total_time_spent INTERVAL DEFAULT INTERVAL '0 seconds';
    END IF;
END $$;

-- Backfill: Set is_online to false for all users
UPDATE users SET is_online = false WHERE is_online IS NULL;
-- Backfill: Set total_time_spent to 0 for all users
UPDATE users SET total_time_spent = INTERVAL '0 seconds' WHERE total_time_spent IS NULL;
