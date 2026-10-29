
import asyncio
import json
import os
import httpx
from typing import Dict, List, Any

from supabase import create_client, Client

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# Configuration
SUPABASE_URL = require_env("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or require_env("SUPABASE_KEY")
GITHUB_TOKEN = os.getenv("GH_API_KEY") or require_env("GITHUB_TOKEN")

def get_repo_path(url: str) -> str:
    """Extract owner/repo from URL"""
    if not url:
        return None
    cleaned = url.rstrip("/").replace(".git", "")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return None

async def fetch_github_languages(repo_path: str) -> Dict[str, float]:
    """Fetch languages from GitHub and calculate percentages"""
    async with httpx.AsyncClient() as client:
        try:
            print(f"Fetching languages for {repo_path}...")
            response = await client.get(
                f"https://api.github.com/repos/{repo_path}/languages",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if response.status_code != 200:
                print(f"GitHub API error: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            total_bytes = sum(data.values())
            
            if total_bytes == 0:
                return {}
                
            breakdown = {}
            for lang, bytes_count in data.items():
                percentage = round((bytes_count / total_bytes) * 100, 2)
                breakdown[lang] = percentage
                
            return breakdown
            
        except Exception as e:
            print(f"Request failed: {e}")
            return None

async def backfill_languages():
    print("Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Fetching projects...")
    response = supabase.table("projects").select("*").execute()
    projects = response.data
    
    updated_count = 0
    
    for project in projects:
        project_id = project["id"]
        report_json = project.get("report_json")
        repo_url = project.get("repo_url")
        
        if not report_json:
            print(f"Project {project_id}: No report_json")
            continue
            
        # Parse if string
        if isinstance(report_json, str):
            try:
                report_json = json.loads(report_json)
            except:
                print(f"Project {project_id}: Failed to parse report_json")
                continue
        
        # FORCE UPDATE for GitHub extraction
        # if "languages" not in report_json or not report_json["languages"]:
        if True:
            print(f"Project {project_id}: Fetching from GitHub...")
            
            repo_path = get_repo_path(repo_url)
            if not repo_path:
                print(f"Project {project_id}: Invalid repo URL {repo_url}")
                continue
                
            breakdown = await fetch_github_languages(repo_path)
            
            if breakdown:
                report_json["languages"] = breakdown
                print(f"Project {project_id}: Fetched languages: {breakdown}")
                
                try:
                    supabase.table("projects").update({"report_json": report_json}).eq("id", project_id).execute()
                    print(f"Project {project_id}: Updated successfully.")
                    updated_count += 1
                except Exception as e:
                    print(f"Project {project_id}: Update failed: {e}")
            else:
                print(f"Project {project_id}: Could not fetch languages from GitHub.")

    print(f"Backfill complete. Updated {updated_count} projects.")

if __name__ == "__main__":
    asyncio.run(backfill_languages())
