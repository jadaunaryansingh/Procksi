#!/usr/bin/env python3
"""
Migration Script: Align Project IDs with Team IDs
Moves existing Projects (and related data) to a new UUID that matches their Team UUID.
"""
import sys
import os
import time
from uuid import UUID

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.backend.database import get_supabase_admin_client

def migrate_ids():
    supabase = get_supabase_admin_client()
    print("Fetching teams with projects...")
    
    # 1. Get all teams that have a project_id
    # Note: We need to check if ID mismatch exists
    teams = supabase.table("teams").select("id, team_name, project_id").not_.is_("project_id", "null").execute()
    
    print(f"Found {len(teams.data)} teams linked to projects.")
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    for team in teams.data:
        team_id = team['id']
        old_project_id = team['project_id']
        team_name = team['team_name']
        
        if team_id == old_project_id:
            print(f"SKIPPING: Team {team_name} IDs already matching ({team_id})")
            skipped_count += 1
            continue
            
        print(f"\nMIGRATING: Team {team_name}")
        print(f"  Team ID:      {team_id}")
        print(f"  Old Proj ID:  {old_project_id}")
        
        try:
            # 1. Fetch old project data
            p_res = supabase.table("projects").select("*").eq("id", old_project_id).execute()
            if not p_res.data:
                print("  ERROR: Project not found!")
                error_count += 1
                continue
            old_project = p_res.data[0]
            
            # WORKAROUND: repo_url is likely unique. We must rename old project's repo_url to allow new insert.
            temp_url = f"MIGRATING_{UUID(int=0)}_{old_project.get('repo_url')}"
            print("  Renaming old project repo_url to avoid unique constraint...")
            supabase.table("projects").update({"repo_url": temp_url}).eq("id", old_project_id).execute()
            
            # 2. Create NEW project with ID = Team ID
            # Remove 'id' from dict if present, we want to set it manually
            new_project_data = old_project.copy()
            new_project_data['id'] = team_id
            new_project_data['team_id'] = team_id # Ensure it points to team
            
            # Check if project already exists at destination (idempotency)
            exists_check = supabase.table("projects").select("id").eq("id", team_id).execute()
            if exists_check.data:
                print("  Target project ID already exists! (Partial migration previously?)")
                # Update it
                print("  Updating target project with old data...")
                supabase.table("projects").update(new_project_data).eq("id", team_id).execute()
            else:
                print("  Creating new project record...")
                supabase.table("projects").insert(new_project_data).execute()
            
            # 3. Move Children Items
            print("  Moving related records...")
            
            # A. Analysis Jobs
            supabase.table("analysis_jobs").update({"project_id": team_id}).eq("project_id", old_project_id).execute()
            
            # B. Issues
            supabase.table("issues").update({"project_id": team_id}).eq("project_id", old_project_id).execute()
            
            # C. Tech Stack
            supabase.table("tech_stack").update({"project_id": team_id}).eq("project_id", old_project_id).execute()
            
            # D. Team Members (Analytics)
            supabase.table("team_members").update({"project_id": team_id}).eq("project_id", old_project_id).execute()
            
            # E. Project Comments
            supabase.table("project_comments").update({"project_id": team_id}).eq("project_id", old_project_id).execute()
            
            # 4. Update Team to point to new Project ID
            print("  Updating Team linkage...")
            supabase.table("teams").update({"project_id": team_id}).eq("id", team_id).execute()
            
            # 5. Delete Old Project
            print("  Deleting old project...")
            supabase.table("projects").delete().eq("id", old_project_id).execute()
            
            migrated_count += 1
            print("  SUCCESS.")
            
        except Exception as e:
            print(f"  FAILED: {e}")
            error_count += 1
            
    print("\n" + "="*30)
    print("MIGRATION COMPLETE")
    print(f"Skipped (Aligned): {skipped_count}")
    print(f"Migrated:          {migrated_count}")
    print(f"Errors:            {error_count}")

if __name__ == "__main__":
    migrate_ids()
