-- Migration: Add Inactivity Tracking
-- Description: Add columns to track team inactivity and alert history

-- Add columns to teams table for inactivity tracking
DO $$ 
BEGIN
    -- Add last_inactivity_alert column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'last_inactivity_alert'
    ) THEN
        ALTER TABLE teams ADD COLUMN last_inactivity_alert TIMESTAMP WITH TIME ZONE;
    END IF;
    
    -- Add inactivity_alert_count column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'inactivity_alert_count'
    ) THEN
        ALTER TABLE teams ADD COLUMN inactivity_alert_count INTEGER DEFAULT 0;
    END IF;
    
    -- Add last_commit_date column (extracted from analysis results)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'last_commit_date'
    ) THEN
        ALTER TABLE teams ADD COLUMN last_commit_date TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Create index for efficient inactivity queries
CREATE INDEX IF NOT EXISTS idx_teams_last_commit_date ON teams(last_commit_date);
CREATE INDEX IF NOT EXISTS idx_teams_last_inactivity_alert ON teams(last_inactivity_alert);

-- Create alert_history table to track all alerts sent
CREATE TABLE IF NOT EXISTS alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN ('inactivity', 'repo_privacy', 'quality', 'duplicate_commits')),
    severity VARCHAR(20) CHECK (severity IN ('warning', 'critical', 'info')),
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    recipient_count INTEGER DEFAULT 0,
    delivery_status VARCHAR(20) DEFAULT 'sent' CHECK (delivery_status IN ('sent', 'failed', 'partial')),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for alert_history
CREATE INDEX IF NOT EXISTS idx_alert_history_team_id ON alert_history(team_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_alert_type ON alert_history(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_sent_at ON alert_history(sent_at DESC);

-- Add comment
COMMENT ON TABLE alert_history IS 'Tracks all email alerts sent to teams';
COMMENT ON COLUMN teams.last_inactivity_alert IS 'Timestamp of last inactivity alert sent';
COMMENT ON COLUMN teams.inactivity_alert_count IS 'Number of inactivity alerts sent to this team';
COMMENT ON COLUMN teams.last_commit_date IS 'Date of most recent commit from analysis results';
