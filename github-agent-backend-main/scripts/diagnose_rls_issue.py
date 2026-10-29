#!/usr/bin/env python3
"""
Diagnostic script to identify RLS and status constraint issues with analysis_jobs table.

This script will:
1. Verify environment variables are set correctly
2. Test admin client configuration
3. Attempt to insert into analysis_jobs table
4. Check RLS policies
5. Verify status constraints
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from uuid import uuid4
from datetime import datetime

# Load environment variables
load_dotenv()

# Import from the actual codebase
from src.api.backend.database import get_supabase_admin_client, SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_environment_variables():
    """Check if required environment variables are set"""
    print_section("1. Environment Variables Check")
    
    results = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY
    }
    
    for var, value in results.items():
        if value:
            # Show first 20 chars for security
            masked = value[:20] + "..." if len(value) > 20 else value
            print(f"✓ {var}: {masked}")
        else:
            print(f"✗ {var}: NOT SET")
    
    # Check if service key is different from anon key
    if results["SUPABASE_SERVICE_KEY"] and results["SUPABASE_KEY"]:
        if results["SUPABASE_SERVICE_KEY"] == results["SUPABASE_KEY"]:
            print(f"\n⚠ WARNING: SUPABASE_SERVICE_KEY is the same as SUPABASE_KEY (anon key)!")
            print(f"   This will cause RLS policy violations!")
        else:
            print(f"\n✓ Service key is different from anon key")
    
    return results

def test_admin_client_creation(env_vars):
    """Test creating admin client"""
    print_section("2. Admin Client Creation Test")
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("✗ Cannot create admin client - missing environment variables")
        return None
    
    try:
        admin_client = get_supabase_admin_client()
        print("✓ Admin client created successfully")
        return admin_client
    except Exception as e:
        print(f"✗ Failed to create admin client: {e}")
        return None

def check_rls_policies(admin_client):
    """Check RLS policies on analysis_jobs table"""
    print_section("3. RLS Policies Check")
    
    if not admin_client:
        print("✗ Cannot check RLS policies - no admin client")
        return
    
    try:
        # Query RLS policies
        query = """
        SELECT 
            schemaname,
            tablename,
            policyname,
            permissive,
            roles,
            cmd,
            qual,
            with_check
        FROM pg_policies
        WHERE tablename = 'analysis_jobs';
        """
        
        result = admin_client.rpc('exec_sql', {'query': query}).execute()
        
        if result.data:
            print(f"Found {len(result.data)} RLS policies:")
            for policy in result.data:
                print(f"\n  Policy: {policy['policyname']}")
                print(f"    Roles: {policy['roles']}")
                print(f"    Command: {policy['cmd']}")
                print(f"    Using: {policy['qual']}")
                print(f"    With Check: {policy['with_check']}")
        else:
            print("No RLS policies found (or unable to query)")
            
    except Exception as e:
        print(f"✗ Failed to check RLS policies: {e}")

def check_table_structure(admin_client):
    """Check analysis_jobs table structure"""
    print_section("4. Table Structure Check")
    
    if not admin_client:
        print("✗ Cannot check table structure - no admin client")
        return
    
    try:
        # Check if table exists and get structure
        result = admin_client.table("analysis_jobs").select("*").limit(1).execute()
        print("✓ analysis_jobs table exists and is accessible")
        
        # Try to get column info
        query = """
        SELECT 
            column_name,
            data_type,
            column_default,
            is_nullable
        FROM information_schema.columns
        WHERE table_name = 'analysis_jobs'
        ORDER BY ordinal_position;
        """
        
        # Note: This might fail if we don't have a custom RPC function
        print("\nTable columns:")
        print("  (Attempting to query column structure...)")
        
    except Exception as e:
        print(f"✗ Failed to check table structure: {e}")

def test_insert_with_admin_client(admin_client):
    """Test inserting into analysis_jobs with admin client"""
    print_section("5. Insert Test with Admin Client")
    
    if not admin_client:
        print("✗ Cannot test insert - no admin client")
        return
    
    # First, get a valid team_id
    try:
        teams = admin_client.table("teams").select("id").limit(1).execute()
        if not teams.data:
            print("✗ No teams found in database - cannot test insert")
            return
        
        team_id = teams.data[0]["id"]
        print(f"✓ Found test team: {team_id}")
        
    except Exception as e:
        print(f"✗ Failed to get test team: {e}")
        return
    
    # Try to insert a test analysis job
    test_job = {
        "team_id": team_id,
        "status": "queued",
        "progress": 0,
        "started_at": datetime.now().isoformat()
    }
    
    print(f"\nAttempting to insert test job:")
    print(f"  team_id: {team_id}")
    print(f"  status: queued")
    
    try:
        result = admin_client.table("analysis_jobs").insert(test_job).execute()
        
        if result.data:
            job_id = result.data[0]["id"]
            print(f"\n✓ SUCCESS! Job inserted with ID: {job_id}")
            
            # Clean up - delete the test job
            admin_client.table("analysis_jobs").delete().eq("id", job_id).execute()
            print(f"✓ Test job cleaned up")
        else:
            print(f"\n✗ Insert returned no data")
            
    except Exception as e:
        error_str = str(e)
        print(f"\n✗ INSERT FAILED!")
        print(f"\nError: {error_str}")
        
        # Parse the error
        if "row-level security policy" in error_str.lower():
            print(f"\n⚠ RLS POLICY VIOLATION DETECTED!")
            print(f"   This means the service_role is not bypassing RLS as expected.")
            print(f"   Possible causes:")
            print(f"   1. Wrong key being used (anon key instead of service key)")
            print(f"   2. RLS policies are incorrectly configured")
            print(f"   3. Supabase client version issue")
        
        if "violates check constraint" in error_str.lower():
            print(f"\n⚠ CONSTRAINT VIOLATION DETECTED!")
            print(f"   The status value 'queued' may not be allowed by a check constraint")
        
        if "violates foreign key" in error_str.lower():
            print(f"\n⚠ FOREIGN KEY VIOLATION DETECTED!")
            print(f"   The team_id may not exist or column name is wrong")

def test_status_values(admin_client):
    """Test which status values are allowed"""
    print_section("6. Status Constraint Test")
    
    if not admin_client:
        print("✗ Cannot test status values - no admin client")
        return
    
    # Get a valid team_id
    try:
        teams = admin_client.table("teams").select("id").limit(1).execute()
        if not teams.data:
            print("✗ No teams found - cannot test status values")
            return
        team_id = teams.data[0]["id"]
    except Exception as e:
        print(f"✗ Failed to get test team: {e}")
        return
    
    # Test different status values
    test_statuses = ["queued", "running", "completed", "failed", "pending", "cancelled"]
    
    print("Testing status values:")
    for status in test_statuses:
        test_job = {
            "team_id": team_id,
            "status": status,
            "progress": 0,
            "started_at": datetime.now().isoformat()
        }
        
        try:
            result = admin_client.table("analysis_jobs").insert(test_job).execute()
            if result.data:
                job_id = result.data[0]["id"]
                print(f"  ✓ '{status}' - ALLOWED")
                # Clean up
                admin_client.table("analysis_jobs").delete().eq("id", job_id).execute()
        except Exception as e:
            error_str = str(e)
            if "row-level security" in error_str.lower():
                print(f"  ✗ '{status}' - RLS BLOCKED (not a constraint issue)")
            elif "check constraint" in error_str.lower():
                print(f"  ✗ '{status}' - CONSTRAINT VIOLATION")
            else:
                print(f"  ✗ '{status}' - ERROR: {str(e)[:50]}")

def main():
    """Run all diagnostic tests"""
    print("\n" + "="*60)
    print("  ANALYSIS JOBS RLS & STATUS DIAGNOSTIC TOOL")
    print("="*60)
    
    # Run diagnostics
    env_vars = check_environment_variables()
    admin_client = test_admin_client_creation(env_vars)
    check_rls_policies(admin_client)
    check_table_structure(admin_client)
    test_insert_with_admin_client(admin_client)
    test_status_values(admin_client)
    
    # Summary
    print_section("DIAGNOSTIC SUMMARY")
    print("Review the results above to identify the root cause.")
    print("\nCommon issues:")
    print("1. RLS Policy Violation → Check if service key is correct")
    print("2. Status Constraint → Check which status values are allowed")
    print("3. Foreign Key Violation → Check if team_id column exists")
    print("\nNext steps:")
    print("- If RLS violation: Fix RLS policies or verify service key")
    print("- If constraint violation: Update status constraint in migration")
    print("- If foreign key violation: Run schema migration to add team_id")

if __name__ == "__main__":
    main()
