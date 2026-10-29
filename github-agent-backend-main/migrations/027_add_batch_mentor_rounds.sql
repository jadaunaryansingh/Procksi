-- Migration: Add mentor_rounds configuration to batches
-- Purpose: Allow admins to schedule mentor marking rounds per batch

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'batches' AND column_name = 'mentor_rounds'
    ) THEN
        ALTER TABLE batches ADD COLUMN mentor_rounds JSONB NOT NULL DEFAULT '[]'::jsonb;
        COMMENT ON COLUMN batches.mentor_rounds IS 'Batch-level mentor grading rounds. Each item: {id, name, marks_out_of, created_at}';
    END IF;
END $$;
