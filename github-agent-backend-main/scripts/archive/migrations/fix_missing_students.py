
import asyncio
import os
import sys
import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

EXCEL_FILE = r"d:\Coding\Github-Agent\top projects 3rd Year.xlsx"

def fix_students():
    if not os.path.exists(EXCEL_FILE):
        print(f"File not found: {EXCEL_FILE}")
        return

    supabase = get_supabase_admin_client()
    
    print("Reading Excel file...")
    try:
        df = pd.read_excel(EXCEL_FILE)
    except Exception as e:
        print(f"Failed to read Excel: {e}")
        return

    # Normalize columns
    df.columns = [str(c).strip() for c in df.columns]
    
    # Identify columns
    team_col = next((c for c in df.columns if 'Team Name' in c), None)
    repo_col = next((c for c in df.columns if 'Github' in c), None)
    email_col = next((c for c in df.columns if 'Mail Id' in c), None)
    
    if not team_col or not repo_col:
        print("Required columns (Team Name, Github Link) not found.")
        return

    print(f"Processing {len(df)} rows...")
    
    stats = {"updates": 0, "skipped": 0, "errors": 0}

    for index, row in df.iterrows():
        try:
            team_names_str = str(row[team_col]).strip()
            repo_url = str(row[repo_col]).strip()
            
            if pd.isna(row[team_col]) or not team_names_str:
                continue
                
            # Find team in DB by repo_url (most reliable)
            # Or by team_name (fuzzy due to the extraction logic)
            
            # Let's try finding by repo_url first
            teams_db = supabase.table("teams").select("id, team_name").eq("repo_url", repo_url).execute()
            
            if not teams_db.data:
                # Try by team name? The simplified name might match keys
                # Simplified name logic from teams.py: first line of team_names_str
                simple_name = team_names_str.split('\n')[0].strip()
                teams_db = supabase.table("teams").select("id, team_name").ilike("team_name", simple_name).execute()
            
            if not teams_db.data:
                print(f"Team not found in DB: {team_names_str[:20]}... (Repo: {repo_url})")
                stats["errors"] += 1
                continue
                
            team_id = teams_db.data[0]['id']
            
            # Check if students already exist
            students_exist = supabase.table("students").select("id", count="exact", head=True).eq("team_id", team_id).execute()
            if students_exist.count > 0:
                print(f"Team {teams_db.data[0]['team_name']} already has students. Skipping.")
                stats["skipped"] += 1
                continue

            # Parse students
            names = [n.strip() for n in team_names_str.split('\n') if n.strip()]
            
            emails = []
            if email_col and not pd.isna(row[email_col]):
                email_str = str(row[email_col]).strip()
                if '\n' in email_str:
                    emails = [e.strip() for e in email_str.split('\n') if e.strip()]
                else:
                    emails = [email_str] # Could be single, or maybe comma separated? Assuming newline based on name format.
            
            # Insert students
            students_insert = []
            for i, name in enumerate(names):
                email = emails[i] if i < len(emails) else None
                students_insert.append({
                    "team_id": team_id,
                    "name": name,
                    "email": email
                })
            
            if students_insert:
                supabase.table("students").insert(students_insert).execute()
                print(f"Added {len(students_insert)} students to {teams_db.data[0]['team_name']}")
                stats["updates"] += 1
                
        except Exception as e:
            print(f"Error processing row {index}: {e}")
            stats["errors"] += 1

    print(f"\nCompleted. Updated: {stats['updates']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")

if __name__ == "__main__":
    fix_students()
