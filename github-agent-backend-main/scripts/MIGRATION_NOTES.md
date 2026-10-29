# Migration Script - Important Notes

## Supabase Schema Cache Issue

After running the SQL migration to add columns (`migration_add_analysis_columns.sql`), Supabase's PostgREST API layer caches the old schema and doesn't immediately recognize the new columns.

### Symptoms
- Error: `Could not find the 'column_name' column of 'teams' in the schema cache`
- The columns exist in the database but the API can't access them

### Solution
You need to reload the Supabase schema cache. There are two ways to do this:

#### Option 1: Reload Schema via Supabase Dashboard (Recommended)
1. Go to your Supabase project dashboard
2. Navigate to **Settings** → **API**
3. Click **Reload schema cache** button
4. Wait a few seconds for the cache to refresh
5. Re-run the migration script

#### Option 2: Wait for Automatic Refresh
- Supabase automatically refreshes the schema cache every few minutes
- Wait 5-10 minutes after running the SQL migration
- Then run the Python migration script

#### Option 3: Use Raw SQL Migration (Alternative)
Instead of using the Python script with the Supabase client, you can perform the entire migration using raw SQL. See `migration_complete_sql.sql` for a pure SQL approach.

## Current Migration Status

### What Works
✅ SQL migration successfully added all analysis columns to teams table  
✅ Migration script successfully matches projects to teams (92/93 matched by repo_url)  
✅ Foreign key update logic is implemented  
✅ Data integrity verification is implemented  

### What Needs Attention
⚠️ **Schema Cache**: Need to reload Supabase schema cache before running Python script  
⚠️ **One Unmatched Project**: Project "Team 98" has no batch_id and couldn't be migrated  
⚠️ **team_members Table**: Already has team_id column, doesn't need project_id migration  

## Recommended Migration Workflow

### Step 1: Add Columns (DONE ✅)
```bash
# Already completed via mcp_supabase_apply_migration
```

### Step 2: Reload Schema Cache
- Use Supabase Dashboard → Settings → API → Reload schema cache
- OR wait 5-10 minutes

### Step 3: Run Migration Script
```bash
cd "proj-github agent"
python scripts/migrate_projects_to_teams.py
```

### Step 4: Verify Results
```sql
-- Check teams have analysis data
SELECT COUNT(*) FROM teams WHERE total_score IS NOT NULL;

-- Check for orphaned records
SELECT COUNT(*) FROM analysis_jobs WHERE project_id NOT IN (SELECT id FROM projects);
```

### Step 5: Drop Projects Table
```bash
# Run migration_drop_projects_table.sql in Supabase SQL Editor
```

## Known Issues

### Issue 1: Project "Team 98" Missing batch_id
**Problem**: One project (ID: 9466e44e-ccb4-401f-a813-63455706d97a) has no batch_id  
**Impact**: Cannot create a new team record (batch_id is NOT NULL)  
**Solution**: Manually assign a batch_id to this project before migration, or handle it separately

**SQL to fix**:
```sql
-- Find the project
SELECT * FROM projects WHERE team_name = 'Team 98';

-- Update with correct batch_id (replace with actual batch_id)
UPDATE projects 
SET batch_id = 'ba461ac2-7b17-455b-b062-6d08dea73216' 
WHERE id = '9466e44e-ccb4-401f-a813-63455706d97a';
```

### Issue 2: team_members Table Already Migrated
**Problem**: team_members table already has team_id column, not project_id  
**Impact**: Foreign key update step will fail for this table  
**Solution**: Skip team_members in the foreign key update, or check which column exists first

## Migration Statistics (Last Run)

```
Projects matched by repo_url:   92
New teams created:               0
Errors:                          93 (due to schema cache issue)

Foreign Keys Updated:
  team_members              0 (already has team_id)
  analysis_jobs             0 (pending schema cache reload)
  tech_stack                0 (pending schema cache reload)
  issues                    0 (pending schema cache reload)
```

## Next Steps

1. **Reload Supabase schema cache** (via dashboard or wait)
2. **Fix Team 98 batch_id** (run SQL update)
3. **Re-run migration script** (should succeed after cache reload)
4. **Verify all data migrated** (run verification queries)
5. **Drop projects table** (run cleanup SQL)
6. **Update backend code** (use teams table instead of projects)
7. **Update frontend code** (fetch from teams endpoints)

## Testing Checklist

Before running in production:

- [ ] Database backup created
- [ ] Schema cache reloaded
- [ ] Team 98 batch_id fixed
- [ ] Migration script runs without errors
- [ ] All 93 projects matched/migrated
- [ ] Foreign keys updated in all tables
- [ ] No orphaned records
- [ ] Score ranges valid (0-100)
- [ ] Projects table dropped
- [ ] Backend tests pass
- [ ] Frontend displays correctly

## Rollback Plan

If migration fails:

1. **Restore from backup**:
   ```bash
   supabase db restore backup_TIMESTAMP.sql
   ```

2. **Or manually revert**:
   ```sql
   -- The projects table still exists until Step 5
   -- Just don't drop it and you can retry
   ```

## Support

If you encounter issues:
1. Check Supabase logs for detailed error messages
2. Verify schema cache has been reloaded
3. Check that all SQL migrations completed successfully
4. Review the migration script output for specific errors
