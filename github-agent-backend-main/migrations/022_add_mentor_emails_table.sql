-- Migration: Add mentor_emails table for tracking mentor-to-team custom emails
-- Purpose: Store history of all custom emails sent by mentors to teams

-- ==================== MENTOR_EMAILS TABLE ====================
CREATE TABLE IF NOT EXISTS mentor_emails (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL,
    sender_email VARCHAR(255),
    sender_name VARCHAR(255),
    subject VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    recipients JSONB DEFAULT '[]'::jsonb,
    cc_emails JSONB DEFAULT '[]'::jsonb,
    send_status VARCHAR(20) DEFAULT 'sent',
    emails_sent INT DEFAULT 0,
    emails_failed INT DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_mentor_emails_team_id ON mentor_emails(team_id);
CREATE INDEX IF NOT EXISTS idx_mentor_emails_sender_id ON mentor_emails(sender_id);
CREATE INDEX IF NOT EXISTS idx_mentor_emails_created_at ON mentor_emails(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mentor_emails_team_sender ON mentor_emails(team_id, sender_id, created_at DESC);

-- Comments
COMMENT ON TABLE mentor_emails IS 'Tracks custom emails sent by mentors to teams';
COMMENT ON COLUMN mentor_emails.recipients IS 'JSON array of recipient email addresses';
COMMENT ON COLUMN mentor_emails.cc_emails IS 'JSON array of CC email addresses';
COMMENT ON COLUMN mentor_emails.send_status IS 'sent, partial, failed';
