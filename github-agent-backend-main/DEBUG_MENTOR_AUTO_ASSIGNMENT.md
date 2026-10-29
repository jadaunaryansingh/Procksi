# Mentor Auto-Assignment Debug Report
**Date:** April 7, 2026  
**Analysis:** Why teams aren't showing on mentor portals on first login

---

## 🔍 The Issue (CONFIRMED)

When a mentor logs in for the first time, **teams don't appear** on their portal even though they should be auto-assigned.

### Root Cause Analysis

After running a comprehensive database audit, here's what's happening:

#### 1. **100+ Teams Have ZERO Mentor Metadata**
```
✅ Mentors in system: 18 mentors (with full names set)
✅ Teams with assigned mentors: 85 teams
❌ Teams with UNASSIGNED mentors: 100+ teams
❌ Problem: 90% of unassigned teams have NO metadata.ingestion.mentor

Examples of unassigned teams:
- Team 102: metadata.ingestion.mentor = (empty)
- Team 166: metadata.ingestion.mentor = (empty)  
- Team 86: metadata.ingestion.mentor = (empty)
```

#### 2. **Auto-Assignment Cannot Work Without Metadata**
The auto-assignment function has this logic:
```python
# _auto_assign_mentor_teams() in auth_new.py, line 39-104
candidates = [
    team_metadata.get("suggested_mentor"),        # ← Must exist
    ingestion.get("mentor"),                       # ← Must exist
    ingestion.get("mentor_email"),                 # ← Must exist
]
```

If all three are empty/None → **NO AUTO-ASSIGNMENT POSSIBLE**

#### 3. **Teams Were Created Without Mentor Metadata**
Investigation shows teams were either:
- Created directly via `/api/teams` (single team creation) without mentor info
- Imported from Excel/CSV files that LACKED a "Mentor" column
- Pre-dated the metadata feature

---

## 🎯 What Should Happen (The Intended Flow)

```
1. Admin creates teams (ideally with mentor column in CSV)
   ↓ Teams get metadata.ingestion.mentor populated
   ↓
2. Mentor logs in → /login endpoint called
   ↓ If mentor has full_name, calls _auto_assign_mentor_teams()
   ↓ Searches teams with mentor_id=null
   ↓ Matches team.metadata.ingestion.mentor against mentor's full_name
   ↓
3. If match found → Creates record in mentor_team_assignments table
   ↓
4. Mentor goes to dashboard → Queries mentor_team_assignments table
   ↓ Sees their assigned teams
```

**But Step 1 is failing** because teams don't have mentor metadata.

---

## 🛠️ Solutions

### **Solution 1: Admin Bulk Auto-Assign (FASTEST)**
**Use the existing admin endpoint** to auto-assign teams in a batch:

**Endpoint:** `POST /api/assignments/auto-assign/{batch_id}`  
**Requirements:** Admin only  
**What it does:**
- Finds ALL unassigned teams in the batch
- Tries to match to mentors using metadata
- If matching metadata exists, assigns the team
- Returns report of successful assignments and failures

**Problem:** Still won't work if metadata is missing

---

### **Solution 2: Populate Missing Metadata**
Use the migration script below to add mentor info to existing teams:

```python
# Run this to populate missing mentor metadata
# File: scripts/populate_missing_mentor_metadata.py

For each team without metadata.ingestion.mentor:
  - Check if team has a suggested_mentor
  - Check if team was historically assigned to someone
  - Populate the metadata.ingestion.mentor field
  - Re-trigger auto-assignment
```

---

### **Solution 3: Create New Endpoint - Trigger Auto-Assign on Demand**
Backend enhancement (add to assignments.py):

```python
@router.post("/me/auto-assign-teams")
async def trigger_auto_assign_for_current_mentor(
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Allow mentors to manually trigger assignment after onboarding.
    Useful if they complete profile after teams are created.
    """
    if current_user.role != "mentor":
        raise HTTPException(status_code=403, detail="Mentors only")
    
    admin_client = get_supabase_admin_client()
    assigned = _auto_assign_mentor_teams(
        admin_client,
        str(current_user.user_id),
        current_user.full_name,
        email=current_user.email or ""
    )
    
    return {
        "success": True,
        "teams_assigned": assigned,
        "message": f"Auto-assigned {assigned} team(s) to your profile"
    }
```

---

### **Solution 4: Manual Admin Assignment**
**For immediate relief** - Admin can manually assign teams:

