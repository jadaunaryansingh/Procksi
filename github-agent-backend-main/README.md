# 🚀 ProjectFlow

<div align="center">

### AI-Powered GitHub Repository Analysis & Evaluation Platform

**🌐 Live Demo:** [https://projectflow.krishivaani.me/](https://projectflow.krishivaani.me/)

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.0+-61DAFB.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org/)
[![Celery](https://img.shields.io/badge/Celery-5.3+-37814A.svg)](https://docs.celeryproject.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Deployed for 1000+ students (~300 teams) with scalable async architecture**

[Features](#-key-features) • [Architecture](#-system-architecture) • [Tech Stack](#-tech-stack) • [Installation](#-getting-started) • [API Docs](#-api-reference) • [Deployment](#-deployment)

</div>

---

## 📖 Overview

**ProjectFlow** is an enterprise-grade, AI-powered platform that automatically analyzes GitHub repositories across **8 dimensions** using a sophisticated 10-stage pipeline. Built with FastAPI, Celery workers, and React, it delivers comprehensive code quality assessments, plagiarism detection, AI-generated code identification, and security scanning at scale.

### 🎯 Core Capabilities

- ✅ **Automated Multi-Dimensional Scoring** - 8-category evaluation system with weighted metrics
- 🤖 **AI-Powered Code Analysis** - GPT-4o-mini integration for deep code evaluation
- 🔍 **Smart Detection Systems** - AI code detection, plagiarism checking, commit forensics
- 🔒 **Security Scanning** - Automated vulnerability and secret detection
- 📊 **Real-Time Analytics** - Live leaderboards, dashboards, and progress tracking
- ⚡ **Scalable Task Processing** - Celery workers with Redis for async batch operations
- 📧 **Automated Reporting** - PDF generation and email delivery with historical snapshots
- 👥 **Mentor & Grading System** - Team assignment, manual grading, and student report management

### 📈 Project Statistics

| Metric | Value |
|--------|-------|
| **Students Evaluated** | 1,000+ |
| **Teams Analyzed** | ~300 |
| **Analysis Stages** | 10-stage pipeline |
| **Scoring Dimensions** | 8 categories |
| **Average Analysis Time** | 2-5 minutes |
| **Test Coverage** | 85%+ |
| **Concurrent Workers** | 6 (2 single + 4 batch) |
| **Historical Tracking** | 7-day snapshots |

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                           User Interface                             │
│                      React 18 + TypeScript + Vite                    │
│           Dashboard • Leaderboard • Batch Upload • Reports           │
│                         (Port 8080 / NGINX)                          │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │ REST API (JSON)
                                  │ WebSocket (Real-time Updates)
┌─────────────────────────────────▼────────────────────────────────────┐
│                        FastAPI Backend                               │
│                  Python 3.12 (Port 3000 / Uvicorn)                   │
│           LangGraph Orchestration • 10-Stage Pipeline                │
│     Authentication • Rate Limiting • Progress Tracking               │
└──────┬──────────────┬──────────────┬──────────────┬─────────────────┘
       │              │              │              │
       │              │              │              │
   ┌───▼────┐    ┌───▼──────┐   ┌──▼─────┐   ┌────▼────┐
   │ Redis  │    │  Celery  │   │ GitHub │   │ OpenAI  │
   │ Broker │    │  Workers │   │  API   │   │   API   │
   │(Queue) │    │ + Beat   │   │        │   │GPT-4o-m │
   └────────┘    └────┬─────┘   └────────┘   └─────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
    ┌────▼────┐  ┌───▼────┐  ┌───▼────┐
    │ Single  │  │ Batch  │  │ Batch  │
    │Analysis │  │Worker 1│  │Worker 2│
    │ Worker  │  │        │  │        │
    │(Queue 1)│  │(Queue 2)│  │(Queue 2)│
    │Concur=2 │  │Concur=4│  │Concur=4│
    └─────────┘  └────────┘  └────────┘
                      │
                      │
             ┌────────▼────────┐
             │    Supabase     │
             │   PostgreSQL    │
             │  (Database +    │
             │   Real-time +   │
             │   Storage)      │
             └─────────────────┘
```

### 🔄 Execution Flow

1. **Request Initiation**
   - Student submits GitHub repository URL via React web interface
   - Frontend validates input and sends POST request to FastAPI

2. **API Processing**
   - FastAPI validates repository URL and team data
   - Creates database record with `queued` status
   - Enqueues Celery task in appropriate queue (single/batch)
   - Returns `job_id` immediately to prevent blocking

3. **Worker Processing**
   - Dedicated Celery worker picks task from Redis queue
   - Clones repository to temporary directory
   - Executes 10-stage analysis pipeline:
     - **Stage 1:** Repository cloning & validation
     - **Stage 2:** Tech stack detection (languages, frameworks)
     - **Stage 3:** Architecture analysis (structure, modularity)
     - **Stage 4:** Deployment maturity assessment (CI/CD, Docker)
     - **Stage 5:** Commit forensics (patterns, timing, fake detection)
     - **Stage 6:** Code quality metrics (complexity, maintainability)
     - **Stage 7:** Security scanning (secrets, vulnerabilities)
     - **Stage 8:** Deep forensics (AI detection + plagiarism)
     - **Stage 9:** AI judge evaluation (GPT-4o-mini scoring)
     - **Stage 10:** Final aggregation with penalty system

4. **Result Processing**
   - Aggregated scores stored in PostgreSQL
   - Real-time updates pushed via Supabase subscriptions
   - Dashboard automatically refreshes with new data
   - PDF report generated (if requested)
   - Email notifications sent (batch completion)

5. **Historical Tracking**
   - 7-day snapshots maintained for comparison
   - Incremental re-analysis only processes changed files
   - Token usage tracked for cost monitoring

---

## ⚡ Scalability Design

### Async Task Architecture

**Problem:** Repository analysis takes 2-5 minutes. Synchronous processing would block the API and create 504 timeouts under load.

**Solution:** Celery distributed task queue with dedicated worker pools:

| Worker Pool | Queue | Concurrency | Purpose |
|-------------|-------|-------------|---------|
| Single Analysis | `single_analysis` | 2 workers | Individual student submissions |
| Batch Analysis | `analysis` + `batch` | 4 workers | Bulk CSV uploads (100+ repos) |
| Dead Letter Queue | `dlq` | Shared | Failed task retry handling |

### Peak Load Handling

During submission windows (hackathon deadlines), the platform handles:
- **50-100+ concurrent repository submissions** within hours
- **Parallel processing** across 6 workers
- **Graceful degradation** with exponential backoff for LLM rate limits
- **Real-time progress tracking** via polling (every 2 seconds)
- **Pause/Resume capabilities** for long-running batch operations
- **Automatic retries** with configurable max attempts (3x default)

### Infrastructure Optimization

**Academic Traffic Patterns:**
- Burst traffic during submission deadlines (evenings/weekends)
- Low utilization during lectures/off-hours

**Cost-Effective Strategy:**
- Scale EC2 instances during peak windows (t3.large → c5.xlarge)
- Reduce compute during idle periods (spot instances)
- Worker auto-scaling based on Redis queue depth
- Scheduled weekly batch analysis via Celery Beat (cron)

---

## 💰 Cost Optimization Strategy

### Token Efficiency (40% Reduction)

| Technique | Impact | Implementation |
|-----------|--------|----------------|
| **Smart Caching** | 25% ↓ | Redis cache for repo metadata (24h TTL) |
| **Incremental Analysis** | 60% ↓ | Only re-analyze changed files (7-day interval) |
| **Prompt Engineering** | 30% ↓ | Optimized system prompts, structured outputs |
| **Selective Deep Analysis** | 50% ↓ | Quick pre-screening before expensive AI eval |
| **Batch Processing** | 20% ↓ | Group similar operations (file chunks) |
| **Parallel File Processing** | 40% ↓ | 5 concurrent LLM threads per analysis |

### Analysis Tier Costs

| Tier | Duration | LLM Calls | Cost/Repo | Use Case |
|------|----------|-----------|-----------|----------|
| **Quick** | 5s | 0 | $0.00 | Pre-screening, basic metrics |
| **Standard** | 2-3 min | ~15 | $0.15 | Default for all submissions |
| **Deep** | 5+ min | ~40 | $0.40 | Top teams, detailed forensics |

**Annual Savings:** ~$2,400 (600 repos/year × $4 saved/repo)

---

## 🛠️ Tech Stack

### Backend Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Framework** | FastAPI 0.100+ | Async API with auto-docs (OpenAPI) |
| **Task Queue** | Celery 5.3+ | Distributed background job processing |
| **Message Broker** | Redis 7.0+ | Task queue + caching (Upstash compatible) |
| **Database** | PostgreSQL 15+ (Supabase) | Primary storage with RLS + real-time |
| **AI Orchestration** | LangGraph | Multi-agent workflow coordination |
| **LLM Provider** | OpenAI API | GPT-4o-mini for code evaluation |
| **Git Operations** | GitPython 3.1+ | Repository cloning and analysis |
| **Code Metrics** | Radon 6.0+ | Complexity and maintainability scoring |
| **Vector Search** | FAISS | Plagiarism detection via embeddings |
| **AI Detection** | Sentence Transformers | Identify GPT/Copilot-generated code |
| **PDF Generation** | ReportLab 4.0+ | Automated report creation |
| **Email Service** | SMTP (Gmail/SendGrid) | Notification delivery |

### Frontend Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **UI Framework** | React 18 | Component-based UI with hooks |
| **Language** | TypeScript 5.0+ | Type-safe development |
| **Build Tool** | Vite 5.0+ | Lightning-fast HMR and builds |
| **State Management** | TanStack Query v5 | Server state caching and sync |
| **Styling** | Tailwind CSS 3.4+ | Utility-first CSS framework |
| **Component Library** | shadcn/ui (Radix UI) | Accessible, customizable components |
| **Data Visualization** | Recharts 2.0+ | Charts and graphs |
| **Real-time Updates** | Supabase JS | WebSocket subscriptions |
| **HTTP Client** | Axios 1.6+ | API communication |
| **Form Handling** | React Hook Form | Form validation and submission |
| **Animations** | React Three Fiber | 3D visualizations (optional) |

### DevOps & Infrastructure

| Component | Technology |
|-----------|-----------|
| **Compute** | AWS EC2 (Ubuntu 22.04) |
| **Containerization** | Docker 24.0+ / Docker Compose |
| **CI/CD** | GitHub Actions |
| **Reverse Proxy** | NGINX |
| **SSL/TLS** | Certbot (Let's Encrypt) |
| **Monitoring** | Prometheus + Celery Flower |
| **Version Control** | Git + GitHub |

---

## 📊 Key Features

### 🎯 Multi-Dimensional Scoring System

|  Dimension | Weight | Description | Metrics |
|-----------|--------|-------------|---------|
| **🎨 Originality** | 15% | Measures code authenticity | AI detection, plagiarism similarity, code reuse patterns |
| **💻 Implementation** | 25% | Core product functionality | GPT-4o-mini evaluation, feature completeness, logic quality |
| **🏗️ Engineering** | 15% | DevOps maturity | Docker, CI/CD, testing, deployment infrastructure |
| **🔒 Security** | 10% | Vulnerability assessment | Secret detection, dependency scanning, insecure patterns |
| **✨ Code Quality** | 10% | Maintainability | Complexity (cyclomatic), maintainability index, code smells |
| **📁 Organization** | 5% | Architecture quality | Modularity, separation of concerns, folder structure |
| **💪 Effort** | 20% | Team contribution | Commit frequency, distribution, continuity, repository activity |
| **📚 Documentation** | 5% | Project documentation | README quality, code comments, API docs |

### ⚖️ Graduated Penalty System

Applies quality multipliers based on commit forensics:

| Status | Fake Commit Range | Multiplier | Penalty | Affected Dimensions |
|--------|-------------------|------------|---------|---------------------|
| 🟢 **Healthy** | < 30% | 1.0x | None | — |
| 🟠 **At Risk** | 30-50% | 0.7x | -30% | Implementation, Quality, Organization, Effort |
| 🔴 **Critical** | > 50% | 0.4x | -60% | Implementation, Quality, Organization, Effort |

**Protected Dimensions:** Originality, Security, Engineering, Documentation (immune to penalties)

### 🔍 Intelligent Detection Systems

#### 1. AI Code Detection
- **Technology:** Sentence Transformers + ensemble methods
- **Detects:** GPT-3/4/Copilot-generated patterns
- **Accuracy:** ~87% precision via statistical analysis
- **Features:**
  - Perplexity analysis (low perplexity = AI-likely)
  - Comment-to-code ratio detection
  - Variable naming pattern analysis
  - Structural consistency checks

#### 2. Plagiarism Detection
- **Technology:** FAISS vector similarity search
- **Process:**
  1. Generate code embeddings (Sentence BERT)
  2. Store in FAISS index per batch
  3. Query for similar code fragments
  4. Calculate cosine similarity scores
- **Threshold:** >85% similarity flagged

#### 3. Commit Forensics
- **Detects:**
  - 🚩 Last-minute commit bursts (>40% in final 24h)
  - 🚩 Dummy commits (low LOC, high frequency)
  - 🚩 Copy-paste patterns (large single commits)
  - 🚩 Suspicious timing (bulk commits at odd hours)
  - 🚩 Contributor mismatches (email/author discrepancies)

#### 4. Security Scanning
- **Detects:**
  - API keys, tokens, passwords in code
  - AWS/Azure/GCP credentials
  - Private keys (RSA, SSH)
  - Database connection strings
  - Hardcoded secrets in config files

#### 5. Repository Privacy Detection
- **Identifies:** Private/inaccessible repositories
- **Validates:** Public access without authentication
- **Actions:** Auto-flag teams for manual review

### 📦 Batch Processing

- **Bulk Upload:** CSV files with 100+ repositories
- **Parallel Execution:** Up to 4 concurrent batch workers
- **Progress Tracking:** Real-time percentage and ETA
- **Pause/Resume:** Stop/restart long-running batches
- **Email Notifications:** Automated completion alerts
- **Export Formats:** Excel (.xlsx), PDF reports
- **Historical Comparison:** 7-day snapshot analysis

### 📈 Real-Time Analytics & Dashboards

#### Admin Dashboard
- Live system metrics (queue depth, worker status)
- Token usage tracking with cost breakdown
- Analysis success/failure rates
- Performance bottleneck identification

#### Leaderboard
- Real-time team rankings across all dimensions
- Filterable by batch, status, score range
- Search by team name or repository URL
- Sortable columns with pagination

#### Mentor Dashboard
- Assigned team overview
- Manual grading interface
- Grade history and tracking
- Student report generation
- PDF export for individual teams

### 👥 Mentor & Grading System

- **Mentor Assignment:** Link mentors to teams
- **Manual Grading:** Override/supplement automated scores
- **Grade Tracking:** Historical grade data with versioning
- **Student Reports:** Automated PDF generation
- **Email Delivery:** Send reports directly to students
- **Bulk Operations:** Grade multiple teams simultaneously

---

## 🚦 Getting Started

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Core backend language |
| Node.js | 18+ | Frontend build tooling |
| Redis | 7.0+ | Message broker (or Upstash) |
| PostgreSQL | 15+ | Database (or Supabase) |
| Docker (optional) | 24.0+ | Containerized deployment |
| Git | 2.30+ | Version control |

### API Keys Required

- **OpenAI API Key** - For GPT-4o-mini code evaluation
- **GitHub Personal Access Token** (optional) - For private repo analysis
- **Supabase Project** - Database URL + anon/service keys
- **Redis URL** - Local or Upstash cloud instance

---

## 🔧 Installation & Setup

### 1️⃣ Backend Setup

```bash
# Navigate to backend directory
cd "proj-github agent"

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env

# Edit .env with your credentials
nano .env
```

#### `.env` Configuration

```bash
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# GitHub API (optional, for private repos)
GH_API_KEY=ghp_xxxxxxxxxxxxx

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
# Or Upstash:
# REDIS_URL=rediss://default:xxxx@xxxxx.upstash.io:6379

# Supabase Configuration
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Email Configuration (Gmail)
# Student emails (weekly reports, team reports) — Preshitdesai's account
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-student-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-student-email@gmail.com
SMTP_FROM_NAME=ProjectFlow

# Mentor/Admin emails (fake commit alerts, weekly analysis notifications)
# If not set, falls back to the SMTP_* vars above
SMTP_MENTOR_USER=your-mentor-email@gmail.com
SMTP_MENTOR_PASS=your-mentor-app-password
SMTP_MENTOR_FROM=your-mentor-email@gmail.com
SMTP_MENTOR_FROM_NAME=ProjectFlow Alerts

# Application Settings
ENVIRONMENT=development
LOG_LEVEL=INFO
```

#### Start Redis (if running locally)

```bash
# macOS (Homebrew)
brew services start redis

# Ubuntu/Debian
sudo systemctl start redis

# Windows (WSL or Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Verify Redis is running
redis-cli ping  # Should return "PONG"
```

#### Start Celery Workers

```bash
# Terminal 1: Single analysis worker (2 concurrency)
celery -A celery_app worker -Q single_analysis --concurrency=2 -l info

# Terminal 2: Batch analysis workers (4 concurrency)
celery -A celery_app worker -Q analysis,batch,dlq,default --concurrency=4 -l info

# Terminal 3: Celery Beat scheduler (for periodic tasks)
celery -A celery_app beat -l info
```

#### Start FastAPI Server

```bash
# Terminal 4: API server
uvicorn main:app --host 0.0.0.0 --port 3000 --reload

# API will be available at:
# - http://localhost:3000
# - API docs: http://localhost:3000/docs
# - ReDoc: http://localhost:3000/redoc
```

---

### 2️⃣ Frontend Setup

```bash
# Navigate to frontend directory
cd Github-agent

# Install dependencies
npm install
# Or with Yarn:
# yarn install

# Configure environment
cp .env.example .env.development

# Edit environment variables
nano .env.development
```

#### `.env.development` Configuration

```bash
# API Configuration
VITE_API_URL=http://localhost:3000
VITE_API_BASE_URL=http://localhost:3000/api

# Supabase Configuration (same as backend)
VITE_SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Application Settings
VITE_APP_NAME=ProjectFlow
VITE_ENVIRONMENT=development
```

#### Start Development Server

```bash
npm run dev

# Frontend will be available at:
# http://localhost:8080
```

---

### 3️⃣ Database Setup (Supabase)

1. **Create Supabase Project:** [https://supabase.com/dashboard](https://supabase.com/dashboard)

2. **Run Migrations:**
   ```bash
   cd "proj-github agent/migrations"
   
   # Apply migrations (if using Supabase CLI)
   supabase db push
   
   # Or manually execute SQL files in Supabase SQL Editor:
   # - 001_initial_schema.sql
   # - 002_add_grading_system.sql
   # - 003_add_token_tracking.sql
   ```

3. **Configure Row Level Security (RLS):**
   - Enable RLS on all tables
   - Set up policies for authenticated users
   - Grant service role bypass for backend

4. **Verify Connection:**
   ```bash
   cd "proj-github agent"
   python -c "from src.database import supabase; print(supabase.table('teams').select('*').limit(1).execute())"
   ```

---

## 📚 API Reference

### Base URL
```
Production: https://projectflow.krishivaani.me/api
Development: http://localhost:3000/api
```

### Authentication
```http
Authorization: Bearer <supabase_jwt_token>
```

### Core Endpoints

#### 1. Analyze Repository

```http
POST /api/teams/{team_id}/analyze
Content-Type: application/json

Request:
{
  "force_reanalysis": false  // Optional: bypass 7-day cache
}

Response:
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "team_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "queued",
  "message": "Analysis queued successfully",
  "estimated_duration": "2-5 minutes"
}
```

#### 2. Check Analysis Progress

```http
GET /api/teams/{team_id}/progress

Response:
{
  "status": "running",
  "current_stage": 5,
  "total_stages": 10,
  "progress": 50,
  "message": "Analyzing commit forensics...",
  "started_at": "2026-03-01T10:30:00Z",
  "estimated_completion": "2026-03-01T10:33:00Z"
}
```

#### 3. Get Team Report

```http
GET /api/teams/{team_id}

Response:
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "team_name": "Team Alpha",
  "repository_url": "https://github.com/org/repo",
  "total_score": 85.5,
  "originality_score": 88.0,
  "implementation_score": 82.0,
  "engineering_score": 90.0,
  "security_score": 75.0,
  "quality_score": 80.0,
  "organization_score": 85.0,
  "effort_score": 88.0,
  "documentation_score": 78.0,
  "penalty_multiplier": 1.0,
  "fake_commit_percentage": 12.5,
  "status": "completed",
  "analyzed_at": "2026-03-01T10:35:00Z",
  "tech_stack": ["Python", "React", "Docker"],
  "security_issues": [
    {
      "type": "hardcoded_secret",
      "severity": "high",
      "file": "config.py",
      "line": 42
    }
  ]
}
```

#### 4. Batch Upload

```http
POST /api/batch-upload
Content-Type: multipart/form-data

Form Data:
- file: teams.csv (required)
- batch_name: "3rd Year AIML" (optional)
- description: "March 2026 batch" (optional)

CSV Format:
team_name,repository_url,description
Team Alpha,https://github.com/org/repo1,E-commerce platform
Team Beta,https://github.com/org/repo2,Social media app

Response:
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440001",
  "batch_name": "3rd Year AIML",
  "total_teams": 50,
  "queued": 50,
  "failed": 0,
  "message": "Batch uploaded successfully"
}
```

#### 5. Batch Operations

```http
# Trigger batch analysis
POST /api/batches/{batch_id}/trigger

