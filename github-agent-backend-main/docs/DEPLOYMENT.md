# Repository Analyzer - Deployment Guide

Complete guide for deploying the Repository Analyzer API to production.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Docker Deployment](#docker-deployment)
4. [Manual Deployment](#manual-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [Post-Deployment](#post-deployment)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)

---

## 🔧 Prerequisites

### Required

- **Python 3.12+** - Application runtime
- **Docker & Docker Compose** - Containerization
- **Git** - Version control
- **Supabase Account** - Database (PostgreSQL)
- **OpenAI API Key** - AI analysis
- **Domain Name** (production) - SSL/HTTPS

### Recommended

- **Linux Server** (Ubuntu 22.04+ recommended)
- **2+ CPU cores, 4GB+ RAM** - For optimal performance
- **Nginx** - Reverse proxy & SSL termination
- **SSL Certificate** - Let's Encrypt or commercial

---

## 🔐 Environment Setup

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/repo-analyzer.git
cd repo-analyzer
```

### Step 2: Configure Environment Variables

```bash
# Copy production environment template
cp .env.production .env

# Edit with your values
nano .env
```

**Required Variables:**

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key_here

# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here

# CORS Settings
CORS_ORIGINS=https://yourfrontend.com,https://www.yourfrontend.com

# Application
ENVIRONMENT=production
LOG_LEVEL=info
WORKERS=4
```

### Step 3: Setup Supabase Database

Run the following SQL in your Supabase SQL editor:

```sql
-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_name TEXT NOT NULL,
    repo_url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    total_score DECIMAL(5,2),
    quality_score DECIMAL(5,2),
    security_score DECIMAL(5,2),
    originality_score DECIMAL(5,2),
    architecture_score DECIMAL(5,2),
    documentation_score DECIMAL(5,2),
    ai_generated_percentage DECIMAL(5,2),
    architecture_pattern TEXT,
    total_commits INTEGER,
    total_files INTEGER,
    total_loc INTEGER,
    test_coverage DECIMAL(5,2),
    burst_commit_warning BOOLEAN DEFAULT false,
    last_minute_commits INTEGER DEFAULT 0,
    secrets_detected INTEGER DEFAULT 0,
    ai_verdict TEXT,
    strengths TEXT[],
    improvements TEXT[],
    commit_forensics_summary JSONB,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Analysis Jobs table
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    current_stage TEXT,
    message TEXT,
    error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tech Stack table
CREATE TABLE IF NOT EXISTS tech_stack (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    technology TEXT NOT NULL,
    category TEXT,
    version TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Languages table (for language breakdown)
CREATE TABLE IF NOT EXISTS languages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    percentage DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Contributors table
CREATE TABLE IF NOT EXISTS contributors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    commits INTEGER NOT NULL,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    percentage DECIMAL(5,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Commit Patterns table
CREATE TABLE IF NOT EXISTS commit_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    timeframe TEXT,
    count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Security Issues table
CREATE TABLE IF NOT EXISTS security_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_total_score ON projects(total_score DESC);
CREATE INDEX IF NOT EXISTS idx_projects_submitted_at ON projects(submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_project_id ON analysis_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_tech_stack_project_id ON tech_stack(project_id);
CREATE INDEX IF NOT EXISTS idx_tech_stack_technology ON tech_stack(technology);

-- Enable Row Level Security (Optional)
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tech_stack ENABLE ROW LEVEL SECURITY;
ALTER TABLE languages ENABLE ROW LEVEL SECURITY;
ALTER TABLE contributors ENABLE ROW LEVEL SECURITY;
ALTER TABLE commit_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_issues ENABLE ROW LEVEL SECURITY;

-- Public read access (adjust based on your needs)
CREATE POLICY "Enable read access for all users" ON projects FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON analysis_jobs FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON tech_stack FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON languages FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON contributors FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON commit_patterns FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON security_issues FOR SELECT USING (true);
```

---

## 🐳 Docker Deployment (Recommended)

### Quick Start

```bash
# Make deploy script executable
chmod +x deploy.sh

# Deploy to production
./deploy.sh production
```

### Manual Docker Commands

```bash
# Build images
docker-compose build

# Start containers
docker-compose up -d

# View logs
docker-compose logs -f api

# Check status
docker-compose ps

# Stop containers
docker-compose down
```

### Docker Configuration

The `docker-compose.yml` includes:
- **API Service** - FastAPI application (4 workers)
- **Nginx** - Reverse proxy with SSL
- **Networks** - Isolated network for services
- **Volumes** - Persistent storage for reports and logs
- **Health Checks** - Automatic service monitoring

---

## 🔨 Manual Deployment (Without Docker)

### Step 1: Install System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y python3.12 python3-pip git curl

# CentOS/RHEL
sudo yum install -y python3 python3-pip git curl
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
```

### Step 3: Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Run Application

**Development:**
```bash
python main.py
```

**Production (Uvicorn):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Production (Gunicorn):**
```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Step 5: Setup as System Service

Create `/etc/systemd/system/repo-analyzer.service`:

```ini
[Unit]
Description=Repository Analyzer API
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/repo-analyzer
Environment="PATH=/opt/repo-analyzer/venv/bin"
EnvironmentFile=/opt/repo-analyzer/.env
ExecStart=/opt/repo-analyzer/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable repo-analyzer
sudo systemctl start repo-analyzer
sudo systemctl status repo-analyzer
```

---

## ☁️ Cloud Deployment

### AWS EC2

1. **Launch EC2 Instance**
   - Ubuntu 22.04 LTS
   - t3.medium or larger
   - Open ports: 80, 443, 8000

2. **Connect and Setup**
   ```bash
   ssh -i your-key.pem ubuntu@your-ec2-ip
   git clone https://github.com/yourusername/repo-analyzer.git
   cd repo-analyzer
   ./deploy.sh production
   ```

3. **Configure Security Group**
   - Inbound: HTTP (80), HTTPS (443)
   - Outbound: All traffic

### AWS ECS (Container)

1. **Build and push image:**
   ```bash
   aws ecr create-repository --repository-name repo-analyzer
   docker build -t repo-analyzer .
   docker tag repo-analyzer:latest AWS_ACCOUNT.dkr.ecr.REGION.amazonaws.com/repo-analyzer:latest
   docker push AWS_ACCOUNT.dkr.ecr.REGION.amazonaws.com/repo-analyzer:latest
   ```

2. **Create task definition and service in ECS**

### Google Cloud Run

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/PROJECT_ID/repo-analyzer
gcloud run deploy repo-analyzer \
  --image gcr.io/PROJECT_ID/repo-analyzer \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars SUPABASE_URL=$SUPABASE_URL,SUPABASE_KEY=$SUPABASE_KEY,OPENAI_API_KEY=$OPENAI_API_KEY
```

### DigitalOcean App Platform

1. Create new app from GitHub repository
2. Configure environment variables
3. Select `Web Service` with Dockerfile
4. Deploy

### Heroku

```bash
# Install Heroku CLI
heroku login
heroku create repo-analyzer-api

# Set environment variables
heroku config:set SUPABASE_URL=your_url
heroku config:set SUPABASE_KEY=your_key
heroku config:set OPENAI_API_KEY=your_key

# Deploy
git push heroku main
```

---

## ✅ Post-Deployment

### 1. Verify API Health

```bash
curl http://your-domain.com/health
# Expected: {"status": "healthy"}
```

### 2. Test Endpoints

```bash
# Get stats
curl http://your-domain.com/api/stats

# Get projects
curl http://your-domain.com/api/projects
```

### 3. Setup SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d api.yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 4. Configure Firewall

```bash
# UFW (Ubuntu)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# iptables
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```

### 5. Setup Logging

```bash
# Create logs directory
mkdir -p /var/log/repo-analyzer

# Configure log rotation
sudo nano /etc/logrotate.d/repo-analyzer
```

Add:
```
/var/log/repo-analyzer/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
}
```

---

## 📊 Monitoring

### Application Monitoring

**Option 1: Prometheus + Grafana**

```bash
# Install Prometheus exporter
pip install prometheus-fastapi-instrumentator

# Add to main.py
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)
```

**Option 2: Sentry**

```bash
pip install sentry-sdk[fastapi]

