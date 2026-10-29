
import os
import asyncio
from supabase import create_client, Client
from pprint import pprint
import json

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# Configuration from .env
SUPABASE_URL = require_env("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or require_env("SUPABASE_KEY")

async def main():
    print("Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    team_id = "f756df3b-444d-42d2-96ec-4afe31e21ab6"
    
    team_res = supabase.table("teams").select("*").eq("id", team_id).execute()
    if not team_res.data:
        print("Team not found!")
        return
    team = team_res.data[0]
    project_id = team.get("project_id")
    
    if not project_id:
        print("No project associated with this team.")
        return
        
    project_res = supabase.table("projects").select("*").eq("id", project_id).execute()
    if not project_res.data:
        print("Project not found!")
        return
    project = project_res.data[0]
    
    report_json = project.get("report_json")
    
    if report_json:
        data = report_json
        if isinstance(report_json, str):
            try:
                data = json.loads(report_json)
            except:
                print("Failed to parse JSON string")
                return
        
        print("Languages (Direct):", data.get("languages"))
        print("Structure Data:", json.dumps(data.get("structure"), indent=2))
        files = data.get("files", [])
        print("Files Count:", len(files))
        if files:
            print("First 3 files:", json.dumps(files[:3], indent=2))

    else:
        print("report_json is empty")

if __name__ == "__main__":
    asyncio.run(main())
