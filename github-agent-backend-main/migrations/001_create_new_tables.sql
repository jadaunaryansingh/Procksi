-- Migration: Create new tables for batch management system
-- Date: 2026-01-17
-- Description: Adds batches, teams, students, mentor_team_assignments tables

-- ==================== RENAME OLD TABLES ====================
-- The old 'batches' table is for batch analysis jobs, not academic batches
-- Rename it to avoid conflicts
DO $$ 
BEGIN
    -- Check if old batches table exists with the old structure
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'total_repos'
    ) THEN
        -- Rename old batches table to analysis_batches
        ALTER TABLE batches RENAME TO analysis_batches;
        
        -- Update foreign key references in analysis_jobs
        ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS analysis_jobs_batch_id_fkey;
        ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_batch_id_fkey 
            FOREIGN KEY (batch_id) REFERENCES analysis_batches(id) ON DELETE SET NULL;
    END IF;
    
    -- Check if old teams table exists (different from our new structure)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'mentor_id'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'batch_id'
    ) THEN
        -- This is the old teams table, rename it
        ALTER TABLE teams RENAME TO user_teams;
        
        -- Update foreign key references
        ALTER TABLE team_memberships DROP CONSTRAINT IF EXISTS team_memberships_team_id_fkey;
        ALTER TABLE team_memberships ADD CONSTRAINT team_memberships_team_id_fkey 
            FOREIGN KEY (team_id) REFERENCES user_teams(id) ON DELETE CASCADE;
            
        ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_team_id_fkey;
        ALTER TABLE projects ADD CONSTRAINT projects_team_id_fkey 
            FOREIGN KEY (team_id) REFERENCES user_teams(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ==================== BATCHES TABLE ====================
CREATE TABLE IF NOT EXISTS batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    semester VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    team_count INTEGER DEFAULT 0,
    student_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_status CHECK (status IN ('active', 'archived', 'upcoming')),
    CONSTRAINT valid_dates CHECK (end_date > start_date),
    CONSTRAINT unique_batch UNIQUE (semester, year)
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_year ON batches(year);

-- Ensure all columns exist (for incremental migrations)
DO $$ 
BEGIN
    -- Add year column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'year'
    ) THEN
        ALTER TABLE batches ADD COLUMN year INTEGER NOT NULL DEFAULT 2024;
    END IF;
    
    -- Add semester column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'semester'
    ) THEN
        ALTER TABLE batches ADD COLUMN semester VARCHAR(50) NOT NULL DEFAULT '4th Sem';
    END IF;
    
    -- Add team_count column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'team_count'
    ) THEN
        ALTER TABLE batches ADD COLUMN team_count INTEGER DEFAULT 0;
    END IF;
    
    -- Add student_count column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'batches' AND column_name = 'student_count'
    ) THEN
        ALTER TABLE batches ADD COLUMN student_count INTEGER DEFAULT 0;
    END IF;
END $$;

-- ==================== TEAMS TABLE ====================
CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    team_name VARCHAR(255) NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    mentor_id UUID,
    student_count INTEGER DEFAULT 0,
    health_status VARCHAR(50) DEFAULT 'on_track',
    risk_flags TEXT[], -- Array of risk flags
    last_activity TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_health_status CHECK (health_status IN ('on_track', 'at_risk', 'critical')),
    CONSTRAINT unique_team_in_batch UNIQUE (batch_id, team_name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_teams_batch_id ON teams(batch_id);
CREATE INDEX IF NOT EXISTS idx_teams_mentor_id ON teams(mentor_id);
CREATE INDEX IF NOT EXISTS idx_teams_project_id ON teams(project_id);
CREATE INDEX IF NOT EXISTS idx_teams_health_status ON teams(health_status);

-- Ensure all teams columns exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'health_status'
    ) THEN
        ALTER TABLE teams ADD COLUMN health_status VARCHAR(50) DEFAULT 'on_track';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'risk_flags'
    ) THEN
        ALTER TABLE teams ADD COLUMN risk_flags TEXT[];
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'last_activity'
    ) THEN
        ALTER TABLE teams ADD COLUMN last_activity TIMESTAMP WITH TIME ZONE;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'teams' AND column_name = 'student_count'
    ) THEN
        ALTER TABLE teams ADD COLUMN student_count INTEGER DEFAULT 0;
    END IF;
END $$;

-- ==================== STUDENTS TABLE ====================
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    github_username VARCHAR(255),
    contribution_score FLOAT DEFAULT 0,
    commit_count INTEGER DEFAULT 0,
    lines_added INTEGER DEFAULT 0,
    lines_deleted INTEGER DEFAULT 0,
    last_commit_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_students_team_id ON students(team_id);
CREATE INDEX IF NOT EXISTS idx_students_email ON students(email);
CREATE INDEX IF NOT EXISTS idx_students_github ON students(github_username);

