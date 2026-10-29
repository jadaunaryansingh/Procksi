# 🚀 GitHub Actions + AWS EC2 Deployment Guide

Complete guide for automated deployment using GitHub Actions.

## 📋 Overview

This setup provides:
- ✅ **Automated Testing** - Run tests on every PR
- ✅ **Automated Deployment** - Deploy to EC2 on push to main
- ✅ **Docker Build** - Build and validate Docker images
- ✅ **Health Checks** - Verify deployment success
- ✅ **Rollback Support** - Easy rollback if deployment fails

---

## 🔧 Prerequisites

### 1. AWS Account
- AWS Account with EC2 access
- IAM user with appropriate permissions

### 2. EC2 Instance
- **OS**: Ubuntu 22.04 LTS
- **Instance Type**: t3.small or larger (2 vCPU, 2GB RAM minimum)
- **Storage**: 20GB+ EBS volume
- **Security Group**: Ports 22, 80, 443, 8000 open

### 3. GitHub Repository
- Repository created on GitHub
- Admin access to configure secrets

### 4. External Services
- Supabase database set up
- OpenAI API key

---

## 🚀 Step-by-Step Setup

### Step 1: Launch EC2 Instance

**Via AWS Console:**

1. Go to EC2 Dashboard → Launch Instance
2. **Name**: `repo-analyzer-production`
3. **AMI**: Ubuntu Server 22.04 LTS
4. **Instance Type**: t3.small (or t3.medium for better performance)
5. **Key Pair**: Create new or select existing
6. **Network Settings**:
   - Create security group with:
     - SSH (22) - Your IP
     - HTTP (80) - Anywhere
     - HTTPS (443) - Anywhere
     - Custom TCP (8000) - Anywhere (temporary, for testing)
7. **Storage**: 20 GB gp3
8. Click **Launch Instance**

**Save the following:**
- ✅ Public IP address
- ✅ Private key file (.pem)

### Step 2: Configure EC2 Instance

**Connect to your EC2:**

```bash
# Set correct permissions for your key
chmod 400 your-key.pem

# Connect via SSH
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

**Run setup script:**

```bash
# Download and run setup script
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/scripts/ec2-setup.sh
chmod +x ec2-setup.sh
./ec2-setup.sh
```

Or manually:

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install dependencies
sudo apt-get install -y git curl python3.12 python3-pip docker.io docker-compose nginx

# Add user to docker group
sudo usermod -aG docker ubuntu

# Create app directory
sudo mkdir -p /home/ubuntu/repo-analyzer
sudo chown -R ubuntu:ubuntu /home/ubuntu/repo-analyzer

# Log out and back in for group changes
exit
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

### Step 3: Configure GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

| Secret Name | Value | Description |
|------------|-------|-------------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | `wJal...` | AWS IAM secret key |
| `AWS_REGION` | `us-east-1` | Your AWS region |
| `EC2_SSH_KEY` | `<full PEM contents>` | **Full content** of your .pem file |
| `EC2_HOST` | `54.123.45.67` | Your EC2 public IP address |
| `EC2_USER` | `ubuntu` | SSH username (ubuntu for Ubuntu AMI) |
| `SUPABASE_URL` | `https://xxx.supabase.co` | Your Supabase project URL |
| `SUPABASE_KEY` | `eyJhbG...` | Your Supabase anon key |
| `OPENAI_API_KEY` | `sk-proj-...` | Your OpenAI API key |
| `CORS_ORIGINS` | `https://yourfrontend.com` | Comma-separated frontend URLs |

**Getting AWS credentials:**

```bash
# Create IAM user for GitHub Actions
aws iam create-user --user-name github-actions-deploy

# Create access key
aws iam create-access-key --user-name github-actions-deploy

# Attach policies (minimal permissions)
aws iam attach-user-policy --user-name github-actions-deploy \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
```

**Getting EC2 SSH Key content:**

```bash
# Display your .pem key
cat your-key.pem

# Copy the ENTIRE output including the header and footer lines of the key.
```

### Step 4: Initial Repository Setup on EC2

**SSH into EC2 and clone your repo:**

```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

cd /home/ubuntu/repo-analyzer

# Clone your repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git .

# Verify
ls -la
```

### Step 5: Push Code to GitHub

**On your local machine:**

```bash
# Initialize git (if not already)
git init

# Add remote
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Add all files
git add .

# Commit
git commit -m "Initial commit with GitHub Actions CI/CD"

# Push to main branch (this will trigger deployment)
git push -u origin main
```

### Step 6: Monitor Deployment

1. Go to your GitHub repository
2. Click **Actions** tab
3. Watch the deployment workflow run
4. Green checkmark = successful deployment ✅

**Deployment steps:**
1. ✅ Run Tests (pytest)
2. ✅ Build Docker Image
3. ✅ Deploy to EC2 (pull code, build, restart containers)
4. ✅ Health Check
5. ✅ Verify Endpoints

---

## 📊 Workflow Details

### Test Workflow (`test.yml`)

**Triggers:**
- Pull requests to `main` or `develop`
- Pushes to `develop` branch

**Actions:**
- Run pytest with coverage
- Test on Python 3.11 and 3.12
- Check code quality with flake8
- Validate imports

### Deploy Workflow (`deploy.yml`)

**Triggers:**
- Push to `main` or `production` branches
- Manual trigger via GitHub UI

**Actions:**
1. **Test Stage**: Run all unit tests
2. **Build Stage**: Build Docker image
3. **Deploy Stage**:
   - SSH into EC2
   - Pull latest code
   - Create `.env` file with secrets
   - Rebuild Docker containers
   - Health check verification
