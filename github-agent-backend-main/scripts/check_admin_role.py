"""
Check and update admin role in Supabase
Verifies that the user role is set correctly in auth.users metadata
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
env_file = Path(__file__).parent.parent / ".env.development"
load_dotenv(env_file)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    sys.exit(1)

def check_user_role(email: str):
    """Check current role for user"""
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        
        # Get user by email
        response = supabase.auth.admin.list_users()
        
        user = None
        for u in response:
            if u.email == email:
                user = u
                break
        
        if not user:
            print(f"❌ User not found: {email}")
            return None
        
        print(f"\n✅ Found user:")
        print(f"   Email: {user.email}")
        print(f"   ID: {user.id}")
        
        # Check app_metadata (this is what JWT uses)
        app_metadata = user.app_metadata or {}
        role_in_jwt = app_metadata.get("role", "NOT SET")
        print(f"\n📋 Role in app_metadata (JWT): {role_in_jwt}")
        
        # Check user_metadata
        user_metadata = user.user_metadata or {}
        role_in_user_meta = user_metadata.get("role", "NOT SET")
        print(f"   Role in user_metadata: {role_in_user_meta}")
        
        if role_in_jwt != "admin":
            print(f"\n⚠️  User is NOT admin in JWT!")
            print(f"   Current JWT role: {role_in_jwt}")
            return user
        else:
            print(f"\n✅ User IS admin in JWT metadata")
            return user
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def set_admin_role(email: str):
    """Set admin role in app_metadata"""
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        
        # Get user
        response = supabase.auth.admin.list_users()
        user = None
        for u in response:
            if u.email == email:
                user = u
                break
        
        if not user:
            print(f"❌ User not found: {email}")
            return False
        
        print(f"\n🔧 Setting admin role for {email}...")
        
        # Update app_metadata with admin role
        updated_user = supabase.auth.admin.update_user_by_id(
            user.id,
            {"app_metadata": {"role": "admin"}}
        )
        
        print(f"✅ Successfully set admin role!")
        print(f"\n⚠️  IMPORTANT:")
        print(f"   1. User must LOGOUT from the application")
        print(f"   2. User must LOGIN again to get new JWT token")
        print(f"   3. Clear browser cookies/cache if issues persist")
        
        return True
        
    except Exception as e:
        print(f"❌ Error setting admin role: {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("🔐 Supabase Admin Role Checker")
    print("=" * 70)
    
    if len(sys.argv) < 2:
        print("\n📖 Usage:")
        print("  python scripts/check_admin_role.py <email>           - Check role")
        print("  python scripts/check_admin_role.py <email> --fix     - Set admin role")
        print("\n📝 Example:")
        print("  python scripts/check_admin_role.py user@gmail.com")
        print("  python scripts/check_admin_role.py user@gmail.com --fix")
        sys.exit(0)
    
    email = sys.argv[1]
    fix = len(sys.argv) > 2 and sys.argv[2] == "--fix"
    
    user = check_user_role(email)
    
    if fix and user:
        print("\n" + "=" * 70)
        set_admin_role(email)
