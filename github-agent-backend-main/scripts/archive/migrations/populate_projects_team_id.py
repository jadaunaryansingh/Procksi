
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

def populate_projects_team_id():
    """
    Populate projects.team_id by looking up teams.project_id.
    This creates the reverse link so FrontendAdapter can read team_id from projects.
    """
    supabase = get_supabase_admin_client()
    
    print("Fetching ALL teams with project links...")
    teams = supabase.table("teams").select("id, team_name, project_id").execute().data
    print(f"Found {len(teams)} teams.")
    
    # Create reverse lookup: project_id -> team_id
    project_to_team = {t["project_id"]: t["id"] for t in teams if t.get("project_id")}
    print(f"Found {len(project_to_team)} project-to-team mappings.")
    
    print("\nFetching ALL projects...")
    projects = supabase.table("projects").select("id, team_name, team_id").execute().data
    print(f"Found {len(projects)} projects.")
    
    updated_count = 0
    
    for project in projects:
        p_id = project["id"]
        p_name = project.get("team_name", "Unknown")
        current_team_id = project.get("team_id")
        
        # Get the team_id from our reverse lookup
        correct_team_id = project_to_team.get(p_id)
        
        if not correct_team_id:
            print(f"Project '{p_name}' ({p_id}) - No team links to this project")
            continue
            
        if current_team_id == correct_team_id:
            print(f"Project '{p_name}' - Already has correct team_id")
            continue
        
        # Update projects.team_id
        print(f"Project '{p_name}' - Setting team_id to {correct_team_id}")
        try:
            supabase.table("projects").update({"team_id": correct_team_id}).eq("id", p_id).execute()
            print(f"  -> Updated successfully.")
            updated_count += 1
        except Exception as e:
            print(f"  -> FAILED: {e}")
    
    print(f"\nDone. Updated {updated_count} projects.")

if __name__ == "__main__":
    populate_projects_team_id()
