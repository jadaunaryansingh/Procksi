
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'proj-github agent'))

from src.api.backend.database import get_supabase_admin_client

def check_t18():
    supabase = get_supabase_admin_client()
    print("Finding T18...")
    t18 = supabase.table("teams").select("id, team_name").ilike("team_name", "T18%").execute()
    if t18.data:
        print(f"ID: {t18.data[0]['id']}")
        print(f"Name: {t18.data[0]['team_name']}")
    else:
        print("T18 NOT FOUND")

if __name__ == "__main__":
    check_t18()
