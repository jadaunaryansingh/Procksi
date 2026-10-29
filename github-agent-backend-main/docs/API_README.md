# Repository Analysis Backend API

Complete FastAPI backend for analyzing GitHub repositories with AI-powered scoring and plagiarism detection.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Supabase Database

1. Create a new project at [supabase.com](https://supabase.com)
2. Run the SQL schema from `supabase_schema.sql` in the SQL Editor
3. Copy your Supabase credentials to `.env`:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
```

### 3. Run the Server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --reload --port 8000
```

### 4. Access API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📡 API Endpoints

### Repository Analysis

#### `POST /api/analyze-repo`
Trigger repository analysis
```json
{
  "repo_url": "https://github.com/username/repo",
  "team_name": "Team Name" // optional
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "status": "queued",
  "message": "Analysis queued successfully"
}
```

#### `GET /api/analysis-status/{job_id}`
Poll for analysis progress (0-100%)

**Response:**
```json
{
  "job_id": "uuid",
  "project_id": "uuid",
  "status": "running",
  "progress": 60,
  "current_stage": "quality_check",
  "started_at": "2026-01-08T10:00:00Z"
}
```

#### `GET /api/analysis-result/{job_id}`
Get complete analysis results (only when status is "completed")

**Response:**
```json
{
  "project_id": "uuid",
  "repo_url": "https://github.com/...",
  "team_name": "Team Name",
  "status": "completed",
  "scores": {
    "total_score": 78.5,
    "originality_score": 85.0,
    "quality_score": 72.0,
    "security_score": 90.0,
    ...
  },
  "tech_stack": [...],
  "issues": [...],
  "team_members": [...],
  "verdict": "Production Ready"
}
```

### Data Management

#### `GET /api/projects`
List all projects with pagination and filters

**Query Parameters:**
- `status`: Filter by status (pending, analyzing, completed, failed)
- `min_score`: Minimum total score
- `max_score`: Maximum total score
- `team_name`: Filter by team name
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20, max: 100)

#### `GET /api/projects/{project_id}`
Get detailed project information

#### `DELETE /api/projects/{project_id}`
Delete project and all related data

### Leaderboard

#### `GET /api/leaderboard`
Get ranked projects

**Query Parameters:**
- `sort_by`: Field to sort by (default: total_score)
- `order`: asc or desc (default: desc)
- `page`: Page number
- `page_size`: Items per page
- `status`: Filter by status (default: completed)

#### `POST /api/batch-upload`
Submit multiple repositories for analysis

```json
{
  "repos": [
    {
      "repo_url": "https://github.com/user/repo1",
      "team_name": "Team 1"
    },
    {
      "repo_url": "https://github.com/user/repo2",
      "team_name": "Team 2"
    }
  ]
}
```

## 🏗️ Architecture

```
main.py                          # FastAPI application entry
backend/
├── database.py                  # Supabase client connection
├── models.py                    # Pydantic data models
├── schemas.py                   # API request/response schemas
├── crud.py                      # Database CRUD operations
├── background.py                # Background job processing
├── routers/
│   ├── analysis.py             # Analysis endpoints
│   ├── projects.py             # Project management
│   └── leaderboard.py          # Leaderboard & batch upload
├── services/
│   ├── analyzer_service.py     # Analysis pipeline wrapper
│   └── data_mapper.py          # Map results to database
└── utils/
    └── progress_tracker.py     # Job progress tracking
```

## 📊 Analysis Pipeline

The analysis runs through 10 stages:

1. **Starting** (0%) - Initialize
2. **Cloning** (10%) - Clone repository
3. **Stack Detection** (20%) - Detect tech stack
4. **Structure Analysis** (30%) - Analyze architecture
5. **Maturity Check** (40%) - Check deployment readiness
6. **Commit Forensics** (50%) - Analyze git history
7. **Quality Check** (60%) - Code quality metrics
8. **Security Scan** (70%) - Scan for secrets/vulnerabilities
9. **Forensic Analysis** (80%) - AI detection & plagiarism
10. **AI Judge** (90%) - Gemini product evaluation
11. **Aggregation** (95%) - Save results
12. **Completed** (100%) - Done

## 🗃️ Database Schema

### Tables
- **projects** - Main project records with scores
- **analysis_jobs** - Track analysis job progress
- **tech_stack** - Detected technologies (many-to-many)
- **issues** - Security/quality/plagiarism issues
- **team_members** - Team contribution stats

See `supabase_schema.sql` for complete schema.

## 🔧 Configuration

All configuration via environment variables in `.env`:

```env
# Supabase
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_SERVICE_KEY=...

# API Keys (for analysis)
GEMINI_API_KEY=...
GITHUB_API_KEY=...

# Optional
PORT=8000
LOG_LEVEL=INFO
```

## 🧪 Testing

### Test Database Connection
```bash
python -c "from backend.database import get_supabase_client; print(get_supabase_client())"
```

### Test Analysis
```bash
curl -X POST http://localhost:8000/api/analyze-repo \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/user/repo"}'
```

### Check Health
```bash
curl http://localhost:8000/health
```

## 🚀 Deployment

### Production Checklist
- [ ] Update CORS origins in `main.py`
- [ ] Set proper environment variables
- [ ] Configure Supabase RLS policies (optional)
- [ ] Setup monitoring/logging
- [ ] Configure rate limiting
- [ ] Setup Redis for job queue (optional)

### Deploy Options
- **Railway**: Connect GitHub repo, Railway auto-detects Python
- **Render**: Web service from repo
- **Fly.io**: `fly launch` and deploy
- **Cloud Run**: Deploy as container

## 📝 License

MIT