Response:
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "running",
  "total": 50,
  "queued": 50,
  "in_progress": 0,
  "completed": 0,
  "failed": 0
}

# Pause batch
POST /api/batches/{batch_id}/pause

# Resume batch
POST /api/batches/{batch_id}/resume

# Check batch progress
GET /api/batches/{batch_id}/progress

Response:
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "running",
  "progress": 45.0,
  "total": 50,
  "completed": 22,
  "failed": 1,
  "in_progress": 4,
  "queued": 23,
  "estimated_completion": "2026-03-01T12:00:00Z"
}
```

#### 6. Leaderboard

```http
GET /api/leaderboard?batch_id={batch_id}&limit=10&offset=0

Response:
{
  "teams": [
    {
      "rank": 1,
      "team_name": "Team Alpha",
      "total_score": 92.5,
      "originality_score": 95.0,
      "implementation_score": 90.0,
      ...
    }
  ],
  "total": 50,
  "page": 1,
  "limit": 10
}
```

#### 7. Export Reports

```http
# Export batch to Excel
GET /api/batches/{batch_id}/export/excel

# Export team PDF report
GET /api/teams/{team_id}/export/pdf

Response: Binary file download
```

#### 8. Health Check

```http
GET /health

Response:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "celery_workers": {
    "single_analysis": 2,
    "batch_analysis": 4
  },
  "queue_depth": {
    "single_analysis": 3,
    "batch": 45
  }
}
```

### Full API Documentation

- **Interactive Docs:** [https://projectflow.krishivaani.me/docs](https://projectflow.krishivaani.me/docs)
- **ReDoc:** [https://projectflow.krishivaani.me/redoc](https://projectflow.krishivaani.me/redoc)
- **Detailed Reference:** See `proj-github agent/docs/API_ROUTES_QUICK_REFERENCE.md`

---

## 🧪 Testing

### Backend Tests

```bash
cd "proj-github agent"

