"""
Test configuration and fixtures
Provides shared test fixtures and configuration for the test suite
"""
import pytest
import os
import sys
from pathlib import Path
from typing import Generator
from fastapi.testclient import TestClient


# Add project root to Python path so src imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "ERROR"

# Set fake Supabase env vars so database.py doesn't raise ValueError
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")

# Mock Supabase database connections for all tests
from unittest.mock import MagicMock

class MockSupabaseTable:
    def __init__(self, name):
        self.name = name
    def select(self, *args, **kwargs): return self
    def eq(self, *args, **kwargs): return self
    def neq(self, *args, **kwargs): return self
    def gt(self, *args, **kwargs): return self
    def gte(self, *args, **kwargs): return self
    def lt(self, *args, **kwargs): return self
    def lte(self, *args, **kwargs): return self
    def like(self, *args, **kwargs): return self
    def ilike(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def in_(self, *args, **kwargs): return self
    def is_(self, *args, **kwargs): return self
    def order(self, *args, **kwargs): return self
    def range(self, *args, **kwargs): return self
    def single(self, *args, **kwargs): return self
    def execute(self, *args, **kwargs):
        class MockResult:
            data = []
            count = 0
        
        res = MockResult()
        if self.name == "users":
            res.data = [{"id": "00000000-0000-0000-0000-000000000000", "role": "admin", "is_mentor": True, "full_name": "Standalone Admin"}]
        elif self.name == "batches":
            res.data = [{
                "id": "00000000-0000-0000-0000-000000000123",
                "name": "Test Batch",
                "semester": "Fall",
                "year": 2026,
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-06-30T23:59:59Z",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z"
            }]
        elif self.name == "teams":
            res.data = [{
                "id": "00000000-0000-0000-0000-000000000001",
                "batch_id": "00000000-0000-0000-0000-000000000123",
                "team_name": "Test Team",
                "name": "Test Team",
                "repo_url": "https://github.com/test-org/test-repo",
                "health_status": "on_track",
                "status": "pending",
                "student_count": 0,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "total_score": None,
                "quality_score": None,
                "security_score": None,
                "analyzed_at": None,
                "last_analyzed_at": None,
                "metadata": None,
                "last_activity": None
            }]
        elif self.name == "analysis_jobs":
            res.data = [{
                "id": "00000000-0000-0000-0000-000000000002",
                "team_id": "00000000-0000-0000-0000-000000000001",
                "status": "queued"
            }]
        return res
    def insert(self, *args, **kwargs): return self
    def update(self, *args, **kwargs): return self
    def delete(self, *args, **kwargs): return self
    def upsert(self, *args, **kwargs): return self

class MockSupabaseClient:
    def table(self, name):
        return MockSupabaseTable(name)
    @property
    def auth(self):
        class MockAuth:
            def get_user(self, *args, **kwargs):
                class MockUserResp:
                    user = None
                return MockUserResp()
        return MockAuth()

# --- Critical: Mock the supabase package BEFORE any app module imports it ---
# This replaces the `create_client` function so that `database.py`'s singleton
# pattern returns our MockSupabaseClient no matter which module calls it.
mock_supabase_module = MagicMock()
mock_supabase_module.create_client = lambda *args, **kwargs: MockSupabaseClient()
mock_supabase_module.Client = MockSupabaseClient
sys.modules["supabase"] = mock_supabase_module

# Mock celery modules to prevent connection hangs
class MockCeleryTask:
    @property
    def id(self):
        return "mock-celery-task-id"

class MockCeleryFunction:
    def delay(self, *args, **kwargs):
        return MockCeleryTask()

mock_celery_worker = MagicMock()
mock_celery_worker.analyze_single_repository_task = MockCeleryFunction()
sys.modules["celery_worker"] = mock_celery_worker

mock_celery_app = MagicMock()
mock_celery_app.celery_app = MagicMock()
sys.modules["celery_app"] = mock_celery_app

# Now import and patch the database module
import src.api.backend.database as db
db.create_client = lambda *args, **kwargs: MockSupabaseClient()
db._supabase_client = MockSupabaseClient()
db._supabase_admin_client = MockSupabaseClient()
db.get_supabase_client = lambda: MockSupabaseClient()
db.get_supabase_admin_client = lambda: MockSupabaseClient()
db.supabase = lambda: MockSupabaseClient()
db.get_supabase = lambda: MockSupabaseClient()


@pytest.fixture(scope="session")
def test_app():
    """Create test FastAPI application"""
    from main import app
    return app


@pytest.fixture(scope="session")
def client(test_app) -> Generator:
    """Create test client"""
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def mock_github_repo():
    """Mock GitHub repository data"""
    return {
        "url": "https://github.com/test-org/test-repo",
        "name": "test-repo",
        "owner": "test-org",
        "default_branch": "main",
        "is_private": False,
        "description": "Test repository for unit tests",
    }


@pytest.fixture
def mock_team_data():
    """Mock team data for testing"""
    return {
        "team_name": "Test Team",
        "name": "Test Team",
        "repository_url": "https://github.com/test-org/test-repo",
        "repo_url": "https://github.com/test-org/test-repo",
        "batch_id": "00000000-0000-0000-0000-000000000123",
        "description": "Test team for unit tests",
    }


@pytest.fixture
def mock_analysis_result():
    """Mock analysis result data"""
    return {
        "total_score": 85.5,
        "originality_score": 90.0,
        "implementation_score": 82.0,
        "engineering_score": 88.0,
        "security_score": 75.0,
        "quality_score": 80.0,
        "organization_score": 85.0,
        "effort_score": 90.0,
        "documentation_score": 78.0,
        "fake_commit_percentage": 5.2,
        "penalty_multiplier": 1.0,
        "tech_stack": ["Python", "FastAPI", "Docker"],
    }


@pytest.fixture
def mock_commits():
    """Mock commit data for forensics testing"""
    return [
        {
            "hash": "abc123",
            "author": "Test User",
            "email": "test@example.com",
            "message": "feat: Add user authentication system",
            "date": "2026-01-01T10:00:00Z",
            "additions": 150,
            "deletions": 20,
            "files_changed": ["auth.py", "models.py"],
        },
        {
            "hash": "def456",
            "author": "Test User",
            "email": "test@example.com",
            "message": "fix: Resolve memory leak in cache utility",
            "date": "2026-01-02T14:30:00Z",
            "additions": 25,
            "deletions": 10,
            "files_changed": ["cache.py"],
        },
    ]
