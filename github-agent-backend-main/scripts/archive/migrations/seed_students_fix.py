
import asyncio
import os
import sys
import random

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase

FAKE_NAMES = [
    "Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Prince", "Evan Wright",
    "Fiona Green", "George King", "Hannah White", "Ian Black", "Julia Roberts"
]

def seed_students():
    supabase = get_supabase()
    
    print("Fetching teams...")
    teams = supabase.table("teams").select("id, team_name").execute()
    
    if not teams.data:
        print("No teams found. Cannot seed students.")
        return

    print(f"Found {len(teams.data)} teams. Seeding students if missing...")
    
    total_added = 0
    
    for team in teams.data:
        t_id = team['id']
        name = team['team_name']
        
        # Check if students exist
        existing = supabase.table("students").select("id").eq("team_id", t_id).execute()
        
        if existing.data and len(existing.data) > 0:
            print(f"Team {name} already has {len(existing.data)} students. Skipping.")
            continue
            
        print(f"Seeding students for {name}...")
        
        # Create 2-3 random students
        num_students = random.randint(2, 3)
        students_to_add = []
        
        for i in range(num_students):
            student_name = random.choice(FAKE_NAMES)
            email = f"{student_name.lower().replace(' ', '.')}@example.com"
            
            students_to_add.append({
                "team_id": t_id,
                "name": student_name,
                "email": email,
                "github_username": student_name.replace(" ", "")
            })
            
        try:
            supabase.table("students").insert(students_to_add).execute()
            print(f"  -> Added {num_students} students.")
            total_added += num_students
        except Exception as e:
            print(f"  -> Failed to add students: {str(e)}")

    print(f"\nSeeding complete. Added {total_added} total students.")

if __name__ == "__main__":
    seed_students()
