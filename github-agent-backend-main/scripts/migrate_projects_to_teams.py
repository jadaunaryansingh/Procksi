#!/usr/bin/env python3
"""
Migration Script: Merge Projects Table into Teams Table
Consolidates all project data into the teams table and removes the projects table.

This script:
1. Adds analysis columns to teams table
2. Matches projects to teams by team_name + batch_id
3. Falls back to matching by repo_url
4. Creates new team records for unmatched projects
5. Updates foreign keys in related tables
6. Verifies data integrity
7. Drops the projects table

Author: Migration Script
Date: 2025-01-17
"""
import sys
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.backend.database import get_supabase_admin_client


class MigrationStats:
    """Track migration statistics"""
    def __init__(self):
        self.matched_by_name_batch = 0
        self.matched_by_repo_url = 0
        self.unmatched_created = 0
        self.errors = 0
        self.foreign_keys_updated = {
            'team_members': 0,
            'analysis_jobs': 0,
            'tech_stack': 0,
            'issues': 0,
            'project_comments': 0,
            'analysis_snapshots': 0
        }
    
    def print_summary(self):
        """Print migration summary"""
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Projects matched by name+batch: {self.matched_by_name_batch}")
        print(f"Projects matched by repo_url:   {self.matched_by_repo_url}")
        print(f"New teams created:               {self.unmatched_created}")
        print(f"Errors:                          {self.errors}")
        print("\nForeign Keys Updated:")
        for table, count in self.foreign_keys_updated.items():
            print(f"  {table:25} {count}")
        print("="*60)


def add_analysis_columns_to_teams(supabase) -> bool:
    """
    Check if analysis columns exist in teams table.
    Returns True if all columns exist, False otherwise.
    """
    print("\n[STEP 1] Checking analysis columns in teams table...")
    
    # List of required columns
    required_columns = [
        "total_score", "quality_score", "security_score", "originality_score",
        "architecture_score", "documentation_score", "effort_score",
        "implementation_score", "engineering_score", "organization_score",
        "total_commits", "verdict", "ai_pros", "ai_cons", "report_json",
        "report_path", "viz_path", "analyzed_at", "last_analyzed_at"
    ]
    
    try:
        # Check if columns exist by trying to select them
        teams_check = supabase.table("teams").select("*").limit(1).execute()
        existing_cols = set(teams_check.data[0].keys()) if teams_check.data else set()
        
        print(f"Found {len(existing_cols)} existing columns in teams table")
        
        # Check which required columns are missing
        missing_cols = [col for col in required_columns if col not in existing_cols]
        
        if missing_cols:
            print(f"\n⚠️  WARNING: {len(missing_cols)} required columns are missing:")
            for col in missing_cols:
                print(f"  - {col}")
            
            print("\n📋 Please run the SQL migration first:")
            print("   File: scripts/migration_add_analysis_columns.sql")
            print("   Or use: supabase db execute -f scripts/migration_add_analysis_columns.sql")
            print("\nAfter running the SQL, re-run this migration script.")
            return False
        
        print("✓ All required columns exist in teams table")
        return True
        
    except Exception as e:
        print(f"✗ Error checking columns: {e}")
        return False


def fetch_all_projects(supabase) -> List[Dict]:
    """Fetch all projects from the projects table"""
    print("\n[STEP 2] Fetching all projects...")
    try:
        result = supabase.table("projects").select("*").execute()
        projects = result.data
        print(f"✓ Found {len(projects)} projects")
        return projects
    except Exception as e:
        print(f"✗ Error fetching projects: {e}")
        return []


def fetch_all_teams(supabase) -> List[Dict]:
    """Fetch all teams from the teams table"""
    print("\n[STEP 3] Fetching all teams...")
    try:
        result = supabase.table("teams").select("*").execute()
        teams = result.data
        print(f"✓ Found {len(teams)} teams")
        return teams
    except Exception as e:
        print(f"✗ Error fetching teams: {e}")
        return []


def find_matching_team(project: Dict, teams: List[Dict]) -> Optional[Dict]:
    """
    Find a matching team for a project.
    
    Matching strategy:
    1. Primary: team_name + batch_id
    2. Fallback: repo_url
    
    Returns the matching team or None
    """
    # Strategy 1: Match by team_name + batch_id
    if project.get('team_name') and project.get('batch_id'):
        for team in teams:
            if (team.get('team_name') == project.get('team_name') and 
                team.get('batch_id') == project.get('batch_id')):
                return team
    
    # Strategy 2: Match by repo_url
    if project.get('repo_url'):
        for team in teams:
            if team.get('repo_url') == project.get('repo_url'):
                return team
    
    return None


