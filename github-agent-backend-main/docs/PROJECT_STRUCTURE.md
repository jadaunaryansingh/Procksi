# Repository Analyzer - Project Structure

## 📁 Directory Structure

```
proj-github-agent/
├── src/                          # Source code
│   ├── api/                      # FastAPI application
│   │   └── backend/              # Backend routers, services, CRUD
│   ├── core/                     # Core business logic
│   │   ├── agent.py              # Main analysis agent
│   │   ├── config.py             # Configuration
│   │   └── *.py                  # Pipeline components
│   ├── detectors/                # Analysis detectors
│   │   ├── alg_detector.py       # Algorithm similarity
│   │   ├── llm_detector.py       # AI-based detection
│   │   ├── security_scan.py      # Security analysis
│   │   └── *.py                  # Other detectors
│   ├── orchestrator/             # LangGraph orchestration
│   └── utils/                    # Utility functions
├── docs/                         # Documentation
├── scripts/                      # Deployment & utility scripts
├── tests/                        # Test suite
│   └── unit/                     # Unit tests
├── .github/workflows/            # CI/CD pipelines
├── main.py                       # Application entry point
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the server
python main.py
```

## 📚 Documentation

- [API Documentation](docs/API_README.md)
- [Frontend Integration Guide](docs/FRONTEND_DEVELOPER_GUIDE.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Testing Guide](docs/TESTING.md)

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## 🔧 Development

```bash
# Run development server with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# API documentation (when running)
http://localhost:8000/docs
```

## 📦 Project Components

### API Layer (`src/api/backend/`)
- **routers/**: FastAPI endpoint definitions
- **services/**: Business logic layer
- **crud.py**: Database operations
- **models.py**: SQLAlchemy ORM models
- **schemas.py**: Pydantic validation schemas

### Core Logic (`src/core/`)
- **agent.py**: Main repository analysis pipeline
- **config.py**: Application configuration
- **scoring.py**: Scoring algorithms
- **workers.py**: Background job processing

### Detectors (`src/detectors/`)
- Algorithm similarity detection
- AI-powered code analysis
- Security vulnerability scanning
- Code quality metrics
- Project maturity assessment

### Utilities (`src/utils/`)
- Git operations
- File handling
- AST parsing
- Visualization tools

## 🌐 API Endpoints

### Public API
- `GET /health` - Health check
- `GET /api/stats` - Platform statistics
- `POST /api/analyze` - Submit repository for analysis
- `GET /api/projects` - List all projects
- `GET /api/projects/{id}` - Get project details
- `GET /api/leaderboard` - Get leaderboard

See [API_README.md](docs/API_README.md) for complete documentation.

## 🔐 Environment Variables

Required variables in `.env`:
```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
GEMINI_API_KEY=your_gemini_key
GH_API_KEY=your_github_token
CORS_ORIGINS=*
```

## 📝 License

MIT License - See LICENSE file for details
