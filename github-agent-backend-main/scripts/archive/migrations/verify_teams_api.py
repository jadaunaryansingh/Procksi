
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

def verify_list_teams():
    """
    Verify that listing teams with projects!projects_teams_fk join works
    """
    supabase = get_supabase_admin_client()
    
    print("Testing list_teams query...")
    try:
        query = supabase.table("teams").select(
            """
            *,
            batches!inner(id, name, semester, year),
            students(count),
            projects!projects_teams_fk(id, total_score, status, last_analyzed_at),
            team_members:projects!projects_teams_fk(team_members(count))
            """
        )
        
        # Add basic pagination
        query = query.range(0, 9)
        
        response = query.execute()
        
        teams = response.data
        print(f"SUCCESS: Fetched {len(teams)} teams.")
        
        if teams:
            t = teams[0]
            print(f"Sample Team: {t.get('team_name')}")
            print(f"Project Data: {t.get('projects')}")
            
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    verify_list_teams()
