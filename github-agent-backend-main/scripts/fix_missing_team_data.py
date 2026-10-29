"""
Fix missing team data (repo URLs, projects, and team members)
This script updates existing teams with missing repo URLs and creates projects/members
Run with: python scripts/fix_missing_team_data.py
"""

import sys
import os
from pathlib import Path
import pandas as pd
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.backend.database import get_supabase_admin_client


def main():
    """Fix missing team data from Excel file"""
    excel_path = Path(__file__).parent.parent.parent / "top projects 3rd year.xlsx"
    
    if not excel_path.exists():
        print(f"❌ Excel file not found: {excel_path}")
        return
    
    print("Reading Excel file...")
    df = pd.read_excel(excel_path)
    
    print(f"Found {len(df)} rows in Excel\n")
    print("Columns:", df.columns.tolist())
    print()
    
    supabase = get_supabase_admin_client()
    
    # Get the batch
    batch_response = supabase.table("batches")\
        .select("id, name")\
        .eq("name", "3rd Year Top Projects 2024")\
        .execute()
    
    if not batch_response.data:
        print("❌ Batch '3rd Year Top Projects 2024' not found")
        return
    
    batch_id = batch_response.data[0]["id"]
    print(f"Found batch: {batch_response.data[0]['name']}")
    print(f"  Batch ID: {batch_id}\n")
    
    # Get all teams in batch
    teams_response = supabase.table("teams")\
        .select("id, team_name, repo_url, project_id")\
        .eq("batch_id", batch_id)\
        .execute()
    
    if not teams_response.data:
        print("❌ No teams found in batch")
        return
    
    print(f"Found {len(teams_response.data)} teams in database\n")
    print("=" * 80)
    
    # Build mapping from team number to Excel row data
    excel_data = {}
    for idx, row in df.iterrows():
        try:
            team_num = str(row.get('Team Number', row.iloc[0])).strip()
            team_name_cell = str(row.get('Team Name', '')).strip()
            github_link = str(row.get('Github Link', '')).strip()
            
            if team_num and team_num != 'nan':
                # Extract member names from team name cell
                member_names = []
                if '\n' in team_name_cell:
                    member_names = [name.strip() for name in team_name_cell.split('\n') if name.strip()]
                elif team_name_cell and team_name_cell != 'nan':
                    member_names = [team_name_cell]
                
                excel_data[team_num] = {
                    'team_number': team_num,
                    'members': member_names,
                    'github_link': github_link if github_link and github_link != 'nan' else None
                }
        except Exception as e:
            print(f"⚠ Error processing row {idx}: {e}")
            continue
    
    print(f"Extracted data for {len(excel_data)} teams from Excel\n")
    
    updated_count = 0
    created_projects = 0
    created_members = 0
    skipped_count = 0
    errors = []
    
    # Update each team
    for team in teams_response.data:
        team_name = team["team_name"]
        team_id = team["id"]
        current_repo = team.get("repo_url")
        current_project = team.get("project_id")
        
        # Extract team number (T18, T03, etc.)
        team_number = None
        if team_name.startswith("T") and " - " in team_name:
            team_number = team_name.split(" - ")[0].strip()
        elif team_name.startswith("Team T"):
            team_number = team_name.split()[1].split(" -")[0]
        
        if not team_number or team_number not in excel_data:
            print(f"  ⊙ SKIP: {team_name} - No Excel data found")
            skipped_count += 1
            continue
        
        excel_row = excel_data[team_number]
        repo_url = excel_row['github_link']
        member_names = excel_row['members']
        
        try:
            # Update repo_url if missing
            if not current_repo and repo_url:
                print(f"\n📝 {team_name}")
                print(f"  ➜ Setting repo URL: {repo_url}")
                
                supabase.table("teams").update({
                    "repo_url": repo_url
                }).eq("id", team_id).execute()
                
                updated_count += 1
            
            # Create project if missing
            if not current_project and repo_url:
                print(f"  ➜ Creating project...")
                
                # Generate UUID for project
                project_id = str(uuid.uuid4())
                
                # Note: Don't include team_id - there's a broken FK constraint
                # Projects will be linked via teams.project_id instead
                project_insert = {
                    "id": project_id,
                    "batch_id": batch_id,
                    "repo_url": repo_url,
                    "team_name": team_name,
                    "status": "pending"
                }
                
                project_response = supabase.table("projects").insert(project_insert).execute()
                
                if project_response.data:
                    # Use the project_id we generated
                    
                    # Update team with project_id
                    supabase.table("teams").update({
                        "project_id": project_id
                    }).eq("id", team_id).execute()
                    
                    created_projects += 1
                    print(f"  ✓ Created project: {project_id}")
                    
                    # Create team members
                    if member_names:
                        print(f"  ➜ Creating {len(member_names)} team members...")
                        
                        for member_name in member_names:
                            member_insert = {
                                "project_id": project_id,
                                "name": member_name,
                                "commits": 0,
                                "contribution_pct": 0.0
                            }
                            supabase.table("team_members").insert(member_insert).execute()
                            created_members += 1
                        
                        print(f"  ✓ Created {len(member_names)} members")
            
            elif not repo_url:
                print(f"  ⚠ {team_name} - No GitHub link in Excel")
                skipped_count += 1
            else:
                print(f"  ✓ {team_name} - Already complete")
                skipped_count += 1
        
        except Exception as e:
            error_msg = f"{team_name}: {str(e)}"
            errors.append(error_msg)
            print(f"  ❌ ERROR: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Teams updated with repo URLs: {updated_count}")
    print(f"  Projects created: {created_projects}")
    print(f"  Team members created: {created_members}")
    print(f"  Skipped (already complete or no data): {skipped_count}")
    print(f"  Errors: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
