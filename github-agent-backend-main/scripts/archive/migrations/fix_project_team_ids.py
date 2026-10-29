
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

def fix_project_ids():
    supabase = get_supabase_admin_client()
    print("Fetching ALL teams...")
    teams = supabase.table("teams").select("id, team_name").execute().data
    print(f"Found {len(teams)} teams.")
    
    print("\nFetching ALL projects to find users...")
    projects_users = supabase.table("projects").select("team_name, submitted_by").execute().data
    team_to_user = {p["team_name"]: p["submitted_by"] for p in projects_users if p.get("submitted_by")}
    
    # Fallback user
    fallback_user_id = None
    try:
        users = supabase.auth.admin.list_users()
        if users:
            fallback_user_id = users[0].id
            print(f"Found fallback user ID: {fallback_user_id}")
        else:
            print("No users found in auth!")
    except Exception as e:
        print(f"Error fetching users: {e}")
            
    print(f"Found {len(team_to_user)} project owners.")
    
    updated_count = 0
    try:
        ut = supabase.table("user_teams").select("*").limit(1).execute()
        if ut.data:
            print(f"user_teams Keys: {list(ut.data[0].keys())}")
        else:
            print("user_teams table is empty")
            
    except Exception as e:
        print(f"Error reading user_teams: {e}")
        
    updated_count = 0
    
    print("\n--- Populating user_teams (Bridge) ---")
    for team in teams:
        t_id = team["id"]
        t_name = team["team_name"]
        
        # Try to insert into user_teams to satisfy FK
        try:
            # Check if exists first
            exists = supabase.table("user_teams").select("id").eq("id", t_id).execute()
            if not exists.data:
                # Find owner
                owner_id = team_to_user.get(t_name)
                
                # Use fallback if no owner found
                if not owner_id and fallback_user_id:
                    owner_id = fallback_user_id
                    
                if not owner_id:
                     print(f"Skipping bridge for {t_name} - No owner found (and no fallback)")
                     continue

                payload = {
                    "id": t_id,
                    "created_by": owner_id,
                }

                try:
                    supabase.table("user_teams").insert(payload).execute()
                    print(f"Inserted bridge record for {t_name}")
                except Exception as e:
                    print(f"FAILED to insert bridge for {t_name}: {e}")
        except Exception as e:
            print(f"Error checking/inserting bridge: {e}")

    print("\n--- Updating Projects ---")
    
    print("Fetching ALL projects...")
    projects = supabase.table("projects").select("id, team_name, team_id").execute().data
    print(f"Found {len(projects)} projects.")
    
    for project in projects:
        p_name = project.get("team_name")
        p_id = project.get("id")
        current_team_id = project.get("team_id")
        
        if current_team_id:
            print(f"Project '{p_name}' already has team_id: {current_team_id} - Skipping")
            continue
            
        print(f"Project '{p_name}' (ID: {p_id}) missing team_id. Searching...")
        
        # Find matching team
        matched_team = None
        for team in teams:
            # Match strictly on name
            if team["team_name"].strip().lower() == p_name.strip().lower():
                matched_team = team
                break
        
        if matched_team:
            print(f"  -> Found match! Team ID: {matched_team['id']}")
            try:
                supabase.table("projects").update({"team_id": matched_team['id']}).eq("id", p_id).execute()
                print("  -> Updated successfully.")
                updated_count += 1
            except Exception as e:
                print(f"  -> FAILED to update: {e}")
        else:
            print(f"  -> NO MATCH found for '{p_name}'")

    print(f"\nDone. Updated {updated_count} projects.")

if __name__ == "__main__":
    fix_project_ids()
