
import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase

def check_data():
    supabase = get_supabase()
    
    print("Fetching teams...")
    teams = supabase.table("teams").select("id, team_name, student_count").execute()
    
    if not teams.data:
        print("No teams found.")
        return

    print(f"Found {len(teams.data)} teams.")
    
    for team in teams.data[:5]: # Check first 5 teams
        t_id = team['id']
        name = team['team_name']
        s_count = team['student_count']
        
        print(f"\nChecking Team: {name} (ID: {t_id})")
        print(f"Expected Student Count (from team record): {s_count}")
        
        # specific query for students
        students = supabase.table("students").select("*").eq("team_id", t_id).execute()
        actual_count = len(students.data) if students.data else 0
        
        print(f"Actual Students in DB: {actual_count}")
        if students.data:
            print("Student sample:", students.data[0])
        else:
            print("NO STUDENTS FOUND in 'students' table for this team.")
            
    # Check specific team from error
    error_team_id = "35a3452a-9088-49c9-a1af-1c88cca454b4"
    print(f"\nChecking Error Team ID: {error_team_id}")
    
    # Simple check
    team = supabase.table("teams").select("*").eq("id", error_team_id).execute()
    if team.data:
        print("Team EXISTS in simplified query.")
        print(f"Team Data: {team.data[0]}")
        
        # Check complex query used in API
        try:
            complex_res = supabase.table("teams").select(
                "*, batches(id, name), students(*), projects(*)"
            ).eq("id", error_team_id).execute()
            
            if complex_res.data:
                print("Team EXISTS in complex query.")
                print("Students:", len(complex_res.data[0].get('students', [])))
            else:
                print("Team FAILED in complex query (Empty result).")
        except Exception as e:
            print(f"Complex query FAILED with error: {e}")
            
    else:
        print("Team NOT FOUND in database.")
        

    print("\n--- Checking user_teams Columns ---")
    p = supabase.table("user_teams").select("*").limit(1).execute()
    if p.data:
        print(f"user_teams Keys: {list(p.data[0].keys())}")
    else:
        print("No user_teams found")

if __name__ == "__main__":
    check_data()
