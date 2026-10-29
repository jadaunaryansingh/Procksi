"""
Migration script to add health tracking columns to the teams table.
Run this script to add risk_flags and last_health_check columns.
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv(".env.development")
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def run_migration():
    """Add health tracking columns to teams table."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        return False
    
    print(f"🔗 Connecting to Supabase: {SUPABASE_URL}")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    # SQL to add the columns
    migration_sql = """
    -- Add risk_flags column (JSONB array of risk flag identifiers)
    ALTER TABLE teams 
    ADD COLUMN IF NOT EXISTS risk_flags JSONB DEFAULT '[]'::jsonb;
    
    -- Add last_health_check column (timestamp of last calculation)
    ALTER TABLE teams 
    ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMPTZ;
    """
    
    try:
        print("📊 Running migration...")
        # Execute the migration using the Supabase RPC
        result = supabase.rpc("exec_sql", {"sql": migration_sql}).execute()
        print("✅ Migration completed successfully!")
        print(f"   Added columns: risk_flags (JSONB), last_health_check (TIMESTAMPTZ)")
        return True
    except Exception as e:
        error_msg = str(e)
        if "function public.exec_sql" in error_msg.lower() or "does not exist" in error_msg.lower():
            print("⚠️  RPC exec_sql not available. Trying direct SQL approach...")
            print("\n📝 Please run this SQL in your Supabase SQL Editor:\n")
            print("-" * 60)
            print("""
ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS risk_flags JSONB DEFAULT '[]'::jsonb;

ALTER TABLE teams 
ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMPTZ;

-- Optional: Add comments for documentation
COMMENT ON COLUMN teams.risk_flags IS 'List of risk flag identifiers (e.g., stale, inactive, imbalanced)';
COMMENT ON COLUMN teams.last_health_check IS 'Timestamp of last health status calculation';
            """.strip())
            print("-" * 60)
            print("\n🔗 Supabase SQL Editor: https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr/sql")
            return False
        else:
            print(f"❌ Error: {e}")
            return False

if __name__ == "__main__":
    print("=" * 60)
    print("🏥 Health Tracking Migration")
    print("=" * 60)
    run_migration()
    print("=" * 60)
