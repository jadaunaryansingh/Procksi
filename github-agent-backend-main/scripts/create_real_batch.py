"""
Create batch with real team data from Excel file
Run with: python scripts/create_real_batch.py
"""

import sys
import os
from pathlib import Path
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.backend.database import get_supabase_admin_client


def extract_github_repos(row):
    """Extract GitHub repository URLs from a row"""
    repos = []
    for col in row.index:
        val = str(row[col])
        if 'github.com' in val.lower() and val.startswith('http'):
            repos.append(val.strip())
    return repos


def extract_team_members(row):
    """Extract team member names from the row"""
    members = []
    # Process columns looking for names (skip first column which is team ID)
    for i in range(1, min(5, len(row))):
        val = str(row.iloc[i]).strip()
        if val and val != 'nan' and not val.startswith('http') and len(val) > 2:
            # Split by newline or comma
            names = val.replace('\n', ',').split(',')
            for name in names:
                name = name.strip()
                if name and len(name) > 2 and not any(x in name.lower() for x in ['http', 'drive', 'github', 'project']):
                    members.append(name)
            if members:  # If we found names, stop looking
                break
    return members[:4]  # Max 4 members per team


def extract_project_description(row):
    """Extract project description from the row"""
    for col_idx in range(2, min(6, len(row))):
        val = str(row.iloc[col_idx]).strip()
        if val and val != 'nan' and not val.startswith('http') and len(val) > 10:
            return val[:200]  # Limit length
    return None