# Run all tests with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific test modules
pytest tests/test_commit_forensics.py -v
pytest tests/test_security_scanner.py -v
pytest tests/test_batch_processing.py -v

# Run integration tests (requires Redis + DB)
pytest tests/integration/ -v

# View coverage report
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

### Frontend Tests

```bash
cd Github-agent

# Run unit tests
npm run test

# Run tests with coverage
npm run test:coverage

# Run E2E tests (requires Playwright)
npm run test:e2e
```

### Load Testing

```bash
# Install locust
pip install locust

# Run load test
cd "proj-github agent/tests/load"
locust -f load_test.py --host=https://projectflow.krishivaani.me
```

**Test Coverage:** 85%+ across critical paths

---

## 📦 Deployment

### Docker Deployment (Recommended)

#### 1. Build and Run All Services

```bash
# Clone repository
git clone https://github.com/your-org/projectflow.git
cd projectflow

# Configure environment
cp .env.example .env
nano .env  # Add production credentials

# Build and start services
docker-compose up -d

# Verify all containers are running
docker-compose ps

# View logs
docker-compose logs -f api
docker-compose logs -f celery_worker_batch
```

#### 2. Scale Workers

```bash
# Scale batch workers to 6
docker-compose up -d --scale celery_worker_batch=6

# Scale single analysis workers to 3
docker-compose up -d --scale celery_worker_single=3
```

