# Database Flush Script

## Overview

The `flush_database.py` script safely clears all data from the database while preserving the schema structure. This prepares the database for a clean migration by removing all existing records.

## Purpose

Use this script when you want to:
- Start fresh with a clean database
- Prepare for bulk data import
- Test migration scripts on clean data
- Remove all test/development data

## ⚠️ WARNING

**This script DELETES ALL DATA from the database!**
- This action cannot be undone without a backup
- Make sure you have a recent backup before running
- All records will be permanently deleted

## Usage

### Step 1: Create Backup (REQUIRED)

Before flushing, create a backup:

```bash
# Using Supabase dashboard: Database → Backups → Create backup
# Or use pg_dump if you have direct access
```

### Step 2: Run Flush Script

```bash
cd "proj-github agent"
python scripts/flush_database.py
```

### Step 3: Confirm Flush

The script will:
1. Show current record counts
2. Ask for confirmation
3. Require you to type `FLUSH` to proceed

```
⚠️  WARNING: This will delete 450 records from 15 tables!
This action cannot be undone without a backup.

Type 'FLUSH' to confirm: FLUSH
```

### Step 4: Verify Results

The script will:
- Delete all records in correct order
- Verify database is empty
- Generate a detailed report

## What Gets Deleted

### Tables Flushed (in order)
1. **analysis_history** - Analysis history records
2. **analysis_snapshots** - Analysis snapshots
3. **analysis_jobs** - Analysis job queue
4. **team_members** - Team member relationships
5. **tech_stack** - Technology stack data
6. **issues** - Issue tracking data
7. **project_comments** - Project comments
8. **students** - Student records
9. **projects** - Project records (will be dropped in migration)
10. **teams** - Team records
11. **batches** - Batch/semester records
12. **users** - Non-admin users only (admin users are preserved)

### What's Preserved
- ✅ **Database schema** - All tables, columns, indexes remain
- ✅ **Admin users** - Users with role='admin' are kept
- ✅ **Constraints** - Foreign keys, checks, etc. remain intact

## Deletion Order

The script deletes data in the correct order to respect foreign key constraints:

```
Children First → Parents Last

analysis_history
analysis_snapshots
analysis_jobs
    ↓
team_members
tech_stack
issues
project_comments
    ↓
students
    ↓
projects
    ↓
teams
    ↓
batches
    ↓
users (non-admin only)
```

## Output

### Console Output

```
======================================================================
DATABASE FLUSH SCRIPT
======================================================================
Started at: 2025-01-17 14:30:00

[STEP 1] Recording current data counts...

Before Flush:
----------------------------------------------------------------------
  analysis_history               50 records
  analysis_jobs                  92 records
  team_members                  153 records
  students                      153 records
  projects                       93 records
  teams                          98 records
  batches                         2 records
  users                          15 records
----------------------------------------------------------------------
  TOTAL                         656 records

⚠️  WARNING: This will delete 656 records from 15 tables!
This action cannot be undone without a backup.

Type 'FLUSH' to confirm: FLUSH

[STEP 2] Flushing database tables...

  Flushing analysis_history...
    ✓ Deleted 50 records from analysis_history
  
  Flushing analysis_jobs...
    ✓ Deleted 92 records from analysis_jobs
  
  ...

[STEP 3] Verifying database is empty...

After Flush:
----------------------------------------------------------------------
  ✓ analysis_history                0 records
  ✓ analysis_jobs                   0 records
  ✓ team_members                    0 records
  ✓ students                        0 records
  ✓ projects                        0 records
  ✓ teams                           0 records
  ✓ batches                         0 records
  ✓ users                           2 records (admin users kept)
----------------------------------------------------------------------
  TOTAL                             2 records

✅ Database successfully flushed!

[STEP 4] Generating flush report...
  ✓ Report saved to: scripts/flush_report_20250117_143005.txt

======================================================================
DATABASE FLUSH SUMMARY
======================================================================

Records Deleted:
----------------------------------------------------------------------
  analysis_history               50 records
  analysis_jobs                  92 records
  team_members                  153 records
  students                      153 records
  projects                       93 records
  teams                          98 records
  batches                         2 records
  users                          13 records
----------------------------------------------------------------------
  TOTAL                         654 records

======================================================================

Completed at: 2025-01-17 14:30:15

✅ Database flush completed successfully!

Next steps:
  1. Run bulk import to refill database
  2. Run migration script: python scripts/migrate_projects_to_teams.py
  3. Verify migration: python scripts/verify_migration.py
```

