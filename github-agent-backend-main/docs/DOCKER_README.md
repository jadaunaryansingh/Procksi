# Docker Setup - Quick Start Guide

## What's Included

This Docker Compose setup runs your **backend services** in Linux containers:
- ✅ **FastAPI** (http://localhost:3000)
- ✅ **Celery Worker** (no more Windows errors!)
- ✅ **Celery Beat** (automated scheduling)

**Frontend:** Run separately with `npm run dev` (port 8080)

---

## Prerequisites

1. **Install Docker Desktop for Windows**
   - Download: https://www.docker.com/products/docker-desktop
   - Restart after installation

2. **Verify Installation**
   ```bash
   docker --version
   docker-compose --version
   ```

---

## Quick Start

### Option 1: Interactive Mode (Recommended for Development)

```bash
.\docker-start.bat
```

**What it does:**
- Builds Docker images
- Starts all services with live logs
- Press `Ctrl+C` to stop

### Option 2: Background Mode

```bash
.\docker-start-bg.bat
```

**What it does:**
- Starts services in background
- View logs: `docker-compose logs -f`
- Stop: `docker-compose down`

---

## Complete Workflow

### 1. Start Backend (Docker)

```bash
cd "d:\Coding\Github-Agent\proj-github agent"
.\docker-start.bat
```

Wait for:
```
✅ Redis cache connected (TLS)
🚀 Repository Analysis API Starting...
```

### 2. Start Frontend (Separate Terminal)

```bash
cd "d:\Coding\Github-Agent\Github-agent"
npm run dev
```

Access:
- Frontend: http://localhost:8080
- Backend API: http://localhost:3000
- API Docs: http://localhost:3000/docs

---

## Useful Commands

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f celery_worker
docker-compose logs -f celery_beat
```

### Stop Services

```bash
docker-compose down
```

### Restart After Code Changes

```bash
# Quick restart (no rebuild)
docker-compose restart

# Full rebuild (for dependency changes)
docker-compose up --build
```

### Access Container Shell

```bash
docker-compose exec celery_worker bash
```

### Check Service Status

```bash
docker-compose ps
```

---

## Troubleshooting

### Port 3000 Already in Use

**Kill existing process:**
```bash
# Find process
netstat -ano | findstr :3000

# Kill process (replace PID)
taskkill /PID <PID> /F
```

### Docker Build Fails

```bash
# Clean rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up
```

### Services Won't Start

**Check `.env` file exists:**
```bash
# Should have all required variables
REDIS_URL=rediss://...
SUPABASE_URL=https://...
GEMINI_API_KEY=...
```

### Celery Worker Crashes

**Check logs:**
```bash
docker-compose logs celery_worker
```

Common issues:
- Missing environment variables
- Invalid Redis URL
- Supabase connection issues

---

## Development Tips

✅ **Hot Reload:** Code changes auto-reload (no restart needed)  
✅ **Volumes:** Source code is mounted, edits reflect immediately  
✅ **Logs:** Real-time logs with color coding  
✅ **Isolation:** No conflicts with host Python environment  

---

## Environment Variables

All variables from `.env` are automatically loaded. **Required:**

```env
REDIS_URL=rediss://default:xxx@useful-minnow-9873.upstash.io:6379
SUPABASE_URL=https://frcdvwuapmunkjaarrzr.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
GEMINI_API_KEY=your-gemini-key
GH_API_KEY=your-github-token
```

---

## What Changed?

**Before (Windows Issues):**
```bash
celery -A celery_app worker --pool=solo  # Limited to single-threaded
# Windows multiprocessing errors
```

**After (Docker - No Issues):**
```bash
docker-compose up  # Full multiprocessing support
# Runs in Linux container
```

---

## Production Deployment

For production, update `docker-compose.yml`:
- Remove `--reload` from FastAPI
- Use production `.env` file
- Add nginx for HTTPS
- Scale workers: `docker-compose up -d --scale celery_worker=3`

---

**Need Help?** Check logs with `docker-compose logs -f`
