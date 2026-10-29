# Repository Analysis API - Frontend Integration Guide

## Base URL
```
http://localhost:8000
```

## Authentication
Currently no authentication required (add in production)

---

## Endpoints

### 1. Submit Repository for Analysis
**POST** `/api/analyze-repo`

Submit a GitHub repository for analysis.

**Request Body:**
```json
{
  "repo_url": "https://github.com/owner/repo",
  "team_name": "Team Name" // optional
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "message": "Analysis started",
  "status": "pending"
}
```

---

### 2. Check Analysis Status
**GET** `/api/analysis-status/{job_id}`

Get real-time progress of analysis job.

**Response:**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "status": "processing",  // pending, processing, completed, failed
  "progress": 45,  // 0-100
  "current_stage": "forensic_analysis",
  "message": "Analyzing commit patterns..."
}
```

**Progress Stages:**
1. `cloning` - Cloning repository
2. `forensic_analysis` - Analyzing commits and contributions
3. `structure_scan` - Scanning project structure
4. `ai_judge` - AI evaluation in progress
5. `aggregation` - Finalizing scores

---

### 3. Get Project Detail
**GET** `/api/projects/{id}`

Get complete project evaluation (matches frontend `ProjectEvaluation` interface).

**Response:**
```json
{
  // Identity
  "id": "uuid",
  "teamName": "Team Name",
  "repoUrl": "https://github.com/owner/repo",
  "submittedAt": "2024-01-15T10:30:00Z",
  "status": "completed",
  
  // Tech Stack
  "techStack": ["Python", "JavaScript", "Docker"],
  "languages": [
    {"name": "Python", "percentage": 65.5},
    {"name": "JavaScript", "percentage": 30.2},
    {"name": "Shell", "percentage": 4.3}
  ],
  "architecturePattern": "Microservices",
  "frameworks": ["FastAPI", "React", "Docker"],
  
  // Scores (0-100)
  "totalScore": 75.5,
  "qualityScore": 80.0,
  "securityScore": 70.0,
  "originalityScore": 85.0,
  "architectureScore": 75.0,
  "documentationScore": 65.0,
  
  // Commit Forensics
  "totalCommits": 250,
  "contributors": [
    {
      "name": "John Doe",
      "commits": 150,
      "additions": 5000,
      "deletions": 2000,
      "percentage": 60.0
    }
  ],
  "commitPatterns": [
    {
      "pattern": "Regular development",
      "timeframe": "Last 7 days",
      "count": 45
    }
  ],
  "burstCommitWarning": false,
  "lastMinuteCommits": 3,
  
  // Security
  "securityIssues": [
    {
      "type": "Hardcoded Secret",
      "severity": "high",
      "file": "config.py",
      "line": 42,
      "description": "API key found in source code"
    }
  ],
  "secretsDetected": 2,
  
  // AI Analysis
  "aiGeneratedPercentage": 15.5,
  "aiVerdict": "The project demonstrates solid engineering practices...",
  "strengths": [
    "Well-structured codebase",
    "Comprehensive test coverage",
    "Good documentation"
  ],
  "improvements": [
    "Add more error handling",
    "Implement rate limiting",
    "Improve security practices"
  ],
  
  // Project Stats
  "totalFiles": 156,
  "totalLinesOfCode": 12500,
  "testCoverage": 75.5
}
```

---

### 4. List All Projects
**GET** `/api/projects`

Get list of all projects with optional filters.

**Query Parameters:**
- `status` (optional): Filter by status (`all`, `completed`, `processing`, `failed`)
- `tech` (optional): Filter by technology (e.g., `Python`, `React`)
- `sort` (optional): Sort order (`recent`, `score`) - default: `recent`
- `search` (optional): Search in team name or repo URL

**Response:** Array of `ProjectListItem`
```json
[
  {
    "id": "uuid",
    "teamName": "Team Name",
    "repoUrl": "https://github.com/owner/repo",
    "status": "completed",
    "totalScore": 75.5,
    "techStack": ["Python", "FastAPI", "React"],
    "securityIssues": 2,
    "submittedAt": "2024-01-15T10:30:00Z"
  }
]
```

**Example Usage:**
```
GET /api/projects?status=completed&sort=score
GET /api/projects?tech=Python&sort=recent
GET /api/projects?search=team1
```

---

### 5. Get Leaderboard
**GET** `/api/leaderboard`

Get ranked list of projects (only completed).

**Query Parameters:**
- `tech` (optional): Filter by technology
- `sort` (optional): Score type to sort by (`total`, `quality`, `security`, `originality`, `architecture`, `documentation`)
- `search` (optional): Search team names

**Response:** Array of `LeaderboardEntry`
```json
[
  {
    "id": "uuid",
    "teamName": "Team Alpha",
    "repoUrl": "https://github.com/team/repo",
    "techStack": ["Python", "React"],
    "totalScore": 85.5,
    "qualityScore": 90.0,
    "securityScore": 80.0,
    "originalityScore": 85.0,
    "architectureScore": 88.0,
    "documentationScore": 82.0
  }
]
```

---

### 6. Get Leaderboard Chart Data
**GET** `/api/leaderboard/chart`

Get top 10 projects with all scores for chart visualization.

**Response:**
```json
[
  {
    "teamName": "Team Alpha",
    "totalScore": 85.5,
    "qualityScore": 90.0,
    "securityScore": 80.0,
    "originalityScore": 85.0,
    "architectureScore": 88.0,
    "documentationScore": 82.0
  }
]
```

---

### 7. Get Dashboard Stats
**GET** `/api/stats`

Get aggregate statistics for dashboard.

**Response:**
```json
{
  "totalProjects": 50,
  "completedProjects": 45,
  "inProgressProjects": 3,
  "averageScore": 72.5,
  "totalTechnologies": 25,
  "totalSecurityIssues": 120,
  "projectsByStatus": {
    "completed": 45,
    "processing": 3,
    "failed": 2
  }
}
```

---

### 8. Get Available Technologies
**GET** `/api/tech-stacks`

Get list of all technologies used across projects (for filters).

**Response:**
```json
[
  {"name": "Python", "count": 30},
  {"name": "JavaScript", "count": 25},
  {"name": "React", "count": 20},
  {"name": "Docker", "count": 15}
]
```

---

### 9. Delete Project
**DELETE** `/api/projects/{id}`

Delete a project and all related data.

**Response:**
```json
{
  "message": "Project deleted successfully"
}
```

---

### 10. Batch Upload
**POST** `/api/batch-upload`

Submit multiple repositories in CSV format.

**Request Body:**
```json
{
  "csv_content": "team_name,repo_url\nTeam1,https://github.com/..."
}
```

**Response:**
```json
{
  "batch_id": "uuid",
  "submitted_count": 10,
  "message": "Batch upload started"
}
```

---

## Data Format Notes

### Naming Convention
- All field names use **camelCase** (e.g., `teamName`, `repoUrl`, `totalScore`)
- This matches JavaScript/TypeScript conventions

### Date Format
- All dates are in ISO 8601 format: `2024-01-15T10:30:00Z`

### Score Range
- All scores are 0-100
- Total score is weighted average of category scores

### Status Values
- `pending` - Queued for analysis
- `processing` - Currently analyzing
- `completed` - Analysis finished
- `failed` - Analysis encountered error

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Status Codes:**
- `200` - Success
- `400` - Bad request (invalid input)
- `404` - Resource not found
- `500` - Internal server error
- `503` - Service unavailable (database error)

---

## Real-time Updates

For real-time progress updates, poll the status endpoint:

```javascript
async function monitorAnalysis(jobId) {
  const checkStatus = async () => {
    const response = await fetch(`/api/analysis-status/${jobId}`);
    const data = await response.json();
    
    console.log(`Progress: ${data.progress}%`);
    console.log(`Stage: ${data.current_stage}`);
    
    if (data.status === 'completed') {
      // Fetch full results
      const result = await fetch(`/api/projects/${data.project_id}`);
      return result.json();
    } else if (data.status === 'failed') {
      throw new Error('Analysis failed');
    } else {
      // Continue polling
      setTimeout(checkStatus, 2000);
    }
  };
  
  return checkStatus();
}
```

---

## Example Frontend Integration

### Submit and Monitor Analysis

```typescript
import axios from 'axios';

