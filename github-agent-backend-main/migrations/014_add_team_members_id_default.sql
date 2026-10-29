-- Migration: Ensure team_members.id has a default UUID
-- Date: 2026-02-09
-- Description: Adds gen_random_uuid() default for team_members.id

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'team_members' AND column_name = 'id'
    ) THEN
        ALTER TABLE team_members ALTER COLUMN id SET DEFAULT gen_random_uuid();
    END IF;
END $$;