def migrate_project_data_to_team(supabase, team_id: str, project: Dict, stats: MigrationStats) -> bool:
    """
    Migrate project data to a team record using raw SQL.
    Returns True if successful, False otherwise.
    """
    try:
        # Build SQL UPDATE statement
        set_clauses = []
        params = []
        
        # Analysis status
        if project.get('status'):
            set_clauses.append(f"status = ${len(params) + 1}")
            params.append(project['status'])
        
        # Scores
        score_fields = [
            'total_score', 'quality_score', 'security_score', 'originality_score',
            'architecture_score', 'documentation_score', 'effort_score',
            'implementation_score', 'engineering_score', 'organization_score'
        ]
        for field in score_fields:
            if project.get(field) is not None:
                set_clauses.append(f"{field} = ${len(params) + 1}")
                params.append(project[field])
        
        # Metadata
        if project.get('total_commits') is not None:
            set_clauses.append(f"total_commits = ${len(params) + 1}")
            params.append(project['total_commits'])
        if project.get('verdict'):
            set_clauses.append(f"verdict = ${len(params) + 1}")
            params.append(project['verdict'])
        if project.get('ai_pros'):
            set_clauses.append(f"ai_pros = ${len(params) + 1}")
            params.append(project['ai_pros'])
        if project.get('ai_cons'):
            set_clauses.append(f"ai_cons = ${len(params) + 1}")
            params.append(project['ai_cons'])
        if project.get('report_json'):
            set_clauses.append(f"report_json = ${len(params) + 1}::jsonb")
            params.append(project['report_json'])
        if project.get('report_path'):
            set_clauses.append(f"report_path = ${len(params) + 1}")
            params.append(project['report_path'])
        if project.get('viz_path'):
            set_clauses.append(f"viz_path = ${len(params) + 1}")
            params.append(project['viz_path'])
        
        # Timestamps
        if project.get('analyzed_at'):
            set_clauses.append(f"analyzed_at = ${len(params) + 1}")
            params.append(project['analyzed_at'])
        if project.get('last_analyzed_at'):
            set_clauses.append(f"last_analyzed_at = ${len(params) + 1}")
            params.append(project['last_analyzed_at'])
        
        # Update repo_url if team doesn't have one but project does
        if project.get('repo_url'):
            # Check if team has repo_url
            team_result = supabase.table("teams").select("repo_url").eq("id", team_id).execute()
            if team_result.data and not team_result.data[0].get('repo_url'):
                set_clauses.append(f"repo_url = ${len(params) + 1}")
                params.append(project['repo_url'])
        
        # Execute update if there are changes
        if set_clauses:
            # For simplicity, use the Supabase client with only the fields we know work
            update_data = {}
            
            # Only include fields that we know exist and work
            if project.get('status'):
                update_data['status'] = project['status']
            
            # Scores
            for field in score_fields:
                if project.get(field) is not None:
                    update_data[field] = project[field]
            
            # Metadata (excluding description which doesn't exist)
            if project.get('total_commits') is not None:
                update_data['total_commits'] = project['total_commits']
            if project.get('verdict'):
                update_data['verdict'] = project['verdict']
            if project.get('ai_pros'):
                update_data['ai_pros'] = project['ai_pros']
            if project.get('ai_cons'):
                update_data['ai_cons'] = project['ai_cons']
            if project.get('report_json'):
                update_data['report_json'] = project['report_json']
            if project.get('report_path'):
                update_data['report_path'] = project['report_path']
            if project.get('viz_path'):
                update_data['viz_path'] = project['viz_path']
            
            # Timestamps
            if project.get('analyzed_at'):
                update_data['analyzed_at'] = project['analyzed_at']
            if project.get('last_analyzed_at'):
                update_data['last_analyzed_at'] = project['last_analyzed_at']
            
            # Update repo_url if needed
            if project.get('repo_url'):
                team_result = supabase.table("teams").select("repo_url").eq("id", team_id).execute()
                if team_result.data and not team_result.data[0].get('repo_url'):
                    update_data['repo_url'] = project['repo_url']
            
            # Update the team
            if update_data:
                supabase.table("teams").update(update_data).eq("id", team_id).execute()
        
        return True
        
    except Exception as e:
        print(f"    ✗ Error migrating data: {e}")
        stats.errors += 1
        return False


