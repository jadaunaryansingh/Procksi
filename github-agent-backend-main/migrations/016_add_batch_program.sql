DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'batches' AND column_name = 'program'
    ) THEN
        ALTER TABLE batches ADD COLUMN program VARCHAR(100);
    END IF;
END $$;
