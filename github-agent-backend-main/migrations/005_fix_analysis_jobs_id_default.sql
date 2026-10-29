-- Add UUID default to analysis_jobs id column
ALTER TABLE analysis_jobs ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- Verify the change
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'analysis_jobs' AND column_name = 'id';
