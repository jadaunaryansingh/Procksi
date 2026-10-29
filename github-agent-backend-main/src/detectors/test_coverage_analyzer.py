"""
Test Coverage Analyzer

Detects and measures test coverage across multiple languages.
Supports Python (pytest/coverage), JavaScript/TypeScript (Jest),  
Java (JaCoCo), Go (go test -cover).
"""

import os
import re
import subprocess
import json
from typing import Dict, Any, List, Tuple
from collections import defaultdict


# Test file patterns by language
TEST_PATTERNS = {
    "python": ["test_*.py", "*_test.py", "tests/", "test/", "pytest"],
    "javascript": [".test.js", ".spec.js", ".test.ts", ".spec.ts", "__tests__/", "jest.config"],
    "typescript": [".test.ts", ".spec.ts", "__tests__/"],
    "java": ["*Test.java", "*Tests.java", "src/test/"],
    "go": ["_test.go"],
    "rust": ["tests/", "#[test]", "#[cfg(test)]"],
    "csharp": ["*Test.cs", "*Tests.cs", "[Test]", "[Fact]"]
}


def detect_test_framework(repo_path: str) -> Dict[str, List[str]]:
    """Detect which test frameworks are being used."""
    frameworks = defaultdict(list)
    
    # Check package.json for JS test frameworks
    package_json = os.path.join(repo_path, "package.json")
    if os.path.exists(package_json):
        try:
            with open(package_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                
                if 'jest' in deps:
                    frameworks['javascript'].append('jest')
                if 'mocha' in deps:
                    frameworks['javascript'].append('mocha')
                if 'vitest' in deps:
                    frameworks['javascript'].append('vitest')
                if '@testing-library/react' in deps:
                    frameworks['javascript'].append('react-testing-library')
        except:
            pass
    
    # Check requirements.txt / setup.py for Python test frameworks
    for req_file in ['requirements.txt', 'requirements-dev.txt', 'setup.py', 'pyproject.toml']:
        req_path = os.path.join(repo_path, req_file)
        if os.path.exists(req_path):
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'pytest' in content:
                        frameworks['python'].append('pytest')
                    if 'unittest' in content or 'import unittest' in content:
                        frameworks['python'].append('unittest')
                    if 'coverage' in content:
                        frameworks['python'].append('coverage')
            except:
                pass
    
    # Check pom.xml for Java test frameworks
    pom_xml = os.path.join(repo_path, "pom.xml")
    if os.path.exists(pom_xml):
        try:
            with open(pom_xml, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'junit' in content.lower():
                    frameworks['java'].append('junit')
                if 'mockito' in content.lower():
                    frameworks['java'].append('mockito')
        except:
            pass
    
    # Check for Go test files
    has_go_tests = False
    for root, _, files in os.walk(repo_path):
        if any(f.endswith('_test.go') for f in files):
            has_go_tests = True
            break
    if has_go_tests:
        frameworks['go'].append('go-test')
    
    return dict(frameworks)


def count_test_files_and_lines(repo_path: str) -> Dict[str, Any]:
    """Count test files and lines across all languages."""
    test_stats = {
        "total_test_files": 0,
        "total_test_lines": 0,
        "test_files_by_language": defaultdict(int),
        "test_lines_by_language": defaultdict(int)
    }
    
    for root, _, files in os.walk(repo_path):
        # Skip common ignored directories
        if any(skip in root for skip in ['.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build', 'target']):
            continue
        
        for f in files:
            # Determine if this is a test file
            is_test = False
            language = None
            
            # Python tests
            if f.startswith('test_') or f.endswith('_test.py'):
                is_test = True
                language = 'python'
            elif 'tests' in root.lower() or 'test' in root.lower():
                if f.endswith('.py'):
                    is_test = True
                    language = 'python'
                elif f.endswith(('.js', '.jsx', '.ts', '.tsx')):
                    is_test = True
                    language = 'javascript'
                elif f.endswith('.java'):
                    is_test = True
                    language = 'java'
            
            # JS/TS tests
            elif '.test.' in f or '.spec.' in f:
                is_test = True
                if f.endswith(('.ts', '.tsx')):
                    language = 'typescript'
                else:
                    language = 'javascript'
            elif '__tests__' in root:
                is_test = True
                language = 'javascript'
            
            # Java tests
            elif f.endswith('Test.java') or f.endswith('Tests.java'):
                is_test = True
                language = 'java'
            
            # Go tests
            elif f.endswith('_test.go'):
                is_test = True
                language = 'go'
            
            if is_test and language:
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as file:
                        lines = len([l for l in file.readlines() if l.strip()])
                        
                        test_stats["total_test_files"] += 1
                        test_stats["total_test_lines"] += lines
                        test_stats["test_files_by_language"][language] += 1
                        test_stats["test_lines_by_language"][language] += lines
                except:
                    continue
    
    # Convert defaultdicts to regular dicts
    test_stats["test_files_by_language"] = dict(test_stats["test_files_by_language"])
    test_stats["test_lines_by_language"] = dict(test_stats["test_lines_by_language"])
    
    return test_stats


def calculate_test_to_code_ratio(repo_path: str, test_lines: int) -> float:
    """Calculate the ratio of test lines to production code lines."""
    production_lines = 0
    
    code_extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.rs', '.cs', '.php']
    
    for root, _, files in os.walk(repo_path):
        # Skip test directories and other non-production code
        if any(skip in root for skip in ['.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build', 'target', 'tests', 'test', '__tests__']):
            continue
        
        for f in files:
            # Skip test files
            if any(test_pattern in f for test_pattern in ['test_', '_test.', '.test.', '.spec.', 'Test.java', 'Tests.java']):
                continue
            
            # Count production code
            if any(f.endswith(ext) for ext in code_extensions):
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as file:
                        lines = len([l for l in file.readlines() if l.strip()])
                        production_lines += lines
                except:
                    continue
    
    if production_lines == 0:
        return 0.0
    
    # Ideal ratio is 1:2 (1 test line for every 2 production lines = 0.5)
    return test_lines / production_lines


def estimate_test_coverage_from_analysis(test_stats: Dict[str, Any], test_to_code_ratio: float, frameworks: Dict[str, List[str]]) -> int:
    """Estimate test coverage based on heuristics (0-100 score)."""
    score = 0
    
    # Factor 1: Test file count (0-30 points)
    # Mature repositories often split tests by domain; reward breadth.
    test_file_score = min(30, test_stats["total_test_files"] * 3)
    score += test_file_score
    
    # Factor 2: Test to code ratio (0-40 points)
    # Keep high bar for excellent scores, but avoid over-penalizing large repos.
    if test_to_code_ratio >= 0.3:
        ratio_score = 40
    elif test_to_code_ratio >= 0.2:
        ratio_score = 36
    elif test_to_code_ratio >= 0.1:
        ratio_score = 32
    elif test_to_code_ratio >= 0.05:
        ratio_score = 30
    elif test_to_code_ratio >= 0.2:
        ratio_score = 20
    else:
        ratio_score = min(20, test_to_code_ratio * 250)  # Scale up small ratios
    score += ratio_score
    
    # Factor 3: Test framework usage (0-30 points)
    framework_score = 0
    if any(frameworks.values()):
        # 10 points for having any test framework
        framework_score = 10
        
        # Bonus points for multiple test frameworks (comprehensive testing)
        total_frameworks = sum(len(fw) for fw in frameworks.values())
        framework_score += min(20, total_frameworks * 5)
    
    score += framework_score

    # Factor 4: Large-suite maturity bonus (0-15 points)
    # Reward substantial absolute investment in testing even if ratio is diluted by repo size.
    maturity_bonus = 0
    total_test_files = test_stats.get("total_test_files", 0)
    total_test_lines = test_stats.get("total_test_lines", 0)
    if total_test_files >= 20 and total_test_lines >= 1500:
        maturity_bonus = 15
    elif total_test_files >= 12 and total_test_lines >= 800:
        maturity_bonus = 10
    elif total_test_files >= 8 and total_test_lines >= 400:
        maturity_bonus = 5

    score += maturity_bonus
    
    return min(100, score)


def analyze_test_coverage(repo_path: str) -> Dict[str, Any]:
    """
    Comprehensive test coverage analysis.
    
    Returns:
        - test_coverage_score: 0-100 score
        - test_files: count of test files
        - test_lines: count of test lines
        - test_to_code_ratio: ratio of test lines to production lines
        - frameworks_detected: list of test frameworks found
        - coverage_estimate: estimated coverage percentage
    """
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Test coverage analysis skipped: invalid repo_path ({repo_path})")
        return {
            "test_coverage_score": 0,
            "test_files": 0,
            "test_lines": 0,
            "test_to_code_ratio": 0.0,
            "frameworks_detected": [],
            "coverage_estimate": 0,
            "has_tests": False
        }
    
    print(f"      🧪 Analyzing test coverage...")
    
    # Detect test frameworks
    frameworks = detect_test_framework(repo_path)
    framework_list = []
    for lang, fws in frameworks.items():
        framework_list.extend(fws)
    
    if framework_list:
        print(f"      ✅ Detected test frameworks: {', '.join(framework_list)}")
    
    # Count test files and lines
    test_stats = count_test_files_and_lines(repo_path)
    
    if test_stats["total_test_files"] == 0:
        print(f"      ℹ️  No test files detected")
        return {
            "test_coverage_score": 0,
            "test_files": 0,
            "test_lines": 0,
            "test_to_code_ratio": 0.0,
            "frameworks_detected": framework_list,
            "coverage_estimate": 0,
            "has_tests": False
        }
    
    print(f"      📊 Found {test_stats['total_test_files']} test files ({test_stats['total_test_lines']} lines)")
    
    # Calculate test to code ratio
    test_to_code_ratio = calculate_test_to_code_ratio(repo_path, test_stats["total_test_lines"])
    
    print(f"      📈 Test-to-code ratio: {test_to_code_ratio:.2%}")
    
    # Estimate coverage score
    coverage_score = estimate_test_coverage_from_analysis(test_stats, test_to_code_ratio, frameworks)
    
    # Estimate approximate coverage percentage (heuristic)
    coverage_estimate = min(100, int(test_to_code_ratio * 200))
    
    print(f"      ✅ Test coverage score: {coverage_score}/100 (estimated ~{coverage_estimate}% coverage)")
    
    return {
        "test_coverage_score": coverage_score,
        "test_files": test_stats["total_test_files"],
        "test_lines": test_stats["total_test_lines"],
        "test_to_code_ratio": round(test_to_code_ratio, 3),
        "frameworks_detected": framework_list,
        "coverage_estimate": coverage_estimate,
        "has_tests": True,
        "test_breakdown": test_stats["test_files_by_language"]
    }
