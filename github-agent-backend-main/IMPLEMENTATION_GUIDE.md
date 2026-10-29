# 🚀 CRITICAL DATABASE IO FIXES - IMPLEMENTATION GUIDE

**Created:** 2026-04-07  
**Priority:** CRITICAL  
**Expected Impact:** 70-90% reduction in disk IO

---

## 📋 PRE-FLIGHT CHECKLIST

Before starting, verify:

```bash
# 1. Backup database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# 2. Check current database size
SELECT pg_size_pretty(pg_database_size(current_database()));

# 3. Check Redis connection
redis-cli ping

# 4. Verify Supabase Storage access
# Login to Supabase dashboard → Storage → Check permissions
```

---

## ⚡ PHASE 1: IMMEDIATE FIXES (Next 2 Hours)

### ✅ **Step 1: Create Database Indexes (10 minutes)**

**Expected Impact:** 90% query speedup

```bash
cd proj-github agent/migrations

# Run index creation (safe - uses CONCURRENTLY)
psql $DATABASE_URL -f 001_add_critical_indexes.sql

# Verify indexes created
psql $DATABASE_URL -c "
SELECT tablename, indexname 
FROM pg_indexes 
WHERE schemaname = 'public' 
ORDER BY tablename;
"
```

**Verification:**
```bash
# Check query performance (should be much faster)
psql $DATABASE_URL -c "
EXPLAIN ANALYZE 
SELECT id, team_name, total_score 
FROM teams 
WHERE batch_id = 'YOUR_BATCH_ID' 
AND status = 'completed';
"

# Look for "Index Scan" instead of "Seq Scan"
```

✅ **Mark as complete:** `status = 'done'` in todos table

---

### ✅ **Step 2: Deploy Optimized Queries (5 minutes)**

**File already fixed:** `src/api/backend/routers/reports.py`

**Changes made:**
- ✅ Line 71-73: Removed `"*, students(*)"` → Specific columns only
- ✅ Line 84-111: Removed JSON.loads() loop → Direct column access
- ✅ Line 137-146: Removed expensive JSON parsing for AI/security stats

**Deploy:**
```bash
# Restart backend
pm2 restart backend
# OR
systemctl restart github-agent-api
# OR
docker-compose restart api
```

**Verification:**
```bash
# Test leaderboard endpoint
curl -X GET "https://your-domain.com/api/reports/batch/{BATCH_ID}" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Check response time (should be <2s instead of 10-15s)
time curl -X GET "https://your-domain.com/api/reports/batch/{BATCH_ID}"
```

✅ **Mark as complete:** `status = 'done'`

---

### ✅ **Step 3: Add Monitoring Middleware (5 minutes)**

**File created:** `src/api/backend/middleware/performance.py`

**Add to main.py:**

```python
# main.py - Add at the top with other imports
from src.api.backend.middleware.performance import PerformanceMonitoringMiddleware

# Add middleware (after CORS, before routes)
app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_threshold=1.0  # Log requests >1 second
)
```

**Add monitoring endpoint:**

```python
# main.py - Add this endpoint
@app.get("/api/admin/performance-stats")
async def get_performance_stats(current_user: dict = Depends(get_current_user)):
    """Get performance monitoring statistics"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from src.api.backend.middleware.performance import app.state.performance_middleware
    return app.state.performance_middleware.get_stats()
```

**Verification:**
```bash
# Check logs for slow request warnings
tail -f logs/api.log | grep "SLOW REQUEST"

# Should see timing headers in responses
curl -I "https://your-domain.com/api/teams"
# Look for: X-Response-Time: 0.123s
```

✅ **Mark as complete:** `status = 'done'`

---

## 🔥 PHASE 2: STORAGE MIGRATION (Next 4-6 Hours)

### ⚠️ **Step 4: Prepare Storage Migration**

**File created:** `src/api/backend/utils/report_storage.py`

**A. Create Supabase Storage Bucket (5 minutes):**

```python
# Run this once to create bucket
python -c "
from src.api.backend.utils.report_storage import ReportStorageManager
ReportStorageManager.ensure_bucket_exists()
"
```

**Verify in Supabase Dashboard:**
- Go to Storage
- Bucket "team-reports" should exist
- Set to Private
- Max file size: 10MB

---

**B. Add New Columns (5 minutes):**

