# ✅ STORAGE SETUP COMPLETE!

## 🎉 What Just Worked

### **Test Results:**
```
✅ Bucket 'team-reports' created
✅ Upload successful (319 bytes)
✅ Download successful - data matches!
✅ Cleanup successful
✅ ALL TESTS PASSED
```

---

## ✅ What's Done

1. **Storage Bucket Created** ✅
   - Bucket name: `team-reports`
   - Type: Private
   - Status: Working

2. **Upload/Download Tested** ✅
   - Test file uploaded successfully
   - Test file downloaded and verified
   - Test file deleted successfully

3. **Code Fixed** ✅
   - `report_storage.py` - fixed imports
   - `data_mapper.py` - saves to storage instead of DB
   - `test_storage_setup.py` - working

---

## ⏳ Next Steps (Complete Deployment)

### **Step 1: Add Database Columns (5 minutes)**

**Check if DATABASE_URL is set:**
```powershell
echo $env:DATABASE_URL
```

**If not set, set it:**
```powershell
$env:DATABASE_URL = "postgresql://postgres:PASSWORD@HOST:PORT/postgres"
```

**Then run migration:**
```powershell
cd "D:\Coding\Github-Agent\proj-github agent"
psql $env:DATABASE_URL -f migrations/002_extract_json_to_columns.sql
```

**Expected output:**
```
ALTER TABLE
CREATE INDEX
UPDATE 300
```

---

### **Step 2: Set Storage Policies (5 minutes)**

Go to: **Supabase Dashboard → Storage → Policies → team-reports**

**Run these 3 SQL commands in Supabase SQL Editor:**

```sql
-- 1. Allow service role to upload
CREATE POLICY "Service role can insert reports"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (
  bucket_id = 'team-reports' 
  AND auth.jwt()->>'role' = 'service_role'
);

-- 2. Allow service role to read
CREATE POLICY "Service role can read reports"
ON storage.objects FOR SELECT
TO authenticated
USING (
  bucket_id = 'team-reports'
  AND auth.jwt()->>'role' = 'service_role'
);

-- 3. Allow service role to update/delete
CREATE POLICY "Service role can update reports"
ON storage.objects FOR UPDATE
TO authenticated
USING (
  bucket_id = 'team-reports'
  AND auth.jwt()->>'role' = 'service_role'
);
```

---

### **Step 3: Restart Backend (2 minutes)**

```powershell
# If using PM2
pm2 restart backend

# If using Docker
docker-compose restart api

# If manual
# Kill the old process, then:
cd "D:\Coding\Github-Agent\proj-github agent\src\api"
python -m uvicorn backend.main:app --reload
```

---

### **Step 4: Test Analysis (5 minutes)**

```powershell
# Test one team analysis
curl -X POST http://localhost:8000/api/teams/YOUR_TEAM_ID/analyze
```

**Check logs for:**
```
✅ Report saved to storage: team-reports/abc-123.json (156789 bytes)
Team data saved successfully (storage-backed)
```

---

### **Step 5: Verify Leaderboard Performance**

```powershell
# Before: 10-15s
# After: <2s
time curl "http://localhost:8000/api/leaderboard?batch_id=YOUR_BATCH_ID"
```

---

### **Step 6: Migrate Existing Teams (TONIGHT 2-6 AM)**

```powershell
# DRY RUN first (no changes)
python migrate_to_storage.py

# LIVE migration (run during low traffic)
python migrate_to_storage.py --live
```

**Expected:**
- Time: 10-30 minutes for 300 teams
- Database size: 500MB → 100-150MB
- Disk IO: drops 70-80%

---

## 📊 Current Status

| Task | Status |
|------|--------|
| ✅ Indexes created | DONE |
| ✅ Leaderboard optimized | DONE |
| ✅ data_mapper.py fixed | DONE |
| ✅ Storage system created | DONE |
| ✅ Storage bucket created | DONE |
| ✅ Storage tested | DONE |
| ⏳ Database columns added | **TODO** (Step 1) |
| ⏳ Storage policies set | **TODO** (Step 2) |
| ⏳ Backend restarted | **TODO** (Step 3) |
| ⏳ Analysis tested | **TODO** (Step 4) |
| ⏳ 300 teams migrated | **TODO** (Step 6 - tonight) |

---

## 🎯 Quick Commands Reference

```powershell
# 1. Add database columns
psql $env:DATABASE_URL -f migrations/002_extract_json_to_columns.sql

# 2. Restart backend
pm2 restart backend

# 3. Test analysis
curl -X POST http://localhost:8000/api/teams/TEAM_ID/analyze

# 4. Check logs
pm2 logs backend | grep "storage"

# 5. Migrate teams (tonight)
python migrate_to_storage.py --live

# 6. Verify database size
psql $env:DATABASE_URL -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

---

## ✅ Success Criteria

- [ ] Database columns added (report_path, ai_percentage, etc.)
- [ ] Storage policies set (3 policies)
- [ ] Backend restarted with new code
- [ ] One test analysis succeeds
- [ ] Leaderboard <2s (vs 10-15s before)
- [ ] 300 teams migrated to storage
- [ ] Database size <200MB (vs 500MB before)
- [ ] Disk IO <30% (vs 100% before)

---

**🚀 Do Steps 1-5 now (20 minutes), then Step 6 tonight!**

See `DEPLOYMENT_STATUS.md` for full details.
