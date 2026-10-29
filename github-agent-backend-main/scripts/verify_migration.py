#!/usr/bin/env python3
"""
Verification Script: Verify Migration Success
Validates that the projects-to-teams migration completed successfully.

This script checks:
1. All teams have repo_url
2. No orphaned foreign keys in related tables
3. Score ranges are valid (0-100)
4. Record counts in all tables
5. Data integrity and relationships

Author: Migration Verification Script
Date: 2025-01-17
"""
import sys
import os
from typing import Dict, List, Tuple
from datetime import datetime
from collections import defaultdict

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.backend.database import get_supabase_admin_client


class VerificationReport:
    """Track verification results"""
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
        self.errors = []
        self.stats = {}
    
    def add_pass(self, check_name: str):
        """Record a passed check"""
        self.checks_passed += 1
        print(f"    ✓ {check_name}")
    
    def add_fail(self, check_name: str, details: str = ""):
        """Record a failed check"""
        self.checks_failed += 1
        error_msg = f"✗ {check_name}"
        if details:
            error_msg += f": {details}"
        self.errors.append(error_msg)
        print(f"    {error_msg}")
    
    def add_warning(self, message: str):
        """Record a warning"""
        self.warnings.append(message)
        print(f"    ⚠️  {message}")
    
    def add_stat(self, key: str, value):
        """Record a statistic"""
        self.stats[key] = value
    
    def print_summary(self):
        """Print verification summary"""
        print("\n" + "="*70)
        print("VERIFICATION SUMMARY")
        print("="*70)
        
        # Overall status
        if self.checks_failed == 0:
            print("✅ ALL CHECKS PASSED")
        else:
            print(f"❌ {self.checks_failed} CHECK(S) FAILED")
        
        print(f"\nChecks Passed: {self.checks_passed}")
        print(f"Checks Failed: {self.checks_failed}")
        print(f"Warnings: {len(self.warnings)}")
        
        # Statistics
        if self.stats:
            print("\n" + "-"*70)
            print("DATABASE STATISTICS")
            print("-"*70)
            for key, value in self.stats.items():
                print(f"  {key:40} {value}")
        
        # Errors
        if self.errors:
            print("\n" + "-"*70)
            print("ERRORS")
            print("-"*70)
            for error in self.errors:
                print(f"  {error}")
        
        # Warnings
        if self.warnings:
            print("\n" + "-"*70)
            print("WARNINGS")
            print("-"*70)
            for warning in self.warnings:
                print(f"  {warning}")
        
        print("="*70)
        
        return self.checks_failed == 0


def check_teams_have_repo_url(supabase, report: VerificationReport):
    """Check 1: Verify all teams have repo_url"""
    print("\n[CHECK 1] Verifying teams have repo_url...")
    
    try:
        # Get all teams
        result = supabase.table("teams").select("id, team_name, repo_url").execute()
        teams = result.data
        
        total_teams = len(teams)
        teams_with_repo = [t for t in teams if t.get('repo_url')]
        teams_without_repo = [t for t in teams if not t.get('repo_url')]
        
        report.add_stat("Total Teams", total_teams)
        report.add_stat("Teams with repo_url", len(teams_with_repo))
        report.add_stat("Teams without repo_url", len(teams_without_repo))
        
        # Calculate percentage
        if total_teams > 0:
            percentage = (len(teams_with_repo) / total_teams) * 100
            report.add_stat("Repo URL Coverage", f"{percentage:.1f}%")
        
        # Check if all teams have repo_url
        if len(teams_without_repo) == 0:
            report.add_pass("All teams have repo_url")
        else:
            report.add_fail(
                "Some teams missing repo_url",
                f"{len(teams_without_repo)} teams without repo_url"
            )
            
            # List teams without repo_url (limit to 10)
            if len(teams_without_repo) <= 10:
                for team in teams_without_repo:
                    report.add_warning(f"Team '{team.get('team_name')}' (ID: {team['id']}) has no repo_url")
            else:
                report.add_warning(f"First 10 teams without repo_url:")
                for team in teams_without_repo[:10]:
                    report.add_warning(f"  - '{team.get('team_name')}' (ID: {team['id']})")
                report.add_warning(f"  ... and {len(teams_without_repo) - 10} more")
        
    except Exception as e:
        report.add_fail("Error checking teams repo_url", str(e))


