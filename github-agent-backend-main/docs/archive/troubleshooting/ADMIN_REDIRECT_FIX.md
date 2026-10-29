# Admin Dashboard Redirect Issue - Analysis & Fix

## 🔍 Problem Summary

**Issue:** When signing in with admin credentials (personal or dev), users are redirected to the mentor dashboard instead of the admin dashboard.

**Root Cause:** The backend auto-creates new users with `role: "mentor"` by default, regardless of their intended role.

---

## 🎯 Root Cause Analysis

### Flow of Events:

1. **User Signs In:**
   - User clicks "Sign in with Google" on admin login page
   - OAuth flow completes → redirected to `/auth/callback`

2. **AuthCallback Component:**
   - Exchanges auth code for session
   - Calls `handleRoleRedirect()` to determine where to redirect

3. **Role Fetch:**
   - Frontend calls `GET /api/auth/me`
   - Backend endpoint: `src/api/backend/routers/auth.py`

4. **Backend Role Resolution:**
   ```python
   # utils/auth.py - get_current_user()
   profile = UserCRUD.get_or_create_user(user_id, email=email, full_name=full_name)
   role = profile.get("role", "student") if profile else "student"
   ```

5. **User Creation (The Problem):**
   ```python
   # crud.py - get_or_create_user() [OLD CODE]
   payload = {
       "id": user_id,
       "email": email,
       "full_name": full_name,
       "role": "mentor",  # ❌ ALWAYS CREATES AS MENTOR
       "is_active": True,
       "created_at": datetime.now().isoformat()
   }
   ```

6. **Redirect:**
   - Frontend receives `role: "mentor"`
   - Redirects to `/mentor/dashboard` instead of `/admin/dashboard`

---

## ✅ Solutions Implemented

### Fix #1: Improved User Creation Logic

**File:** `src/api/backend/crud.py` (line 494-532)

**What Changed:**
- Now checks Supabase Auth metadata for role before creating user
- Falls back to `mentor` only if no role is found in metadata
- This allows admins to pre-set roles in Supabase Auth

**Code:**
```python
@staticmethod
def get_or_create_user(user_id: str, email: Optional[str] = None, full_name: Optional[str] = None) -> Dict[str, Any]:
    supabase = get_supabase_admin_client()

    existing = UserCRUD.get_user(user_id)
    if existing:
        return existing

    # Try to fetch role from Supabase Auth metadata
    default_role = "mentor"  # Default to mentor instead of student
    try:
        user_response = supabase.auth.admin.get_user_by_id(user_id)
        if user_response and user_response.user:
            # Check app_metadata first (set by admin), then user_metadata
            app_metadata = user_response.user.app_metadata or {}
            user_metadata = user_response.user.user_metadata or {}
            metadata_role = app_metadata.get("role") or user_metadata.get("role")
            if metadata_role in ["admin", "mentor"]:
                default_role = metadata_role
                print(f"[UserCRUD] Creating user with role from metadata: {default_role}")
    except Exception as e:
        print(f"[UserCRUD] Could not fetch user metadata, using default role: {e}")

    payload = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": default_role,
        "is_active": True,
        "created_at": datetime.now().isoformat()
    }

    result = supabase.table("users").insert(payload).execute()
    return result.data[0] if result.data else payload
```

### Fix #2: Admin Role Management Script

**File:** `set_admin_role.py` (new file)

**Purpose:**
- Quickly set admin role for any user by email
- List all users in the database
- Verify role changes

**Usage:**
```bash
# Set admin role for a user
python set_admin_role.py john@example.com

# List all users
python set_admin_role.py --list
```

---

## 🚀 How to Fix Your Account

### Method 1: Using the Script (Recommended)

1. **Navigate to backend directory:**
   ```bash
   cd "d:\Coding\Github-Agent\proj-github agent"
   ```

2. **List all users to find your email:**
   ```bash
   python set_admin_role.py --list
   ```

3. **Set your role to admin:**
   ```bash
   python set_admin_role.py your-email@example.com
   ```

4. **Sign out and sign in again**

### Method 2: Manual Supabase Update

1. **Go to Supabase Dashboard:**
   - URL: https://frcdvwuapmunkjaarrzr.supabase.co
   - Click on "Table Editor" in the sidebar

