-- Email send log table for tracking every weekly report email
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS email_send_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- Which run triggered this email
  notification_id UUID REFERENCES notifications(id) ON DELETE SET NULL,
  task_run_id TEXT,                              -- UUID of the celery task run
  
  -- Recipient info
  team_id UUID,
  team_name TEXT,
  student_name TEXT,
  student_email TEXT NOT NULL,
  batch_id UUID,
  
  -- Delivery result
  status TEXT NOT NULL DEFAULT 'pending',        -- 'sent', 'failed', 'pending'
  error_message TEXT,                            -- error details if failed
  
  -- Email metadata
  email_type TEXT NOT NULL DEFAULT 'weekly_report',  -- 'weekly_report', 'test', etc.
  subject TEXT,
  has_report_pdf BOOLEAN DEFAULT FALSE,
  has_leaderboard_pdf BOOLEAN DEFAULT FALSE,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  sent_at TIMESTAMPTZ                            -- actual send time (null if failed)
);

-- Indexes for common queries
CREATE INDEX idx_email_send_log_notification ON email_send_log (notification_id);
CREATE INDEX idx_email_send_log_status ON email_send_log (status, created_at DESC);
CREATE INDEX idx_email_send_log_team ON email_send_log (team_id);
CREATE INDEX idx_email_send_log_student ON email_send_log (student_email);
CREATE INDEX idx_email_send_log_created ON email_send_log (created_at DESC);
CREATE INDEX idx_email_send_log_task_run ON email_send_log (task_run_id);
CREATE INDEX idx_email_send_log_batch ON email_send_log (batch_id);

-- RLS
ALTER TABLE email_send_log ENABLE ROW LEVEL SECURITY;

-- Admins can read all logs
CREATE POLICY "Authenticated users can read email_send_log" ON email_send_log
  FOR SELECT TO authenticated USING (true);

-- Service role can insert (from celery workers)
CREATE POLICY "Service role can insert email_send_log" ON email_send_log
  FOR INSERT WITH CHECK (true);

-- Service role can update (status changes)
CREATE POLICY "Service role can update email_send_log" ON email_send_log
  FOR UPDATE USING (true) WITH CHECK (true);
