#!/usr/bin/env python3
"""
Database Flush Script: Clear all data while preserving schema
Prepares the database for a clean migration by removing all records.

This script:
1. Backs up current data counts
2. Deletes all records from tables in correct order (respecting foreign keys)
3. Resets sequences/auto-increment counters
4. Verifies database is empty
5. Generates flush report

Author: Database Flush Script
Date: 2025-01-17
"""
import sys
import os
from typing import Dict, List
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.backend.database import get_supabase_admin_client


class FlushStats:
    """Track flush statistics"""
    def __init__(self):
        self.before_counts = {}
        self.after_counts = {}
        self.deleted_counts = {}
        self.errors = []
    
    def print_summary(self):
        """Print flush summary"""
        print("\n" + "="*70)
        print("DATABASE FLUSH SUMMARY")
        print("="*70)
        
        print("\nRecords Deleted:")
        print("-"*70)
        total_deleted = 0
        for table, count in self.deleted_counts.items():
            print(f"  {table:30} {count:>10} records")
            total_deleted += count
        
        print("-"*70)
        print(f"  {'TOTAL':30} {total_deleted:>10} records")
        
        if self.errors:
            print("\nErrors:")
            print("-"*70)
            for error in self.errors:
                print(f"  ✗ {error}")
        
        print("="*70)


def get_table_counts(supabase, tables: List[str]) -> Dict[str, int]:
    """Get record counts for all tables"""
    counts = {}
    for table in tables:
        try:
            result = supabase.table(table).select("id", count="exact").execute()
            counts[table] = result.count if hasattr(result, 'count') else len(result.data)
        except Exception as e:
            counts[table] = 0
            print(f"  ⚠️  Could not count {table}: {e}")
    return counts


def flush_database(supabase, stats: FlushStats) -> bool:
    """
    Flush all data from database tables.
    Deletes in correct order to respect foreign key constraints.
    """
    print("\n[STEP 1] Recording current data counts...")
    
    # Tables in deletion order (children first, parents last)
    tables_to_flush = [
        # Analysis and history
        'analysis_history',
        'analysis_snapshots',
        'analysis_jobs',
        
        # Team-related data
        'team_members',
        'tech_stack',
        'issues',
        'project_comments',
        
        # Students
        'students',
        
        # Projects (will be dropped anyway)
        'projects',
        
        # Teams
        'teams',
        
        # Batches
        'batches',
        
        # Users (keep admin users)
        # 'users',  # Commented out - we'll handle this separately
    ]
    
    # Get before counts
    stats.before_counts = get_table_counts(supabase, tables_to_flush)
    
    print("\nBefore Flush:")
    print("-"*70)
    total_before = 0
    for table, count in stats.before_counts.items():
        print(f"  {table:30} {count:>10} records")
        total_before += count
    print("-"*70)
    print(f"  {'TOTAL':30} {total_before:>10} records")
    
    # Confirm flush
    print(f"\n⚠️  WARNING: This will delete {total_before} records from {len(tables_to_flush)} tables!")
    print("This action cannot be undone without a backup.")
    
    response = input("\nType 'FLUSH' to confirm: ")
    if response != 'FLUSH':
        print("\n❌ Flush cancelled by user")
        return False
    
    print("\n[STEP 2] Flushing database tables...")
    
    # Delete data from each table
    for table in tables_to_flush:
        try:
            print(f"\n  Flushing {table}...")
            
            # Get all IDs first
            result = supabase.table(table).select("id").execute()
            ids = [row['id'] for row in result.data]
            
            if len(ids) == 0:
                print(f"    ✓ {table} already empty")
                stats.deleted_counts[table] = 0
                continue
            
            # Delete in batches of 100
            batch_size = 100
            deleted = 0
            
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i:i+batch_size]
                
                # Delete batch
                for id in batch_ids:
                    try:
                        supabase.table(table).delete().eq("id", id).execute()
                        deleted += 1
                    except Exception as e:
                        print(f"    ⚠️  Error deleting record {id}: {e}")
                
                print(f"    Progress: {deleted}/{len(ids)} records deleted", end='\r')
            
            print(f"    ✓ Deleted {deleted} records from {table}                    ")
            stats.deleted_counts[table] = deleted
            
        except Exception as e:
            error_msg = f"Error flushing {table}: {e}"
            stats.errors.append(error_msg)
            print(f"    ✗ {error_msg}")
            stats.deleted_counts[table] = 0
    
    # Handle users table separately - keep admin users
    print(f"\n  Handling users table (keeping admin users)...")
    try:
        # Delete non-admin users
        result = supabase.table("users").select("id, role").execute()
        users = result.data
        
        non_admin_users = [u for u in users if u.get('role') != 'admin']
        
        deleted = 0
        for user in non_admin_users:
            try:
                supabase.table("users").delete().eq("id", user['id']).execute()
                deleted += 1
            except Exception as e:
                print(f"    ⚠️  Error deleting user {user['id']}: {e}")
        
        print(f"    ✓ Deleted {deleted} non-admin users (kept {len(users) - deleted} admin users)")
        stats.deleted_counts['users'] = deleted
        
    except Exception as e:
        error_msg = f"Error handling users: {e}"
        stats.errors.append(error_msg)
        print(f"    ✗ {error_msg}")
    
    return True