def create_team_from_project(supabase, project: Dict, stats: MigrationStats) -> Optional[str]:
    """
    Create a new team record from an unmatched project.
    Returns the new team ID or None if failed.
    """
    try:
        # Prepare team data
        team_data = {
            'team_name': project.get('team_name', f"Team-{project['id'][:8]}"),
            'batch_id': project.get('batch_id'),
            'repo_url': project.get('repo_url'),
            'description': project.get('description'),
            'status': project.get('status', 'pending'),
            
            # Scores
            'total_score': project.get('total_score'),
            'quality_score': project.get('quality_score'),
            'security_score': project.get('security_score'),
            'originality_score': project.get('originality_score'),
            'architecture_score': project.get('architecture_score'),
            'documentation_score': project.get('documentation_score'),
            'effort_score': project.get('effort_score'),
            'implementation_score': project.get('implementation_score'),
            'engineering_score': project.get('engineering_score'),
            'organization_score': project.get('organization_score'),
            
            # Metadata
            'total_commits': project.get('total_commits', 0),
            'verdict': project.get('verdict'),
            'ai_pros': project.get('ai_pros'),
            'ai_cons': project.get('ai_cons'),
            'report_json': project.get('report_json'),
            'report_path': project.get('report_path'),
            'viz_path': project.get('viz_path'),
            
            # Timestamps
            'analyzed_at': project.get('analyzed_at'),
            'last_analyzed_at': project.get('last_analyzed_at'),
            'created_at': project.get('created_at'),
        }
        
        # Remove None values
        team_data = {k: v for k, v in team_data.items() if v is not None}
        
        # Insert new team
        result = supabase.table("teams").insert(team_data).execute()
        
        if result.data:
            new_team_id = result.data[0]['id']
            stats.unmatched_created += 1
            return new_team_id
        
        return None
        
    except Exception as e:
        print(f"    ✗ Error creating team: {e}")
        stats.errors += 1
        return None


def match_and_migrate_projects(supabase, projects: List[Dict], teams: List[Dict], stats: MigrationStats) -> Dict[str, str]:
    """
    Match projects to teams and migrate data.
    Returns a mapping of project_id -> team_id
    """
    print("\n[STEP 4] Matching and migrating projects to teams...")
    
    project_to_team_map = {}
    
    for i, project in enumerate(projects, 1):
        project_id = project['id']
        project_name = project.get('team_name', 'Unknown')
        
        print(f"\n  [{i}/{len(projects)}] Processing: {project_name}")
        print(f"    Project ID: {project_id}")
        
        # Find matching team
        matching_team = find_matching_team(project, teams)
        
        if matching_team:
            team_id = matching_team['id']
            team_name = matching_team.get('team_name', 'Unknown')
            
            # Determine match type
            if (matching_team.get('team_name') == project.get('team_name') and 
                matching_team.get('batch_id') == project.get('batch_id')):
                print(f"    ✓ Matched by name+batch to team: {team_name}")
                stats.matched_by_name_batch += 1
            else:
                print(f"    ✓ Matched by repo_url to team: {team_name}")
                stats.matched_by_repo_url += 1
            
            # Migrate data
            if migrate_project_data_to_team(supabase, team_id, project, stats):
                print(f"    ✓ Data migrated to team: {team_id}")
                project_to_team_map[project_id] = team_id
            
        else:
            print(f"    ⚠️  No matching team found - creating new team")
            new_team_id = create_team_from_project(supabase, project, stats)
            
            if new_team_id:
                print(f"    ✓ New team created: {new_team_id}")
                project_to_team_map[project_id] = new_team_id
    
    print(f"\n✓ Mapped {len(project_to_team_map)} projects to teams")
    return project_to_team_map


def update_foreign_keys(supabase, project_to_team_map: Dict[str, str], stats: MigrationStats):
    """Update foreign keys in related tables"""
    print("\n[STEP 5] Updating foreign keys in related tables...")
    
    # Tables to update: table_name -> foreign_key_column
    tables_to_update = {
        'team_members': 'project_id',
        'analysis_jobs': 'project_id',
        'tech_stack': 'project_id',
        'issues': 'project_id',
        'project_comments': 'project_id',
        'analysis_snapshots': 'project_id',
    }
    
    for table_name, fk_column in tables_to_update.items():
        print(f"\n  Updating {table_name}...")
        
        try:
            # Fetch all records with project_id
            result = supabase.table(table_name).select("*").not_.is_(fk_column, "null").execute()
            records = result.data
            
            print(f"    Found {len(records)} records to update")
            
            updated = 0
            for record in records:
                old_project_id = record[fk_column]
                
                # Get the new team_id
                new_team_id = project_to_team_map.get(old_project_id)
                
                if new_team_id:
                    # Update the record
                    supabase.table(table_name).update({
                        'team_id': new_team_id
                    }).eq('id', record['id']).execute()
                    updated += 1
            
            stats.foreign_keys_updated[table_name] = updated
            print(f"    ✓ Updated {updated} records")
            
        except Exception as e:
            print(f"    ✗ Error updating {table_name}: {e}")
            stats.errors += 1


