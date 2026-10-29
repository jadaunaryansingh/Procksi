-- Fix FK constraint - analysis_jobs.batch_id should reference batches, not analysis_batches

-- Drop the incorrect foreign key constraint
ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS analysis_jobs_batch_id_fkey;

-- Add correct foreign key constraint
ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_batch_id_fkey 
    FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE;

-- Verify the constraint
SELECT 
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.table_name = 'analysis_jobs' 
    AND tc.constraint_type = 'FOREIGN KEY'
    AND kcu.column_name = 'batch_id';