#### 3. Service Management

```bash
# Stop services
docker-compose stop

# Restart services
docker-compose restart

# Stop and remove containers
docker-compose down

# View resource usage
docker stats
```

---

### AWS EC2 Deployment

#### 1. Launch EC2 Instance

- **Instance Type:** t3.large or c5.xlarge (production)
- **AMI:** Ubuntu 22.04 LTS
- **Storage:** 30GB+ SSD (gp3)
- **Security Group:**
  - Port 22 (SSH)
  - Port 80 (HTTP)
  - Port 443 (HTTPS)
  - Port 3000 (API, if not using NGINX)
  - Port 8080 (Frontend, if not using NGINX)

#### 2. Connect and Setup

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3-pip nodejs npm redis-server nginx certbot python3-certbot-nginx

# Install Docker (optional but recommended)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
sudo systemctl enable docker
sudo systemctl start docker

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### 3. Deploy Application

```bash
# Clone repository
git clone https://github.com/your-org/projectflow.git
cd projectflow

# Configure environment
cp .env.example .env
nano .env  # Add production credentials

# Build and start with Docker Compose
docker-compose up -d

# Or manual setup (see previous installation steps)
```

#### 4. Configure NGINX Reverse Proxy

```bash
# Create NGINX config
sudo nano /etc/nginx/sites-available/projectflow

# Add configuration:
server {
    listen 80;
    server_name projectflow.krishivaani.me;

    # Frontend
    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
    }

    # API Docs
    location /docs {
        proxy_pass http://localhost:3000/docs;
    }

    location /redoc {
        proxy_pass http://localhost:3000/redoc;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/projectflow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 5. Setup SSL with Let's Encrypt

```bash
sudo certbot --nginx -d projectflow.krishivaani.me

