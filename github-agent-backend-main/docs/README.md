# Repository Analyzer

AI-powered GitHub repository analysis and scoring system with automated quality, security, and originality assessment.

## 🚀 Features

- **Automated Analysis** - Submit any GitHub repository for comprehensive evaluation
- **Multi-Dimensional Scoring** - Quality, Security, Originality, Architecture, Documentation
- **AI Detection** - Identify AI-generated code using advanced pattern matching
- **Security Scanning** - Detect secrets, vulnerabilities, and security issues
- **Commit Forensics** - Analyze contribution patterns and detect suspicious activity
- **Tech Stack Detection** - Automatic identification of languages, frameworks, and tools
- **REST API** - Complete API with frontend-compatible camelCase responses
- **Real-time Progress** - Track analysis progress with live status updates
- **Leaderboard** - Compare projects and view rankings

## 📊 Tech Stack

- **Backend**: FastAPI (Python 3.12)
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenAI GPT-4, LangGraph orchestration
- **Deployment**: Docker, AWS EC2, GitHub Actions
- **Testing**: Pytest (79 unit tests, 100% passing)

## 🔧 Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose
- Supabase account
- OpenAI API key

### Local Development

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/repo-analyzer.git
cd repo-analyzer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.production .env
# Edit .env with your credentials

# Run server
python main.py
```

Visit `http://localhost:8000/docs` for interactive API documentation.

### Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f api

# Check health
curl http://localhost:8000/health
```

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/stats` | GET | Dashboard statistics |
| `/api/projects` | GET | List all projects |
| `/api/projects/{id}` | GET | Project details |
| `/api/leaderboard` | GET | Project rankings |
| `/api/tech-stacks` | GET | All technologies |
| `/api/analyze-repo` | POST | Submit repository |
| `/api/analysis-status/{job_id}` | GET | Analysis progress |

Full API documentation: [FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md)

## 🚀 Deployment

### AWS EC2 with GitHub Actions (Recommended)

Automated deployment on push to main branch.

**Setup:**
1. Launch EC2 instance (Ubuntu 22.04, t3.small+)
2. Configure GitHub Secrets (see [GITHUB_ACTIONS_DEPLOYMENT.md](GITHUB_ACTIONS_DEPLOYMENT.md))
3. Push to main branch → automatic deployment

```bash
# Configure EC2
./scripts/ec2-setup.sh

# Push code (triggers deployment)
git push origin main
```

See complete guide: [GITHUB_ACTIONS_DEPLOYMENT.md](GITHUB_ACTIONS_DEPLOYMENT.md)

### Other Platforms

- **Google Cloud Run**: One-click deployment
- **Heroku**: `git push heroku main`
- **DigitalOcean**: App Platform integration

See [DEPLOYMENT.md](DEPLOYMENT.md) for details.

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest --cov=. --cov-report=html

# Test API endpoints
python test_frontend_api.py
```

**Test Status**: ✅ 79/79 passing (100%)

## 📚 Documentation

- **[FRONTEND_DEVELOPER_GUIDE.md](FRONTEND_DEVELOPER_GUIDE.md)** - Complete API reference (800+ lines)
- **[GITHUB_ACTIONS_DEPLOYMENT.md](GITHUB_ACTIONS_DEPLOYMENT.md)** - CI/CD setup guide
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment options (Docker, Cloud)
- **[QUICKSTART.md](QUICKSTART.md)** - Quick deployment guide

## 🏗️ Architecture

```
┌─────────────────┐
│   FastAPI App   │
│   (main.py)     │
└────────┬────────┘
         │
         ├─── Routers (frontend_api.py)
         │
         ├─── Services (frontend_adapter.py)
         │
         ├─── Orchestrator (LangGraph)
         │    └─── Agent Workflow
         │
         ├─── Detectors
         │    ├── AI Detection
         │    ├── Security Scanner
         │    ├── Quality Metrics
         │    ├── Commit Forensics
         │    └── Stack Detection
         │
         └─── Database (Supabase)
              ├── Projects
              ├── Analysis Jobs
              ├── Tech Stack
              ├── Security Issues
              └── Contributors
```

## 🔒 Security

- **Environment Variables** - Never commit `.env` files
- **SSL/HTTPS** - Required for production
- **Rate Limiting** - Nginx configuration included
- **Input Validation** - All inputs sanitized
- **CORS** - Configurable origins

## 📈 Performance

- **Multi-worker** - 4 Uvicorn workers
- **Connection Pooling** - Supabase connection management
- **Async Operations** - Non-blocking analysis
- **Docker Optimized** - Multi-stage builds
- **Health Checks** - Automatic monitoring

## 🤝 Contributing

```bash
# Fork repository
# Create feature branch
git checkout -b feature/amazing-feature

# Make changes and test
pytest tests/

# Commit and push
git commit -m "Add amazing feature"
git push origin feature/amazing-feature

# Open Pull Request
```

## 📝 Environment Variables

```env
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key
OPENAI_API_KEY=sk-your-key

# Optional
CORS_ORIGINS=http://localhost:3000,https://yourfrontend.com
ENVIRONMENT=production
LOG_LEVEL=info
WORKERS=4
```

## 🐛 Troubleshooting

### API Won't Start
```bash
# Check logs
docker-compose logs api

# Verify environment variables
cat .env
```

### Database Connection Failed
```bash
# Test Supabase connection
curl -X GET "$SUPABASE_URL/rest/v1/" \
  -H "apikey: $SUPABASE_KEY"
```

### Port Already in Use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux
sudo lsof -i :8000
sudo kill -9 <PID>
```

## 📞 Support

- **Documentation**: See `/docs` folder
- **API Docs**: `http://localhost:8000/docs`
- **Issues**: GitHub Issues

## 📄 License

MIT License - see [LICENSE](LICENSE) file

## 🎯 Roadmap

- [ ] WebSocket support for real-time updates
- [ ] Batch repository upload
- [ ] Advanced analytics dashboard
- [ ] Custom scoring rules
- [ ] GitHub App integration
- [ ] Multi-language support
- [ ] Advanced caching layer
- [ ] GraphQL API

## ⭐ Acknowledgments

- FastAPI for the excellent web framework
- Supabase for database infrastructure
- OpenAI for AI capabilities
- LangGraph for workflow orchestration

---

**Built with ❤️ for automated code quality assessment**

[![Tests](https://github.com/YOUR_USERNAME/repo-analyzer/workflows/Run%20Tests/badge.svg)](https://github.com/YOUR_USERNAME/repo-analyzer/actions)
[![Deploy](https://github.com/YOUR_USERNAME/repo-analyzer/workflows/Deploy%20to%20AWS%20EC2/badge.svg)](https://github.com/YOUR_USERNAME/repo-analyzer/actions)
