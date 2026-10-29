"""
Database Setup Script
Checks if Supabase tables exist and helps set them up
"""
import sys
from backend.database import get_supabase_client

print("="*80)
print("SUPABASE DATABASE SETUP CHECK")
print("="*80)

try:
    client = get_supabase_client()
    print("✅ Connected to Supabase successfully!")
    print()
    
    # Check each table
    tables = ["projects", "analysis_jobs", "tech_stack", "issues", "team_members"]
    
    for table_name in tables:
        try:
            result = client.table(table_name).select("id").limit(1).execute()
            print(f"✅ Table '{table_name}' exists")
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                print(f"❌ Table '{table_name}' does NOT exist")
            else:
                print(f"⚠️  Table '{table_name}' - Error: {str(e)[:100]}")
    
    print()
    print("="*80)
    print("SETUP INSTRUCTIONS:")
    print("="*80)
    print()
    print("If any tables are missing, you need to run the SQL schema:")
    print()
    print("1. Open Supabase Dashboard: https://app.supabase.com")
    print("2. Select your project: frcdvwuapmunkjaarrzr")
    print("3. Go to: SQL Editor → New Query")
    print("4. Copy and paste the content from: supabase_schema.sql")
    print("5. Click 'Run' to create all tables")
    print()
    print("Schema file location: supabase_schema.sql")
    print()
    
except Exception as e:
    print(f"❌ Failed to connect to Supabase!")
    print(f"Error: {e}")
    print()
    print("Check your .env file has correct credentials:")
    print("  SUPABASE_URL=...")
    print("  SUPABASE_KEY=...")
    print("  SUPABASE_SERVICE_KEY=...")
    sys.exit(1)