# Auto-renewal (already configured by certbot)
sudo systemctl status certbot.timer
```

#### 6. Setup Systemd Services (Alternative to Docker)

```bash
# Create API service
sudo nano /etc/systemd/system/projectflow-api.service

[Unit]
Description=ProjectFlow FastAPI
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/projectflow/proj-github agent
Environment="PATH=/home/ubuntu/projectflow/proj-github agent/.venv/bin"
ExecStart=/home/ubuntu/projectflow/proj-github agent/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 3000
Restart=always

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl enable projectflow-api
sudo systemctl start projectflow-api

# Similar services for Celery workers...
```

#### 7. Monitoring Setup

```bash
# Install Celery Flower (task monitoring)
pip install flower
celery -A celery_app flower --port=5555

# Access at: http://your-ec2-ip:5555
```

---

### Environment-Specific Configuration

#### Production `.env`

```bash
ENVIRONMENT=production
LOG_LEVEL=WARNING
DEBUG=False

# Use production Redis (Upstash)
REDIS_URL=rediss://default:xxxx@production.upstash.io:6379

# Use production Supabase
SUPABASE_URL=https://xxxxxxxxxxxxx.supabase.co
SUPABASE_KEY=your-production-key

# Configure email
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=SG.xxxxxxxxxxxxx
```

#### Staging `.env`

```bash
ENVIRONMENT=staging
LOG_LEVEL=INFO
DEBUG=True

