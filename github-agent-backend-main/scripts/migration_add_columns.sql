-- Migration: Add missing columns to projects table
-- Run this in Supabase SQL Editor

-- Add ai_pros column for AI positive feedback
ALTER TABLE projects ADD COLUMN IF NOT EXISTS ai_pros TEXT;

-- Add ai_cons column for AI constructive feedback  
ALTER TABLE projects ADD COLUMN IF NOT EXISTS ai_cons TEXT;

-- Add report_json column if not exists (for storing full analysis data)
ALTER TABLE projects ADD COLUMN IF NOT EXISTS report_json JSONB;

-- Remove verdict constraint if exists (allow any verdict value)
ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_verdict_check;

-- Verify columns exist
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'projects' 
AND column_name IN ('ai_pros', 'ai_cons', 'report_json', 'verdict');
