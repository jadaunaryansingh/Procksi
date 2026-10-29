-- Migration: create_celery_beat_overrides
-- Description: Creates the celery_beat_overrides table to store scheduled task schedules configured from the admin panel

-- Up Migration
CREATE TABLE IF NOT EXISTS celery_beat_overrides (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    schedule_key TEXT NOT NULL UNIQUE,        -- e.g. 'weekly-batch-analysis'
    task_path TEXT NOT NULL,                  -- e.g. 'celery_worker.auto_trigger_batch_analysis'
    day_of_week TEXT,                         -- crontab day_of_week (0-6 or '*')
    hour TEXT,                                -- crontab hour (0-23 or '*/2' etc.)
    minute TEXT,                              -- crontab minute (0-59 or '*/15' etc.)
    enabled BOOLEAN DEFAULT TRUE,
    args JSONB DEFAULT '[]',
    updated_by TEXT,                          -- admin email who last changed it
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_celery_beat_overrides_updated_at ON celery_beat_overrides;
CREATE TRIGGER update_celery_beat_overrides_updated_at
    BEFORE UPDATE ON celery_beat_overrides
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS
ALTER TABLE celery_beat_overrides ENABLE ROW LEVEL SECURITY;

-- Create policies (only authenticated admins can read/write, but we use service role anyway)
CREATE POLICY "Allow read access to authenticated users"
    ON celery_beat_overrides FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "Allow all access to service role"
    ON celery_beat_overrides FOR ALL
    USING (auth.jwt()->>'role' = 'service_role');
