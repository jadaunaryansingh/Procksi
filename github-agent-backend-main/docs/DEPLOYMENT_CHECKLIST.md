# 🚀 GitHub + EC2 Deployment Checklist

Follow these steps to deploy your Repository Analyzer to AWS EC2 with GitHub Actions.

## ✅ Step-by-Step Checklist

### 1. GitHub Repository Setup

- [ ] Create new repository on GitHub
  ```bash
  # Go to github.com → New Repository
  # Name: repo-analyzer (or your choice)
  # Public or Private
  # Don't initialize with README (we have one)
  ```

### 2. AWS EC2 Setup

- [ ] **Launch EC2 Instance**
  - [ ] Instance Type: `t3.small` or larger
  - [ ] AMI: Ubuntu Server 22.04 LTS
  - [ ] Storage: 20GB gp3
  - [ ] Security Group:
    - [ ] SSH (22) - Your IP
    - [ ] HTTP (80) - 0.0.0.0/0
    - [ ] HTTPS (443) - 0.0.0.0/0
    - [ ] Custom TCP (8000) - 0.0.0.0/0
  - [ ] Download key pair (.pem file)
  - [ ] **Note EC2 Public IP**: __________________

- [ ] **Configure EC2 Instance**
  ```bash
  chmod 400 your-key.pem
  ssh -i your-key.pem ubuntu@YOUR_EC2_IP
  
  # Run setup
  curl -O https://raw.githubusercontent.com/YOUR_USERNAME/repo-analyzer/main/scripts/ec2-setup.sh
  chmod +x ec2-setup.sh
  ./ec2-setup.sh
  ```

### 3. Configure GitHub Secrets

Go to: GitHub Repository → Settings → Secrets and variables → Actions → New repository secret

- [ ] `AWS_ACCESS_KEY_ID` = (Your AWS access key)
- [ ] `AWS_SECRET_ACCESS_KEY` = (Your AWS secret key)
- [ ] `AWS_REGION` = (e.g., us-east-1)
- [ ] `EC2_SSH_KEY` = (Full content of your .pem file)
- [ ] `EC2_HOST` = (Your EC2 public IP)
- [ ] `EC2_USER` = ubuntu
- [ ] `SUPABASE_URL` = (Your Supabase project URL)
- [ ] `SUPABASE_KEY` = (Your Supabase anon key)
- [ ] `OPENAI_API_KEY` = (Your OpenAI API key)
- [ ] `CORS_ORIGINS` = (Your frontend URLs, comma-separated)

**Getting EC2_SSH_KEY:**
```bash
# Display full key content
cat your-key.pem

# Copy EVERYTHING including the header and footer lines of the key
```

### 4. Supabase Database Setup

- [ ] Run SQL from DEPLOYMENT.md in Supabase SQL Editor
  - [ ] Creates 7 tables (projects, analysis_jobs, tech_stack, etc.)
  - [ ] Adds indexes
  - [ ] Sets up RLS policies

### 5. Push Code to GitHub

```bash
# Initialize git (if not done)
git init

# Add files
git add .

# Commit
git commit -m "Initial commit with GitHub Actions CI/CD"

# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/repo-analyzer.git

# Push to main
git push -u origin main
```

### 6. Verify Deployment

- [ ] **Check GitHub Actions**
  - Go to: Repository → Actions tab
  - Watch workflow run
  - All steps should be green ✅

- [ ] **Test API**
  ```bash
  # Replace with your EC2 IP
  export EC2_IP="YOUR_EC2_IP"
  
  # Health check
  curl http://$EC2_IP/health
  
  # Get stats
  curl http://$EC2_IP/api/stats
  
  # View docs
  # Visit: http://$EC2_IP/docs in browser
  ```

### 7. Optional: Setup Domain & SSL

- [ ] **Point DNS to EC2**
  - Create A record: `api.yourdomain.com` → EC2 IP

- [ ] **Install SSL Certificate**
  ```bash
  ssh -i your-key.pem ubuntu@YOUR_EC2_IP
  sudo certbot --nginx -d api.yourdomain.com
  ```

---

## 🎯 Quick Commands Reference

### Local Development
```bash
python main.py                    # Start local server
python test_frontend_api.py       # Test API endpoints
pytest tests/ -v                  # Run unit tests
```

### Git Operations
```bash
git add .                         # Stage changes
git commit -m "message"           # Commit
git push origin main              # Deploy to EC2 (auto)
```

### EC2 Management
```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# View logs
cd /home/ubuntu/repo-analyzer
docker-compose logs -f api

# Restart
docker-compose restart

# Manual deploy
git pull && docker-compose up -d --build
```

### Testing Endpoints
```bash
# Health
curl http://YOUR_EC2_IP/health

# Stats
curl http://YOUR_EC2_IP/api/stats

# Projects
curl http://YOUR_EC2_IP/api/projects

# Docs (browser)
http://YOUR_EC2_IP/docs
```

---

## 📋 Important Information to Save

```
EC2 Public IP: _______________________
EC2 SSH Command: ssh -i your-key.pem ubuntu@YOUR_EC2_IP
GitHub Repo: https://github.com/YOUR_USERNAME/repo-analyzer
API URL: http://YOUR_EC2_IP
API Docs: http://YOUR_EC2_IP/docs
```

---

## 🐛 Troubleshooting

### Deployment Failed?
1. Check GitHub Actions logs
2. SSH into EC2 and check: `docker-compose logs api`
3. Verify all secrets are set correctly

### Can't Connect to EC2?
1. Check security group allows your IP on port 22
2. Verify key file permissions: `chmod 400 your-key.pem`

### API Not Responding?
```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
docker ps                         # Check containers running
docker-compose logs api           # Check logs
docker-compose restart            # Restart if needed
```

---

## ✅ All Set?

When everything above is checked off:

✨ **Your app is deployed and running on AWS EC2!** ✨

- API accessible at: `http://YOUR_EC2_IP`
- Auto-deploys on every push to `main`
- Complete documentation ready for frontend team

**Share with frontend:**
- API URL
- [FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md)
- Make sure CORS_ORIGINS includes their domain

---

## 📚 Full Documentation

- **[GITHUB_ACTIONS_DEPLOYMENT.md](GITHUB_ACTIONS_DEPLOYMENT.md)** - Complete deployment guide
- **[FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md)** - API reference (800+ lines)
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Alternative deployment methods
- **[README.md](README.md)** - Project overview

**Happy Deploying! 🚀**
