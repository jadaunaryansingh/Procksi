# Projects to Teams Table Migration

This directory contains scripts for migrating data from the `projects` table into the `teams` table, consolidating the database schema.

## Overview

The migration consolidates two separate tables (`teams` and `projects`) that store overlapping data into a single unified `teams` table. This eliminates data duplication, fixes broken relationships, and simplifies the architecture.

### Current State
- **teams table**: 98 rows, all have repo_url, none have project_id
- **projects table**: 93 rows, all have repo_url, none have team_id
- **Relationship**: BROKEN - no links between tables

### Target State
- **teams table**: Unified table with all team and analysis data
- **projects table**: DROPPED
- **Related tables**: Updated to reference teams instead of projects

## Migration Files

1. **migration_add_analysis_columns.sql** - Adds analysis columns to teams table
2. **migrate_projects_to_teams.py** - Main migration script (Python)
3. **migration_drop_projects_table.sql** - Drops the projects table after migration
4. **verify_migration.py** - Verification script (to be created)

## Prerequisites

1. **Database Backup**: Create a full backup before starting
   ```bash
   # Using Supabase dashboard or CLI
   supabase db dump > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Environment Setup**: Ensure you have the required environment variables
   ```bash
   SUPABASE_URL=your_supabase_url
   SUPABASE_SERVICE_KEY=your_service_key
   ```

3. **Python Dependencies**: Install required packages
   ```bash
   pip install supabase python-dotenv
   ```

## Migration Steps

### Step 1: Add Analysis Columns to Teams Table

Run the SQL script in Supabase SQL Editor:

```bash
# Copy the contents of migration_add_analysis_columns.sql
# and run it in Supabase SQL Editor
```

Or use the Supabase CLI:
```bash
supabase db execute -f scripts/migration_add_analysis_columns.sql
```

**Verification**: The script will output the newly added columns. Verify that all 21 columns were added successfully.

### Step 2: Run the Migration Script

Execute the Python migration script:

```bash
cd "proj-github agent"
python scripts/migrate_projects_to_teams.py
```

**What it does**:
1. Verifies all required columns exist in teams table
2. Fetches all projects (93 rows) and teams (98 rows)
3. Matches projects to teams using:
   - Primary: `team_name` + `batch_id`
   - Fallback: `repo_url`
4. Migrates analysis data to matched teams
5. Creates new team records for unmatched projects
6. Updates foreign keys in related tables:
   - `team_members`
   - `analysis_jobs`
   - `tech_stack`
   - `issues`
   - `project_comments`
   - `analysis_snapshots`
7. Verifies data integrity
8. Provides SQL to drop the projects table

**Expected Output**:
```
MIGRATION SUMMARY
==========================================
Projects matched by name+batch: ~85
Projects matched by repo_url:   ~5
New teams created:               ~3
Errors:                          0

Foreign Keys Updated:
  team_members              153
  analysis_jobs             92
  tech_stack                95
  issues                    2
  project_comments          0
  analysis_snapshots        0
==========================================
```

### Step 3: Verify Migration Success

Review the migration output and verify:

- [ ] All projects were matched or converted (93 total)
- [ ] No errors reported
- [ ] Foreign keys updated in all related tables
- [ ] Data integrity checks passed

You can also run manual verification queries:

```sql
-- Check teams with analysis data
SELECT COUNT(*) FROM teams WHERE total_score IS NOT NULL;

-- Check for orphaned records
SELECT COUNT(*) FROM team_members WHERE team_id NOT IN (SELECT id FROM teams);
SELECT COUNT(*) FROM analysis_jobs WHERE team_id NOT IN (SELECT id FROM teams);

