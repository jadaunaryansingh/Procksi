"""
Deployment Verification Module

Checks if a project is actually deployed and accessible.
Verifies live URLs from README, config files, and deployment platforms.
"""

import os
import re
import json
import requests
from typing import Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse


# Deployment platform config files
DEPLOYMENT_CONFIGS = {
    "vercel": [".vercel/project.json", "vercel.json"],
    "netlify": ["netlify.toml", ".netlify/state.json"],
    "heroku": ["Procfile", "app.json"],
    "railway": ["railway.json", "railway.toml"],
    "fly": ["fly.toml"],
    "render": ["render.yaml"],
    "aws": [".elasticbeanstalk/config.yml", "aws-sam.yaml", "cdk.json"],
    "gcp": ["app.yaml", "cloudbuild.yaml"],
    "azure": ["azure-pipelines.yml", ".azure/"],
    "docker": ["docker-compose.yml", "Dockerfile", ".dockerignore"]
}


def extract_urls_from_text(text: str) -> List[str]:
    """Extract all URLs from text content."""
    # Regex pattern for URLs
    url_pattern = r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
    
    urls = re.findall(url_pattern, text)
    
    # Filter out common non-deployment URLs
    excluded_domains = [
        'github.com', 'gitlab.com', 'bitbucket.org',
        'stackoverflow.com', 'npmjs.com', 'pypi.org',
        'maven.org', 'docker.io', 'hub.docker.com',
        'youtube.com', 'youtu.be', 'twitter.com', 'linkedin.com',
        'shields.io', 'img.shields.io', 'badge',
        'localhost', '127.0.0.1', 'example.com', 'test.com'
    ]
    
    filtered_urls = []
    for url in urls:
        if not any(domain in url.lower() for domain in excluded_domains):
            filtered_urls.append(url)
    
    return filtered_urls


def check_url_live(url: str, timeout: int = 5) -> Tuple[bool, int, str]:
    """
    Check if a URL is live and accessible.
    
    Returns:
        Tuple of (is_live, status_code, reason)
    """
    try:
        # Add proper user agent to avoid bot blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.head(url, timeout=timeout, headers=headers, allow_redirects=True)
        
        # Some servers don't respond to HEAD, try GET
        if response.status_code == 405:
            response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        
        if response.status_code < 400:
            return True, response.status_code, "Success"
        else:
            return False, response.status_code, f"HTTP {response.status_code}"
    
    except requests.exceptions.Timeout:
        return False, 0, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, 0, "Connection Error"
    except requests.exceptions.TooManyRedirects:
        return False, 0, "Too Many Redirects"
    except requests.exceptions.RequestException as e:
        return False, 0, f"Error: {str(e)[:50]}"
    except Exception as e:
        return False, 0, f"Unknown Error: {str(e)[:50]}"


