"""
Test Runner Script
Runs all tests with different configurations and generates reports
"""
import sys
import os
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle output"""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}\n")
    
    result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
    
    if result.returncode != 0:
        print(f"\n❌ {description} FAILED")
        return False
    else:
        print(f"\n✅ {description} PASSED")
        return True


def main():
    """Main test runner"""
    # Set environment variables for testing
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_KEY"] = "test_key"
    os.environ["SUPABASE_SERVICE_KEY"] = "test_service_key"
    os.environ["OPENAI_API_KEY"] = "test_openai_key"
    
    results = []
    
    # 1. Run unit tests with coverage
    results.append(run_command(
        "pytest tests/unit -v --cov=backend --cov-report=term-missing --cov-report=html:htmlcov/unit",
        "UNIT TESTS"
    ))
    
    # 2. Run integration tests
    results.append(run_command(
        "pytest tests/integration/test_api.py tests/integration/test_workflows.py -v",
        "INTEGRATION TESTS"
    ))
    
    # 3. Run performance tests (excluding slow tests)
    results.append(run_command(
        "pytest tests/integration/test_performance.py -v -m 'not slow'",
        "PERFORMANCE TESTS (FAST)"
    ))
    
    # 4. Generate combined coverage report
    print(f"\n{'='*80}")
    print("GENERATING COMBINED COVERAGE REPORT")
    print(f"{'='*80}\n")
    
    subprocess.run(
        "pytest tests/ --cov=backend --cov-report=html:htmlcov --cov-report=term",
        shell=True
    )
    
    # Print summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}\n")
    
    total_tests = len(results)
    passed_tests = sum(results)
    failed_tests = total_tests - passed_tests
    
    print(f"Total Test Suites: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {failed_tests} ❌")
    print(f"\nSuccess Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if failed_tests > 0:
        print("\n❌ Some tests failed. Please review the output above.")
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        print(f"\n📊 Coverage report generated at: {Path('htmlcov/index.html').absolute()}")
        sys.exit(0)


if __name__ == "__main__":
    # Check if pytest is installed
    try:
        import pytest
    except ImportError:
        print("❌ pytest is not installed. Please run:")
        print("   pip install -r requirements.txt")
        sys.exit(1)
    
    main()
