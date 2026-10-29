# 📦 OBJECT STORAGE SETUP GUIDE

## 🎯 Goal
Move 300KB `report_json` from database → Supabase Storage
**Expected Impact:** 80% database size reduction (500MB → 100MB)

---

## ✅ STEP 1: Run Database Migration

```powershell
cd "D:\Coding\Github-Agent\proj-github agent"

# Add new columns for storage paths
psql $env:DATABASE_URL -f migrations/002_extract_json_to_columns.sql
```

**This adds:**
- `report_path` (stores file URL)
- `report_size` (tracks size)
- `ai_percentage`, `security_issues_count` (extracted from JSON)

**Expected output:**
```
ALTER TABLE
CREATE INDEX
UPDATE 300
```

---

## ✅ STEP 2: Create Supabase Storage Bucket

### **Option A: Auto-Create (Easiest)**

The code will auto-create the bucket on first use:

```python
# This runs automatically when you start migration
from src.api.backend.utils.report_storage import ReportStorageManager

ReportStorageManager.ensure_bucket_exists()
# ✅ Creates "team-reports" bucket automatically
```

### **Option B: Manual Creation (via Supabase Dashboard)**

1. Go to: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/storage/buckets
2. Click **"New Bucket"**
3. Settings:
   - **Name:** `team-reports`
   - **Public:** ❌ No (Private)
   - **File size limit:** 10MB
   - **Allowed MIME types:** `application/json`
4. Click **Create**

---

## ✅ STEP 3: Configure Storage Policies (IMPORTANT)

**Go to:** Storage → Policies → `team-reports` bucket

### **Add These Policies:**

#### **Policy 1: Allow Service Role to Upload**
```sql
CREATE POLICY "Service role can insert reports"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'team-reports' 
  AND auth.jwt()->>'role' = 'service_role'
);
```

#### **Policy 2: Allow Service Role to Read**
```sql
CREATE POLICY "Service role can read reports"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'team-reports'
  AND auth.jwt()->>'role' = 'service_role'
);
```

#### **Policy 3: Allow Service Role to Update**
```sql
CREATE POLICY "Service role can update reports"
ON storage.objects FOR UPDATE
TO authenticated
USING (
  bucket_id = 'team-reports'
  AND auth.jwt()->>'role' = 'service_role'
);
```

---

## ✅ STEP 4: Test Storage Upload

Create a test script:

```python
# test_storage_upload.py
import sys
sys.path.append('proj-github agent/src/api')

from backend.utils.report_storage import ReportStorageManager
from uuid import UUID

# Test upload
test_team_id = UUID("YOUR_TEAM_ID_HERE")  # Replace with real team ID
test_report = {
    "commit_details": {"total_commits": 100},
    "security_issues": [],
    "ai_generated_percentage": 15.5
}

try:
    result = ReportStorageManager.save_report_to_storage(test_team_id, test_report)
    print("✅ Upload successful!")
    print(f"Path: {result['report_path']}")
    print(f"Size: {result['report_size']} bytes")
except Exception as e:
    print(f"❌ Upload failed: {e}")
```

**Run it:**
```powershell
python test_storage_upload.py
```

**Expected output:**
```
✅ Upload successful!
Path: team-reports/abc123-def4-5678-9012-345678901234.json
Size: 1234 bytes
```

---

## ✅ STEP 5: Migrate Existing Teams to Storage

**⚠️ RUN DURING LOW-TRAFFIC HOURS (2-6 AM)**

```python
# migrate_to_storage.py
import sys
sys.path.append('proj-github agent/src/api')

from backend.utils.report_storage import ReportStorageManager
import asyncio

async def run_migration():
    """Migrate all teams to storage"""
    
    print("🚀 Starting migration...")
    print("⏱️  This will take 10-30 minutes for 300 teams")
    
    results = await ReportStorageManager.migrate_all_teams(
        batch_size=50,  # Process 50 teams at a time
        dry_run=False   # Set to True to test first
    )
    
    print(f"\n✅ Migration complete!")
    print(f"   Migrated: {results['migrated']}")
    print(f"   Failed: {results['failed']}")
    print(f"   Skipped: {results['skipped']}")

# Run migration
asyncio.run(run_migration())
```

**Run with dry-run first:**
```powershell
# Test mode (no changes)
# Edit migrate_to_storage.py: dry_run=True
python migrate_to_storage.py

# Real migration (after dry-run succeeds)
# Edit migrate_to_storage.py: dry_run=False
python migrate_to_storage.py
```

---

## ✅ STEP 6: Update Code to Use Storage

Replace the old `save_analysis_results()` function:

### **File: `src/api/backend/services/data_mapper.py`**

Find line ~238 (the old function):
```python
async def save_analysis_results(...):
    # OLD CODE - builds report_json
```