const API_BASE = 'http://localhost:8000';

// Submit repository
async function analyzeRepository(repoUrl: string, teamName: string) {
  const response = await axios.post(`${API_BASE}/api/analyze-repo`, {
    repo_url: repoUrl,
    team_name: teamName
  });
  
  return response.data.job_id;
}

// Monitor progress
async function waitForCompletion(jobId: string): Promise<ProjectEvaluation> {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const status = await axios.get(`${API_BASE}/api/analysis-status/${jobId}`);
        
        if (status.data.status === 'completed') {
          clearInterval(interval);
          const result = await axios.get(`${API_BASE}/api/projects/${status.data.project_id}`);
          resolve(result.data);
        } else if (status.data.status === 'failed') {
          clearInterval(interval);
          reject(new Error('Analysis failed'));
        }
      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, 2000); // Poll every 2 seconds
  });
}

// Usage
const jobId = await analyzeRepository('https://github.com/user/repo', 'My Team');
const result = await waitForCompletion(jobId);
console.log('Analysis complete:', result);
```

### Fetch Dashboard Data

```typescript
async function loadDashboard() {
  // Get stats
  const stats = await axios.get(`${API_BASE}/api/stats`);
  
  // Get recent projects
  const projects = await axios.get(`${API_BASE}/api/projects?sort=recent`);
  
  // Get leaderboard
  const leaderboard = await axios.get(`${API_BASE}/api/leaderboard?sort=total`);
  
  return {
    stats: stats.data,
    recentProjects: projects.data,
    topTeams: leaderboard.data.slice(0, 10)
  };
}
```

### Filter Projects

```typescript
async function filterProjects(filters: {
  status?: string;
  tech?: string;
  search?: string;
}) {
  const params = new URLSearchParams();
  if (filters.status) params.append('status', filters.status);
  if (filters.tech) params.append('tech', filters.tech);
  if (filters.search) params.append('search', filters.search);
  
  const response = await axios.get(`${API_BASE}/api/projects?${params}`);
  return response.data;
}
```

---

## Notes for Production

1. **Add Authentication**: Implement JWT tokens or API keys
2. **Rate Limiting**: Add rate limits to prevent abuse
3. **CORS**: Update CORS settings with specific frontend origins
4. **Caching**: Add Redis caching for leaderboard and stats
5. **WebSockets**: Consider WebSocket for real-time progress updates instead of polling
6. **Pagination**: Add pagination for large lists (projects, leaderboard)
7. **Error Tracking**: Integrate Sentry or similar for error monitoring

---

## Testing the API

Use the provided test script:

```bash
# Make sure server is running
python main.py

# In another terminal
python test_frontend_api.py
```

Or use the interactive API docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