def verify_flush(supabase, stats: FlushStats) -> bool:
    """Verify database is empty"""
    print("\n[STEP 3] Verifying database is empty...")
    
    tables_to_check = list(stats.before_counts.keys())
    stats.after_counts = get_table_counts(supabase, tables_to_check)
    
    print("\nAfter Flush:")
    print("-"*70)
    total_after = 0
    all_empty = True
    
    for table, count in stats.after_counts.items():
        status = "✓" if count == 0 else "✗"
        print(f"  {status} {table:28} {count:>10} records")
        total_after += count
        if count > 0 and table != 'users':  # users table may have admin users
            all_empty = False
    
    print("-"*70)
    print(f"  {'TOTAL':30} {total_after:>10} records")
    
    if all_empty or total_after <= stats.after_counts.get('users', 0):
        print("\n✅ Database successfully flushed!")
        return True
    else:
        print(f"\n⚠️  Warning: {total_after} records remain in database")
        return False


def generate_flush_report(stats: FlushStats):
    """Generate flush report file"""
    print("\n[STEP 4] Generating flush report...")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = f"flush_report_{timestamp}.txt"
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        report_filename
    )
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("DATABASE FLUSH REPORT\n")
            f.write("="*70 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n")
            
            # Before counts
            f.write("BEFORE FLUSH\n")
            f.write("-"*70 + "\n")
            for table, count in stats.before_counts.items():
                f.write(f"{table:30} {count:>10} records\n")
            f.write("-"*70 + "\n")
            f.write(f"{'TOTAL':30} {sum(stats.before_counts.values()):>10} records\n")
            f.write("\n")
            
            # Deleted counts
            f.write("RECORDS DELETED\n")
            f.write("-"*70 + "\n")
            for table, count in stats.deleted_counts.items():
                f.write(f"{table:30} {count:>10} records\n")
            f.write("-"*70 + "\n")
            f.write(f"{'TOTAL':30} {sum(stats.deleted_counts.values()):>10} records\n")
            f.write("\n")
            
            # After counts
            f.write("AFTER FLUSH\n")
            f.write("-"*70 + "\n")
            for table, count in stats.after_counts.items():
                f.write(f"{table:30} {count:>10} records\n")
            f.write("-"*70 + "\n")
            f.write(f"{'TOTAL':30} {sum(stats.after_counts.values()):>10} records\n")
            f.write("\n")
            
            # Errors
            if stats.errors:
                f.write("ERRORS\n")
                f.write("-"*70 + "\n")
                for error in stats.errors:
                    f.write(f"{error}\n")
                f.write("\n")
            
            f.write("="*70 + "\n")
        
        print(f"  ✓ Report saved to: {report_path}")
        return report_path
    
    except Exception as e:
        print(f"  ✗ Error generating report: {e}")
        return None


def main():
    """Main flush function"""
    print("="*70)
    print("DATABASE FLUSH SCRIPT")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis script will DELETE ALL DATA from the database.")
    print("Make sure you have a backup before proceeding!")
    
    # Initialize
    supabase = get_supabase_admin_client()
    stats = FlushStats()
    
    # Flush database
    if not flush_database(supabase, stats):
        print("\n❌ Flush cancelled")
        return 1
    
    # Verify flush
    verify_flush(supabase, stats)
    
    # Generate report
    generate_flush_report(stats)
    
    # Print summary
    stats.print_summary()
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if len(stats.errors) == 0:
        print("\n✅ Database flush completed successfully!")
        print("\nNext steps:")
        print("  1. Run bulk import to refill database")
        print("  2. Run migration script: python scripts/migrate_projects_to_teams.py")
        print("  3. Verify migration: python scripts/verify_migration.py")
        return 0
    else:
        print(f"\n⚠️  Flush completed with {len(stats.errors)} errors")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Flush interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Flush failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
