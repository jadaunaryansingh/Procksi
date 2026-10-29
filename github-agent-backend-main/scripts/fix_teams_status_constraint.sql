-- Fix teams table status constraint to include 'queued' and 'cancelled'
-- Issue: Code tries to set status='queued' but constraint doesn't allow it

-- Drop the old constraint
ALTER TABLE teams DROP CONSTRAINT IF EXISTS valid_analysis_status;

-- Add new constraint with all required status values
ALTER TABLE teams ADD CONSTRAINT valid_analysis_status 
CHECK (status IN (
    'pending',      -- Initial state
    'queued',       -- Queued for analysis (NEW)
    'analyzing',    -- Currently being analyzed
    'completed',    -- Analysis completed successfully
    'failed',       -- Analysis failed
    'cancelled',    -- Analysis cancelled (NEW)
    'active',       -- Team is active
    'inactive'      -- Team is inactive
));

-- Verify the constraint was updated
SELECT 
    conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS constraint_definition
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
JOIN pg_class cl ON cl.oid = c.conrelid
WHERE cl.relname = 'teams' 
AND conname = 'valid_analysis_status';
