# Testing Guide

## Overview

This project includes comprehensive test coverage across multiple levels:
- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test API endpoints and request/response cycles  
- **End-to-End Tests**: Test complete user workflows
- **Performance Tests**: Test system behavior under load

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures and configuration
├── unit/
│   ├── test_crud.py                 # Database operations (40+ tests)
│   ├── test_data_mapper.py          # Data mapping logic (25+ tests)
│   └── test_schemas.py              # Schema validation (35+ tests)
└── integration/
    ├── test_api.py                  # API endpoint tests (50+ tests)
    ├── test_workflows.py            # E2E workflow tests (30+ tests)
    └── test_performance.py          # Performance/load tests (20+ tests)
```

**Total: 200+ test cases**

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This includes:
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `pytest-mock` - Mocking utilities
- `httpx` - Async HTTP client for testing
- `faker` - Generate test data

### 2. Set Environment Variables

For testing, set dummy environment variables:

```bash
# Windows
set SUPABASE_URL=https://test.supabase.co
set SUPABASE_KEY=test_key
set SUPABASE_SERVICE_KEY=test_service_key
set GEMINI_API_KEY=test_gemini_key

# Linux/Mac
export SUPABASE_URL=https://test.supabase.co
export SUPABASE_KEY=test_key
export SUPABASE_SERVICE_KEY=test_service_key
export GEMINI_API_KEY=test_gemini_key
```

## Running Tests

### Quick Start - Run All Tests

```bash
# Using the test runner script (recommended)
python run_tests.py

# Or directly with pytest
pytest tests/ -v
```

### Run Specific Test Suites

```bash
# Unit tests only
pytest tests/unit -v

# Integration tests only
pytest tests/integration -v

# Specific test file
pytest tests/unit/test_crud.py -v

# Specific test class
pytest tests/unit/test_crud.py::TestProjectCRUD -v

# Specific test method
pytest tests/unit/test_crud.py::TestProjectCRUD::test_create_project -v
```

### Run with Coverage

```bash
# Generate coverage report
pytest tests/ --cov=backend --cov-report=html --cov-report=term

# View HTML report (opens in browser)
# Open: htmlcov/index.html

# Coverage for specific module
pytest tests/unit/test_crud.py --cov=backend.crud --cov-report=term
```

### Run Performance Tests

```bash
# Fast performance tests only
pytest tests/integration/test_performance.py -v -m "not slow"

# All performance tests (including slow ones)
pytest tests/integration/test_performance.py -v

# With timing information
pytest tests/integration/test_performance.py -v --durations=10
```

### Run with Verbose Output

```bash
# Show print statements
pytest tests/ -v -s

# Show detailed failure information
pytest tests/ -v -vv

# Stop on first failure
pytest tests/ -x

# Run last failed tests
pytest tests/ --lf
```

## Test Categories

### Unit Tests (100+ tests)

**test_crud.py** - Database CRUD Operations
- `TestProjectCRUD`: Create, read, update, delete projects (15 tests)
- `TestAnalysisJobCRUD`: Job management and status updates (8 tests)
- `TestTechStackCRUD`: Technology stack operations (2 tests)
- `TestIssueCRUD`: Issue tracking operations (2 tests)
- `TestTeamMemberCRUD`: Team member management (2 tests)

**test_data_mapper.py** - Business Logic
- `TestDataMapper`: Score calculation, data transformation (17 tests)
- `TestDataMapperEdgeCases`: Error handling, None values (8 tests)

**test_schemas.py** - API Validation
- `TestAnalyzeRepoRequest`: Request validation (6 tests)
- `TestBatchUploadRequest`: Batch limits (4 tests)
- `TestProjectFilterParams`: Filter validation (7 tests)
- `TestLeaderboardParams`: Sort/order validation (5 tests)
- `TestScoreBreakdown`: Score models (3 tests)
- `TestSchemaEdgeCases`: Boundary testing (4 tests)

### Integration Tests (80+ tests)

**test_api.py** - API Endpoints
- `TestHealthEndpoint`: Health checks (2 tests)
- `TestAnalysisEndpoints`: Analysis submission and monitoring (7 tests)
- `TestProjectsEndpoints`: Project CRUD operations (7 tests)
- `TestLeaderboardEndpoints`: Leaderboard generation (5 tests)
- `TestErrorHandling`: Error scenarios (4 tests)
- `TestConcurrency`: Concurrent requests (1 test)

**test_workflows.py** - End-to-End Flows
- `TestCompleteAnalysisWorkflow`: Full analysis lifecycle (2 tests)
- `TestBatchWorkflow`: Batch processing (1 test)
- `TestProjectManagementWorkflow`: CRUD workflows (1 test)
- `TestLeaderboardWorkflow`: Ranking and filtering (1 test)
- `TestErrorRecoveryWorkflow`: Failure handling (2 tests)
- `TestDataConsistency`: Cross-endpoint consistency (1 test)
- `TestRateLimiting`: Load handling (1 test)

**test_performance.py** - Performance & Load
- `TestPerformance`: Response time benchmarks (3 tests)
- `TestConcurrentLoad`: Concurrent request handling (4 tests)
- `TestScalability`: Large dataset handling (3 tests)
- `TestStressTest`: Breaking point analysis (2 tests, marked as slow)
- `TestResourceLimits`: Limit enforcement (3 tests)
- `TestResponseSizes`: Response size handling (3 tests)

## Test Fixtures

Located in `tests/conftest.py`:

### Mock Fixtures
- `mock_supabase_client`: Mocked Supabase client with chainable methods

### Data Fixtures
- `sample_project_data`: Basic project data
- `completed_project_data`: Fully analyzed project with scores
- `sample_job_data`: Analysis job data
- `sample_tech_stack`: Technology stack items
- `sample_issues`: Security/AI/plagiarism issues
- `sample_team_members`: Team member contributions
- `sample_analysis_report`: Complete analysis results from agent.py

## Writing New Tests

### Test Structure

```python
import pytest

