-- Migration: Add Scheduled Task Execution Tracking Table
-- Purpose: Automatically track Celery Beat scheduled task executions
-- Created: 2026-03-02

-- ============================================================
-- Drop existing tables if they exist (for clean migration)
-- ============================================================
DROP TABLE IF EXISTS scheduled_task_executions CASCADE;
DROP TABLE IF EXISTS scheduled_task_health CASCADE;

-- ============================================================
-- Table: scheduled_task_executions
-- Purpose: Track every execution of scheduled tasks
-- ============================================================
CREATE TABLE scheduled_task_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Task identification
    task_name VARCHAR(255) NOT NULL,
    task_display_name VARCHAR(255),
    celery_task_id VARCHAR(255),
    
    -- Execution tracking
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds NUMERIC(10, 2),
    
    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'running',
    -- Status values: 'running', 'completed', 'failed', 'timeout', 'skipped'
    
    -- Results
    result_summary JSONB DEFAULT '{}'::jsonb,
    error_message TEXT,
    error_traceback TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- Table: scheduled_task_health
-- Purpose: Track health metrics and last execution status for each task
-- ============================================================
CREATE TABLE scheduled_task_health (
    task_name VARCHAR(255) PRIMARY KEY,
    task_display_name VARCHAR(255),
    
    -- Last execution tracking
    last_execution_id UUID REFERENCES scheduled_task_executions(id),
    last_success_at TIMESTAMP WITH TIME ZONE,
    last_failure_at TIMESTAMP WITH TIME ZONE,
    last_status VARCHAR(50),
    
    -- Health metrics
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    success_rate NUMERIC(5, 2) DEFAULT 0.0,
    
    -- Expected schedule
    expected_schedule VARCHAR(255),
    expected_next_run TIMESTAMP WITH TIME ZONE,
    
    -- Alert tracking
    consecutive_failures INTEGER DEFAULT 0,
    alert_sent_at TIMESTAMP WITH TIME ZONE,
    health_status VARCHAR(50) DEFAULT 'healthy',
    -- Health status values: 'healthy', 'degraded', 'critical', 'unknown'
    
    -- Timestamps
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- Indexes for Performance
-- ============================================================
CREATE INDEX idx_scheduled_executions_task_name ON scheduled_task_executions(task_name);
CREATE INDEX idx_scheduled_executions_started_at ON scheduled_task_executions(started_at DESC);
CREATE INDEX idx_scheduled_executions_status ON scheduled_task_executions(status);
CREATE INDEX idx_scheduled_executions_task_status ON scheduled_task_executions(task_name, status);

-- ============================================================
-- Function: Update task health after execution
-- ============================================================
CREATE OR REPLACE FUNCTION update_scheduled_task_health()
RETURNS TRIGGER AS $$
BEGIN
    -- Only update health when execution completes
    IF NEW.status IN ('completed', 'failed', 'timeout', 'skipped') AND OLD.status = 'running' THEN
        
        -- Upsert into scheduled_task_health
        INSERT INTO scheduled_task_health (
            task_name,
            task_display_name,
            last_execution_id,
            last_success_at,
            last_failure_at,
            last_status,
            total_executions,
            successful_executions,
            failed_executions,
            consecutive_failures,
            updated_at
        )
        VALUES (
            NEW.task_name,
            NEW.task_display_name,
            NEW.id,
            CASE WHEN NEW.status = 'completed' THEN NEW.completed_at ELSE NULL END,
            CASE WHEN NEW.status IN ('failed', 'timeout') THEN NEW.completed_at ELSE NULL END,
            NEW.status,
            1,
            CASE WHEN NEW.status = 'completed' THEN 1 ELSE 0 END,
            CASE WHEN NEW.status IN ('failed', 'timeout') THEN 1 ELSE 0 END,
            CASE WHEN NEW.status IN ('failed', 'timeout') THEN 1 ELSE 0 END,
            NOW()
        )
        ON CONFLICT (task_name) 
        DO UPDATE SET
            last_execution_id = NEW.id,
            last_success_at = CASE WHEN NEW.status = 'completed' THEN NEW.completed_at ELSE scheduled_task_health.last_success_at END,
            last_failure_at = CASE WHEN NEW.status IN ('failed', 'timeout') THEN NEW.completed_at ELSE scheduled_task_health.last_failure_at END,
            last_status = NEW.status,
            total_executions = scheduled_task_health.total_executions + 1,
            successful_executions = scheduled_task_health.successful_executions + CASE WHEN NEW.status = 'completed' THEN 1 ELSE 0 END,
            failed_executions = scheduled_task_health.failed_executions + CASE WHEN NEW.status IN ('failed', 'timeout') THEN 1 ELSE 0 END,
            success_rate = ROUND(
                (scheduled_task_health.successful_executions + CASE WHEN NEW.status = 'completed' THEN 1 ELSE 0 END)::numeric / 
                (scheduled_task_health.total_executions + 1) * 100, 
                2
            ),
            consecutive_failures = CASE 
                WHEN NEW.status = 'completed' THEN 0
                WHEN NEW.status IN ('failed', 'timeout') THEN scheduled_task_health.consecutive_failures + 1
                ELSE scheduled_task_health.consecutive_failures
            END,
            health_status = CASE
                WHEN NEW.status = 'completed' THEN 'healthy'
                WHEN (scheduled_task_health.consecutive_failures + CASE WHEN NEW.status IN ('failed', 'timeout') THEN 1 ELSE 0 END) >= 3 THEN 'critical'
                WHEN (scheduled_task_health.consecutive_failures + CASE WHEN NEW.status IN ('failed', 'timeout') THEN 1 ELSE 0 END) >= 2 THEN 'degraded'
                ELSE 'healthy'
            END,
            updated_at = NOW();
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Trigger: Auto-update health on execution completion
-- ============================================================
CREATE TRIGGER trigger_update_task_health
AFTER UPDATE ON scheduled_task_executions
FOR EACH ROW
EXECUTE FUNCTION update_scheduled_task_health();

-- ============================================================
-- Function: Clean up old execution logs (keep last 90 days)
-- ============================================================
CREATE OR REPLACE FUNCTION cleanup_old_scheduled_executions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM scheduled_task_executions
    WHERE started_at < NOW() - INTERVAL '90 days'
    AND status IN ('completed', 'failed', 'timeout', 'skipped');
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Initial task health records for known scheduled tasks
-- ============================================================
INSERT INTO scheduled_task_health (task_name, task_display_name, expected_schedule, health_status) VALUES
    ('weekly-batch-analysis', 'Weekly Batch Analysis', 'Monday 9:00 AM IST', 'unknown'),
    ('auto-resume-paused-batches', 'Auto-Resume Paused Batches', 'Monday 9:05 AM IST', 'unknown'),
    ('retry-dlq-nightly', 'Retry DLQ Jobs', 'Daily 2:00 AM IST', 'unknown'),
    ('update-health-status', 'Update Team Health', 'Every 2 hours', 'unknown'),
    ('weekly-student-reports', 'Weekly Student Reports', 'Monday 12:00 PM IST', 'unknown'),
    ('cleanup-stuck-jobs', 'Cleanup Stuck Jobs', 'Every 15 minutes', 'unknown')
ON CONFLICT (task_name) DO NOTHING;

-- ============================================================
-- Grant permissions (adjust based on your RLS setup)
-- ============================================================
-- Note: Adjust these based on your actual roles and RLS policies
-- For now, allowing service_role full access

-- Enable RLS
ALTER TABLE scheduled_task_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_task_health ENABLE ROW LEVEL SECURITY;

-- Policy: Allow service role full access
CREATE POLICY "Allow service role full access on scheduled_task_executions"
ON scheduled_task_executions
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Allow service role full access on scheduled_task_health"
ON scheduled_task_health
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Policy: Allow authenticated admins to view
CREATE POLICY "Allow admin read on scheduled_task_executions"
ON scheduled_task_executions
FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users 
        WHERE users.id = auth.uid() 
        AND users.role = 'admin'
    )
);

CREATE POLICY "Allow admin read on scheduled_task_health"
ON scheduled_task_health
FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users 
        WHERE users.id = auth.uid() 
        AND users.role = 'admin'
    )
);

-- ============================================================
-- Comments for documentation
-- ============================================================
COMMENT ON TABLE scheduled_task_executions IS 'Tracks every execution of Celery Beat scheduled tasks with detailed logs and timing information';
COMMENT ON TABLE scheduled_task_health IS 'Maintains health metrics and status for each scheduled task, including success rates and failure tracking';
COMMENT ON COLUMN scheduled_task_health.health_status IS 'Current health: healthy (ok), degraded (1 failure), critical (2+ failures), unknown (never run)';
COMMENT ON COLUMN scheduled_task_health.consecutive_failures IS 'Number of consecutive failures - triggers critical status at 3';