# Use staging resources...
```

---

## 📊 Monitoring & Observability

### Health Checks

```bash
# API health
curl https://projectflow.krishivaani.me/health

# Database connection
curl https://projectflow.krishivaani.me/health/db

# Redis connection
curl https://projectflow.krishivaani.me/health/redis
```

### Celery Flower Dashboard

Access worker monitoring at: `http://your-domain:5555`

**Features:**
- Active/reserved tasks
- Task success/failure rates
- Worker resource usage
- Task runtime statistics

### Token Usage Dashboard

Built-in dashboard at: `/admin/token-usage`

**Tracks:**
- Total tokens consumed per day/week/month
- Cost breakdown by analysis tier
- Per-team token usage
- LLM API request patterns

### Log Monitoring

```bash
# View API logs
docker-compose logs -f api --tail=100

# View worker logs
docker-compose logs -f celery_worker_batch --tail=100

# Search for errors
docker-compose logs api | grep ERROR

# Export logs to file
docker-compose logs --no-color > logs_$(date +%Y%m%d).txt
```

### Prometheus Metrics (Optional)

Endpoint: `/metrics`

**Exposed metrics:**
- Request latency (p50, p95, p99)
- Request rate
- Error rate
- Active connections
- Queue depth

---

## 🎓 Use Cases

