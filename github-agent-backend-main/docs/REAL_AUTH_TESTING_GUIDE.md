# Real Authentication Testing Guide

## 🎯 Objective
Test Phase 1 endpoints with real Google OAuth authentication.

## 📋 Prerequisites Checklist

### 1. Google OAuth Configuration in Supabase ✓

**Step 1: Create Google OAuth Credentials**
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or select existing)
3. Create OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URIs: 
     ```
     https://frcdvwuapmunkjaarrzr.supabase.co/auth/v1/callback
     http://localhost:8000/auth/callback
     file:///D:/Coding/Github-Agent/proj-github%20agent/get_token.html
     ```
4. Copy **Client ID** and **Client Secret**

**Step 2: Configure Supabase**
1. Open [Supabase Dashboard](https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr/auth/providers)
2. Go to Authentication → Providers
3. Enable **Google** provider
4. Enter your Google OAuth credentials:
   - Client ID: `[paste from step 1]`
   - Client Secret: `[paste from step 1]`
5. Click **Save**

### 2. Verify Backend is Running

```powershell
# Check if server is running
Get-Process | Where-Object { $_.ProcessName -like "*python*" }

# If not running, start it:
cd "D:\Coding\Github-Agent\proj-github agent"
.\.venv\Scripts\python.exe main.py
```

Server should be accessible at: http://localhost:8000

### 3. Get Your Google ID Token

**Option A: Use the HTML Token Getter (Easiest)** ✅ RECOMMENDED
```powershell
# Open the token getter page
start get_token.html
```

Steps:
1. Click "Login with Google"
2. Sign in with your Google account
3. Copy the token displayed
4. Ready to test!

**Option B: Using Browser DevTools**
1. Go to http://localhost:8000/docs
2. Click "Authorize" button
3. Login with Google OAuth
4. Open DevTools (F12) → Console
5. Run: `localStorage.getItem('sb-access-token')`
6. Copy the token

**Option C: Using cURL**
```bash
curl -X POST 'https://frcdvwuapmunkjaarrzr.supabase.co/auth/v1/token' \
  -H "Content-Type: application/json" \
  -H "apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{"email": "your@email.com", "password": "your-password"}'
```

## 🧪 Running the Tests

### Step 1: Run the Interactive Test Script

```powershell
cd "D:\Coding\Github-Agent\proj-github agent"
.\.venv\Scripts\python.exe test_real_auth.py
```

The script will:
1. Ask if you have a Google ID token
2. Guide you through authentication
3. Test all Phase 1 endpoints with real auth
4. Display results with color-coded output

### Step 2: Expected Test Results

**With Regular User Token:**
- ✅ Login (POST /api/auth/login)
- ✅ Get Profile (GET /api/auth/me)
- ✅ Update Profile (PUT /api/auth/me)
- ✅ List Batches (GET /api/batches)
- ✅ Get Batch Details (GET /api/batches/{id})
- ⚠️ Create Batch (POST /api/batches) - Will fail with 403 (need admin role)
- ✅ Refresh Token (POST /api/auth/refresh)
- ✅ Logout (POST /api/auth/logout)

**With Admin Token:**
- All above tests plus:
- ✅ Create Batch (POST /api/batches)
- ✅ Update Batch (PUT /api/batches/{id})
- ✅ Delete Batch (DELETE /api/batches/{id})

### Step 3: Grant Admin Role (Optional)

To test admin-only endpoints, you need admin privileges:

1. Login with your Google account first
2. Get your user ID from the test output
3. Run this SQL in [Supabase SQL Editor](https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr/sql):

```sql
-- Replace with your email
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'::jsonb
WHERE email = 'your@email.com';
```

4. Get a new token (old one won't have admin role)
5. Run tests again

## 🔍 Manual Testing with Swagger UI

Alternative way to test:

1. Go to http://localhost:8000/docs
2. Click "Authorize" button at top right
3. In the value field, paste: `Bearer YOUR_TOKEN_HERE`
4. Click "Authorize" and "Close"
5. Try any endpoint - it will include your auth token

## 📊 Test Scenarios

### Scenario 1: Basic User Authentication
```python
# Run this in Python
python test_real_auth.py
# Select: yes (have token)
# Expected: Login ✓, Profile ✓, List Batches ✓
```

### Scenario 2: Admin Operations
```python
# After granting admin role
python test_real_auth.py
# Expected: All tests pass including Create Batch ✓
```

### Scenario 3: Token Refresh
```python
# The script automatically tests token refresh
# Wait 5 seconds between tests
# Expected: Old token works → Refresh → New token works ✓
```

### Scenario 4: Unauthorized Access
```python
# Try endpoints without token
curl http://localhost:8000/api/batches
# Expected: 401 Unauthorized
```

## 🐛 Troubleshooting

### Issue: "Google OAuth not configured"
**Solution:** Complete Step 1 above - configure Google OAuth in Supabase dashboard

### Issue: "Invalid token" or 401 errors
**Cause:** Token expired (tokens last ~1 hour)
**Solution:** Get a new token using `get_token.html`

### Issue: "403 Forbidden" on admin endpoints
**Cause:** Your account doesn't have admin role
**Solution:** Run the SQL query in Step 3 to grant admin privileges

### Issue: "Connection refused" to localhost:8000
**Cause:** Backend server not running
**Solution:** 
```powershell
cd "D:\Coding\Github-Agent\proj-github agent"
.\.venv\Scripts\python.exe main.py
```

### Issue: Google sign-in popup blocked
**Cause:** Browser blocking popups
**Solution:** Allow popups for localhost or use direct login URL

### Issue: Redirect not working in get_token.html
**Cause:** Redirect URI not configured in Google Console
**Solution:** Add `file:///D:/Coding/Github-Agent/proj-github%20agent/get_token.html` to authorized redirect URIs

## 📝 Test Results Documentation

After running tests, save the output:

```powershell
.\.venv\Scripts\python.exe test_real_auth.py > test_results_with_auth.txt
```

## 🎯 Success Criteria

✅ All tests pass with authenticated user
✅ Admin tests pass with admin role
✅ Tokens can be refreshed successfully
✅ Logout invalidates tokens properly
✅ Protected endpoints reject invalid tokens (401)
✅ Admin endpoints reject non-admin users (403)

## 🔗 Useful Links

- **Supabase Dashboard:** https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr
- **Auth Providers:** https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr/auth/providers
- **SQL Editor:** https://supabase.com/dashboard/project/frcdvwuapmunkjaarrzr/sql
- **API Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Google Cloud Console:** https://console.cloud.google.com/apis/credentials

## 📞 Next Steps After Testing

Once authentication tests pass:
1. Document any issues found
2. Proceed to Phase 2 implementation (Team & Student Management)
3. Integrate auth with frontend application
4. Set up proper OAuth flow in production

---

**Note:** Keep your tokens secure and never commit them to git!
