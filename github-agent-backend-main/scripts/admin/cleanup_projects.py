import os
import sys
# Add current directory to path
sys.path.append(os.getcwd())

from src.api.backend.database import get_supabase_admin_client

def cleanup_orphaned_projects():
    supabase = get_supabase_admin_client()
    print("🚀 Starting Database Cleanup...")

    # 1. Get all teams with valid batch_ids
    # Actually, easier to get teams with NULL batch_id
    # But Supabase filter 'is' null might be tricky in some clients, let's fetch all and filter in python for safety/clarity
    
    # Fetch all teams
    teams = supabase.table('teams').select('id, team_name, batch_id').execute()
    all_teams = teams.data
    
    orphaned_team_ids = set()
    valid_team_ids = set()
    
    for team in all_teams:
        if not team.get('batch_id'):
            orphaned_team_ids.add(team['id'])
        else:
            valid_team_ids.add(team['id'])
            
    print(f"Found {len(orphaned_team_ids)} teams without batch_id")
    print(f"Found {len(valid_team_ids)} valid teams")

    # 2. Get all projects
    projects = supabase.table('projects').select('id, team_id, repo_url').execute()
    all_projects = projects.data
    
    projects_to_delete = []
    
    for project in all_projects:
        team_id = project.get('team_id')
        
        # Condition 1: Project has no team
        if not team_id:
            projects_to_delete.append(project)
            continue
            
        # Condition 2: Project's team is orphaned (no batch_id)
        if team_id in orphaned_team_ids:
            projects_to_delete.append(project)
            continue
            
        # Condition 3: Project's team doesn't exist in teams table (integrity error)
        if team_id not in valid_team_ids and team_id not in orphaned_team_ids:
             projects_to_delete.append(project)

    print(f"found {len(projects_to_delete)} projects to delete")

    if not projects_to_delete:
        print("✅ No orphaned projects found.")
        return

    # 3. Perform Deletion
    # We must handle dependencies manually due to FK constraints
    project_ids_to_del = [p['id'] for p in projects_to_delete]
    
    print(f"Deleting {len(project_ids_to_del)} projects and their dependencies...")
    
    count_jobs = 0
    count_projects = 0
    
    for pid in project_ids_to_del:
        try:
            # 1. Delete Tech Stack
            supabase.table('tech_stack').delete().eq('project_id', pid).execute()
            
            # 2. Delete Issues
            supabase.table('issues').delete().eq('project_id', pid).execute()
            
            # 3. Delete Team Members
            supabase.table('team_members').delete().eq('project_id', pid).execute()
            
            # 4. Delete Analysis Jobs
            res_jobs = supabase.table('analysis_jobs').delete().eq('project_id', pid).execute()
            count_jobs += len(res_jobs.data) if res_jobs.data else 0
            
            # 5. Unlink Project from Teams (Set project_id to NULL)
            supabase.table('teams').update({'project_id': None}).eq('project_id', pid).execute()
            
            # 6. Delete Project
            res_proj = supabase.table('projects').delete().eq('id', pid).execute()
            
            if res_proj.data:
                count_projects += 1
                print(f"  ✅ Deleted project {pid}")
            else:
                print(f"  ⚠️  Failed to delete project {pid} (row not found?)")
                
        except Exception as e:
            print(f"  ❌ Error deleting project {pid}: {e}")

    print(f"✅ Cleanup Complete.")
    print(f"  - Deleted {count_jobs} analysis jobs")
    print(f"  - Deleted {count_projects} projects")

    # Optional: Delete the orphaned teams without projects?
    # User only asked to remove PROJECTS. I won't touch teams to be safe, unless explicit.
    # The request was "remove project from database which doesnt have batch id".

if __name__ == "__main__":
    try:
        cleanup_orphaned_projects()
    except Exception as e:
        print(f"Error: {e}")