-- Verify score ranges
SELECT COUNT(*) FROM teams WHERE total_score < 0 OR total_score > 100;
```

### Step 4: Drop the Projects Table

After verifying the migration was successful, run the cleanup SQL:

```bash
# Copy the contents of migration_drop_projects_table.sql
# and run it in Supabase SQL Editor
```

Or use the Supabase CLI:
```bash
supabase db execute -f scripts/migration_drop_projects_table.sql
```

**Verification**: Query to confirm the table is gone:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' AND table_name = 'projects';
-- Should return no rows
```

## Rollback Procedure

If the migration fails or produces unexpected results:

### Option 1: Restore from Backup (Recommended)

```bash
# Restore the database from backup
supabase db restore backup_TIMESTAMP.sql
```

### Option 2: Manual Rollback

If you need to rollback after Step 2 but before Step 4:

1. The projects table still exists, so no data is lost
2. You can re-run the migration script after fixing any issues
3. The script is idempotent for most operations

## Data Matching Strategy

The migration uses a two-tier matching strategy:

### Primary Match: team_name + batch_id
```python
if (team.team_name == project.team_name AND 
    team.batch_id == project.batch_id):
    # Match found
```

### Fallback Match: repo_url
```python
if team.repo_url == project.repo_url:
    # Match found
```

### No Match: Create New Team
```python
# Creates a new team record with all project data
new_team = create_team_from_project(project)
```

## Foreign Key Updates

The script updates the following tables to use `team_id` instead of `project_id`:

| Table | Records | Foreign Key |
|-------|---------|-------------|
| team_members | 153 | project_id → team_id |
| analysis_jobs | 92 | project_id → team_id |
| tech_stack | 95 | project_id → team_id |
| issues | 2 | project_id → team_id |
| project_comments | 0 | project_id → team_id |
| analysis_snapshots | 0 | project_id → team_id |

## Troubleshooting

### Issue: "Column already exists" error

**Solution**: The script checks for existing columns. If you see this, the columns were already added. You can proceed to Step 2.

### Issue: "No matching team found" warnings

**Solution**: This is expected for projects that don't have corresponding teams. The script will create new team records for these projects.

### Issue: Foreign key constraint violations

**Solution**: This indicates orphaned records. Check the verification output and manually clean up any orphaned records before proceeding.

### Issue: Migration script hangs or times out

**Solution**: 
1. Check your database connection
2. Verify Supabase service key has admin privileges
3. Check for any locks on the tables
4. Try running during low-traffic period

## Post-Migration Tasks

After successful migration:

1. **Update Backend Code**: Update API endpoints to use teams table
2. **Update Frontend Code**: Update components to fetch from teams endpoints
3. **Update Tests**: Update test suites to reflect new schema
4. **Monitor Logs**: Watch for any errors in production
5. **Update Documentation**: Update API docs and database schema docs

## Performance Impact

**Expected Improvements**:
- API response time: 60-75% faster (no joins needed)
- Database queries: Simpler, single-table queries
- Frontend load time: Fewer API calls required

**Before** (with joins):
```sql
SELECT t.*, p.* 
FROM teams t 
LEFT JOIN projects p ON t.project_id = p.id
WHERE t.batch_id = 'uuid';
-- Average: 150ms
```

**After** (single table):
```sql
SELECT * FROM teams WHERE batch_id = 'uuid';
-- Average: 50ms (3x faster)
```

## Support

If you encounter issues during migration:

1. Check the migration output for specific error messages
2. Review the verification queries
3. Check Supabase logs for database errors
4. Ensure you have a recent backup before proceeding

## Success Criteria

✅ Migration is successful when:
- All 98 teams have complete data
- All 93 projects matched or converted
- No orphaned records in related tables
- All integrity checks pass
- Projects table dropped
- No errors in application logs

## Timeline

- **Preparation**: 30 minutes (backup, review scripts)
- **Step 1** (Add columns): 2 minutes
- **Step 2** (Run migration): 5-10 minutes
- **Step 3** (Verification): 5 minutes
- **Step 4** (Drop table): 1 minute

**Total**: ~45 minutes (including verification)