```bash
# Add columns for storage migration
psql $DATABASE_URL -f migrations/002_extract_json_to_columns.sql
```

**Verify columns added:**
```bash
psql $DATABASE_URL -c "
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'teams' 
AND column_name IN ('report_path', 'report_size', 'ai_percentage', 'security_issues_count');
"
```

---

**C. Update data_mapper.py (30 minutes):**

**File:** `src/api/backend/services/data_mapper.py`

**Replace the `save_analysis_results` function:**

```python
# At top of file, add import
from src.api.backend.utils.report_storage import save_analysis_results_with_storage

# Find the save_analysis_results function (around line 186)
# Replace entire function with:
@staticmethod
def save_analysis_results(project_id: UUID, report: Dict[str, Any]) -> bool:
    """Save analysis results with storage optimization"""
    return save_analysis_results_with_storage(project_id, report)
```

**Verification:**
```bash
# Test with single team analysis
# The report should now:
# 1. Save full JSON to storage
# 2. Save minimal JSON to DB
# 3. Save report_path and report_size

# Check database size (should not grow anymore)
psql $DATABASE_URL -c "
SELECT pg_size_pretty(pg_database_size(current_database()));
"
```

---

**D. Migrate Existing Teams (2-4 hours for 1000 teams):**

**⚠️ CRITICAL: Run during low-traffic hours (e.g., midnight-4am)**

```bash
# Dry run first (test with 10 teams)
python -c "
from src.api.backend.utils.report_storage import ReportStorageManager
from src.api.backend.database import get_supabase_admin_client

supabase = get_supabase_admin_client()
teams = supabase.table('teams').select('id').limit(10).execute()

for team in teams.data:
    try:
        ReportStorageManager.migrate_team_to_storage(team['id'])
        print(f'✅ Migrated {team[\"id\"]}')
    except Exception as e:
        print(f'❌ Failed {team[\"id\"]}: {e}')
"

# If dry run successful, migrate all teams
python src/api/backend/utils/report_storage.py migrate
```

**Monitor migration:**
```bash
# In another terminal, watch progress
watch -n 5 "psql $DATABASE_URL -c '
SELECT 
    COUNT(*) FILTER (WHERE report_path IS NOT NULL) as migrated,
    COUNT(*) FILTER (WHERE report_json IS NOT NULL) as not_migrated,
    COUNT(*) as total 
FROM teams;
'"
```

**After migration completes:**
```bash
# Verify storage usage
# Supabase Dashboard → Storage → team-reports
# Should see 1000+ JSON files

# Check database size reduction
psql $DATABASE_URL -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
# Should be ~80% smaller
```

✅ **Mark as complete:** `status = 'done'` for 'move-json-storage'

---

### ⚠️ **Step 5: Enable Caching (30 minutes)**

**File created:** `src/api/backend/utils/enhanced_cache.py`

**Add to reports.py:**

```python
# At top of reports.py
from ..utils.enhanced_cache import cached, invalidate_cache, invalidate_team_caches

# Wrap the batch report function
@router.get("/api/reports/batch/{batchId}")
@cached(ttl=3600, key_prefix="batch_report")  # 1 hour cache
async def get_batch_report(batchId: str, ...):
    # existing code
```

**Add cache invalidation when teams update:**

```python
# In teams.py update_team function
@router.put("/api/teams/{team_id}")
async def update_team(team_id: str, data: dict, ...):
    # Update database
    TeamCRUD.update_team(team_id, data)
    
    # Invalidate caches
    team = TeamCRUD.get_team(team_id)
    invalidate_team_caches(team_id, team.get("batch_id"))
    
    return {"message": "Team updated"}
```

**Verification:**
```bash
# First request (cache miss)
time curl "https://your-domain.com/api/reports/batch/{BATCH_ID}"
# Should take 2-3 seconds

# Second request (cache hit)
time curl "https://your-domain.com/api/reports/batch/{BATCH_ID}"
# Should take <500ms

# Check Redis
redis-cli KEYS "*batch_report*"
# Should show cached keys
```

✅ **Mark as complete:** `status = 'done'` for 'add-caching'

---

## 📊 PHASE 3: VERIFICATION & MONITORING (Ongoing)

### **Step 6: 72-Hour Performance Test**

**Baseline (from your SUPABASE_METRICS_BASELINE_2026-03-31.md):**
- Current IO: High (needs reduction)
- Slow queries: Multiple JSON-heavy queries