def read_excel_teams():
    """Read teams from Excel file"""
    excel_path = Path(__file__).parent.parent.parent / "top projects 3rd year.xlsx"
    
    if not excel_path.exists():
        print(f"❌ Excel file not found: {excel_path}")
        print("Please ensure 'top projects 3rd year.xlsx' is in the workspace root")
        return []
    
    print(f"📖 Reading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)
    
    print(f"📊 Found {len(df)} rows in Excel file")
    
    teams = []
    for idx, row in df.iterrows():
        try:
            # Extract team ID from 'Team Number' column
            team_id = str(row.get('Team Number', row.iloc[0])).strip()
            if not team_id or team_id == 'nan' or len(team_id) > 10:
                continue
            
            # Extract project name from 'Project Name' column
            project_name = str(row.get('Project Name', '')).strip()
            if not project_name or project_name == 'nan':
                project_name = extract_project_description(row) or f"Project {team_id}"
            
            # Format team name as "T## - Project Name"
            team_name = f"{team_id} - {project_name}"
            
            # Extract GitHub repos
            github_repos = []
            github_link = str(row.get('Github Link', '')).strip()
            if github_link and github_link != 'nan' and 'github.com' in github_link:
                github_repos.append(github_link)
            
            if not github_repos:
                # Fallback to searching all columns
                github_repos = extract_github_repos(row)
            
            if not github_repos:
                print(f"⚠️  Team {team_id}: No GitHub repo found, skipping")
                continue
            
            # Extract team members from 'Team Name ' column (note the space)
            members = []
            team_members_str = str(row.get('Team Name ', row.get('Team Name', ''))).strip()
            if team_members_str and team_members_str != 'nan':
                # Split by newline
                members = [m.strip() for m in team_members_str.split('\n') if m.strip()]
            
            if not members:
                # Fallback to old extraction method
                members = extract_team_members(row)
            
            if not members:
                members = [f"Student {idx + 1}"]
            
            # Use project name as description
            description = project_name
            
            teams.append({
                "id": team_id,
                "name": team_name,
                "students": members,
                "repo": github_repos[0],
                "description": description
            })
            
        except Exception as e:
            print(f"⚠️  Error processing row {idx}: {e}")
            continue
    
    print(f"✅ Extracted {len(teams)} teams from Excel")
    return teams


# Load teams from Excel
REAL_TEAMS = []  # Will be populated when script runs

def create_real_batch():
    """Create batch with real teams from Excel data"""
    
    # Read teams from Excel first
    teams_data = read_excel_teams()
    
    if not teams_data:
        print("❌ No teams found in Excel file")
        return
    
    supabase = get_supabase_admin_client()
    
    print("\n" + "=" * 80)
    print("Creating Real Data Batch from Excel")
    print("=" * 80)
    
    # Step 1: Create batch
    batch_data = {
        "name": "3rd Year Top Projects 2024",
        "semester": "3rd Sem",
        "year": 2024,
        "start_date": "2024-08-01T00:00:00Z",
        "end_date": "2024-12-31T23:59:59Z",
        "status": "active"
    }
    
    try:
        # Check if batch exists
        existing_batch = supabase.table("batches")\
            .select("id, name")\
            .eq("name", batch_data["name"])\
            .execute()
        
        if existing_batch.data and len(existing_batch.data) > 0:
            batch_id = existing_batch.data[0]["id"]
            print(f"✓ Using existing batch: {batch_data['name']}")
            print(f"  Batch ID: {batch_id}")
        else:
            result = supabase.table("batches").insert(batch_data).execute()
            if result.data and len(result.data) > 0:
                batch_id = result.data[0]["id"]
                print(f"✓ Created batch: {batch_data['name']}")
                print(f"  Batch ID: {batch_id}")
            else:
                print("✗ Failed to create batch")
                return
                
    except Exception as e:
        print(f"✗ Error creating batch: {str(e)}")
        return
    
    # Step 2: Get mentors (optional - we'll leave unassigned)
    print("\n" + "=" * 80)
    print("Creating Teams from Excel Data")
    print("=" * 80)
    
    created_teams = 0
    skipped_teams = 0
    failed_teams = 0
    
    for team_data in teams_data:
        try:
            # Check if team exists
            existing_team = supabase.table("teams")\
                .select("id, team_name")\
                .eq("batch_id", batch_id)\
                .eq("team_name", team_data["name"])\
                .execute()
            
            if existing_team.data and len(existing_team.data) > 0:
                print(f"  ⊙ {team_data['name']} - already exists")
                skipped_teams += 1
                continue
            
            # Create team
            team_insert = {
                "batch_id": batch_id,
                "team_name": team_data["name"],
                "health_status": "on_track",
                "student_count": len(team_data["students"]),
                "status": "active"
            }
            
            result = supabase.table("teams").insert(team_insert).execute()
            
            if result.data and len(result.data) > 0:
                team_id = result.data[0]["id"]
                
                # Create project
                project_insert = {
                    "team_id": team_id,
                    "batch_id": batch_id,
                    "repo_url": team_data["repo"],
                    "status": "pending"
                }
                
                project_result = supabase.table("projects").insert(project_insert).execute()
                
                if project_result.data:
                    project_id = project_result.data[0]["id"]
                    # Update team with project_id
                    supabase.table("teams").update({"project_id": project_id}).eq("id", team_id).execute()
                
                # Create students
                for student_name in team_data["students"]:
                    # Generate email from name
                    email_name = student_name.lower().replace(' ', '.').replace("'", "")
                    student_insert = {
                        "team_id": team_id,
                        "name": student_name,
                        "email": f"{email_name}@student.edu"
                    }
                    try:
                        supabase.table("students").insert(student_insert).execute()
                    except:
                        pass  # Skip if student already exists
                
                print(f"  ✓ {team_data['name']} - {len(team_data['students'])} students")
                created_teams += 1
            else:
                print(f"  ✗ Failed to create {team_data['name']}")
                failed_teams += 1
                
        except Exception as e:
            print(f"  ✗ Error creating {team_data['name']}: {str(e)}")
            failed_teams += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Batch: {batch_data['name']} (ID: {batch_id})")
    print(f"  ✓ Created: {created_teams} teams")
    print(f"  ⊙ Skipped: {skipped_teams} teams (already exist)")
    print(f"  ✗ Failed:  {failed_teams} teams")
    print(f"\nTotal teams in batch: {created_teams + skipped_teams}")
    print("\n" + "=" * 80)
    print("Next steps:")
    print("  1. Navigate to admin panel and select '3rd Year Top Projects 2024'")
    print("  2. Assign mentors to teams via 'Assign Teams' page")
    print("  3. Trigger analysis for teams with repos")
    print("=" * 80)


if __name__ == "__main__":
    create_real_batch()