### Report File

A detailed report is saved to:
```
scripts/flush_report_YYYYMMDD_HHMMSS.txt
```

The report includes:
- Before flush counts
- Records deleted per table
- After flush counts
- Any errors encountered

## Next Steps After Flush

### 1. Bulk Import Data

Import your data using the bulk import functionality:

```bash
# Via API
POST /api/admin/bulk-import
# Upload CSV/Excel file with team data

# Or via frontend
# Navigate to Admin → Teams → Import Teams
```

### 2. Run Migration

After importing data, run the migration:

```bash
python scripts/migrate_projects_to_teams.py
```

### 3. Verify Migration

Verify the migration was successful:

```bash
python scripts/verify_migration.py
```

## Troubleshooting

### Issue: Foreign Key Constraint Errors

**Cause**: Tables deleted in wrong order  
**Solution**: The script handles this automatically by deleting in correct order

### Issue: Some Records Remain

**Cause**: Deletion failed for some records  
**Solution**: 
- Check the error messages in console output
- Review the flush report file
- Manually delete remaining records if needed

### Issue: Admin Users Deleted

**Cause**: Users table was flushed completely  
**Solution**: 
- Restore from backup
- The script is designed to keep admin users, but verify your admin users have role='admin'

### Issue: Script Hangs

**Cause**: Large number of records or slow connection  
**Solution**:
- Be patient - deletion happens in batches of 100
- Check your internet connection
- Verify Supabase service is running

## Safety Features

1. **Confirmation Required**: Must type 'FLUSH' to proceed
2. **Record Counts Shown**: See exactly what will be deleted
3. **Progress Reporting**: Real-time feedback during deletion
4. **Error Handling**: Continues even if some deletions fail
5. **Verification**: Confirms database is empty after flush
6. **Report Generation**: Detailed log of what was deleted
7. **Admin Preservation**: Keeps admin users for system access

## Rollback

If you need to restore data after flush:

### Option 1: Restore from Backup

```bash
# Using Supabase dashboard
# Database → Backups → Restore from backup

# Or using pg_restore
pg_restore -d database_name backup_file.sql
```

### Option 2: Re-import Data

If you have the original CSV/Excel files:
1. Use bulk import to re-import teams
2. Re-run analysis if needed

## Performance

- **Small database** (< 1000 records): ~30 seconds
- **Medium database** (1000-10000 records): 1-3 minutes
- **Large database** (> 10000 records): 5-10 minutes

Deletion happens in batches of 100 records to avoid timeouts.

## Requirements

- Python 3.8+
- Supabase Python client
- Environment variables:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_KEY`
- Admin/service role access to database

## Related Scripts

- `migrate_projects_to_teams.py` - Main migration script
- `verify_migration.py` - Verification script
- `rollback_migration.py` - Rollback script

## When to Use This Script

✅ **Good Use Cases**:
- Starting fresh with clean data
- Testing migration on clean database
- Removing all test/development data
- Preparing for production data import

❌ **Bad Use Cases**:
- Production database with live data (use migration instead)
- Partial data cleanup (use targeted deletes instead)
- Without a backup (ALWAYS backup first!)

## Exit Codes

- **0**: Flush completed successfully
- **1**: Flush failed or was cancelled

## Support

If you encounter issues:
1. Check the console output for error messages
2. Review the flush report file
3. Verify you have admin access to Supabase
4. Ensure database is accessible
5. Check for any locks on tables

## Important Notes

- This script does NOT drop tables - only deletes data
- Schema remains intact after flush
- Admin users are preserved for system access
- Always create a backup before flushing
- Cannot be undone without a backup
- Safe to run multiple times (idempotent)