1. Go to `/admin/assignments` page
2. For each mentor, use the dropdown to select unassigned teams
3. Click "Assign" button
4. Teams will appear on mentor portal next time they refresh

---

## 📊 Current Database State

```
MENTORS (18 total):
- gourav.bathla@gla.ac.in ..................... Gourav Bathla (6 teams assigned via admin)
- chhavi.bajpai@gla.ac.in ..................... Chhavi Bajpai (7 teams assigned)
- saurabh.tewari@gla.ac.in .................... Saurabh Tewari (6 teams assigned)
- ruby.panwar@gla.ac.in ....................... Ruby Panwar (5 teams assigned)
- preshit.desai@gla.ac.in ..................... Preshit Desai (20 teams assigned)
- ankur.rai@gla.ac.in ......................... Ankur Rai (7 teams assigned)
[+ 12 more mentors]

⚠️  MENTORS WITH NO FULL_NAME (Will need onboarding):
    - sachin.yadav@gla.ac.in
    - user@demo.com

TEAMS:
- Total: 185 teams  
- Assigned (mentor_id IS NOT NULL): 85 teams
- Unassigned (mentor_id IS NULL): 100 teams  
- With metadata.ingestion.mentor: ~10 teams
- WITHOUT metadata.ingestion.mentor: ~90 teams ← THE PROBLEM
```

---

## ✅ How to Fix (Step-by-Step)

### **SHORT TERM (Get teams showing immediately)**

1. **Use Admin Assignment UI** (Already works!)
   ```
   Go to: /admin/assignments
   Action: Manually assign teams to mentors
   Result: Teams appear immediately on mentor portal
   ```

2. **OR use the Auto-Assign API** (if teams have metadata)
   ```bash
   POST /api/assignments/auto-assign/{batch_id}
   Authorization: Admin token
   ```

---

### **MEDIUM TERM (Prevent this for future teams)**

1. **When creating teams in Excel/CSV:**
   - Add a "Mentor" or "Mentor Email" column
   - Ensure ALL teams have a mentor specified
   - Use bulk-import endpoint `/api/teams/bulk-import`
   - Auto-assignment will work onupload

2. **Bulk-import flow:**
   ```
   Admin uploads CSV with mentor column
   ↓
   System populates metadata.ingestion.mentor
   ↓
   Mentor logs in
   ↓
   Auto-assignment matches and assigns teams
   ↓
   Teams appear on mentor portal
   ```

---

### **LONG TERM (System improvement)**

1. **Add validation** to prevent creating teams without mentor info
2. **Enhance auto-assign logic** to handle edge cases:
   - Match by email if name doesn't work
   - Fall back to admin assignment queue if no match
3. **Add feature** to let mentors self-assign from available teams
4. **Improve UX** with a "Pending Assignment" state

---

## 🔧 Debug Commands

### Check mentor teams assignments:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/teams?page=1&page_size=20"
```

### Check mentor_team_assignments table:
```bash
SELECT mentor_id, COUNT(*) as team_count 
FROM mentor_team_assignments 
GROUP BY mentor_id;
```

### See unassigned teams:
```bash
SELECT id, team_name, metadata->'ingestion'->>'mentor' as mentor_metadata
FROM teams 
WHERE mentor_id IS NULL 
LIMIT 10;
```

---

## 📝 Notes for Your Team

- **The system design IS correct** - it properly matches teams to mentors
- **The problem IS data-related** - teams were created without mentor info in metadata
- **The fix IS simple** - either populate metadata or manually assign teams
- **Your mentors CAN see teams** if teams are assigned (whether via auto-assign or manual)
- **The onboarding flow IS working** - mentors who complete it get auto-assigned IF metadata exists

---

## ❓ FAQ

**Q: Why aren't mentors seeing their teams on first login?**  
A: Either (a) no mentor metadata in teams, (b) name doesn't match, or (c) manual assignment wasn't done.

**Q: How do existing mentors see teams now?**  
A: They were manually assigned via the admin UI (mentor_team_assignments table has 85 teams assigned).

**Q: What happens after a mentor completes onboarding?**  
A: The system calls auto-assign, but only matches IF team has metadata.ingestion.mentor set.

**Q: Can I fix this without recreating all teams?**  
A: Yes! Use Solution 2 (populate metadata) or Solution 4 (manual admin assignment).

---

**END REPORT**