def find_deployment_urls_in_readme(repo_path: str) -> List[str]:
    """Find deployment URLs in README files."""
    urls = []
    
    # Look for README files
    readme_patterns = ['README.md', 'README.MD', 'readme.md', 'README', 'README.txt']
    
    for pattern in readme_patterns:
        readme_path = os.path.join(repo_path, pattern)
        if os.path.exists(readme_path):
            try:
                with open(readme_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # Look for common deployment section markers
                    deployment_sections = re.findall(
                        r'(?:##?\s+(?:Live|Demo|Deployment|Website|Application|URL|Link|Preview|Visit).*?\n)(.*?)(?=\n##|$)',
                        content,
                        re.IGNORECASE | re.DOTALL
                    )
                    
                    # Extract URLs from deployment sections
                    for section in deployment_sections:
                        section_urls = extract_urls_from_text(section)
                        urls.extend(section_urls)
                    
                    # If no deployment section, extract all URLs
                    if not urls:
                        all_urls = extract_urls_from_text(content)
                        # Prioritize URLs from markdown links
                        markdown_urls = re.findall(r'\[.*?\]\((https?://[^\)]+)\)', content)
                        urls.extend(markdown_urls)
                        
                        # Add other URLs if we still don't have any
                        if not urls:
                            urls.extend(all_urls[:3])  # Limit to first 3
                
                break  # Found README, stop looking
            except:
                continue
    
    return list(set(urls))  # Remove duplicates


def detect_deployment_platform(repo_path: str) -> Dict[str, bool]:
    """Detect which deployment platforms are configured."""
    platforms = {}
    
    for platform, config_files in DEPLOYMENT_CONFIGS.items():
        platform_detected = False
        
        for config_file in config_files:
            config_path = os.path.join(repo_path, config_file)
            
            # Check for directory existence (e.g., .azure/)
            if config_file.endswith('/'):
                if os.path.isdir(config_path.rstrip('/')):
                    platform_detected = True
                    break
            # Check for file existence
            elif os.path.exists(config_path):
                platform_detected = True
                break
        
        platforms[platform] = platform_detected
    
    return platforms


def extract_url_from_vercel_config(repo_path: str) -> Optional[str]:
    """Extract deployment URL from Vercel config."""
    vercel_path = os.path.join(repo_path, ".vercel/project.json")
    if os.path.exists(vercel_path):
        try:
            with open(vercel_path, 'r') as f:
                data = json.load(f)
                project_id = data.get('projectId')
                org_id = data.get('orgId')
                if project_id:
                    # Vercel projects are typically at projectname.vercel.app
                    return f"https://{project_id}.vercel.app"
        except:
            pass
    return None


def extract_url_from_netlify_config(repo_path: str) -> Optional[str]:
    """Extract deployment URL from Netlify config."""
    netlify_toml = os.path.join(repo_path, "netlify.toml")
    if os.path.exists(netlify_toml):
        try:
            with open(netlify_toml, 'r') as f:
                content = f.read()
                # Look for URL in comments or settings
                url_match = re.search(r'https?://[a-zA-Z0-9-]+\.netlify\.app', content)
                if url_match:
                    return url_match.group(0)
        except:
            pass
    return None


def check_github_releases(repo_url: str) -> List[Dict[str, Any]]:
    """Check if the GitHub repository has any releases."""
    if not repo_url or "github.com" not in repo_url:
        return []
    
    try:
        # Extract owner and repo from url (e.g., https://github.com/owner/repo)
        parts = repo_url.rstrip('/').split('/')
        if len(parts) >= 2:
            owner = parts[-2]
            repo = parts[-1]
            if repo.endswith('.git'):
                repo = repo[:-4]
                
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            headers = {'Accept': 'application/vnd.github.v3+json'}
            
            # Use token if available to avoid rate limits
            token = os.environ.get('GITHUB_TOKEN')
            if token:
                headers['Authorization'] = f'token {token}'
                
            response = requests.get(api_url, headers=headers, timeout=5)
            if response.status_code == 200:
                releases = response.json()
                return releases
    except Exception as e:
        print(f"      ⚠️ Failed to check GitHub releases: {str(e)[:50]}")
    
    return []


def verify_deployment(repo_path: str, repo_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Comprehensive deployment verification.
    
    Checks:
    1. Deployment platform configuration
    2. Live URLs from README
    3. Actual URL accessibility
    
    Returns deployment score and details.
    """
    if not repo_path or not os.path.exists(repo_path):
        print(f"⚠️ Deployment verification skipped: invalid repo_path ({repo_path})")
        return {
            "deployment_score": 0,
            "is_deployed": False,
            "is_accessible": False,
            "has_releases": False,
            "platforms_configured": [],
            "live_urls": [],
            "verification_details": {}
        }
    
    print(f"      🚀 Verifying deployment status...")
    
    # Detect deployment platforms
    platforms = detect_deployment_platform(repo_path)
    platforms_configured = [p for p, configured in platforms.items() if configured]
    
    if platforms_configured:
        print(f"      ✅ Deployment platforms detected: {', '.join(platforms_configured)}")
    else:
        print(f"      ℹ️  No deployment platform configuration found")
    
    # Find URLs from README
    readme_urls = find_deployment_urls_in_readme(repo_path)
    
    # Try to extract URLs from platform configs
    config_urls = []
    if platforms.get('vercel'):
        vercel_url = extract_url_from_vercel_config(repo_path)
        if vercel_url:
            config_urls.append(vercel_url)
    if platforms.get('netlify'):
        netlify_url = extract_url_from_netlify_config(repo_path)
        if netlify_url:
            config_urls.append(netlify_url)
    
    # Combine all URLs
    all_urls = list(set(readme_urls + config_urls))
    
    if not all_urls:
        print(f"      ℹ️  No deployment URLs found")
    else:
        print(f"      🔍 Checking {len(all_urls)} URL(s) for accessibility...")
    
    # Verify each URL
    verification_details = {}
    accessible_urls = []
    
    if all_urls:
        for url in all_urls[:5]:  # Limit to first 5 URLs to avoid excessive requests
            is_live, status_code, reason = check_url_live(url)
            
            verification_details[url] = {
                "accessible": is_live,
                "status_code": status_code,
                "reason": reason
            }
            
            if is_live:
                accessible_urls.append(url)
                print(f"      ✅ {url} - Accessible (HTTP {status_code})")
            else:
                print(f"      ❌ {url} - Not accessible ({reason})")
            
    # Check for GitHub releases ONLY if no accessible URL was found (fallback)
    releases = []
    has_releases = False
    if repo_url and not accessible_urls:
        print(f"      🔍 No accessible URLs found. Checking for GitHub releases as fallback...")
        releases = check_github_releases(repo_url)
        if releases:
            has_releases = True
            print(f"      ✅ Found {len(releases)} release(s)")
        else:
            print(f"      ℹ️  No GitHub releases found")
    
    # Calculate deployment score
    deployment_score = 0
    
    # Base score for having deployment config (0-30 points)
    if platforms_configured:
        deployment_score += min(30, len(platforms_configured) * 10)
    
    # Score for having URLs in README (0-20 points)
    if readme_urls:
        deployment_score += 20
    
    # Score for accessible URLs (0-50 points)
    if accessible_urls:
        # Full credit if at least one URL is accessible
        deployment_score += 50
        
    # Bonus points for GitHub releases if not already capped (0-20 points)
    if has_releases:
        deployment_score = min(100, deployment_score + 20)
    
    is_deployed = len(platforms_configured) > 0 or len(readme_urls) > 0 or has_releases or len(accessible_urls) > 0
    is_accessible = len(accessible_urls) > 0
    
    print(f"      ✅ Deployment score: {deployment_score}/100")
    
    return {
        "deployment_score": deployment_score,
        "is_deployed": is_deployed,
        "is_accessible": is_accessible,
        "has_releases": has_releases,
        "platforms_configured": platforms_configured,
        "live_urls": accessible_urls,
        "attempted_urls": all_urls,
        "verification_details": verification_details,
        "total_urls_checked": len(all_urls),
        "releases_count": len(releases)
    }
