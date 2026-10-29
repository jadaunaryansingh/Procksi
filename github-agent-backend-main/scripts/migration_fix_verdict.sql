-- Migration: Remove verdict constraint
-- Run this in Supabase SQL Editor to allow any verdict value

ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_verdict_check;

-- Verify the constraint is removed
SELECT conname FROM pg_constraint WHERE conrelid = 'projects'::regclass;
