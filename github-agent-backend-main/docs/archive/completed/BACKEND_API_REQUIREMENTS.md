# Backend API Requirements for HackScore 2.0

**Project:** HackScore - End-to-End Project Evaluation Platform  
**Created:** January 17, 2026  
**Status:** Specification for Implementation  

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication & User Management](#authentication--user-management)
3. [Batch Management APIs](#batch-management-apis)
4. [Team Management APIs](#team-management-apis)
5. [Mentor Management APIs](#mentor-management-apis)
6. [Assignment APIs](#assignment-apis)
7. [Admin Portal APIs](#admin-portal-apis)
8. [Mentor Portal APIs](#mentor-portal-apis)
9. [Analysis & Reports APIs](#analysis--reports-apis)
10. [Database Schema Changes](#database-schema-changes)

---

## Overview

### New Architecture Changes

The frontend has been completely redesigned with:
- **Three separate portals:** Landing Page (public), Admin Portal, Mentor Portal
- **Batch-based organization:** Projects organized by semester/batch (e.g., "4th Sem 2024")
- **Role-based access control:** Admin and Mentor roles with different permissions
- **Mentor-Team assignments:** Admins assign specific teams to mentors
- **Batch selector:** Admins can filter everything by batch
- **Mentor view impersonation:** Admins can view the platform as any mentor

### API Design Principles

- **RESTful endpoints** with clear resource naming
- **Role-based authorization** using JWT tokens with role claims
- **Batch context** - most endpoints need batch filtering
- **Pagination** for list endpoints
- **Filtering and sorting** capabilities
- **Supabase authentication** integration
- **camelCase** response format for frontend compatibility

---

## Authentication & User Management

### 1. User Profile & Roles

#### GET `/api/auth/user`
Get current authenticated user with role information.

**Response:**
```json
{
  "id": "uuid",
  "email": "admin@example.com",
  "fullName": "John Admin",
  "avatarUrl": "https://...",
  "role": "admin", // "admin" | "mentor"
  "createdAt": "2024-01-15T10:00:00Z",
  "updatedAt": "2024-01-17T10:00:00Z"
}
```

#### POST `/api/auth/login`
Supabase OAuth login (Google).

**Request:**
```json
{
  "provider": "google",
  "redirectUri": "http://localhost:8080/auth/callback"
}
```

**Response:**
```json
{
  "url": "https://supabase-oauth-url...",
  "success": true
}
```

#### POST `/api/auth/callback`
Handle OAuth callback and establish session.

**Request:**
```json
{
  "code": "oauth-code",
  "redirectUri": "http://localhost:8080/auth/callback"
}
```

**Response:**
```json
{
  "user": { /* User object */ },
  "session": { /* Session object */ },
  "accessToken": "jwt-token"
}
```

#### POST `/api/auth/logout`
Logout current user.

**Response:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

---

## Batch Management APIs

### 2. Batch CRUD Operations

#### GET `/api/batches`
Get all batches (admin only).

**Query Parameters:**
- `status` (optional): "active" | "completed" | "archived"
- `sort` (optional): "name" | "startDate" | "-startDate"

**Response:**
```json
{
  "batches": [
    {
      "id": "4th-sem-2024",
      "name": "4th Semester 2024",
      "semester": "4th Sem",
      "year": "2024",
      "startDate": "2024-01-15",
      "endDate": "2024-05-30",
      "status": "active",
      "teamCount": 12,
      "studentCount": 48,
      "mentorCount": 4,
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 10
}
```

#### POST `/api/batches`
Create a new batch (admin only).

**Request:**
```json
{
  "name": "4th Semester 2024",
  "semester": "4th Sem",
  "year": "2024",
  "startDate": "2024-01-15",
  "endDate": "2024-05-30",
  "status": "active"
}
```

**Response:**
```json
{
  "batch": { /* Batch object */ },
  "message": "Batch created successfully"
}
```

#### PUT `/api/batches/{batchId}`
Update batch details (admin only).

**Request:**
```json
{
  "name": "Updated Semester Name",
  "status": "completed",
  "endDate": "2024-06-15"
}
```

**Response:**
```json
{
  "batch": { /* Updated batch object */ },
  "message": "Batch updated successfully"
}
```

#### DELETE `/api/batches/{batchId}`
Delete a batch (admin only). Should fail if batch has teams.

**Response:**
```json
{
  "success": true,
  "message": "Batch deleted successfully"
}
```

#### GET `/api/batches/{batchId}/stats`
Get statistics for a specific batch.

**Response:**
```json
{
  "batchId": "4th-sem-2024",
  "totalTeams": 12,
  "activeTeams": 10,
  "completedTeams": 2,
  "totalMentors": 4,
  "totalStudents": 48,
  "averageScore": 78.5,
  "teamsWithIssues": 3,
  "unassignedTeams": 2,
  "analysisQueue": 1
}
```

---

## Team Management APIs

### 3. Team CRUD Operations

#### GET `/api/teams`
Get teams (filtered by batch and role).

**Query Parameters:**
- `batchId` (required for admin): Batch ID to filter
- `status` (optional): "active" | "inactive" | "archived"
- `mentorId` (optional): Filter by assigned mentor
- `search` (optional): Search by team name or repo URL
- `page` (optional): Page number (default: 1)
- `pageSize` (optional): Items per page (default: 20)
- `sort` (optional): "name" | "totalScore" | "-totalScore" | "createdAt"

**Response (Admin):**
```json
{
  "teams": [
    {
      "id": "uuid",
      "batchId": "4th-sem-2024",
      "name": "Team Alpha",
      "repoUrl": "https://github.com/team-alpha/project",
      "description": "AI Assistant Project",
      "status": "active",
      "assignedMentorId": "mentor-uuid",
      "assignedMentorName": "John Mentor",
      "totalScore": 85.5,
      "lastAnalyzedAt": "2024-01-16T10:00:00Z",
      "lastActivity": "2 hours ago",
      "healthStatus": "on_track", // "on_track" | "at_risk" | "critical"
      "riskFlags": [],
      "studentCount": 4,
      "createdAt": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 50,
  "page": 1,
  "pageSize": 20,
  "totalPages": 3
}
```

**Response (Mentor) - Only assigned teams:**
```json
{
  "teams": [ /* Only teams assigned to this mentor */ ],
  "total": 3
}
```

#### POST `/api/teams`
Create a new team (admin only).

**Request:**
```json
{
  "batchId": "4th-sem-2024",
  "name": "Team Alpha",
  "repoUrl": "https://github.com/team-alpha/project",
  "description": "AI Assistant Project",
  "students": [
    {
      "name": "Alice Johnson",
      "email": "alice@example.com",
      "rollNumber": "CS2021001"
    },
    {
      "name": "Bob Smith",
      "email": "bob@example.com",
      "rollNumber": "CS2021002"
    }
  ]
}
```

**Response:**
```json
{
  "team": { /* Team object */ },
  "message": "Team created successfully"
}
```

#### POST `/api/teams/batch-upload`
Bulk upload teams via CSV (admin only).

**Request:** `multipart/form-data`
- `file`: CSV file
- `batchId`: Batch ID

**CSV Format:**
```csv
teamName,repoUrl,description,studentName1,studentEmail1,studentName2,studentEmail2
Team Alpha,https://github.com/team-alpha/project,AI Assistant,Alice Johnson,alice@ex.com,Bob Smith,bob@ex.com
```

**Response:**
```json
{
  "successful": 10,
  "failed": 2,
  "total": 12,
  "errors": [
    {
      "row": 3,
      "teamName": "Team Charlie",
      "error": "Invalid GitHub URL"
    }
  ],
  "teams": [ /* Created team objects */ ],
  "message": "Batch upload completed: 10 successful, 2 failed"
}
```

#### GET `/api/teams/{teamId}`
Get detailed team information.

**Response:**
```json
{
  "id": "uuid",
  "batchId": "4th-sem-2024",
  "batchName": "4th Semester 2024",
  "name": "Team Alpha",
  "repoUrl": "https://github.com/team-alpha/project",
  "description": "AI Assistant Project",
  "status": "active",
  "assignedMentorId": "mentor-uuid",
  "assignedMentorName": "John Mentor",
  "students": [
    {
      "id": "uuid",
      "name": "Alice Johnson",
      "email": "alice@example.com",
      "rollNumber": "CS2021001"
    }
  ],
  "projectAnalysis": {
    "id": "project-uuid",
    "totalScore": 85.5,
    "qualityScore": 88,
    "securityScore": 92,
    "originalityScore": 78,
    "architectureScore": 85,
    "documentationScore": 82,
    "techStack": ["Python", "FastAPI", "React"],
    "lastAnalyzedAt": "2024-01-16T10:00:00Z",
    "status": "completed"
  },
  "healthStatus": "on_track",
  "riskFlags": [],
  "contributionBalance": 85,
  "lastActivity": "2 hours ago",
  "createdAt": "2024-01-15T10:00:00Z",
  "updatedAt": "2024-01-17T10:00:00Z"
}
```

#### PUT `/api/teams/{teamId}`
Update team details (admin only).

**Request:**
```json
{
  "name": "Updated Team Name",
  "description": "Updated description",
  "status": "inactive"
}
```

**Response:**
```json
{
  "team": { /* Updated team object */ },
  "message": "Team updated successfully"
}
```

#### DELETE `/api/teams/{teamId}`
Delete a team and its associated data (admin only).

**Response:**
```json
{
  "success": true,
  "message": "Team deleted successfully"
}
```

#### POST `/api/teams/{teamId}/analyze`
Trigger analysis for a team's repository.

**Request:**
```json
{
  "force": false // If true, re-analyze even if already analyzed
}
```

**Response:**
```json
{
  "jobId": "uuid",
  "projectId": "uuid",
  "status": "queued",
  "message": "Analysis queued successfully"
}
```

---

## Mentor Management APIs

### 4. Mentor CRUD Operations

#### GET `/api/mentors`
Get all mentors (admin only).

**Query Parameters:**
- `batchId` (optional): Filter mentors by batch
- `search` (optional): Search by name or email
- `status` (optional): "active" | "inactive"
- `sort` (optional): "name" | "email" | "teamCount"

**Response:**
```json
{
  "mentors": [
    {
      "id": "uuid",
      "email": "mentor@example.com",
      "fullName": "John Mentor",
      "avatarUrl": "https://...",
      "status": "active",
      "teamCount": 3,
      "batches": ["4th-sem-2024", "6th-sem-2024"],
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 10
}
```

#### POST `/api/mentors`
Add a new mentor (admin only).

**Request:**
```json
{
  "email": "newmentor@example.com",
  "fullName": "Jane Mentor",
  "status": "active"
}
```

**Response:**
```json
{
  "mentor": { /* Mentor object */ },
  "message": "Mentor added successfully"
}
```

#### GET `/api/mentors/{mentorId}`
Get mentor details with assigned teams.

**Response:**
```json
{
  "id": "uuid",
  "email": "mentor@example.com",
  "fullName": "John Mentor",
  "avatarUrl": "https://...",
  "status": "active",
  "assignedTeams": [
    {
      "teamId": "uuid",
      "teamName": "Team Alpha",
      "batchId": "4th-sem-2024",
      "batchName": "4th Semester 2024",
      "status": "active",
      "healthStatus": "on_track",
      "lastActivity": "2 hours ago"
    }
  ],
  "teamCount": 3,
  "batches": ["4th-sem-2024"],
  "createdAt": "2024-01-01T00:00:00Z"
}
```

#### PUT `/api/mentors/{mentorId}`
Update mentor details (admin only).

**Request:**
```json
{
  "fullName": "Updated Name",
  "status": "inactive"
}
```

**Response:**
```json
{
  "mentor": { /* Updated mentor object */ },
  "message": "Mentor updated successfully"
}
```

#### DELETE `/api/mentors/{mentorId}`
Remove a mentor (admin only). Unassigns all teams first.

**Response:**
```json
{
  "success": true,
  "message": "Mentor removed successfully",
  "unassignedTeams": 3
}
```

---

## Assignment APIs

### 5. Mentor-Team Assignments

#### POST `/api/assignments`
Assign teams to a mentor (admin only).

**Request:**
```json
{
  "mentorId": "mentor-uuid",
  "teamIds": ["team-uuid-1", "team-uuid-2", "team-uuid-3"]
}
```

**Response:**
```json
{
  "success": true,
  "message": "3 teams assigned to mentor successfully",
  "assignments": [
    {
      "id": "assignment-uuid",
      "mentorId": "mentor-uuid",
      "teamId": "team-uuid-1",
      "assignedAt": "2024-01-17T10:00:00Z"
    }
  ]
}
```

#### DELETE `/api/assignments`
Unassign teams from a mentor (admin only).

**Request:**
```json
{
  "mentorId": "mentor-uuid",
  "teamIds": ["team-uuid-1", "team-uuid-2"]
}
```

**Response:**
```json
{
  "success": true,
  "message": "2 teams unassigned successfully"
}
```

#### GET `/api/assignments/unassigned`
Get teams that are not assigned to any mentor (admin only).

**Query Parameters:**
- `batchId` (required): Batch ID to filter

**Response:**
```json
{
  "teams": [
    {
      "id": "uuid",
      "name": "Team Unassigned",
      "batchId": "4th-sem-2024",
      "repoUrl": "https://...",
      "status": "active"
    }
  ],
  "total": 5
}
```

---

## Admin Portal APIs

### 6. Admin Dashboard

#### GET `/api/admin/dashboard`
Get admin dashboard overview for a specific batch.

**Query Parameters:**
- `batchId` (required): Batch ID

**Response:**
```json
{
  "batchId": "4th-sem-2024",
  "batchName": "4th Semester 2024",
  "overview": {
    "totalTeams": 12,
    "activeTeams": 10,
    "inactiveTeams": 2,
    "totalMentors": 4,
    "totalStudents": 48,
    "unassignedTeams": 2,
    "analysisQueue": 1
  },
  "healthDistribution": {
    "onTrack": 7,
    "atRisk": 3,
    "critical": 2
  },
  "recentActivity": [
    {
      "id": "uuid",
      "type": "team_created",
      "message": "New team added",
      "teamName": "Team Alpha",
      "timestamp": "2024-01-17T09:30:00Z"
    },
    {
      "id": "uuid",
      "type": "analysis_completed",
      "message": "Project completed analysis",
      "teamName": "Team Beta",
      "timestamp": "2024-01-17T09:15:00Z"
    }
  ],
  "mentorWorkload": [
    {
      "mentorId": "uuid",
      "mentorName": "John Mentor",
      "assignedTeams": 3,
      "onTrack": 2,
      "atRisk": 1
    }
  ]
}
```

#### GET `/api/admin/users`
Get all users with role management (admin only).

**Query Parameters:**
- `role` (optional): "admin" | "mentor"
- `search` (optional): Search by name or email
- `page` (optional): Page number
- `pageSize` (optional): Items per page

**Response:**
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "fullName": "John Doe",
      "role": "mentor",
      "status": "active",
      "lastLogin": "2024-01-17T10:00:00Z",
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 25,
  "page": 1,
  "pageSize": 20
}
```

#### PUT `/api/admin/users/{userId}/role`
Change user role (admin only).

**Request:**
```json
{
  "role": "mentor" // "admin" | "mentor"
}
```

**Response:**
```json
{
  "user": { /* Updated user object */ },
  "message": "User role updated successfully"
}
```

---

## Mentor Portal APIs

### 7. Mentor Dashboard & Teams

#### GET `/api/mentor/dashboard`
Get mentor's dashboard with assigned teams overview.

**Response:**
```json
{
  "mentorId": "uuid",
  "mentorName": "John Mentor",
  "overview": {
    "totalTeams": 3,
    "onTrack": 2,
    "atRisk": 1,
    "critical": 0
  },
  "teams": [
    {
      "id": "uuid",
      "name": "Team Alpha",
      "batchId": "4th-sem-2024",
      "batchName": "4th Semester 2024",
      "repoUrl": "https://github.com/team-alpha/project",
      "healthStatus": "on_track",
      "lastActivity": "2 hours ago",
      "contributionBalance": 85,
      "riskFlags": [],
      "totalScore": 85.5
    }
  ],
  "recentActivity": [
    {
      "teamId": "uuid",
      "teamName": "Team Alpha",
      "type": "commit",
      "message": "New commits pushed",
      "timestamp": "2024-01-17T09:30:00Z"
    }
  ]
}
```

#### GET `/api/mentor/teams`
Get all teams assigned to mentor.

**Query Parameters:**
- `batchId` (optional): Filter by batch
- `healthStatus` (optional): "on_track" | "at_risk" | "critical"
- `search` (optional): Search by team name
- `sort` (optional): "name" | "lastActivity" | "healthStatus"

**Response:**
```json
{
  "teams": [ /* Array of team objects */ ],
  "total": 3
}
```

---

## Analysis & Reports APIs

### 8. Team Analytics

#### GET `/api/teams/{teamId}/analytics`
Get comprehensive analytics for a team (admin or assigned mentor only).

**Response:**
```json
{
  "teamId": "uuid",
  "teamName": "Team Alpha",
  "batchId": "4th-sem-2024",
  "analysis": {
    "totalScore": 85.5,
    "qualityScore": 88,
    "securityScore": 92,
    "originalityScore": 78,
    "architectureScore": 85,
    "documentationScore": 82
  },
  "commits": {
    "total": 150,
    "lastWeek": 25,
    "contributionDistribution": [
      {
        "contributorName": "Alice Johnson",
        "commits": 75,
        "percentage": 50,
        "additions": 5000,
        "deletions": 1000
      }
    ],
    "timeline": [
      {
        "date": "2024-01-17",
        "commits": 5,
        "additions": 250,
        "deletions": 50
      }
    ],
    "burstDetected": false,
    "lastMinuteCommits": 10
  },
  "codeMetrics": {
    "totalFiles": 42,
    "totalLinesOfCode": 5000,
    "languages": [
      { "name": "Python", "percentage": 65 },
      { "name": "JavaScript", "percentage": 35 }
    ],
    "techStack": ["Python", "FastAPI", "React", "PostgreSQL"],
    "architecturePattern": "Client-Server"
  },
  "security": {
    "score": 92,
    "issues": [
      {
        "type": "Hardcoded Secret",
        "severity": "high",
        "file": "config.py",
        "line": 42,
        "description": "API key detected"
      }
    ],
    "secretsDetected": 1
  },
  "aiAnalysis": {
    "aiGeneratedPercentage": 25,
    "verdict": "Partially AI-assisted",
    "strengths": [
      "Well-documented codebase",
      "Good project structure"
    ],
    "improvements": [
      "Add more unit tests",
      "Reduce code duplication"
    ]
  },
  "healthStatus": "on_track",
  "riskFlags": [],
  "lastAnalyzedAt": "2024-01-16T10:00:00Z"
}
```

#### GET `/api/teams/{teamId}/commits`
Get commit history for a team.

**Query Parameters:**
- `author` (optional): Filter by contributor name
- `startDate` (optional): Filter from date
- `endDate` (optional): Filter to date
- `page` (optional): Page number
- `pageSize` (optional): Items per page

**Response:**
```json
{
  "commits": [
    {
      "sha": "commit-hash",
      "author": "Alice Johnson",
      "authorEmail": "alice@example.com",
      "message": "Add user authentication",
      "date": "2024-01-17T09:30:00Z",
      "additions": 150,
      "deletions": 20,
      "filesChanged": 3
    }
  ],
  "total": 150,
  "page": 1,
  "pageSize": 20
}
```

#### GET `/api/teams/{teamId}/file-tree`
Get repository file tree structure.

**Response:**
```json
{
  "tree": [
    {
      "path": "src",
      "type": "directory",
      "children": [
        {
          "path": "src/main.py",
          "type": "file",
          "size": 1024,
          "language": "Python"
        }
      ]
    }
  ],
  "totalFiles": 42,
  "totalSize": 512000
}
```

### 9. Reports

#### GET `/api/reports/batch/{batchId}`
Generate batch-wide report (admin only).

**Query Parameters:**
- `format` (optional): "json" | "pdf" | "csv"

**Response (JSON):**
```json
{
  "batchId": "4th-sem-2024",
  "batchName": "4th Semester 2024",
  "generatedAt": "2024-01-17T10:00:00Z",
  "summary": {
    "totalTeams": 12,
    "averageScore": 78.5,
    "topTeam": "Team Alpha",
    "topScore": 92.5
  },
  "teams": [
    {
      "rank": 1,
      "teamName": "Team Alpha",
      "totalScore": 92.5,
      "qualityScore": 95,
      "securityScore": 90
    }
  ],
  "insights": {
    "mostUsedTech": "Python",
    "averageAiUsage": 18.5,
    "totalSecurityIssues": 45
  }
}
```

#### GET `/api/reports/mentor/{mentorId}`
Generate report for mentor's assigned teams (admin or mentor).

**Query Parameters:**
- `batchId` (optional): Filter by batch
- `format` (optional): "json" | "pdf"

**Response:**
```json
{
  "mentorId": "uuid",
  "mentorName": "John Mentor",
  "generatedAt": "2024-01-17T10:00:00Z",
  "teams": [ /* Mentor's team data */ ],
  "summary": {
    "totalTeams": 3,
    "averageScore": 82.3,
    "teamsOnTrack": 2,
    "teamsAtRisk": 1
  }
}
```

#### GET `/api/reports/team/{teamId}`
Generate detailed team report.

**Query Parameters:**
- `format` (optional): "json" | "pdf"

**Response:** Same as GET `/api/teams/{teamId}/analytics` with additional formatting

---

## Database Schema Changes

### 10. New Tables Required

#### `batches` table
```sql
CREATE TABLE batches (
  id VARCHAR(100) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  semester VARCHAR(50) NOT NULL,
  year VARCHAR(10) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status VARCHAR(50) DEFAULT 'active', -- active, completed, archived
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_batches_status ON batches(status);
CREATE INDEX idx_batches_year ON batches(year);
```

#### `teams` table
```sql
CREATE TABLE teams (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id VARCHAR(100) NOT NULL REFERENCES batches(id),
  name VARCHAR(255) NOT NULL,
  repo_url VARCHAR(500) NOT NULL,
  description TEXT,
  status VARCHAR(50) DEFAULT 'active', -- active, inactive, archived
  assigned_mentor_id UUID REFERENCES users(id),
  project_id UUID REFERENCES projects(id), -- Link to analyzed project
  health_status VARCHAR(50) DEFAULT 'on_track', -- on_track, at_risk, critical
  risk_flags JSONB DEFAULT '[]',
  contribution_balance FLOAT DEFAULT 0,
  last_activity_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(batch_id, name),
  UNIQUE(repo_url)
);

CREATE INDEX idx_teams_batch_id ON teams(batch_id);
CREATE INDEX idx_teams_mentor_id ON teams(assigned_mentor_id);
CREATE INDEX idx_teams_status ON teams(status);
CREATE INDEX idx_teams_health_status ON teams(health_status);
```

#### `students` table
```sql
CREATE TABLE students (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  roll_number VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW(),
  
  UNIQUE(team_id, email)
);

CREATE INDEX idx_students_team_id ON students(team_id);
CREATE INDEX idx_students_email ON students(email);
```

#### `mentor_team_assignments` table
```sql
CREATE TABLE mentor_team_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mentor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  assigned_at TIMESTAMP DEFAULT NOW(),
  assigned_by UUID REFERENCES users(id),
  
  UNIQUE(team_id) -- One team can only have one mentor
);

CREATE INDEX idx_assignments_mentor_id ON mentor_team_assignments(mentor_id);
CREATE INDEX idx_assignments_team_id ON mentor_team_assignments(team_id);
```

#### Update `users` table
```sql
ALTER TABLE users
  ADD COLUMN status VARCHAR(50) DEFAULT 'active',
  ADD COLUMN last_login_at TIMESTAMP;

-- Ensure role column exists with proper constraints
ALTER TABLE users
  ALTER COLUMN role SET DEFAULT 'mentor',
  ADD CONSTRAINT valid_role CHECK (role IN ('admin', 'mentor'));
```

#### Update `projects` table
```sql
ALTER TABLE projects
  ADD COLUMN batch_id VARCHAR(100) REFERENCES batches(id),
  ADD COLUMN team_id UUID REFERENCES teams(id);

CREATE INDEX idx_projects_batch_id ON projects(batch_id);
CREATE INDEX idx_projects_team_id ON projects(team_id);
```

---

## Implementation Priority

### Phase 1: Core Infrastructure (Week 1)
1. ✅ Authentication & user management endpoints
2. ✅ Batch CRUD operations
3. ✅ Database schema migration
4. ✅ Role-based middleware

### Phase 2: Team & Mentor Management (Week 2)
1. ✅ Team CRUD operations
2. ✅ Mentor CRUD operations
3. ✅ Assignment system
4. ✅ CSV batch upload

### Phase 3: Portal Features (Week 3)
1. ✅ Admin dashboard endpoints
2. ✅ Mentor dashboard endpoints
3. ✅ Team analytics endpoints
4. ✅ Health status calculation logic

### Phase 4: Reports & Analytics (Week 4)
1. ✅ Team analytics detailed view
2. ✅ Batch reports
3. ✅ Mentor reports
4. ✅ PDF generation

---

## Authorization Matrix

| Endpoint | Public | Mentor | Admin |
|----------|--------|--------|-------|
| GET /api/auth/user | ✅ | ✅ | ✅ |
| GET /api/batches | ❌ | ❌ | ✅ |
| POST /api/batches | ❌ | ❌ | ✅ |
| GET /api/teams | ❌ | ✅* | ✅ |
| POST /api/teams | ❌ | ❌ | ✅ |
| GET /api/teams/{id} | ❌ | ✅* | ✅ |
| GET /api/teams/{id}/analytics | ❌ | ✅* | ✅ |
| GET /api/mentors | ❌ | ❌ | ✅ |
| POST /api/mentors | ❌ | ❌ | ✅ |
| POST /api/assignments | ❌ | ❌ | ✅ |
| GET /api/mentor/dashboard | ❌ | ✅ | ❌ |
| GET /api/admin/dashboard | ❌ | ❌ | ✅ |
| GET /api/reports/* | ❌ | ✅* | ✅ |

*Mentor can only access their assigned teams

---

## Response Format Standards

### Success Response
```json
{
  "data": { /* Response payload */ },
  "message": "Operation successful",
  "timestamp": "2024-01-17T10:00:00Z"
}
```

### Error Response
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "batchId",
      "issue": "Required field missing"
    }
  },
  "timestamp": "2024-01-17T10:00:00Z"
}
```

### Pagination Response
```json
{
  "data": [ /* Array of items */ ],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "total": 100,
    "totalPages": 5,
    "hasNext": true,
    "hasPrevious": false
  }
}
```

---

## Testing Requirements

### Unit Tests
- [ ] All CRUD operations
- [ ] Authorization middleware
- [ ] Batch filtering logic
- [ ] Assignment validation
- [ ] Health status calculation

### Integration Tests
- [ ] Admin workflow: Create batch → Add teams → Assign mentors
- [ ] Mentor workflow: View assigned teams → Access analytics
- [ ] CSV batch upload
- [ ] Report generation
- [ ] Role-based access control

### E2E Tests
- [ ] Admin portal full workflow
- [ ] Mentor portal full workflow
- [ ] Authentication flows
- [ ] Batch switching

---

## Notes for Implementation

1. **Middleware Required:**
   - `requireAuth()` - Verify JWT token
   - `requireRole(['admin'])` - Admin-only endpoints
   - `requireRole(['admin', 'mentor'])` - Both roles
   - `requireMentorAccess(teamId)` - Verify mentor has access to team

2. **Business Logic:**
   - Calculate health status based on:
     - Last activity time (>3 days = at risk)
     - Contribution balance (<50% = at risk)
     - Security issues (>5 = critical)
     - Burst commits (>50% in last 20% = at risk)
   
3. **Performance Considerations:**
   - Cache batch statistics
   - Paginate all list endpoints
   - Index foreign keys
   - Consider Redis for frequently accessed data

4. **Security:**
   - Validate batch/team ownership before allowing access
   - Prevent SQL injection in search queries
   - Rate limit batch upload endpoints
   - Sanitize CSV input

---

**End of API Requirements Document**