class TestMyFeature:
    """Test my feature description"""
    
    def test_happy_path(self, mock_supabase_client):
        """Test normal operation"""
        # Arrange
        mock_supabase_client.table().execute.return_value.data = [...]
        
        # Act
        result = my_function()
        
        # Assert
        assert result == expected
    
    def test_error_case(self):
        """Test error handling"""
        with pytest.raises(ValueError):
            my_function(invalid_input)
```

### Using Fixtures

```python
def test_with_project(self, sample_project_data):
    """Use existing fixture"""
    project = sample_project_data
    assert project["team_name"] == "Test Team"

def test_with_mock(self, mock_supabase_client):
    """Mock database calls"""
    mock_supabase_client.table().execute.return_value.data = []
    # Your test code
```

### Testing API Endpoints

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_endpoint():
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert "projects" in response.json()
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Run tests
      run: python run_tests.py
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
        SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
        GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## Best Practices

### 1. Test Isolation
- Each test should be independent
- Use fixtures for setup/teardown
- Mock external dependencies

### 2. Clear Test Names
- Use descriptive names: `test_create_project_with_valid_data`
- Indicate what is being tested and expected outcome

### 3. Arrange-Act-Assert Pattern
```python
def test_something():
    # Arrange: Set up test data
    data = prepare_data()
    
    # Act: Execute the function
    result = function_under_test(data)
    
    # Assert: Verify the outcome
    assert result == expected_value
```

### 4. Test Edge Cases
- Empty inputs
- None values
- Boundary conditions
- Maximum/minimum values
- Invalid data types

### 5. Mock External Services
- Database calls
- API requests
- File system operations
- Time-dependent code

### 6. Meaningful Assertions
```python
# Bad
assert result

# Good
assert result.status_code == 200
assert "project_id" in result.json()
assert result.json()["team_name"] == "Test Team"
```

## Troubleshooting

### Tests Fail Due to Missing Environment Variables
```bash
# Ensure environment variables are set
python -c "import os; print(os.environ.get('SUPABASE_URL'))"
```

### Import Errors
```bash
# Add project root to PYTHONPATH
# Windows
set PYTHONPATH=%PYTHONPATH%;d:\Coding\Github-Agent\proj-github agent

# Linux/Mac
export PYTHONPATH=$PYTHONPATH:/path/to/proj-github agent
```

### Coverage Not Showing Files
```bash
# Ensure tests are run from project root
cd "d:\Coding\Github-Agent\proj-github agent"
pytest tests/ --cov=backend
```

### Slow Tests
```bash
# Skip slow tests
pytest tests/ -m "not slow"

# Run only slow tests
pytest tests/ -m "slow"
```

### Debugging Failed Tests
```bash
# Show print statements
pytest tests/ -s

# Drop into debugger on failure
pytest tests/ --pdb

# Show local variables on failure
pytest tests/ -l
```

## Coverage Goals

Target coverage metrics:
- **Overall**: ≥ 85%
- **backend/crud.py**: ≥ 90%
- **backend/services/**: ≥ 85%
- **backend/routers/**: ≥ 80%
- **backend/schemas.py**: ≥ 95%

Check current coverage:
```bash
pytest tests/ --cov=backend --cov-report=term-missing
```

## Continuous Improvement

### Adding New Tests
1. Identify untested code paths using coverage report
2. Write test cases for edge cases
3. Add regression tests when bugs are found
4. Update fixtures as models evolve

### Test Maintenance
- Review and update tests when APIs change
- Remove obsolete tests
- Refactor duplicated test code
- Keep fixtures DRY (Don't Repeat Yourself)

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
