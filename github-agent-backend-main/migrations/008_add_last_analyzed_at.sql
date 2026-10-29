-- Migration 008: Add last_analyzed_at column to projects table
-- Purpose: Track when each project was last analyzed for better progress monitoring

DO $$
BEGIN
    -- Add last_analyzed_at column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' 
        AND column_name = 'last_analyzed_at'
    ) THEN
        ALTER TABLE projects 
        ADD COLUMN last_analyzed_at TIMESTAMPTZ;
        
        RAISE NOTICE 'Added last_analyzed_at column to projects table';
    ELSE
        RAISE NOTICE 'Column last_analyzed_at already exists in projects table';
    END IF;
    
    -- Create index for faster queries on last_analyzed_at
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'projects' 
        AND indexname = 'idx_projects_last_analyzed_at'
    ) THEN
        CREATE INDEX idx_projects_last_analyzed_at 
        ON projects(last_analyzed_at);
        
        RAISE NOTICE 'Created index on last_analyzed_at';
    ELSE
        RAISE NOTICE 'Index idx_projects_last_analyzed_at already exists';
    END IF;
END $$;

-- Verify the migration
DO $$
DECLARE
    col_exists BOOLEAN;
    idx_exists BOOLEAN;
BEGIN
    -- Check column
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' 
        AND column_name = 'last_analyzed_at'
    ) INTO col_exists;
    
    -- Check index
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'projects' 
        AND indexname = 'idx_projects_last_analyzed_at'
    ) INTO idx_exists;
    
    IF col_exists AND idx_exists THEN
        RAISE NOTICE '✅ Migration 008 completed successfully!';
        RAISE NOTICE '   - last_analyzed_at column: EXISTS';
        RAISE NOTICE '   - Index on last_analyzed_at: EXISTS';
    ELSE
        RAISE WARNING '⚠️ Migration 008 incomplete:';
        IF NOT col_exists THEN
            RAISE WARNING '   - last_analyzed_at column: MISSING';
        END IF;
        IF NOT idx_exists THEN
            RAISE WARNING '   - Index: MISSING';
        END IF;
    END IF;
END $$;