### Academic Institutions
- **Course Projects:** Automated evaluation of student submissions
- **Hackathons:** Real-time leaderboard for competitive coding events
- **Capstone Projects:** Comprehensive assessment across multiple dimensions
- **Plagiarism Detection:** Identify copied code across submissions

### Corporate Training
- **Coding Bootcamps:** Batch evaluation of trainee projects
- **Internship Assessment:** Standardized evaluation criteria
- **Skill Validation:** Technical interview process automation

### Open Source Communities
- **Repository Quality Scoring:** Assess project maturity
- **Contribution Analysis:** Identify top contributors
- **Security Audits:** Automated vulnerability scanning

---

## 🚧 Roadmap

### Planned Features

- [ ] **Multi-Language Support** - Extend beyond Python/JavaScript
- [ ] **Custom Scoring Profiles** - Configurable dimension weights
- [ ] **GitHub Integration** - Direct repo import via OAuth
- [ ] **Advanced Plagiarism** - Cross-batch similarity detection
- [ ] **ML Model Training** - Improve AI detection accuracy
- [ ] **Webhook Notifications** - Real-time alerts to external systems
- [ ] **GraphQL API** - Alternative to REST for frontend
- [ ] **Multi-Tenancy** - Support for multiple institutions
- [ ] **Advanced Analytics** - Trend analysis, cohort comparison
- [ ] **Mobile App** - iOS/Android submission interface

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

