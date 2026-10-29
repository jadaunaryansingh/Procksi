-- Migration: Add teams.metadata JSONB column for flexible metadata
-- Date: 2026-02-09
-- Description: Stores suggested mentor info and other ingestion metadata

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'teams' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE teams ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
    END IF;
END $$;
