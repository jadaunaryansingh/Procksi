# Migration Verification Script

## Overview

The `verify_migration.py` script validates that the projects-to-teams migration completed successfully. It performs comprehensive checks on data integrity, relationships, and migration completeness.

## Purpose

This script should be run **after** the migration script (`migrate_projects_to_teams.py`) to ensure:
- All data was migrated correctly
- No data was lost
- All relationships are valid
- Score ranges are correct
- Foreign keys are properly updated

## Usage

### Basic Usage

```bash
cd "proj-github agent"
python scripts/verify_migration.py
```

### Expected Output

The script will:
1. Check all teams have `repo_url`
2. Verify no orphaned foreign keys
3. Validate score ranges (0-100)
4. Count records in all tables
5. Check data integrity and relationships
6. Generate a detailed report file

### Exit Codes

- **0**: All checks passed - migration successful
- **1**: One or more checks failed - review errors

## Verification Checks

### Check 1: Teams Have repo_url
- **Purpose**: Ensure all teams have GitHub repository URLs
- **Pass Criteria**: 100% of teams have `repo_url` populated
- **Warning**: Lists teams without `repo_url`

### Check 2: Orphaned Foreign Keys
- **Purpose**: Verify all foreign key relationships are valid
- **Pass Criteria**: 
  - No orphaned `team_id` references in related tables
  - No remaining `project_id` references (should be migrated to `team_id`)
- **Tables Checked**:
  - `team_members`
  - `analysis_jobs`
  - `tech_stack`
  - `issues`
  - `project_comments`
  - `analysis_snapshots`

### Check 3: Score Ranges
- **Purpose**: Validate all analysis scores are within valid range
- **Pass Criteria**: All scores between 0 and 100
- **Score Fields Checked**:
  - `total_score`
  - `quality_score`
  - `security_score`
  - `originality_score`
  - `architecture_score`
  - `documentation_score`
  - `effort_score`
  - `implementation_score`
  - `engineering_score`
  - `organization_score`

### Check 4: Record Counts
- **Purpose**: Count records in all tables and verify projects table is dropped
- **Pass Criteria**: 
  - Projects table is empty or dropped
  - All other tables have expected record counts
- **Tables Counted**:
  - `teams`
  - `batches`
  - `students`
  - `team_members`
  - `analysis_jobs`
  - `users`

### Check 5: Data Integrity
- **Purpose**: Verify data consistency and relationships
- **Pass Criteria**:
  - Teams with scores have `analyzed_at` timestamp
  - All teams reference valid batches
  - All students reference valid teams

## Output

### Console Output

The script provides real-time feedback with:
- ✓ Passed checks (green)
- ✗ Failed checks (red)
- ⚠️ Warnings (yellow)

### Report File

A detailed report is saved to:
```
scripts/migration_verification_report_YYYYMMDD_HHMMSS.txt
```

The report includes:
- Overall status (PASS/FAIL)
- Checks passed/failed count
- Database statistics
- Detailed errors
- Warnings

## Example Output

### Successful Verification

```
======================================================================
MIGRATION VERIFICATION
======================================================================
Started at: 2025-01-17 10:30:00

[CHECK 1] Verifying teams have repo_url...
    ✓ All teams have repo_url

[CHECK 2] Checking for orphaned foreign keys...
    ✓ team_members: No orphaned team_id references
    ✓ analysis_jobs: No orphaned team_id references
    ✓ team_members: No project_id references (migrated)
    ✓ analysis_jobs: No project_id references (migrated)

[CHECK 3] Validating score ranges...
    ✓ All score fields have valid ranges

[CHECK 4] Counting records in all tables...
    ✓ Projects table dropped or inaccessible
    ✓ teams: 98 records

[CHECK 5] Verifying data integrity...
    ✓ All teams with scores have analyzed_at timestamp
    ✓ All teams have valid batch_id references
    ✓ All students have valid team_id references

======================================================================
VERIFICATION SUMMARY
======================================================================
✅ ALL CHECKS PASSED

Checks Passed: 30
Checks Failed: 0
Warnings: 0

✅ Migration verification PASSED - 100% data integrity confirmed!
📄 Detailed report: scripts/migration_verification_report_20250117_103005.txt
```

### Failed Verification

```
======================================================================
VERIFICATION SUMMARY
======================================================================
❌ 3 CHECK(S) FAILED

Checks Passed: 20
Checks Failed: 3
Warnings: 5

----------------------------------------------------------------------
ERRORS
----------------------------------------------------------------------
  ✗ Some teams missing repo_url: 6 teams without repo_url
  ✗ team_members: Still has project_id references: 153 records
  ✗ Projects table still exists: 93 records found

❌ Migration verification FAILED - 3 issue(s) found
Please review the errors above and fix any issues.
```

## Troubleshooting

### Issue: "Some teams missing repo_url"
**Cause**: Teams were created without GitHub repository URLs  
**Solution**: 
- Check if these teams should have repo URLs
- Update teams manually if needed
- Re-run bulk import with correct data

### Issue: "Still has project_id references"
**Cause**: Migration script didn't complete foreign key updates  
**Solution**:
- Re-run migration script
- Check migration logs for errors
- Manually update foreign keys if needed

### Issue: "Projects table still exists"
**Cause**: Projects table wasn't dropped after migration  
**Solution**:
- Run the SQL script: `scripts/migration_drop_projects_table.sql`
- Or manually drop the table in Supabase SQL Editor

### Issue: "Invalid batch references"
**Cause**: Teams reference batches that don't exist  
**Solution**:
- Check if batches were deleted
- Verify batch IDs are correct
- Update team records with valid batch IDs

## Pre-Migration vs Post-Migration

### Before Migration (Expected Failures)
- ✗ Projects table still exists
- ✗ Foreign keys still reference project_id
- ⚠️ team_id columns don't exist yet

### After Migration (Expected Success)
- ✓ Projects table dropped
- ✓ All foreign keys reference team_id
- ✓ No orphaned records
- ✓ All data migrated

## Integration with Migration Workflow

1. **Backup Database**
   ```bash
   # Create backup before migration
   ```

2. **Run Migration**
   ```bash
   python scripts/migrate_projects_to_teams.py
   ```

3. **Verify Migration** ← **This Script**
   ```bash
   python scripts/verify_migration.py
   ```

4. **Review Report**
   - Check console output
   - Review detailed report file
   - Fix any issues found

5. **Drop Projects Table** (if verification passes)
   ```sql
   DROP TABLE IF EXISTS projects CASCADE;
   ```

## Requirements

- Python 3.8+
- Supabase Python client
- Environment variables:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_KEY`

## Notes

- The script uses the **admin client** (service role key) to access all data
- No data is modified - this is a read-only verification
- Safe to run multiple times
- Can be run before or after migration to compare results

## Related Scripts

- `migrate_projects_to_teams.py` - Main migration script
- `rollback_migration.py` - Rollback script (if needed)
- `migration_add_analysis_columns.sql` - SQL to add columns
- `migration_drop_projects_table.sql` - SQL to drop projects table

## Support

If verification fails:
1. Review the detailed report file
2. Check migration logs
3. Verify database state in Supabase dashboard
4. Run rollback script if needed
5. Fix issues and re-run migration