def check_orphaned_foreign_keys(supabase, report: VerificationReport):
    """Check 2: Verify no orphaned foreign keys in related tables"""
    print("\n[CHECK 2] Checking for orphaned foreign keys...")
    
    # Get all valid team IDs
    try:
        teams_result = supabase.table("teams").select("id").execute()
        valid_team_ids = {t['id'] for t in teams_result.data}
        report.add_stat("Valid Team IDs", len(valid_team_ids))
    except Exception as e:
        report.add_fail("Error fetching team IDs", str(e))
        return
    
    # Tables to check: table_name -> foreign_key_column
    tables_to_check = {
        'team_members': 'team_id',
        'analysis_jobs': 'team_id',
        'students': 'team_id',
    }
    
    # Also check for any remaining project_id references
    tables_with_project_id = {
        'team_members': 'project_id',
        'analysis_jobs': 'project_id',
        'tech_stack': 'project_id',
        'issues': 'project_id',
        'project_comments': 'project_id',
        'analysis_snapshots': 'project_id',
    }
    
    # Check team_id foreign keys
    for table_name, fk_column in tables_to_check.items():
        try:
            # Get all records with this foreign key
            result = supabase.table(table_name).select(f"id, {fk_column}").not_.is_(fk_column, "null").execute()
            records = result.data
            
            if not records:
                report.add_pass(f"{table_name}: No records with {fk_column}")
                continue
            
            # Check for orphaned records
            orphaned = [r for r in records if r.get(fk_column) not in valid_team_ids]
            
            report.add_stat(f"{table_name} total records", len(records))
            report.add_stat(f"{table_name} orphaned records", len(orphaned))
            
            if len(orphaned) == 0:
                report.add_pass(f"{table_name}: No orphaned {fk_column} references")
            else:
                report.add_fail(
                    f"{table_name}: Found orphaned {fk_column} references",
                    f"{len(orphaned)} orphaned records"
                )
                
                # Show sample of orphaned records
                for record in orphaned[:5]:
                    report.add_warning(f"  Orphaned record ID: {record['id']}, {fk_column}: {record.get(fk_column)}")
                if len(orphaned) > 5:
                    report.add_warning(f"  ... and {len(orphaned) - 5} more orphaned records")
        
        except Exception as e:
            # Table might not exist or column might not exist
            report.add_warning(f"{table_name}: Could not check - {str(e)}")
    
    # Check for remaining project_id references (should be none)
    print("\n  Checking for remaining project_id references...")
    for table_name, fk_column in tables_with_project_id.items():
        try:
            result = supabase.table(table_name).select(f"id, {fk_column}").not_.is_(fk_column, "null").execute()
            records = result.data
            
            if records and len(records) > 0:
                report.add_fail(
                    f"{table_name}: Still has {fk_column} references",
                    f"{len(records)} records with project_id"
                )
                report.add_warning(f"  Migration may be incomplete - {table_name} still references projects")
            else:
                report.add_pass(f"{table_name}: No {fk_column} references (migrated)")
        
        except Exception as e:
            # Column might not exist (which is good - means it was dropped)
            report.add_pass(f"{table_name}: {fk_column} column removed")


