#!/usr/bin/env python3
"""
Set a user's role to admin in Supabase (auth + public users table).
Usage: python scripts/set_admin_role.py <email>
"""
import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.backend.database import get_supabase_admin_client

load_dotenv()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_admin_role.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    supabase = get_supabase_admin_client()

    # Lookup user in public users table
    user_resp = supabase.table("users").select("id, email, role").ilike("email", email).execute()
    if not user_resp.data:
        print(f"User not found in users table for email: {email}")
        sys.exit(1)

    user = user_resp.data[0]
    user_id = user["id"]

    # Update auth metadata (app_metadata + user_metadata)
    try:
        supabase.auth.admin.update_user_by_id(user_id, {
            "app_metadata": {"role": "admin"},
            "user_metadata": {"role": "admin"}
        })
        print(f"Updated auth metadata for {email} -> admin")
    except Exception as e:
        print(f"Failed to update auth metadata: {e}")
        sys.exit(1)

    # Update public users table role
    try:
        supabase.table("users").update({"role": "admin"}).eq("id", user_id).execute()
        print(f"Updated users table role for {email} -> admin")
    except Exception as e:
        print(f"Failed to update users table role: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