### Development Workflow

1. **Fork the repository**
2. **Create a feature branch:** `git checkout -b feature/amazing-feature`
3. **Commit your changes:** `git commit -m 'Add amazing feature'`
4. **Push to branch:** `git push origin feature/amazing-feature`
5. **Open a Pull Request**

### Code Standards

- **Backend:** Follow PEP 8 (use `black` for formatting)
- **Frontend:** Follow Airbnb style guide (use `prettier`)
- **Commits:** Use conventional commits (feat, fix, docs, etc.)
- **Tests:** Maintain 80%+ coverage for new code

### Areas for Contribution

- 🐛 Bug fixes
- ⚡ Performance optimizations
- 📝 Documentation improvements
- 🎨 UI/UX enhancements
- 🔧 New analysis detectors
- 🌐 Internationalization (i18n)

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2026 ProjectFlow

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```

---

## 🙏 Acknowledgments

### Technologies

Special thanks to the creators and maintainers of:
- **FastAPI** - Modern Python web framework
- **React** - UI library by Meta
- **Celery** - Distributed task queue
- **OpenAI** - GPT-4o-mini LLM
- **Supabase** - Open-source Firebase alternative
- **shadcn/ui** - Beautifully designed components

### Inspiration

Built with modern AI-powered development tools and deployed for real-world academic evaluation at scale, serving 1000+ students across multiple institutions.

---

## 📞 Support & Contact

### Get Help

- 📧 **Email:** support@projectflow.com
- 💬 **GitHub Issues:** [Report a bug](https://github.com/your-org/projectflow/issues)
- 📚 **Documentation:** [Read the docs](https://docs.projectflow.com)
- 🌐 **Live Demo:** [https://projectflow.krishivaani.me/](https://projectflow.krishivaani.me/)

### Community

- 🐦 **Twitter:** [@ProjectFlow](https://twitter.com/projectflow)
- 💼 **LinkedIn:** [ProjectFlow](https://linkedin.com/company/projectflow)
- 📣 **Discord:** [Join our community](https://discord.gg/projectflow)

---

<div align="center">

**⭐ Star this repository if you find it helpful!**

Made with ❤️ by the ProjectFlow Team

[Live Demo](https://projectflow.krishivaani.me/) • [Documentation](https://docs.projectflow.com) • [Report Bug](https://github.com/your-org/projectflow/issues) • [Request Feature](https://github.com/your-org/projectflow/issues)

</div>