**New metrics to track:**

```bash
# Create monitoring script
cat > monitor_performance.sh << 'EOF'
#!/bin/bash

echo "=== Database Performance Check ==="
echo "Date: $(date)"
echo ""

# 1. Database size
echo "Database Size:"
psql $DATABASE_URL -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
echo ""

# 2. Top slow queries
echo "Top 5 Slow Queries:"
psql $DATABASE_URL -c "
SELECT 
    substring(query, 1, 50) as query_snippet,
    calls,
    mean_exec_time::numeric(10,2) as avg_ms,
    total_exec_time::numeric(10,2) as total_ms
FROM pg_stat_statements 
WHERE query NOT LIKE '%pg_stat%'
ORDER BY mean_exec_time DESC 
LIMIT 5;
"
echo ""

# 3. Table sizes
echo "Largest Tables:"
psql $DATABASE_URL -c "
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 5;
"
echo ""

# 4. Cache hit rate
echo "Cache Stats:"
redis-cli INFO stats | grep hits
echo ""

echo "=== End Report ==="
EOF

chmod +x monitor_performance.sh

# Run every 6 hours for 72 hours
0 */6 * * * /path/to/monitor_performance.sh >> performance_log.txt
```

**Expected results after 72 hours:**
- ✅ Database size: 500MB → 100-200MB (60-80% reduction)
- ✅ Leaderboard query: 10-15s → 1-2s (90% faster)
- ✅ Average response time: <1s for most endpoints
- ✅ Cache hit rate: >50%
- ✅ Disk IO: <80% consistently

---

## 🎯 SUCCESS CRITERIA

**Before:**
- Database size: ~500MB
- Leaderboard endpoint: 10-15s
- teams table: 300KB per row (report_json)
- SELECT * queries: 13+ instances
- No caching
- No indexes on foreign keys

**After (Target):**
- Database size: <200MB (60% reduction) ✅
- Leaderboard endpoint: <2s (85% faster) ✅
- teams table: <20KB per row (minimal JSON) ✅
- SELECT * fixed: All use specific columns ✅
- Caching: >50% hit rate ✅
- Indexes: 12+ critical indexes ✅

---

## 🚨 ROLLBACK PLAN (If Issues Occur)

**If migration causes problems:**

```bash
# 1. Restore database from backup
pg_restore -d $DATABASE_URL backup_20260407.sql

# 2. Revert code changes
git checkout HEAD~1 src/api/backend/routers/reports.py
git checkout HEAD~1 src/api/backend/services/data_mapper.py

# 3. Restart services
pm2 restart all

# 4. Clear cache
redis-cli FLUSHDB
```

**Keep storage bucket** - it doesn't affect existing functionality

---

## 📞 SUPPORT & TROUBLESHOOTING

**Common Issues:**

1. **Migration fails midway:**
   - Check storage bucket permissions
   - Verify report_path column exists
   - Resume from last successful team_id

2. **Cache not working:**
   - Check Redis connection: `redis-cli ping`
   - Verify REDIS_URL in .env
   - Check logs for cache errors

3. **Queries still slow:**
   - Run `ANALYZE` on tables: `psql $DATABASE_URL -c "ANALYZE teams;"`
   - Verify indexes exist: `\di` in psql
   - Check for blocking queries: `SELECT * FROM pg_stat_activity;`

4. **Storage bucket full:**
   - Check bucket size in Supabase dashboard
   - Compress old reports
   - Archive reports >30 days

---

## ✅ COMPLETION CHECKLIST

- [ ] Step 1: Indexes created and verified
- [ ] Step 2: Optimized queries deployed
- [ ] Step 3: Monitoring middleware added
- [ ] Step 4A: Storage bucket created
- [ ] Step 4B: New columns added
- [ ] Step 4C: data_mapper.py updated
- [ ] Step 4D: All teams migrated to storage
- [ ] Step 5: Caching enabled and verified
- [ ] Step 6: 72-hour performance test started
- [ ] Backup created before changes
- [ ] Rollback plan documented
- [ ] Team notified of maintenance window
- [ ] Performance baseline captured
- [ ] Post-migration metrics captured

---

**Next Review:** 72 hours after Step 4D completion  
**Expected Outcome:** 70-90% disk IO reduction, 85% faster queries

**Questions?** Check logs or rollback immediately if issues arise.
