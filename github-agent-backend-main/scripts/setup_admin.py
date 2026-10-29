"""
Admin User Setup Script
Creates or updates a user with admin role in Supabase
"""
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
env_file = Path(__file__).parent.parent / ".env.development"
load_dotenv(env_file)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env.development")
    sys.exit(1)

def setup_admin(email: str):
    """
    Grant admin role to a user by email
    User must already exist (have logged in at least once via Google OAuth)
    """
    try:
        # Create admin client (bypasses RLS)
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        
        print(f"🔍 Looking for user: {email}")
        
        # Get user by email using admin API
        response = supabase.auth.admin.list_users()
        
        user = None
        for u in response:
            if u.email == email:
                user = u
                break
        
        if not user:
            print(f"❌ User not found: {email}")
            print("💡 The user must login via Google OAuth first to create the account.")
            print("   Steps:")
            print("   1. Start backend: uvicorn main:app --reload")
            print("   2. Go to http://localhost:8000/docs")
            print("   3. Use POST /api/auth/login with Google ID token")
            print("   4. Then run this script again")
            return False
        
        print(f"✅ Found user: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Created: {user.created_at}")
        
        # Update user metadata to add admin role
        current_metadata = user.app_metadata or {}
        current_role = current_metadata.get("role", "mentor")
        
        print(f"   Current role: {current_role}")
        
        if current_role == "admin":
            print("✅ User already has admin role!")
            return True
        
        # Update to admin role
        updated_user = supabase.auth.admin.update_user_by_id(
            user.id,
            {"app_metadata": {"role": "admin"}}
        )
        
        print(f"✅ Successfully granted admin role to {email}")
        print("⚠️  The user must logout and login again to get a new token with admin privileges")
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def list_users():
    """List all users and their roles"""
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        response = supabase.auth.admin.list_users()
        
        if not response:
            print("No users found in database")
            return
        
        print("\n📋 Current Users:")
        print(f"{'Email':<40} {'Role':<10} {'Created':<20}")
        print("-" * 70)
        
        for user in response:
            email = user.email or "N/A"
            metadata = user.app_metadata or {}
            role = metadata.get("role", "mentor")
            created = user.created_at[:10] if user.created_at else "N/A"
            print(f"{email:<40} {role:<10} {created:<20}")
        
    except Exception as e:
        print(f"❌ Error listing users: {str(e)}")


if __name__ == "__main__":
    print("=" * 70)
    print("🔐 Admin User Setup")
    print("=" * 70)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            list_users()
        else:
            email = sys.argv[1]
            setup_admin(email)
    else:
        print("\n📖 Usage:")
        print("  python scripts/setup_admin.py <email>       - Grant admin role to user")
        print("  python scripts/setup_admin.py list          - List all users and roles")
        print("\n📝 Examples:")
        print("  python scripts/setup_admin.py admin@example.com")
        print("  python scripts/setup_admin.py list")
        print("\n⚠️  Note: User must have logged in via Google OAuth at least once")
