#!/usr/bin/env python3
"""
Helper script to set admin role for a user in Supabase.
Usage: python set_admin_role.py <email>
"""
import sys
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def set_admin_role(email: str):
    """Set admin role for a user by email"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return False
    
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    try:
        # Find user by email
        print(f"🔍 Looking for user with email: {email}")
        response = supabase.table("users").select("*").eq("email", email).execute()
        
        if not response.data:
            print(f"❌ User not found with email: {email}")
            print("\n💡 The user needs to sign in at least once to be created in the database.")
            return False
        
        user = response.data[0]
        user_id = user["id"]
        current_role = user.get("role", "none")
        
        print(f"✅ Found user: {email}")
        print(f"   Current role: {current_role}")
        
        if current_role == "admin":
            print("✅ User is already an admin!")
            return True
        
        # Update role to admin
        print(f"🔧 Updating role to admin...")
        update_response = supabase.table("users").update({
            "role": "admin"
        }).eq("id", user_id).execute()
        
        if update_response.data:
            print("✅ Successfully updated role to admin!")
            print(f"\n📝 Updated user:")
            print(f"   Email: {email}")
            print(f"   ID: {user_id}")
            print(f"   New role: admin")
            print("\n🚀 User can now sign in to the admin dashboard!")
            return True
        else:
            print("❌ Failed to update role")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def list_all_users():
    """List all users in the database"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return
    
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    try:
        print("\n📋 All users in database:")
        print("-" * 80)
        response = supabase.table("users").select("id, email, role, full_name, created_at").order("created_at", desc=True).execute()
        
        if not response.data:
            print("   No users found.")
            return
        
        for user in response.data:
            role = user.get("role", "none")
            email = user.get("email", "N/A")
            full_name = user.get("full_name", "N/A")
            created = user.get("created_at", "N/A")[:10] if user.get("created_at") else "N/A"
            
            role_badge = "👑" if role == "admin" else "👨‍🏫" if role == "mentor" else "👤"
            print(f"{role_badge} {email:<40} | {role:<10} | {full_name:<30} | {created}")
        
        print("-" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("=" * 80)
    print("🔧 Supabase User Role Manager")
    print("=" * 80)
    
    if len(sys.argv) < 2:
        print("\n📖 Usage:")
        print("   python set_admin_role.py <email>           - Set admin role for user")
        print("   python set_admin_role.py --list            - List all users")
        print("\n💡 Examples:")
        print("   python set_admin_role.py john@example.com")
        print("   python set_admin_role.py --list")
        print()
        list_all_users()
        sys.exit(0)
    
    arg = sys.argv[1]
    
    if arg == "--list" or arg == "-l":
        list_all_users()
    else:
        email = arg
        success = set_admin_role(email)
        sys.exit(0 if success else 1)