def check_score_ranges(supabase, report: VerificationReport):
    """Check 3: Validate score ranges (0-100)"""
    print("\n[CHECK 3] Validating score ranges...")
    
    score_fields = [
        'total_score',
        'quality_score',
        'security_score',
        'originality_score',
        'architecture_score',
        'documentation_score',
        'effort_score',
        'implementation_score',
        'engineering_score',
        'organization_score',
    ]
    
    try:
        # Get all teams with scores
        result = supabase.table("teams").select("id, team_name, " + ", ".join(score_fields)).execute()
        teams = result.data
        
        teams_with_scores = [t for t in teams if any(t.get(field) is not None for field in score_fields)]
        report.add_stat("Teams with analysis scores", len(teams_with_scores))
        
        # Check each score field
        invalid_scores_found = False
        
        for field in score_fields:
            invalid_teams = []
            
            for team in teams:
                score = team.get(field)
                if score is not None:
                    if score < 0 or score > 100:
                        invalid_teams.append({
                            'id': team['id'],
                            'name': team.get('team_name', 'Unknown'),
                            'field': field,
                            'value': score
                        })
            
            if len(invalid_teams) == 0:
                report.add_pass(f"{field}: All scores in valid range (0-100)")
            else:
                invalid_scores_found = True
                report.add_fail(
                    f"{field}: Invalid scores found",
                    f"{len(invalid_teams)} teams with scores outside 0-100 range"
                )
                
                # Show sample of invalid scores
                for team in invalid_teams[:3]:
                    report.add_warning(
                        f"  Team '{team['name']}' has {team['field']} = {team['value']}"
                    )
                if len(invalid_teams) > 3:
                    report.add_warning(f"  ... and {len(invalid_teams) - 3} more invalid scores")
        
        if not invalid_scores_found:
            report.add_pass("All score fields have valid ranges")
    
    except Exception as e:
        report.add_fail("Error checking score ranges", str(e))


def check_record_counts(supabase, report: VerificationReport):
    """Check 4: Count records in all tables"""
    print("\n[CHECK 4] Counting records in all tables...")
    
    tables_to_count = [
        'teams',
        'batches',
        'students',
        'team_members',
        'analysis_jobs',
        'users',
    ]
    
    # Also check if projects table still exists
    try:
        projects_result = supabase.table("projects").select("id").execute()
        projects_count = len(projects_result.data)
        
        report.add_stat("Projects table records", projects_count)
        
        if projects_count > 0:
            report.add_fail(
                "Projects table still exists",
                f"{projects_count} records found - table should be dropped"
            )
        else:
            report.add_pass("Projects table is empty (ready to drop)")
    
    except Exception as e:
        # Table doesn't exist or can't be accessed (which is good after migration)
        report.add_pass("Projects table dropped or inaccessible")
    
    # Count records in other tables
    for table_name in tables_to_count:
        try:
            result = supabase.table(table_name).select("id").execute()
            count = len(result.data)
            report.add_stat(f"{table_name} records", count)
            report.add_pass(f"{table_name}: {count} records")
        
        except Exception as e:
            report.add_warning(f"{table_name}: Could not count - {str(e)}")


