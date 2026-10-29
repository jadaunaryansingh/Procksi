import asyncio
import json
from src.api.backend.database import get_supabase

async def main():
    supabase = get_supabase()
    # Get a project that has analysis result
    response = supabase.table("projects").select("report_json").not_.is_("report_json", "null").limit(1).execute()
    
    if response.data:
        report = response.data[0]["report_json"]
        if isinstance(report, str):
            report = json.loads(report)
            
        # Check commit_details
        commit_details = report.get("commit_details", {})
        print(f"\nCommit Details Keys: {commit_details.keys()}")
        
        # Check forensics
        forensics = report.get("forensics", {})
        print(f"\nForensics Keys: {forensics.keys()}")

        if "all_commits" in commit_details:
             all_commits = commit_details['all_commits']
             print(f"\nFound 'all_commits' in commit_details with {len(all_commits)} items")
             for i in range(min(5, len(all_commits))):
                 c = all_commits[i]
                 print(f"\nCommit {i}:")
                 print(f"  Message: {c.get('message')}")
                 print(f"  Keys: {c.keys()}")
                 files_changed = c.get('files_changed')
                 print(f"  Files Changed: {files_changed}")
                 if isinstance(files_changed, list) and len(files_changed) > 0:
                     print(f"  First File Keys: {files_changed[0].keys()}")

    else:
        print("No project found with report_json")

if __name__ == "__main__":
    asyncio.run(main())