2. **Open the `users` table**

3. **Find your user record:**
   - Search for your email in the table

4. **Update the role:**
   - Click on the `role` cell for your user
   - Change from `mentor` to `admin`
   - Save the change

5. **Sign out and sign in again**

### Method 3: Using Supabase SQL Editor

1. **Go to Supabase Dashboard → SQL Editor**

2. **Run this query (replace with your email):**
   ```sql
   UPDATE users
   SET role = 'admin'
   WHERE email = 'your-email@example.com';
   ```

3. **Sign out and sign in again**

---

## 🔒 Setting Role via Supabase Auth Metadata (For Future Users)

To pre-set roles for users before they first sign in:

1. **Go to Supabase Dashboard → Authentication → Users**

2. **Click on a user**

3. **Scroll to "Raw User Meta Data"**

4. **Add/Edit JSON:**
   ```json
   {
     "role": "admin"
   }
   ```
   OR in App Meta Data:
   ```json
   {
     "role": "admin"
   }
   ```

5. **Save**

Now when this user signs in for the first time, they'll be created with the admin role automatically.

---

## 📊 Testing the Fix

### Test Steps:

1. **Restart the backend server:**
   ```bash
   cd "d:\Coding\Github-Agent\proj-github agent"
   uvicorn main:app --reload --port 8000
   ```

2. **Set your role to admin** (using one of the methods above)

3. **Sign out from the frontend** (if logged in)

4. **Sign in again:**
   - Go to http://localhost:5173/login/admin
   - Click "Sign in with Google"
   - Complete OAuth flow

5. **Verify redirect:**
   - Should redirect to `/admin/dashboard` ✅
   - Should NOT redirect to `/mentor/dashboard` ❌

6. **Check browser console:**
   - Should see: `[Auth] Fetched role: admin`
   - Should see: `[Auth] Redirecting to: /admin/dashboard`

---

## 🛡️ Prevention for Future Users

### For New Admins:

**Option A:** Pre-set role in Supabase Auth (as shown above)

**Option B:** Create user record manually before first sign-in:
```sql
INSERT INTO users (id, email, full_name, role, is_active, created_at)
VALUES (
  'supabase-user-id-here',
  'admin@example.com',
  'Admin Name',
  'admin',
  true,
  NOW()
);
```

**Option C:** Use the admin portal to promote users after they sign in:
1. Admin signs in
2. Goes to Admin Portal → Users
3. Updates role for new admin

---

## 🔍 Debugging Tips

### Check Current Role:

**Browser Console:**
```javascript
// While logged in, run in console:
fetch('/api/auth/me', {
  headers: {
    'Authorization': 'Bearer ' + (await supabase.auth.getSession()).data.session.access_token
  }
}).then(r => r.json()).then(console.log)
```

**Backend Logs:**
- Look for: `[Auth] Final role for <email>: <role>`
- Look for: `[UserCRUD] Creating user with role from metadata: <role>`

**Database Query:**
```sql
SELECT email, role, created_at FROM users ORDER BY created_at DESC;
```

---

## 📝 Summary

**What was wrong:**
- New users were always created with `role: "mentor"` by default
- No check for intended role from auth metadata

**What was fixed:**
1. Updated `get_or_create_user()` to check Supabase Auth metadata
2. Created helper script to manage user roles
3. Documented multiple ways to set admin role

**What you need to do:**
1. Run `python set_admin_role.py your-email@example.com`
2. Sign out and sign in again
3. You should now land on the admin dashboard! 🎉

---

## 🎯 Quick Reference

**Restart Backend:**
```bash
cd "d:\Coding\Github-Agent\proj-github agent"
uvicorn main:app --reload --port 8000
```

**Set Admin Role:**
```bash
python set_admin_role.py your-email@example.com
```

**List Users:**
```bash
python set_admin_role.py --list
```

**Check Logs:**
- Backend: Look for `[Auth] Final role for <email>: <role>`
- Frontend: Browser console → `[Auth] Fetched role: <role>`

---

**Need Help?**
- Check backend logs for authentication errors
- Verify Supabase credentials in `.env` file
- Make sure user exists in database before setting role
- Try clearing browser cache and localStorage