-- ==================== MENTOR_TEAM_ASSIGNMENTS TABLE ====================
CREATE TABLE IF NOT EXISTS mentor_team_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mentor_id UUID NOT NULL,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_by UUID,
    
    CONSTRAINT unique_mentor_team UNIQUE (mentor_id, team_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_mentor_id ON mentor_team_assignments(mentor_id);
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_team_id ON mentor_team_assignments(team_id);
CREATE INDEX IF NOT EXISTS idx_mentor_assignments_batch_id ON mentor_team_assignments(batch_id);

-- ==================== UPDATE EXISTING TABLES ====================

-- Add batch_id to projects table if not exists
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'projects' AND column_name = 'batch_id'
    ) THEN
        ALTER TABLE projects ADD COLUMN batch_id UUID REFERENCES batches(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_projects_batch_id ON projects(batch_id);
    END IF;
END $$;

-- ==================== FUNCTIONS & TRIGGERS ====================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_batches_updated_at ON batches;
CREATE TRIGGER update_batches_updated_at
    BEFORE UPDATE ON batches
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_teams_updated_at ON teams;
CREATE TRIGGER update_teams_updated_at
    BEFORE UPDATE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_students_updated_at ON students;
CREATE TRIGGER update_students_updated_at
    BEFORE UPDATE ON students
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to update batch team_count and student_count
CREATE OR REPLACE FUNCTION update_batch_counts()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE batches 
        SET team_count = (SELECT COUNT(*) FROM teams WHERE batch_id = NEW.batch_id)
        WHERE id = NEW.batch_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE batches 
        SET team_count = (SELECT COUNT(*) FROM teams WHERE batch_id = OLD.batch_id)
        WHERE id = OLD.batch_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger for batch counts
DROP TRIGGER IF EXISTS update_batch_team_count ON teams;
CREATE TRIGGER update_batch_team_count
    AFTER INSERT OR DELETE ON teams
    FOR EACH ROW
    EXECUTE FUNCTION update_batch_counts();

-- Function to update team student_count
CREATE OR REPLACE FUNCTION update_team_student_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE teams 
        SET student_count = (SELECT COUNT(*) FROM students WHERE team_id = NEW.team_id)
        WHERE id = NEW.team_id;
        
        -- Also update batch student_count
        UPDATE batches 
        SET student_count = (
            SELECT COUNT(*) FROM students s 
            JOIN teams t ON s.team_id = t.id 
            WHERE t.batch_id = (SELECT batch_id FROM teams WHERE id = NEW.team_id)
        )
        WHERE id = (SELECT batch_id FROM teams WHERE id = NEW.team_id);
        
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE teams 
        SET student_count = (SELECT COUNT(*) FROM students WHERE team_id = OLD.team_id)
        WHERE id = OLD.team_id;
        
        -- Also update batch student_count
        UPDATE batches 
        SET student_count = (
            SELECT COUNT(*) FROM students s 
            JOIN teams t ON s.team_id = t.id 
            WHERE t.batch_id = (SELECT batch_id FROM teams WHERE id = OLD.team_id)
        )
        WHERE id = (SELECT batch_id FROM teams WHERE id = OLD.team_id);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger for team student count
DROP TRIGGER IF EXISTS update_team_student_count_trigger ON students;
CREATE TRIGGER update_team_student_count_trigger
    AFTER INSERT OR DELETE ON students
    FOR EACH ROW
    EXECUTE FUNCTION update_team_student_count();

-- ==================== ROW LEVEL SECURITY (RLS) ====================

-- Enable RLS on new tables
ALTER TABLE batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
ALTER TABLE mentor_team_assignments ENABLE ROW LEVEL SECURITY;

-- Policies for batches table
DROP POLICY IF EXISTS "Public can view active batches" ON batches;
CREATE POLICY "Public can view active batches"
    ON batches FOR SELECT
    USING (status = 'active');

DROP POLICY IF EXISTS "Admins can manage all batches" ON batches;
CREATE POLICY "Admins can manage all batches"
    ON batches FOR ALL
    USING (auth.jwt() ->> 'role' = 'admin');

-- Policies for teams table
DROP POLICY IF EXISTS "Public can view teams" ON teams;
CREATE POLICY "Public can view teams"
    ON teams FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "Admins can manage all teams" ON teams;
CREATE POLICY "Admins can manage all teams"
    ON teams FOR ALL
    USING (auth.jwt() ->> 'role' = 'admin');

DROP POLICY IF EXISTS "Mentors can view their assigned teams" ON teams;
CREATE POLICY "Mentors can view their assigned teams"
    ON teams FOR SELECT
    USING (
        mentor_id::text = auth.jwt() ->> 'sub' OR
        EXISTS (
            SELECT 1 FROM mentor_team_assignments 
            WHERE team_id = teams.id 
            AND mentor_id::text = auth.jwt() ->> 'sub'
        )
    );

-- Policies for students table
DROP POLICY IF EXISTS "Public can view students" ON students;
CREATE POLICY "Public can view students"
    ON students FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "Admins can manage all students" ON students;
CREATE POLICY "Admins can manage all students"
    ON students FOR ALL
    USING (auth.jwt() ->> 'role' = 'admin');

-- Policies for mentor_team_assignments table
DROP POLICY IF EXISTS "Mentors can view their assignments" ON mentor_team_assignments;
CREATE POLICY "Mentors can view their assignments"
    ON mentor_team_assignments FOR SELECT
    USING (mentor_id::text = auth.jwt() ->> 'sub');

DROP POLICY IF EXISTS "Admins can manage all assignments" ON mentor_team_assignments;
CREATE POLICY "Admins can manage all assignments"
    ON mentor_team_assignments FOR ALL
    USING (auth.jwt() ->> 'role' = 'admin');

-- ==================== SAMPLE DATA (Optional) ====================

-- Insert sample batch (commented out for production)
-- INSERT INTO batches (name, semester, year, start_date, end_date, status)
-- VALUES ('4th Sem 2024', '4th Sem', 2024, '2024-01-01', '2024-06-30', 'active');

COMMENT ON TABLE batches IS 'Academic batches/semesters';
COMMENT ON TABLE teams IS 'Student teams within batches';
COMMENT ON TABLE students IS 'Students belonging to teams';
COMMENT ON TABLE mentor_team_assignments IS 'Mentor-team assignments for batch guidance';
