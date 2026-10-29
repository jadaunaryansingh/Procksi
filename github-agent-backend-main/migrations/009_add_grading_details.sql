-- Migration: Add grading_details column to students table
-- Date: 2026-01-29
-- Description: Adds a JSONB column to store multi-round grading details.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'students' AND column_name = 'grading_details'
    ) THEN
        ALTER TABLE students ADD COLUMN grading_details JSONB DEFAULT '{}'::jsonb;
    END IF;
END $$;
