import os
from typing import Dict, Any
from src.utils.file_utils import read_file

# Patterns that indicate testing infrastructure
TEST_PATTERNS = [
    "test_", "_test.py", ".spec.js", ".test.js", 
    "src/test", "tests/", "__tests__", "go_test.go"
]

# Patterns that indicate deployment/devops
DEVOPS_FILES = {
    "Docker": ["Dockerfile", "docker-compose.yml", ".dockerignore"],
    "CI/CD": [".github/workflows", ".gitlab-ci.yml", "azure-pipelines.yml", "circleci.config.yml"],
    "Cloud": ["vercel.json", "netlify.toml", "app.yaml", "serverless.yml", "procfile"],
    "Linting": [".eslintrc", ".pylintrc", "pyproject.toml", ".prettierrc"]
}

def scan_project_maturity(repo_path: str, repo_url: str = None) -> Dict[str, Any]:
    # Validate repo_path
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Maturity scan skipped: invalid repo_path ({repo_path})")
        return {
            "score": 20,
            "test_files": 0,
            "test_lines": 0,
            "devops_tools": [],
            "has_tests": False,
            "is_deployable": False,
            "ci_cd": None
        }
    test_files_count = 0
    test_lines_count = 0
    devops_stack = []
    has_ci = False
    
    # 1. Walk file tree
    for root, _, files in os.walk(repo_path):
        # Check for CI folders
        if ".github" in root:
            has_ci = True
            
        for f in files:
            f_lower = f.lower()
            path = os.path.join(root, f)
            
            # A. Check for DevOps Configs
            for category, filenames in DEVOPS_FILES.items():
                if any(name.lower() in f_lower for name in filenames):
                    if category not in devops_stack:
                        devops_stack.append(category)
            
            # B. Check for Tests
            is_test = any(p in f_lower or p in root.lower() for p in TEST_PATTERNS)
            if is_test and not f_lower.endswith((".png", ".xml", ".json")):
                try:
                    content = read_file(path)
                    # Heuristic: Real tests usually have "assert", "expect", or "Testing" imports
                    if "assert" in content or "expect(" in content or "testing" in content:
                        test_files_count += 1
                        test_lines_count += len(content.splitlines())
                except:
                    pass

    # 2. Score Calculation
    # 20 points for Docker, 20 for CI, 10 for Linting
    # 50 points based on test volume
    
    devops_score = 0
    if "Docker" in devops_stack: devops_score += 20
    if "Cloud" in devops_stack: devops_score += 20
    if "CI/CD" in devops_stack or has_ci: 
        devops_score += 20
        if "CI/CD" not in devops_stack: devops_stack.append("CI/CD")
    if "Linting" in devops_stack: devops_score += 10
    
    # Cap test score at 30 (assuming 5 test files is "good" for a hackathon)
    test_score = min(30, test_files_count * 6)
    
    maturity_score = min(100, devops_score + test_score)

    # 3. CI/CD Deep Analysis (workflow parsing + GitHub Actions API)
    ci_cd_data = None
    if repo_url:
        try:
            from src.detectors.github_actions_analyzer import analyze_ci_cd
            ci_cd_data = analyze_ci_cd(repo_path, repo_url)
            
            # Boost maturity score with CI/CD insights (up to 10 bonus points)
            if ci_cd_data and ci_cd_data.get("ci_cd_score", 0) > 0:
                ci_bonus = min(10, ci_cd_data["ci_cd_score"] // 10)
                maturity_score = min(100, maturity_score + ci_bonus)
        except Exception as e:
            print(f"⚠️ CI/CD analysis failed: {e}")

    return {
        "score": maturity_score,
        "test_files": test_files_count,
        "test_lines": test_lines_count,
        "devops_tools": devops_stack,
        "has_tests": test_files_count > 0,
        "is_deployable": ("Docker" in devops_stack) or ("Cloud" in devops_stack),
        "ci_cd": ci_cd_data
    }