Replace with:
```python
from src.api.backend.utils.report_storage import ReportStorageManager

async def save_analysis_results(...):
    """Save analysis results using storage system"""
    
    # Build report JSON as before
    report_json = {
        "commit_details": commit_details_summary,
        "security_issues": security_issues,
        # ... rest of report
    }
    
    # 🆕 NEW: Save to storage instead of database
    storage_result = ReportStorageManager.save_report_to_storage(
        team_id=team_id,
        report_json=report_json
    )
    
    # 🆕 NEW: Update team with storage path (not full JSON)
    await supabase.table("teams").update({
        "report_path": storage_result["report_path"],
        "report_size": storage_result["report_size"],
        "report_summary": storage_result["report_summary"],  # <50KB
        "ai_percentage": report_json.get("aiGeneratedPercentage", 0),
        "security_issues_count": len(security_issues),
        # ... other columns
    }).eq("id", team_id).execute()
    
    # ✅ No more 300KB report_json in database!
```

---

## ✅ STEP 7: Update Report Retrieval

### **File: `src/api/backend/routers/reports.py`**

For **detail view** (single team):

```python
@router.get("/teams/{team_id}/report")
async def get_team_report(team_id: UUID):
    """Get full report (from storage)"""
    
    # Get team with storage path
    team = await supabase.table("teams").select(
        "id, team_name, report_path, report_summary"
    ).eq("id", team_id).single().execute()
    
    # 🆕 Fetch full report from storage
    full_report = ReportStorageManager.get_report_from_storage(
        team["report_path"]
    )
    
    return {
        "team": team,
        "report": full_report  # 300KB, but only for detail view
    }
```

For **leaderboard** (NO storage access):

```python
@router.get("/leaderboard")
async def get_leaderboard(batch_id: UUID):
    """Get leaderboard (NO report_json, NO storage)"""
    
    # ✅ Only use columns - NEVER touch JSON or storage
    teams = await supabase.table("teams").select(
        "id, team_name, total_score, ai_percentage, security_issues_count"
        # NO report_json, NO report_path
    ).eq("batch_id", batch_id).execute()
    
    return teams  # <10KB per team, blazing fast
```

---

## ✅ STEP 8: Verify Migration Success

```sql
-- Check migration status
psql $env:DATABASE_URL -c "
SELECT 
    COUNT(*) as total_teams,
    COUNT(*) FILTER (WHERE report_path IS NOT NULL) as migrated_to_storage,
    COUNT(*) FILTER (WHERE report_json IS NOT NULL) as still_in_db,
    AVG(report_size) as avg_report_size_bytes,
    SUM(report_size) / 1024 / 1024 as total_storage_mb
FROM teams;
"
```

**Expected output:**
```
 total_teams | migrated_to_storage | still_in_db | avg_report_size_bytes | total_storage_mb
-------------+---------------------+-------------+-----------------------+------------------
         300 |                 300 |         300 |                150000 |               43
```

**After successful migration (Phase 2):**
```sql
-- Remove report_json column (after confirming storage works)
-- ⚠️ BACKUP DATABASE FIRST!
ALTER TABLE teams DROP COLUMN report_json;

-- Check database size reduction
SELECT pg_size_pretty(pg_database_size('postgres')) as db_size;
```

**Expected:** 500MB → 100-150MB (70-80% reduction)

---

## 📊 Before/After Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Database size | 500MB | 100-150MB | **70-80% smaller** |
| Leaderboard query | 10-15s | 1-2s | **80-90% faster** |
| Data per team (hot path) | 300KB | <5KB | **98% less** |
| Disk IO | 100% | 20-30% | **70-80% reduction** |
| Storage cost | $25/mo | $5/mo DB + $2/mo storage | **72% cheaper** |

---

## 🚨 IMPORTANT NOTES

1. **Backup first:**
   ```bash
   pg_dump $DATABASE_URL > backup_before_storage_migration.sql
   ```

2. **Run migration during low traffic** (2-6 AM)

3. **Keep report_json column for 1 week** as backup
   - After 1 week of stable storage: DROP COLUMN report_json

4. **Monitor storage usage:**
   - Supabase Dashboard → Storage → team-reports bucket
   - Should be ~40-50MB for 300 teams

5. **Set up storage retention** (optional):
   - Delete reports older than 90 days
   - Archive to S3 Glacier for long-term storage

---

## ✅ SUCCESS CRITERIA

- [ ] Bucket "team-reports" exists
- [ ] Storage policies configured
- [ ] Test upload works
- [ ] 300 teams migrated (report_path set)
- [ ] Database size reduced (500MB → 150MB)
- [ ] Leaderboard <2s (no JSON access)
- [ ] Detail view works (fetches from storage)

---

## 🆘 Troubleshooting

**Error: "Bucket not found"**
```python
# Run auto-create
from src.api.backend.utils.report_storage import ReportStorageManager
ReportStorageManager.ensure_bucket_exists()
```

**Error: "Permission denied"**
- Check storage policies (see Step 3)
- Ensure service_role key is used

**Error: "File too large"**
- Check report size: Should be <150KB
- If larger, enable compression in report_storage.py

**Migration stuck:**
```python
# Check progress
psql $env:DATABASE_URL -c "
SELECT COUNT(*) FROM teams WHERE report_path IS NOT NULL;
"
```

---

## 🎉 Next Steps After Storage Migration

1. ✅ Monitor disk IO (should drop 70-80%)
2. ✅ Add caching (Redis) for leaderboard
3. ✅ Remove report_json column (after 1 week)
4. ✅ Set up automated backups for storage bucket

**See IMPLEMENTATION_GUIDE.md for full workflow**