# Add to main.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"))
```

### Server Monitoring

```bash
# Install monitoring tools
sudo apt-get install htop iotop nethogs

# Check resource usage
htop
docker stats  # If using Docker
```

### Log Monitoring

```bash
# View API logs
docker-compose logs -f api

# Or for manual deployment
tail -f /var/log/repo-analyzer/api.log

# Check for errors
grep -i error /var/log/repo-analyzer/api.log
```

---

## 🐛 Troubleshooting

### API Not Starting

```bash
# Check logs
docker-compose logs api

# Check environment variables
docker-compose exec api printenv | grep SUPABASE

# Restart container
docker-compose restart api
```

### Database Connection Issues

```bash
# Test Supabase connection
curl -X GET "$SUPABASE_URL/rest/v1/" \
  -H "apikey: $SUPABASE_KEY"
```

### High Memory Usage

```bash
# Reduce workers
# In docker-compose.yml or main.py
WORKERS=2  # Instead of 4
```

### Slow Analysis

```bash
# Check OpenAI API status
curl https://status.openai.com/api/v2/status.json

# Increase timeout
# In config.py
ANALYSIS_TIMEOUT = 600  # 10 minutes
```

### Port Already in Use

```bash
# Find process using port 3000
sudo lsof -i :3000
sudo netstat -tulpn | grep 3000