4. **Verify Stage**: Test endpoints

---

## 🔍 Verification

### Check Deployment Status

```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

# Check Docker containers
docker ps

# View logs
cd /home/ubuntu/repo-analyzer
docker-compose logs -f api

# Test health endpoint
curl http://localhost:8000/health
```

### Test API Endpoints

```bash
# From anywhere
export EC2_IP="YOUR_EC2_PUBLIC_IP"

# Health check
curl http://$EC2_IP/health

# Get stats
curl http://$EC2_IP/api/stats

# View API docs
curl http://$EC2_IP/docs
```

Or visit in browser:
- `http://YOUR_EC2_IP/docs` - Interactive API documentation
- `http://YOUR_EC2_IP/health` - Health check

---

## 🔄 Making Updates

### Standard Workflow

```bash
# Make changes locally
git add .
git commit -m "Add new feature"
git push origin main

# GitHub Actions automatically:
# 1. Runs tests
# 2. Builds Docker image
# 3. Deploys to EC2
# 4. Verifies deployment
```

### Manual Deployment Trigger

Go to GitHub → **Actions** → **Deploy to AWS EC2** → **Run workflow**

### Rollback

```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

cd /home/ubuntu/repo-analyzer

# Rollback to previous commit
git log --oneline
git reset --hard COMMIT_HASH

# Restart containers
docker-compose down
docker-compose up -d --build
```

---

## 🔒 Security Best Practices

### 1. Secure EC2 Instance

```bash
# Update SSH configuration
sudo nano /etc/ssh/sshd_config

# Set:
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd
```

### 2. Setup Firewall

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 3. Enable SSL Certificate

```bash
# After configuring domain DNS
sudo certbot --nginx -d api.yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 4. Rotate Secrets Regularly

- Update GitHub Secrets every 90 days
- Rotate AWS IAM credentials
- Update OpenAI API keys as needed

---

## 🐛 Troubleshooting

### Deployment Failed in GitHub Actions

**Check logs:**
1. Go to Actions tab
2. Click failed workflow
3. Expand failed step
4. Read error messages

**Common issues:**

**SSH Connection Failed:**
```
# Verify EC2_SSH_KEY secret is complete
# Include the header and footer lines of the key

# Verify EC2_HOST is correct public IP
# Check security group allows port 22 from GitHub Actions IPs
```

**Health Check Failed:**
```bash
# SSH into EC2 and check logs
docker-compose logs api

# Check if containers are running
docker ps

# Manually test health
curl http://localhost:8000/health
```

**Docker Build Failed:**
```bash
# Check if Docker has enough space
df -h

# Clean up old images
docker system prune -a
```

### Can't SSH into EC2

```bash
# Check security group allows your IP
# Verify key file permissions
chmod 400 your-key.pem

# Test connection
ssh -v -i your-key.pem ubuntu@YOUR_EC2_IP
```

### API Not Responding

```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# Check containers
docker ps

# View logs
docker-compose logs api

# Restart containers
docker-compose restart
```

### Database Connection Failed

```bash
# Verify environment variables
docker-compose exec api printenv | grep SUPABASE

# Test Supabase connection
curl -X GET "$SUPABASE_URL/rest/v1/" \
  -H "apikey: $SUPABASE_KEY"
```

---

## 📈 Monitoring & Logs

### View Application Logs

```bash
# Real-time logs
docker-compose logs -f api

# Last 100 lines
docker-compose logs --tail=100 api

# Save logs to file
docker-compose logs api > api.log
```

### Monitor Resource Usage

```bash
# Container stats
docker stats

# System resources
htop

# Disk usage
df -h
```

### Setup CloudWatch (Optional)

Install CloudWatch agent for advanced monitoring:

```bash
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i -E ./amazon-cloudwatch-agent.deb
```

---

## 🎯 Next Steps

- [ ] **Setup Domain**: Point DNS to EC2 IP
- [ ] **Enable SSL**: Run `certbot --nginx`
- [ ] **Setup Monitoring**: CloudWatch, Sentry, or Grafana
- [ ] **Configure Backups**: Automated database backups
- [ ] **Add Auto-scaling**: Launch multiple EC2 instances with load balancer
- [ ] **Setup Staging**: Create separate staging environment

---

## 📞 Quick Reference

### Important URLs
- **API**: `http://YOUR_EC2_IP`
- **Health**: `http://YOUR_EC2_IP/health`
- **Docs**: `http://YOUR_EC2_IP/docs`
- **GitHub Actions**: `https://github.com/YOUR_USERNAME/YOUR_REPO/actions`

### Important Commands

```bash
# Deploy manually
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
cd /home/ubuntu/repo-analyzer
git pull && docker-compose up -d --build

# View logs
docker-compose logs -f api

# Restart
docker-compose restart

# Stop
docker-compose down

# Full rebuild
docker-compose down && docker-compose up -d --build
```

---

## ✅ Pre-Deployment Checklist

- [ ] EC2 instance launched and running
- [ ] Security group configured (ports 22, 80, 443)
- [ ] SSH key pair downloaded
- [ ] EC2 setup script executed
- [ ] GitHub repository created
- [ ] All GitHub Secrets configured
- [ ] Supabase database tables created
- [ ] Initial code pushed to GitHub
- [ ] GitHub Actions workflow completed successfully
- [ ] Health endpoint responding
- [ ] API endpoints tested

**Your automated deployment is ready! 🚀**

Push to `main` branch and watch your code automatically deploy to AWS EC2!
