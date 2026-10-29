-- Migration: Add projects.description column
-- Date: 2026-02-09
-- Description: Stores project description from team ingestion

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'projects' AND column_name = 'description'
    ) THEN
        ALTER TABLE projects ADD COLUMN description TEXT;
    END IF;
END $$;
