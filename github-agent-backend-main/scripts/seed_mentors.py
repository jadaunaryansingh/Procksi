"""
Seed mentor accounts for the semester
Run once before batch creation: python scripts/seed_mentors.py
"""

import sys
import os
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.backend.database import get_supabase_admin_client

# Pre-defined mentors for the semester
MENTORS = [
    {
        "email": "drsmith@university.edu",
        "full_name": "Dr. John Smith",
        "max_teams": 5,
        "department": "Computer Science"
    },
    {
        "email": "profjohnson@university.edu",
        "full_name": "Prof. Sarah Johnson",
        "max_teams": 5,
        "department": "Computer Science"
    },
    {
        "email": "drwilliams@university.edu",
        "full_name": "Dr. Michael Williams",
        "max_teams": 5,
        "department": "Software Engineering"
    },
    {
        "email": "profbrown@university.edu",
        "full_name": "Prof. Emily Brown",
        "max_teams": 5,
        "department": "Information Technology"
    }
]


def seed_mentors():
    """Create/update mentor accounts in database"""
    supabase = get_supabase_admin_client()
    default_password = os.getenv("MENTOR_DEFAULT_PASSWORD")
    if not default_password:
        raise RuntimeError("Missing required env var: MENTOR_DEFAULT_PASSWORD")
    
    print("Seeding mentors...")
    print("=" * 60)
    
    created_count = 0
    updated_count = 0
    
    for mentor_data in MENTORS:
        try:
            # Check if user exists in public users table
            existing = supabase.table("users")\
                .select("id, email, role")\
                .eq("email", mentor_data["email"])\
                .execute()
            
            if existing.data and len(existing.data) > 0:
                # Update existing user's mentor metadata
                user_id = existing.data[0]["id"]
                supabase.table("users")\
                    .update({
                        "role": "mentor",
                        "full_name": mentor_data["full_name"],
                        "max_teams": mentor_data["max_teams"],
                        "department": mentor_data["department"]
                    })\
                    .eq("id", user_id)\
                    .execute()
                
                print(f"✓ Updated: {mentor_data['full_name']} ({mentor_data['email']})")
                updated_count += 1
            else:
                # Create auth user first with a default password (they should change it)
                try:
                    # Use Supabase Admin Auth API to create user
                    auth_response = supabase.auth.admin.create_user({
                        "email": mentor_data["email"],
                        "password": default_password,
                        "email_confirm": True,  # Auto-confirm email
                        "user_metadata": {
                            "full_name": mentor_data["full_name"],
                            "role": "mentor"
                        }
                    })
                    
                    if hasattr(auth_response, 'user') and auth_response.user:
                        auth_user_id = auth_response.user.id
                        
                        # Now create the corresponding public users table entry
                        user_data = {
                            "id": auth_user_id,  # Use auth user's UUID
                            "email": mentor_data["email"],
                            "full_name": mentor_data["full_name"],
                            "role": "mentor",
                            "max_teams": mentor_data["max_teams"],
                            "department": mentor_data["department"]
                        }
                        
                        result = supabase.table("users").insert(user_data).execute()
                        
                        if result.data:
                            print(f"✓ Created: {mentor_data['full_name']} ({mentor_data['email']})")
                            created_count += 1
                        else:
                            print(f"✗ Failed to create users table entry for: {mentor_data['email']}")
                    else:
                        print(f"✗ Auth user creation failed for: {mentor_data['email']}")
                        
                except Exception as auth_err:
                    # Check if user already exists in auth but not in public users
                    error_str = str(auth_err)
                    if "already been registered" in error_str or "already exists" in error_str:
                        print(f"⚠ Auth user exists but not in users table: {mentor_data['email']}")
                        print(f"  Please create the users table entry manually or delete the auth user first.")
                    else:
                        raise auth_err
                    
        except Exception as e:
            print(f"✗ Error processing {mentor_data['email']}: {str(e)}")
    
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  Created: {created_count}")
    print(f"  Updated: {updated_count}")
    print(f"  Total mentors: {len(MENTORS)}")
    
    # List all mentors
    print(f"\nAll mentors in database:")
    try:
        all_mentors = supabase.table("users")\
            .select("email, full_name, department, max_teams, role")\
            .eq("role", "mentor")\
            .execute()
        
        if all_mentors.data:
            for m in all_mentors.data:
                print(f"  • {m['full_name']} ({m['email']}) - {m['department']} - Max: {m['max_teams']} teams")
        else:
            print("  No mentors found")
    except Exception as e:
        print(f"  Error fetching mentors: {str(e)}")


if __name__ == "__main__":
    seed_mentors()
