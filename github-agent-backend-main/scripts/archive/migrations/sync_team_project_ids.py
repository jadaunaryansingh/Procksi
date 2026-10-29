
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

def sync_team_project_ids():
    """
    Sync team.project_id with project.id by matching team_name.
    This ensures that teams.project_id points to the correct project.
    """
    supabase = get_supabase_admin_client()
    
    print("Fetching ALL teams...")
    teams = supabase.table("teams").select("id, team_name, project_id").execute().data
    print(f"Found {len(teams)} teams.")
    
    print("\nFetching ALL projects...")
    projects = supabase.table("projects").select("id, team_name").execute().data
    print(f"Found {len(projects)} projects.")
    
    # Create lookup by team_name
    project_lookup = {p["team_name"].strip().lower(): p["id"] for p in projects if p.get("team_name")}
    
    updated_count = 0
    
    for team in teams:
        t_id = team["id"]
        t_name = team.get("team_name", "")
        current_project_id = team.get("project_id")
        
        # Find matching project
        matching_project_id = project_lookup.get(t_name.strip().lower())
        
        if not matching_project_id:
            print(f"Team '{t_name}' - No matching project found")
            continue
            
        if current_project_id == matching_project_id:
            print(f"Team '{t_name}' - Already linked to project {matching_project_id}")
            continue
        
        # Update team.project_id
        print(f"Team '{t_name}' - Linking to project {matching_project_id}")
        try:
            supabase.table("teams").update({"project_id": matching_project_id}).eq("id", t_id).execute()
            print(f"  -> Updated successfully.")
            updated_count += 1
        except Exception as e:
            print(f"  -> FAILED: {e}")
    
    print(f"\nDone. Updated {updated_count} teams.")

if __name__ == "__main__":
    sync_team_project_ids()