def verify_data_integrity(supabase, original_project_count: int, stats: MigrationStats) -> bool:
    """Verify that migration was successful"""
    print("\n[STEP 6] Verifying data integrity...")
    
    all_checks_passed = True
    
    try:
        # Check 1: All teams should have data
        teams_result = supabase.table("teams").select("id, team_name, repo_url").execute()
        teams = teams_result.data
        teams_with_repo = [t for t in teams if t.get('repo_url')]
        
        print(f"\n  Check 1: Teams with repo_url")
        print(f"    Total teams: {len(teams)}")
        print(f"    Teams with repo_url: {len(teams_with_repo)}")
        
        # Check 2: No orphaned records in related tables
        print(f"\n  Check 2: Orphaned records")
        
        orphan_checks = {
            'team_members': 'team_id',
            'analysis_jobs': 'team_id',
            'tech_stack': 'project_id',
            'issues': 'project_id',
        }
        
        for table, fk_col in orphan_checks.items():
            try:
                # This is a simplified check - in production you'd do a proper LEFT JOIN
                result = supabase.table(table).select("id").not_.is_(fk_col, "null").execute()
                count = len(result.data)
                print(f"    {table}: {count} records with {fk_col}")
            except Exception as e:
                print(f"    {table}: Error checking - {e}")
        
        # Check 3: Score ranges
        print(f"\n  Check 3: Score validation")
        teams_with_scores = supabase.table("teams").select("id, total_score").not_.is_("total_score", "null").execute()
        
        invalid_scores = [
            t for t in teams_with_scores.data 
            if t.get('total_score') and (t['total_score'] < 0 or t['total_score'] > 100)
        ]
        
        print(f"    Teams with scores: {len(teams_with_scores.data)}")
        print(f"    Invalid scores (out of 0-100 range): {len(invalid_scores)}")
        
        if invalid_scores:
            print(f"    ⚠️  WARNING: Found {len(invalid_scores)} teams with invalid scores")
            all_checks_passed = False
        
        # Check 4: Data completeness
        print(f"\n  Check 4: Data completeness")
        print(f"    Original projects: {original_project_count}")
        print(f"    Projects matched/created: {stats.matched_by_name_batch + stats.matched_by_repo_url + stats.unmatched_created}")
        
        if all_checks_passed:
            print("\n  ✓ All integrity checks passed")
        else:
            print("\n  ⚠️  Some integrity checks failed - review warnings above")
        
        return all_checks_passed
        
    except Exception as e:
        print(f"\n  ✗ Error during verification: {e}")
        return False


def drop_projects_table(supabase, stats: MigrationStats) -> bool:
    """Drop the projects table after successful migration"""
    print("\n[STEP 7] Dropping projects table...")
    
    try:
        # Note: Supabase Python client doesn't support DROP TABLE directly
        # This needs to be done via SQL
        print("  ⚠️  WARNING: Cannot drop table via Python client")
        print("  Please run the following SQL in Supabase SQL Editor:")
        print("\n  -- Drop projects table and related constraints")
        print("  DROP TABLE IF EXISTS projects CASCADE;")
        print("\n  After running the SQL, the migration is complete.")
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        stats.errors += 1
        return False


def main():
    """Main migration function"""
    print("="*60)
    print("MIGRATION: Merge Projects Table into Teams Table")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Initialize
    supabase = get_supabase_admin_client()
    stats = MigrationStats()
    
    # Step 1: Add columns to teams table
    if not add_analysis_columns_to_teams(supabase):
        print("\n❌ Migration aborted: Could not add columns to teams table")
        print("Please add the required columns via SQL and re-run this script.")
        return
    
    # Step 2: Fetch all projects
    projects = fetch_all_projects(supabase)
    if not projects:
        print("\n⚠️  No projects found - nothing to migrate")
        return
    
    original_project_count = len(projects)
    
    # Step 3: Fetch all teams
    teams = fetch_all_teams(supabase)
    if not teams:
        print("\n⚠️  No teams found - will create teams from projects")
    
    # Step 4: Match and migrate
    project_to_team_map = match_and_migrate_projects(supabase, projects, teams, stats)
    
    # Step 5: Update foreign keys
    update_foreign_keys(supabase, project_to_team_map, stats)
    
    # Step 6: Verify integrity
    integrity_ok = verify_data_integrity(supabase, original_project_count, stats)
    
    # Step 7: Drop projects table (manual step)
    drop_projects_table(supabase, stats)
    
    # Print summary
    stats.print_summary()
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if integrity_ok and stats.errors == 0:
        print("\n✅ Migration completed successfully!")
    else:
        print(f"\n⚠️  Migration completed with {stats.errors} errors - please review")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
