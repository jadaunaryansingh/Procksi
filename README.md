# Project Management System (Procksi) - Procksi

A comprehensive, enterprise-grade **Project Management System (Procksi)** built for Procksi. The platform is designed as a unified monorepo containing 4 React web applications (`apps/`) and 4 FastAPI backend microservices (`backend/`), backed by PostgreSQL/Supabase DB, Redis caching, AI Agents, and automated multi-channel communication services.

---

## 📑 Table of Contents

- [System Architecture & Tech Stack](#-system-architecture--tech-stack)
- [Monorepo Structure](#-monorepo-structure)
- [Service & Port Mapping](#-service--port-mapping)
- [Environment Variables (.env) Structure](#-environment-variables-env-structure)
- [AI Agents & Background Services](#-ai-agents--background-services)
- [Twilio Voice & Presentation Escalation Service](#-twilio-voice--presentation-escalation-service)
- [GitHub Analytics Agent](#-github-analytics-agent)
- [API Architecture & Endpoint Reference](#-api-architecture--endpoint-reference)
- [Quick Start Guide](#-quick-start-guide)
- [Database & DDL Auto-Migrations](#-database--ddl-auto-migrations)

---

## 🚀 System Architecture & Tech Stack

### Frontend Stack (`apps/`)
- **Core**: React 18, Vite, JavaScript (ES6+).
- **Styling**: Vanilla CSS with curated dark/light design systems, smooth CSS transitions, glassmorphism, and responsive grid layouts.
- **Icons & Data Display**: Lucide React, Axios HTTP client, Chart.js.

### Backend Stack (`backend/`)
- **Framework**: Python 3.12, FastAPI, Uvicorn ASGI server.
- **Database & ORM**: Supabase PostgreSQL, SQLAlchemy 2.0 (Async), Asyncpg driver.
- **Caching**: Redis client for high-performance session and dashboard response caching.
- **AI & Integrations**: Twilio Python SDK, OpenAI API, GitHub REST API v3, SMTP email libraries.

---

## 📂 Monorepo Structure

```text
Procksi Latest/
├── apps/
│   ├── admin/             # Admin Portal (React + Vite, Port 3000)
│   ├── panel/             # Panel Portal (React + Vite, Port 3001)
│   ├── student/           # Student Portal (React + Vite, Port 3002)
│   └── mentor/            # Mentor Portal (React + Vite, Port 3003)
├── backend/
│   ├── admin-api/         # Admin Microservice (FastAPI, Port 8000)
│   │   ├── app/
│   │   │   ├── presentation_reminder_service.py  # Twilio & Email Escalation Agent
│   │   │   ├── email_notifier.py                 # Professional HTML Email Engine
│   │   │   └── main.py                           # App entry & Startup Schedulers
│   ├── panel-api/         # Panel Microservice (FastAPI, Port 8001)
│   ├── student-api/       # Student Microservice (FastAPI, Port 8002)
│   └── mentor-api/        # Mentor Microservice (FastAPI, Port 8003)
│       └── app/
│           ├── api/auth.py                       # Mentor Auth & Phone Persistence
│           └── models/mentor.py                  # Mentor ORM Schema (with Phone)
├── docker-compose.yml     # Multi-container orchestrator
└── start_procksi.bat          # Windows local environment launcher
```

---

## 🔌 Service & Port Mapping

| Service Name | Component Directory | Frontend URL | Backend URL | Key API Base Path |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Portal** | `apps/admin` & `backend/admin-api` | `http://localhost:3000` | `http://localhost:8000` | `/api/data/*` |
| **Panel Portal** | `apps/panel` & `backend/panel-api` | `http://localhost:3001` | `http://localhost:8001` | `/api/panel/*` |
| **Student Portal** | `apps/student` & `backend/student-api` | `http://localhost:3002` | `http://localhost:8002` | `/api/student/*` |
| **Mentor Portal** | `apps/mentor` & `backend/mentor-api` | `http://localhost:3003` | `http://localhost:8003` | `/api/mentor/*` |

---

## 🔑 Environment Variables (.env) Structure

> [!IMPORTANT]
> Create a `.env` file in the project root. Below is the exact environment structure with **placeholder values**. Do **NOT** commit real API tokens or secrets to version control.

```env
# ==========================================
# Database & Supabase Configuration
# ==========================================
SUPABASE_URL=https://your-supabase-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
DATABASE_URL=postgresql+asyncpg://postgres:your_password@db.your-supabase-project.supabase.co:5432/postgres

# ==========================================
# SMTP Automated Email Notifier
# ==========================================
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your_system_email@domain.com
MAIL_PASSWORD=your_app_password_here
MAIL_FROM=your_system_email@domain.com

# ==========================================
# Twilio Communication Integration
# ==========================================
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_PHONE_NUMBER=+10000000000

# ==========================================
# GitHub Analytics Agent Configuration
# ==========================================
GITHUB_TOKEN=your_github_personal_access_token_here
GITHUB_AGENT_KEY=your_github_agent_secret_key

# ==========================================
# AI Services & OpenAI Configuration
# ==========================================
OPENAI_API_KEY=sk-proj-your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# ==========================================
# Application System & Security Settings
# ==========================================
SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200
FRONTEND_URL=http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003
```

---

## 🤖 AI Agents & Background Services

The system runs autonomous background services wired directly into backend startup event loops:

### 1. 📢 Presentation Schedule Escalation Agent
- **Path**: `backend/admin-api/app/presentation_reminder_service.py`
- **Schedule**: Polling loop executes every **60 seconds**.
- **Role**: Continuously inspects today's scheduled presentation slots in `schedule_slots` against active evaluations, draft submissions, and completed score records.

### 2. ✉️ Automated Notification Agent
- **Path**: `backend/admin-api/app/email_notifier.py`
- **Role**: Asynchronously builds and dispatches branded HTML email notifications for system events (allocation confirmation, proposal decision, published results).

### 3. 🐙 GitHub Analytics Agent
- **Path**: `backend/mentor-api/app/services/github_service.py`
- **Role**: Audits remote student repositories, parses commit logs, tracks code frequency, and calculates security & effort scorecards.

---

## 📞 Twilio Voice & Presentation Escalation Service

The presentation reminder agent follows a strict **3-stage escalation workflow** for overdue evaluation slots:

```mermaid
flowchart TD
    Start[Schedule Poller Runs Every 60s] --> Query[Fetch Today's Slots in schedule_slots]
    Query --> CheckStatus{Evaluation Started or Draft Saved?}
    CheckStatus -- YES --> Stop[Bypass All Reminders - Session Active]
    CheckStatus -- NO --> Calc[Calculate Elapsed Minutes Since Slot Start Time]
    
    Calc --> Step1{5 <= Minutes < 10?}
    Step1 -- YES --> Email1[Send +5m 1st Reminder Email via SMTP]
    
    Calc --> Step2{10 <= Minutes < 15?}
    Step2 -- YES --> Email2[Send +10m 2nd Urgent Email via SMTP]
    
    Calc --> Step3{Minutes >= 15?}
    Step3 -- YES --> TwilioCall[Place Automated Twilio Voice Call via TwiML]
```

### Escalation Rules:
1. **+5 Minutes Overdue**: Sends a **1st Reminder Email** with action link to Panel Portal.
2. **+10 Minutes Overdue**: Sends a **2nd Urgent Alert Email** notifying evaluator that students and panel members are waiting.
3. **+15 Minutes Overdue**: Places an **Automated Twilio Voice Call** to the faculty evaluator's mobile phone number using inline TwiML:
   > *"Hello Professor. This is an urgent automated reminder from the Procksi Project Management System. Your scheduled presentation evaluation slot for Team {team_id} started 15 minutes ago. Please join and initiate your evaluation session on the Panel Portal immediately. Thank you."*

### Smart Evaluation Status Check:
Before placing any call or sending an email, the scheduler cross-references all 4 status tables:
- `evaluations`
- `presentation_evaluations`
- `evaluation_drafts`
- `results`

If the evaluator has initiated the session or saved a draft score, **all reminders are automatically bypassed**.

---

## 🐙 GitHub Analytics Agent

Integrated into the **Mentor Portal (`apps/mentor`)**, the GitHub Agent provides real-time oversight of student team repositories:

- **Repository Tracking**: Monitors commit volume, lines added/deleted, and active branch activity.
- **Contributor Effort Score**: Calculates individual student contribution percentages to prevent single-student effort imbalance.
- **Code Quality & Security Scorecard**: Audits repository files for hardcoded secrets, large binaries, and proper commit messages.

---

## 🌐 API Architecture & Endpoint Reference

### Admin API (`:8000`)
- `GET /api/data/schedule_slots`: List all active presentation schedules.
- `GET /api/dashboard/stats`: Retrieve semester-wide analytics.
- `POST /api/data/governance_audit/upsert`: Audit log entry creation.

### Panel API (`:8001`)
- `POST /auth/signup`: Faculty panelist signup with phone number persistence.
- `POST /auth/login`: Panelist authentication & JWT issuance.
- `GET /evaluation/session/{team_id}`: Interactive scoring dashboard for active slots.

### Mentor API (`:8003`)
- `POST /api/auth/signup`: Faculty mentor registration (captures `name`, `email`, `phone`, `domains`).
- `GET /api/mentor/teams`: View assigned student teams & project progress.
- `GET /api/github/analytics/{team_id}`: Fetch remote repository analytics scorecard.

---

## 🛠️ Quick Start Guide

### Running via Docker Compose (Recommended)

To build and run all 4 frontend apps and 4 backend microservices in Docker:

```bash
docker compose up --build
```

### Running Locally on Windows

Execute the unified batch script:

```cmd
start_procksi.bat
```

---

## 🗄️ Database & DDL Auto-Migrations

The backend features startup **DDL auto-migrations** executed directly on SQLAlchemy engines:

- **Mentors Table**: Automatically checks and executes `ALTER TABLE public.mentors ADD COLUMN IF NOT EXISTS phone VARCHAR(50);` on startup so phone numbers are preserved for Twilio voice calls.
- **Semester Config**: Auto-migrates missing results and audit columns.

---

## 📝 License & Rights
Developed for **Procksi Project Management System**. All rights reserved.
