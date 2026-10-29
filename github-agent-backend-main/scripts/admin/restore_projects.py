import os
import sys
import pandas as pd
from uuid import uuid4

# Add current directory to path
sys.path.append(os.getcwd())

from src.api.backend.database import get_supabase_admin_client

def restore_projects():
    supabase = get_supabase_admin_client()
    print("🚀 Starting Project Restoration...")

    # 1. Read Excel
    try:
        df = pd.read_excel('projects.xlsx')
        # Fill NaN with empty string to avoid errors
        df = df.fillna('')
        print(f"📄 Loaded Excel with {len(df)} rows.")
        print(f"    Columns: {df.columns.tolist()}")
    except Exception as e:
        print(f"❌ Failed to read Excel: {e}")
        return

    # 2. Fetch Existing Teams
    # We need to match Excel rows to DB teams.
    # DB Team Format observed: "T18 - Voice Cloning & Personalized Speech Synthesis"
    teams_result = supabase.table('teams').select('id, team_name').execute()
    db_teams = teams_result.data
    
    # Create a lookup map for faster access
    # Map: "T18" -> team_obj
    team_map = {} 
    for t in db_teams:
        name = t['team_name'] 
        if " - " in name:
            t_num = name.split(" - ")[0].strip()
            team_map[t_num] = t
            
    print(f"🔍 Found {len(db_teams)} teams in DB. Mapped {len(team_map)} by T-number.")
    print(f"    Sample Map Keys: {list(team_map.keys())[:5]}")

    restored_count = 0
    skipped_count = 0
    
    for index, row in df.iterrows():
        # Clean keys by stripping
        row_data = {k.strip(): v for k, v in row.items()}
        
        t_num = str(row_data.get('Team Number', '')).strip()
        repo_url = str(row_data.get('Github Repo', '')).strip()
        
        # Fallback: search for github.com in any column if main column is empty
        if not repo_url or "github.com" not in repo_url:
            for k, v in row_data.items():
                val = str(v).strip()
                if "github.com" in val:
                    repo_url = val
                    print(f"    Found repo in '{k}': {repo_url}")
                    break
        
        # Debug output for first few rows
        if index < 3:
             print(f"    Row {index}: t_num='{t_num}', repo='{repo_url}'")
        
        if not t_num or not repo_url or repo_url.lower() == 'nan':
            # print(f"⚠️  Skipping Row {index}: Missing Team Num or Repo URL")
            skipped_count += 1
            continue
        
        if not t_num or not repo_url or repo_url.lower() == 'nan':
            # print(f"⚠️  Skipping Row {index}: Missing Team Num or Repo URL")
            skipped_count += 1
            continue
            
        # Find team
        team = team_map.get(t_num)
        
        if not team:
            print(f"⚠️  Skipping '{t_num}': Team not found in DB keys")
            skipped_count += 1
            continue
            
        # Check if repo link is valid (basic check)
        if "github.com" not in repo_url:
             print(f"⚠️  Skipping {t_num}: Invalid Repo URL '{repo_url}'")
             skipped_count += 1
             continue
             
        # Create Project
        # Check if project already exists for this team?
        # The user said "u removed 18 project", so they are likely gone.
        # But let's check if team['project_id'] is None (it should be after my cleanup)
        
        # Insert Project
        new_project_id = str(uuid4())
        project_data = {
            "id": new_project_id,
            "repo_url": repo_url,
            "team_name": team['team_name'],
            "status": "pending",
            "created_at": "now()"
        }
        
        try:
            # Insert project
            res_proj = supabase.table('projects').insert(project_data).execute()
            
            if res_proj.data:
                # Update Team with project_id
                supabase.table('teams').update({'project_id': new_project_id}).eq('id', team['id']).execute()
                print(f"✅ Restored {t_num}: Linked to {repo_url}")
                restored_count += 1
            else:
                 print(f"❌ Failed to insert project for {t_num}")

        except Exception as e:
            print(f"❌ Error restoring {t_num}: {e}")
            
    print(f"\n🎉 Restoration Complete.")
    print(f"  - Restored: {restored_count}")
    print(f"  - Skipped: {skipped_count}")

if __name__ == "__main__":
    restore_projects()
