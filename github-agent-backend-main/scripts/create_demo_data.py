"""
Create complete demo data: batch + teams with repos + mentor assignments
Run with: python scripts/create_demo_data.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.backend.database import get_supabase_admin_client


# Demo teams with repo URLs
DEMO_TEAMS = [
    {"name": "Team Alpha", "repo": "https://github.com/facebook/react", "mentor": "drsmith@university.edu"},
    {"name": "Team Beta", "repo": "https://github.com/vuejs/core", "mentor": "drsmith@university.edu"},
    {"name": "Team Gamma", "repo": "https://github.com/angular/angular", "mentor": "profjohnson@university.edu"},
    {"name": "Team Delta", "repo": "https://github.com/sveltejs/svelte", "mentor": "profjohnson@university.edu"},
    {"name": "Team Epsilon", "repo": "https://github.com/solidjs/solid", "mentor": "drwilliams@university.edu"},
]


def create_demo_batch():
    """Create demo batch with teams"""
    supabase = get_supabase_admin_client()
    
    print("Creating demo batch and teams...")
    print("=" * 60)
    
    # Step 1: Create batch
    batch_data = {
        "name": "4th Semester 2024",
        "semester": "4th Sem",
        "year": 2024,
        "start_date": "2024-01-15T00:00:00Z",
        "end_date": "2024-05-30T23:59:59Z",
        "status": "active"
    }
    
    try:
        # Check if batch exists
        existing_batch = supabase.table("batches")\
            .select("id, name")\
            .eq("semester", batch_data["semester"])\
            .eq("year", batch_data["year"])\
            .execute()
        
        if existing_batch.data and len(existing_batch.data) > 0:
            batch_id = existing_batch.data[0]["id"]
            print(f"✓ Using existing batch: {batch_data['name']} (ID: {batch_id})")
        else:
            result = supabase.table("batches").insert(batch_data).execute()
            if result.data and len(result.data) > 0:
                batch_id = result.data[0]["id"]
                print(f"✓ Created batch: {batch_data['name']} (ID: {batch_id})")
            else:
                print("✗ Failed to create batch")
                return
                
    except Exception as e:
        print(f"✗ Error creating batch: {str(e)}")
        return
    
    # Step 2: Get mentor IDs
    mentor_map = {}
    try:
        mentors = supabase.table("users")\
            .select("id, email")\
            .eq("role", "mentor")\
            .execute()
        
        if mentors.data:
            for m in mentors.data:
                mentor_map[m["email"]] = m["id"]
            print(f"\n✓ Found {len(mentor_map)} mentors")
        else:
            print("\n⚠️  No mentors found. Run seed_mentors.py first!")
            
    except Exception as e:
        print(f"\n✗ Error fetching mentors: {str(e)}")
    
    # Step 3: Create teams with repos and mentor assignments
    print("\nCreating teams...")
    print("-" * 60)
    
    created_teams = 0
    for team_data in DEMO_TEAMS:
        try:
            # Check if team exists
            existing_team = supabase.table("teams")\
                .select("id")\
                .eq("batch_id", batch_id)\
                .eq("team_name", team_data["name"])\
                .execute()
            
            if existing_team.data and len(existing_team.data) > 0:
                print(f"  • {team_data['name']} - already exists")
                continue
            
            # Get mentor ID
            mentor_id = mentor_map.get(team_data["mentor"])
            
            # Create team
            team_insert = {
                "batch_id": batch_id,
                "team_name": team_data["name"],
                "repo_url": team_data["repo"],
                "mentor_id": mentor_id,
                "health_status": "on_track"
            }
            
            result = supabase.table("teams").insert(team_insert).execute()
            
            if result.data:
                mentor_name = team_data["mentor"].split('@')[0]
                print(f"  ✓ {team_data['name']} → {mentor_name}")
                created_teams += 1
            else:
                print(f"  ✗ Failed to create {team_data['name']}")
                
        except Exception as e:
            print(f"  ✗ Error creating {team_data['name']}: {str(e)}")
    
    print("-" * 60)
    print(f"\nCreated {created_teams} teams")
    
    # Step 4: Summary
    print("\n" + "=" * 60)
    print("DEMO DATA SUMMARY")
    print("=" * 60)
    
    try:
        # Get batch info
        batch_info = supabase.table("batches")\
            .select("*")\
            .eq("id", batch_id)\
            .execute()
        
        if batch_info.data:
            b = batch_info.data[0]
            print(f"\nBatch: {b['name']}")
            print(f"  ID: {b['id']}")
            print(f"  Status: {b['status']}")
            print(f"  Teams: {b.get('team_count', 0)}")
        
        # Get teams
        teams_info = supabase.table("teams")\
            .select("team_name, repo_url, mentor_id")\
            .eq("batch_id", batch_id)\
            .execute()
        
        if teams_info.data:
            print(f"\nTeams ({len(teams_info.data)}):")
            for t in teams_info.data:
                mentor_email = "unassigned"
                if t.get("mentor_id"):
                    for email, mid in mentor_map.items():
                        if mid == t["mentor_id"]:
                            mentor_email = email.split('@')[0]
                            break
                print(f"  • {t['team_name']} - {mentor_email}")
        
        # Mentor distribution
        print(f"\nMentor Distribution:")
        for mentor_email, mentor_id in mentor_map.items():
            team_count = sum(1 for t in teams_info.data if t.get("mentor_id") == mentor_id)
            name = mentor_email.split('@')[0]
            print(f"  • {name}: {team_count} teams")
            
    except Exception as e:
        print(f"\nError fetching summary: {str(e)}")
    
    print("\n" + "=" * 60)
    print("\nNext steps:")
    print("  1. Verify data in Supabase dashboard")
    print("  2. Run migration: 002_add_weekly_analysis.sql")
    print("  3. Test batch analysis trigger")
    print("=" * 60)


if __name__ == "__main__":
    create_demo_batch()
