# ⚠️ MENTOR AUTO-ASSIGNMENT FIX

## Problem Summary

When a new or existing mentor logs in for the first time, **teams are NOT showing on their portal** even though they should be auto-assigned.

**Root Cause:** 100+ teams in the system don't have mentor metadata, so auto-assignment can't match them to mentors.

---

## 🚀 Quick Fixes (Choose ONE)

### **OPTION 1: Manual Admin Assignment (2 minutes)**
This works immediately for any teams, regardless of metadata.

**Steps:**
1. Go to `http://localhost:3000/admin/assignments`
2. For each mentor, select teams from the dropdown
3. Click "Assign" button
4. Mentor will see teams on next dashboard refresh

**Pros:** Works immediately, no coding  
**Cons:** Manual work for each team

---

### **OPTION 2: Auto-Populate Missing Metadata (5 minutes)**
Automatically fills in missing mentor information from historical data.

**Steps:**

1. Run the migration script to see what would change:
```bash
cd d:\Github Agent\github-agent-backend
$env:PYTHONPATH="d:\Github Agent\github-agent-backend"
python scripts\migrate_populate_mentor_metadata.py --dry-run
```

2. If output looks good, execute the migration:
```bash
python scripts\migrate_populate_mentor_metadata.py --execute
```

3. Now trigger auto-assignment for all batches:
```bash
# For each batch, run:
curl -X POST http://localhost:8000/api/assignments/auto-assign/{BATCH_ID} \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

4. Mentors will see teams on next login

**Pros:** Fixes all teams at once, prevents future issues  
**Cons:** Requires running script

---

### **OPTION 3: Add Backend Endpoint (10 minutes)**
Create an easy way for mentors to trigger assignment after onboarding.

**File:** `d:\Github Agent\github-agent-backend\src\api\backend\routers\assignments.py`

**Add this endpoint at the end of the file:**

```python
@router.post("/me/auto-assign")
async def mentor_trigger_auto_assign(
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Allow a mentor to trigger team auto-assignment for themselves.
    Call this after updating your profile.
    """
    if current_user.role != "mentor":
        raise HTTPException(status_code=403, detail="Mentors only")
    
    admin_client = get_supabase_admin_client()
    
    # Import the function from auth_new
    from .auth_new import _auto_assign_mentor_teams
    
    try:
        assigned = _auto_assign_mentor_teams(
            admin_client,
            str(current_user.user_id),
            current_user.full_name or "",
            email=current_user.email or ""
        )
        
        return {
            "success": True,
            "teams_assigned": assigned,
            "message": f"Successfully assigned {assigned} team(s) to your profile"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Auto-assignment failed: {str(e)}"
        )
```

**Then update frontend** (MentorTeams or dashboard page) to show a button:

```tsx
const [autoAssignLoading, setAutoAssignLoading] = useState(false);

const handleAutoAssign = async () => {
  setAutoAssignLoading(true);
  try {
    const response = await apiClient.post("/api/assignments/me/auto-assign");
    toast.success(`${response.teams_assigned} team(s) assigned!`);
    // Refresh teams
    queryClient.invalidateQueries({ queryKey: ["teams"] });
  } catch (err) {
    toast.error("Auto-assignment failed");
  } finally {
    setAutoAssignLoading(false);
  }
};

// In JSX:
{teams.length === 0 && (
  <Button onClick={handleAutoAssign} disabled={autoAssignLoading}>
    {autoAssignLoading ? "Assigning..." : "Auto-Assign Teams"}
  </Button>
)}
```

**Pros:** Clean, allows mentors self-service  
**Cons:** Requires code changes

---

## 📊 What's Actually Happening

```
DATABASE STATE:
├── Mentors: 18 mentors ✅
├── Teams: 185 total
│   ├── 85 with assigned mentor ✅
│   │   └── Via admin manual assignment
│   └── 100 UNASSIGNED ❌
│       └── No mentor metadata → Can't auto-assign
└── Auto-assign feature: Disabled ❌ (no metadata to match)
```

## 🔍 Understanding The Flow

### Current (Broken) Flow:
```
Mentor logs in
  ↓
Sets full_name in onboarding (✅)
  ↓
Auto-assign function called (✅)
  ↓
Searches for teams with metadata.ingestion.mentor (❌ NOT FOUND)
  ↓
No teams assigned → Portal shows empty
```

### Expected (Fixed) Flow:
```
Mentor logs in
  ↓
Sets full_name in onboarding (✅)
  ↓
Auto-assign function called (✅)
  ↓
Searches for teams with metadata.ingestion.mentor (✅ NOW FOUND after fix)
  ↓
Matches mentor name to team metadata (✅)
  ↓
Creates mentor_team_assignments record (✅)
  ↓
Teams appear on portal on next refresh
```

---

## 🧑‍💻 For Developers: Understanding the Code

### Where auto-assignment happens:

**File:** `d:\Github Agent\github-agent-backend\src\api\backend\routers\auth_new.py`

**Key function:** `_auto_assign_mentor_teams()` (lines 39-139)

**Logic:**
```python
def _auto_assign_mentor_teams(admin_client, user_id, full_name, email):
    # Find unassigned teams
    teams = admin_client.table("teams")\
        .select("id, metadata")\
        .is_("mentor_id", "null")\
        .execute()
    
    # Try to match team metadata to mentor name
    for team in teams.data:
        metadata = team.get("metadata") or {}
        ingestion = metadata.get("ingestion") or {}
        
        # These are what we're trying to match:
        candidates = [
            metadata.get("suggested_mentor"),    # ← Empty for 100 teams  
            ingestion.get("mentor"),              # ← Empty for 100 teams
            ingestion.get("mentor_email"),        # ← Empty for 100 teams
        ]
        
        # If any match the mentor's full_name → AUTO-ASSIGN
        if mentor_name matches candidate:
            create_assignment()  # ✅ Teams appear
        else:
            skip()  # ✅ No error, just skipped
```

### Where teams should get metadata:

**File:** `d:\Github Agent\github-agent-backend\src\api\backend\routers\teams.py`

**Function:** `bulk_import_teams_with_mentors()` (lines 572-1090)

**Logic:**
```python
# When importing from CSV/Excel:
if file_has_mentor_column:
    team_metadata["ingestion"]["mentor"] = mentor_name_from_csv  # ✅ Stored
    create_team(with_metadata)
else:
    create_team(with_empty_metadata)  # ❌ This is what happened
```

---

## ✅ Prevention: Future-Proof Your System

### When creating teams in the UI:
1. Require a "Mentor" field when creating/importing teams
2. Validate that the mentor exists in the system
3. Store in metadata.ingestion.mentor automatically

### When importing from CSV/Excel:
1. Ensure CSV has a "Mentor" column
2. Use the bulk-import endpoint
3. The metadata is populated automatically

### Example CSV format:
```
Team Name,Repo URL,Mentor,Project Statement
Team A,https://github.com/a,John Smith,Our project
Team B,https://github.com/b,Jane Doe,Another project
```

---

## 🐛 Debugging Commands

### Check if database was fixed:
```bash
$env:PYTHONPATH="d:\Github Agent\github-agent-backend"
python scripts\debug_mentor_auto_assign.py

# Look for teams WITH mentor metadata in section 5
```

### Check mentor assignments:
```sql
SELECT mentor_id, COUNT(*) as assignments
FROM mentor_team_assignments
GROUP BY mentor_id
ORDER BY assignments DESC;
```

### Check team metadata:
```sql
SELECT team_name, 
       metadata->'ingestion'->>'mentor' as mentor,
       metadata->'ingestion'->>'mentor_email' as email
FROM teams
WHERE mentor_id IS NULL
LIMIT 10;
```

---

## ❓ FAQ

**Q: Why is this happening now?**  
A: Teams were created before the auto-assign feature was fully implemented, or they were imported without mentor information.

**Q: Do mentors' existing assignments still work?**  
A: Yes! The 85 teams that are already assigned will show up. New teams need auto-assignment or manual assignment.

**Q: Will this break anything?**  
A: No. The fix only populates missing metadata fields. Existing data is preserved.

**Q: How long does the migration take?**  
A: Seconds. About 1ms per team.

**Q: Do I need to restart the backend?**  
A: No. Changes are immediate.

---

## 📞 Support

If you need help:
1. Check the DEBUG_MENTOR_AUTO_ASSIGNMENT.md file in the backend directory
2. Run the debug script to see current state
3. Try Option 1 (manual assignment) first - it's guaranteed to work

---

**Last Updated:** April 7, 2026