# Kill process
sudo kill -9 <PID>
```

---

## 🔒 Security Best Practices

1. **Environment Variables**
   - Never commit `.env` files
   - Use secrets management (AWS Secrets Manager, HashiCorp Vault)

2. **SSL/TLS**
   - Always use HTTPS in production
   - Use strong cipher suites
   - Enable HSTS

3. **Rate Limiting**
   - Nginx configuration includes rate limiting
   - Monitor for abuse

4. **Database Security**
   - Use Row Level Security in Supabase
   - Limit API key permissions
   - Regular backups

5. **API Security**
   - Validate all inputs
   - Sanitize repository URLs
   - Implement authentication (future)

---

## 📈 Scaling

### Horizontal Scaling

```bash
# Scale API containers
docker-compose up -d --scale api=3
```

### Load Balancing

Update `nginx.conf`:

```nginx
upstream api_backend {
    server api1:3000;
    server api2:3000;
    server api3:3000;
}
```

### Database Optimization

```sql
-- Add indexes for frequently queried fields
CREATE INDEX idx_projects_status_score ON projects(status, total_score DESC);

-- Vacuum analyze
VACUUM ANALYZE projects;
```

---

## 🔄 Updates & Maintenance

### Updating Application

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database Migrations

```bash
# Backup database first
pg_dump -h supabase-host -U postgres -d postgres > backup.sql

# Apply migrations
psql -h supabase-host -U postgres -d postgres -f migrations/001_add_column.sql
```

### Backup Strategy

```bash
# Database backup (automated)
0 2 * * * pg_dump -h supabase-host -U postgres -d postgres | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz

# Report files backup
0 3 * * * tar -czf /backups/reports_$(date +\%Y\%m\%d).tar.gz /app/report/
```

---

## 📞 Support

- **Documentation**: [FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md)
- **API Docs**: http://your-domain.com/docs
- **Health Check**: http://your-domain.com/health

---

## ✅ Deployment Checklist

- [ ] Environment variables configured
- [ ] Supabase database setup complete
- [ ] OpenAI API key valid
- [ ] Docker containers running
- [ ] Health check passing
- [ ] SSL certificate installed
- [ ] Firewall configured
- [ ] Monitoring setup
- [ ] Backups automated
- [ ] Logs rotating
- [ ] CORS origins updated
- [ ] Frontend notified of API URL

**Deployment complete! 🎉**
