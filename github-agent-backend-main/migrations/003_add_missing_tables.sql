-- Migration: Add missing tables/columns used by backend
-- Date: 2026-01-18
-- Description: Adds team_members table and teams.status column if missing

-- ==================== TEAMS STATUS COLUMN ====================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'teams' AND column_name = 'status'
    ) THEN
        ALTER TABLE teams ADD COLUMN status VARCHAR(50) DEFAULT 'active';
    END IF;
END $$;

-- Optional constraint for status values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'valid_team_status'
    ) THEN
        ALTER TABLE teams ADD CONSTRAINT valid_team_status CHECK (status IN ('active', 'inactive'));
    END IF;
END $$;

-- Index for status
CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);

-- ==================== TEAM_MEMBERS TABLE ====================
CREATE TABLE IF NOT EXISTS team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255),
    commits INTEGER DEFAULT 0,
    contribution_pct FLOAT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_team_members_project_id ON team_members(project_id);

-- Ensure columns exist (incremental safety)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'team_members' AND column_name = 'contribution_pct'
    ) THEN
        ALTER TABLE team_members ADD COLUMN contribution_pct FLOAT DEFAULT 0;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'team_members' AND column_name = 'commits'
    ) THEN
        ALTER TABLE team_members ADD COLUMN commits INTEGER DEFAULT 0;
    END IF;
END $$;

-- ==================== USERS STATUS COLUMN ====================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'status'
    ) THEN
        ALTER TABLE users ADD COLUMN status VARCHAR(50) DEFAULT 'active';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
