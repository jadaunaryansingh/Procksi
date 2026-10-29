-- Migration: Add quality_alerts table for tracking commit quality alert history
-- Purpose: Track when quality alerts are sent to teams to prevent duplicates and provide history

-- ==================== QUALITY_ALERTS TABLE ====================
CREATE TABLE IF NOT EXISTS quality_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    fake_commit_ratio FLOAT NOT NULL,
    fake_commit_count INT NOT NULL,
    commit_health VARCHAR(20) NOT NULL CHECK (commit_health IN ('Healthy', 'At Risk', 'Critical')),
    total_commits INT NOT NULL,
    threshold_used FLOAT NOT NULL CHECK (threshold_used >= 0 AND threshold_used <= 100),
    sent_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    email_recipients TEXT[], -- Array of email addresses that received the alert
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_quality_alerts_team_id ON quality_alerts(team_id);
CREATE INDEX IF NOT EXISTS idx_quality_alerts_sent_at ON quality_alerts(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_quality_alerts_team_sent ON quality_alerts(team_id, sent_at DESC);

-- Add comment for documentation
COMMENT ON TABLE quality_alerts IS 'Tracks commit quality alerts sent to teams';
COMMENT ON COLUMN quality_alerts.fake_commit_ratio IS 'Percentage of fake commits at time of alert (0-100)';
COMMENT ON COLUMN quality_alerts.commit_health IS 'Health status: Healthy, At Risk, or Critical';
COMMENT ON COLUMN quality_alerts.threshold_used IS 'Threshold percentage used to trigger alert';
COMMENT ON COLUMN quality_alerts.email_recipients IS 'Array of student email addresses that received the alert';