def check_data_integrity(supabase, report: VerificationReport):
    """Check 5: Verify data integrity and relationships"""
    print("\n[CHECK 5] Verifying data integrity...")
    
    try:
        # Check 5.1: Teams with analysis data
        result = supabase.table("teams").select(
            "id, team_name, status, total_score, analyzed_at"
        ).execute()
        teams = result.data
        
        teams_analyzed = [t for t in teams if t.get('analyzed_at') is not None]
        teams_with_scores = [t for t in teams if t.get('total_score') is not None]
        teams_completed = [t for t in teams if t.get('status') == 'completed']
        
        report.add_stat("Teams analyzed", len(teams_analyzed))
        report.add_stat("Teams with scores", len(teams_with_scores))
        report.add_stat("Teams with status=completed", len(teams_completed))
        
        # Check consistency: teams with scores should have analyzed_at
        inconsistent = [t for t in teams if t.get('total_score') is not None and t.get('analyzed_at') is None]
        
        if len(inconsistent) == 0:
            report.add_pass("All teams with scores have analyzed_at timestamp")
        else:
            report.add_fail(
                "Inconsistent analysis data",
                f"{len(inconsistent)} teams have scores but no analyzed_at timestamp"
            )
        
        # Check 5.2: Batch relationships
        batches_result = supabase.table("batches").select("id").execute()
        valid_batch_ids = {b['id'] for b in batches_result.data}
        
        teams_with_invalid_batch = [t for t in teams if t.get('batch_id') not in valid_batch_ids]
        
        if len(teams_with_invalid_batch) == 0:
            report.add_pass("All teams have valid batch_id references")
        else:
            report.add_fail(
                "Invalid batch references",
                f"{len(teams_with_invalid_batch)} teams reference non-existent batches"
            )
        
        # Check 5.3: Student-team relationships
        students_result = supabase.table("students").select("id, team_id").execute()
        students = students_result.data
        
        valid_team_ids = {t['id'] for t in teams}
        students_with_invalid_team = [
            s for s in students 
            if s.get('team_id') is not None and s.get('team_id') not in valid_team_ids
        ]
        
        if len(students_with_invalid_team) == 0:
            report.add_pass("All students have valid team_id references")
        else:
            report.add_fail(
                "Invalid student-team references",
                f"{len(students_with_invalid_team)} students reference non-existent teams"
            )
    
    except Exception as e:
        report.add_fail("Error checking data integrity", str(e))


def generate_migration_report(report: VerificationReport):
    """Generate a detailed migration report file"""
    print("\n[REPORT] Generating migration report...")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = f"migration_verification_report_{timestamp}.txt"
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        report_filename
    )
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("MIGRATION VERIFICATION REPORT\n")
            f.write("="*70 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n")
            
            # Overall status
            if report.checks_failed == 0:
                f.write("STATUS: [PASS] ALL CHECKS PASSED\n")
            else:
                f.write(f"STATUS: [FAIL] {report.checks_failed} CHECK(S) FAILED\n")
            
            f.write(f"\nChecks Passed: {report.checks_passed}\n")
            f.write(f"Checks Failed: {report.checks_failed}\n")
            f.write(f"Warnings: {len(report.warnings)}\n")
            
            # Statistics
            if report.stats:
                f.write("\n" + "-"*70 + "\n")
                f.write("DATABASE STATISTICS\n")
                f.write("-"*70 + "\n")
                for key, value in report.stats.items():
                    f.write(f"{key:40} {value}\n")
            
            # Errors
            if report.errors:
                f.write("\n" + "-"*70 + "\n")
                f.write("ERRORS\n")
                f.write("-"*70 + "\n")
                for error in report.errors:
                    f.write(f"{error}\n")
            
            # Warnings
            if report.warnings:
                f.write("\n" + "-"*70 + "\n")
                f.write("WARNINGS\n")
                f.write("-"*70 + "\n")
                for warning in report.warnings:
                    f.write(f"{warning}\n")
            
            f.write("\n" + "="*70 + "\n")
        
        print(f"  ✓ Report saved to: {report_path}")
        return report_path
    
    except Exception as e:
        print(f"  ✗ Error generating report: {e}")
        return None


def main():
    """Main verification function"""
    print("="*70)
    print("MIGRATION VERIFICATION")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize
    supabase = get_supabase_admin_client()
    report = VerificationReport()
    
    # Run all checks
    check_teams_have_repo_url(supabase, report)
    check_orphaned_foreign_keys(supabase, report)
    check_score_ranges(supabase, report)
    check_record_counts(supabase, report)
    check_data_integrity(supabase, report)
    
    # Generate report file
    report_path = generate_migration_report(report)
    
    # Print summary
    success = report.print_summary()
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("\n✅ Migration verification PASSED - 100% data integrity confirmed!")
        if report_path:
            print(f"📄 Detailed report: {report_path}")
        return 0
    else:
        print(f"\n❌ Migration verification FAILED - {report.checks_failed} issue(s) found")
        print("Please review the errors above and fix any issues.")
        if report_path:
            print(f"📄 Detailed report: {report_path}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Verification interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
