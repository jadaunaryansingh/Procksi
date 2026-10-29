"""
GitHub Actions Analyzer
Parses .yml workflow files and calls GitHub Actions API for run history.
"""
import os
import re
import requests
from typing import Dict, Any, List, Optional


def parse_repo_url(repo_url: str) -> tuple:
    """Extract owner and repo name from a GitHub URL."""
    # Handle various URL formats
    patterns = [
        r'github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$',
        r'github\.com[/:]([^/]+)/([^/.]+?)/?$',
    ]
    for pattern in patterns:
        match = re.search(pattern, repo_url)
        if match:
            return match.group(1), match.group(2)
    return None, None


def parse_workflow_files(repo_path: str) -> List[Dict[str, Any]]:
    """
    Parse .yml/.yaml workflow files in .github/workflows/ directory.
    Extracts workflow name, triggers, and detected actions (build, test, lint, deploy).
    """
    workflows = []
    workflows_dir = os.path.join(repo_path, ".github", "workflows")
    
    if not os.path.isdir(workflows_dir):
        return workflows
    
    for fname in os.listdir(workflows_dir):
        if not fname.endswith(('.yml', '.yaml')):
            continue
        
        fpath = os.path.join(workflows_dir, fname)
        try:
            content = open(fpath, 'r', encoding='utf-8', errors='ignore').read()
        except Exception:
            continue
        
        workflow = {
            "file": fname,
            "name": fname.replace('.yml', '').replace('.yaml', ''),
            "triggers": [],
            "actions": [],
            "raw_steps_count": 0,
        }
        
        # Extract workflow name (YAML: name: ...)
        name_match = re.search(r'^name:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        if name_match:
            workflow["name"] = name_match.group(1).strip()
        
        # Extract triggers from 'on:' block
        # Simple patterns: on: push, on: [push, pull_request], on:\n  push:\n  pull_request:
        trigger_patterns = [
            r'\bon:\s*\[([^\]]+)\]',           # on: [push, pull_request]
            r'\bon:\s+(push|pull_request|schedule|workflow_dispatch|release|create|delete)',  # on: push
            r'\bon:\s*\n((?:\s+\w+:.*\n?)+)',   # on:\n  push:\n  pull_request:
        ]
        
        for tp in trigger_patterns:
            t_match = re.search(tp, content)
            if t_match:
                matched = t_match.group(1)
                # Parse triggers from the match
                triggers = re.findall(r'(push|pull_request|schedule|workflow_dispatch|release|create|delete|merge_group)', matched)
                workflow["triggers"] = list(set(triggers))
                break
        
        # Count steps
        steps = re.findall(r'^\s*- (?:name|uses|run):', content, re.MULTILINE)
        workflow["raw_steps_count"] = len(steps)
        
        # Detect what the workflow does based on content analysis
        content_lower = content.lower()
        detected_actions = set()
        
        # Build detection
        build_signals = ['npm run build', 'yarn build', 'mvn package', 'gradle build',
                         'docker build', 'go build', 'cargo build', 'pip install',
                         'npm ci', 'npm install', 'yarn install', 'pnpm install']
        if any(sig in content_lower for sig in build_signals):
            detected_actions.add("build")
        
        # Test detection
        test_signals = ['npm test', 'npm run test', 'yarn test', 'pytest', 'jest',
                        'go test', 'cargo test', 'mvn test', 'gradle test',
                        'unittest', 'mocha', 'vitest', 'cypress']
        if any(sig in content_lower for sig in test_signals):
            detected_actions.add("test")
        
        # Lint detection
        lint_signals = ['eslint', 'pylint', 'flake8', 'black', 'prettier', 'rubocop',
                        'golint', 'clippy', 'npm run lint', 'yarn lint', 'ruff']
        if any(sig in content_lower for sig in lint_signals):
            detected_actions.add("lint")
        
        # Deploy detection
        deploy_signals = ['deploy', 'vercel', 'netlify', 'heroku', 'aws', 'gcloud',
                          'azure', 'firebase deploy', 'gh-pages', 'render',
                          'docker push', 'kubectl apply', 'ssh', 'rsync',
                          'actions/deploy', 'peaceiris/actions-gh-pages']
        if any(sig in content_lower for sig in deploy_signals):
            detected_actions.add("deploy")
        
        # Security/scanning detection
        security_signals = ['codeql', 'snyk', 'dependabot', 'trivy', 'sonarqube',
                            'security', 'audit', 'vulnerability']
        if any(sig in content_lower for sig in security_signals):
            detected_actions.add("security_scan")
        
        workflow["actions"] = sorted(list(detected_actions))
        workflows.append(workflow)
    
    return workflows


def fetch_github_actions_history(owner: str, repo: str, token: str = None) -> Optional[Dict[str, Any]]:
    """
    Call GitHub Actions API to get workflow run history.
    Paginates through all runs for accurate totals.
    Returns summary of run success/failure rates.
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    
    try:
        all_runs = []
        page = 1
        total_count = None
        
        while True:
            url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=100&page={page}"
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 404:
                return None
            
            if response.status_code == 403:
                print(f"[CI/CD] GitHub API rate limited or forbidden for {owner}/{repo}")
                return None
            
            if response.status_code != 200:
                print(f"[CI/CD] GitHub Actions API returned {response.status_code} for {owner}/{repo}")
                return None
            
            data = response.json()
            
            # Use total_count from API for accurate total (available on first page)
            if total_count is None:
                total_count = data.get("total_count", 0)
            
            runs = data.get("workflow_runs", [])
            if not runs:
                break
            
            all_runs.extend(runs)
            
            # Stop if we've fetched all runs or hit a reasonable cap (500 runs)
            if len(all_runs) >= total_count or len(all_runs) >= 500:
                break
            
            page += 1
        
        if not all_runs:
            return {
                "total_runs": 0,
                "successful": 0,
                "failed": 0,
                "pass_rate": 0,
                "last_run_date": None,
                "last_run_status": None,
            }
        
        successful = sum(1 for r in all_runs if r.get("conclusion") == "success")
        failed = sum(1 for r in all_runs if r.get("conclusion") == "failure")
        cancelled = sum(1 for r in all_runs if r.get("conclusion") == "cancelled")
        total = len(all_runs)
        
        # Last run info (first in the list = most recent)
        last_run = all_runs[0]
        
        return {
            "total_runs": total,
            "successful": successful,
            "failed": failed,
            "cancelled": cancelled,
            "pass_rate": round((successful / total * 100), 1) if total > 0 else 0,
            "last_run_date": last_run.get("created_at"),
            "last_run_status": last_run.get("conclusion") or last_run.get("status"),
            "last_run_workflow": last_run.get("name"),
        }
    
    except requests.exceptions.Timeout:
        print(f"[CI/CD] GitHub Actions API timed out for {owner}/{repo}")
        return None
    except Exception as e:
        print(f"[CI/CD] Error fetching GitHub Actions history: {e}")
        return None


def analyze_ci_cd(repo_path: str, repo_url: str) -> Dict[str, Any]:
    """
    Full CI/CD analysis: parse workflow files + fetch GitHub Actions run history.
    
    Args:
        repo_path: Local path to the cloned repository
        repo_url: GitHub repository URL (for API calls)
    
    Returns:
        Dict with workflows, run_history, and ci_cd_score
    """
    result = {
        "workflows": [],
        "run_history": None,
        "has_ci_cd": False,
        "ci_cd_score": 0,
        "summary": "No CI/CD pipelines detected",
    }
    
    # 1. Parse workflow YAML files
    workflows = parse_workflow_files(repo_path)
    result["workflows"] = workflows
    
    if workflows:
        result["has_ci_cd"] = True
    
    # 2. Fetch GitHub Actions run history
    owner, repo = parse_repo_url(repo_url)
    if owner and repo:
        token = os.getenv("GH_API_KEY") or os.getenv("GITHUB_TOKEN")
        run_history = fetch_github_actions_history(owner, repo, token)
        result["run_history"] = run_history
    
    # 3. Calculate CI/CD score (0-100)
    score = 0
    
    # Points for having workflows (up to 30)
    if workflows:
        score += min(30, len(workflows) * 15)  # 15 per workflow, max 30
    
    # Points for workflow actions (up to 30)
    all_actions = set()
    for wf in workflows:
        all_actions.update(wf.get("actions", []))
    
    action_points = {
        "build": 8,
        "test": 10,
        "lint": 5,
        "deploy": 10,
        "security_scan": 7,
    }
    for action, pts in action_points.items():
        if action in all_actions:
            score += pts
    
    # Points for run history (up to 30)
    run_history = result.get("run_history")
    if run_history and run_history.get("total_runs", 0) > 0:
        pass_rate = run_history.get("pass_rate", 0)
        total_runs = run_history.get("total_runs", 0)
        
        # Activity points (up to 10) — having runs at all
        score += min(10, total_runs * 2)
        
        # Pass rate points (up to 20)
        if pass_rate >= 90:
            score += 20
        elif pass_rate >= 70:
            score += 15
        elif pass_rate >= 50:
            score += 10
        elif pass_rate > 0:
            score += 5
    
    result["ci_cd_score"] = min(100, score)
    
    # Generate human-readable summary
    if not workflows:
        result["summary"] = "No CI/CD pipelines detected"
    else:
        wf_names = [w["name"] for w in workflows]
        actions_str = ", ".join(sorted(all_actions)) if all_actions else "none detected"
        summary = f"{len(workflows)} workflow(s): {', '.join(wf_names)}. Actions: {actions_str}."
        
        if run_history and run_history.get("total_runs", 0) > 0:
            summary += f" Pass rate: {run_history['pass_rate']}% ({run_history['successful']}/{run_history['total_runs']} runs)."
        
        result["summary"] = summary
    
    print(f"[CI/CD] Analysis complete: {result['summary']} (score: {result['ci_cd_score']})")
    return result
