-- Notifications table for in-app admin notifications
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS notifications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  type TEXT NOT NULL DEFAULT 'info',           -- 'success', 'error', 'info', 'warning'
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',                 -- { team_id, job_id, batch_id, team_name }
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast unread queries
CREATE INDEX idx_notifications_unread ON notifications (is_read, created_at DESC);
CREATE INDEX idx_notifications_created ON notifications (created_at DESC);

-- RLS
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Admins can read all notifications
CREATE POLICY "Authenticated users can read notifications" ON notifications
  FOR SELECT TO authenticated USING (true);

-- Service role can insert (from celery workers)
CREATE POLICY "Service role can insert notifications" ON notifications
  FOR INSERT WITH CHECK (true);

-- Admins can update (mark as read)
CREATE POLICY "Authenticated users can update notifications" ON notifications
  FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
