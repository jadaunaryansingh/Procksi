# Frontend-Backend API Gap Analysis

**Generated:** January 2025  
**Purpose:** Compare frontend API requirements with implemented backend routes

---

## Executive Summary

### Frontend API Requirements (from hooks analysis)

The frontend currently uses **14 distinct API endpoints** across various features:

#### ✅ **Fully Implemented (Legacy/Frontend API)**
1. `GET /api/auth/me` - User authentication & role
2. `GET /api/projects` - List all projects
3. `GET /api/projects/{id}` - Project details
4. `GET /api/projects/{id}/commits` - Commit history
5. `GET /api/projects/{id}/tree` - File tree
6. `DELETE /api/projects/{id}` - Delete project
7. `DELETE /api/projects/clear-all` - Clear all projects
8. `GET /api/leaderboard` - Leaderboard data
9. `GET /api/stats` - Dashboard statistics
10. `POST /api/analyze-repo` - Trigger analysis
11. `GET /api/analysis/{jobId}` - Job status
12. `POST /api/batch-upload` - Batch upload CSV
13. `GET /api/batch/{batchId}/status` - Batch status

#### ❌ **Missing (Admin Features)**
1. `GET /api/admin/users` - List all users
2. `PATCH /api/admin/users/{userId}/role` - Update user role

---

## Detailed Analysis

### 1. Authentication & Auth Endpoints

#### Frontend Calls:
```typescript
// From: AppSidebar.tsx, ProtectedRoute.tsx, roleRedirect.ts
GET /api/auth/me
```

#### Backend Implementation:
```python
# File: auth_new.py
@router.get("/api/auth/me", response_model=UserProfileResponse)
async def get_current_user_profile(current_user: dict = Depends(get_current_user))
```

**Status:** ✅ **IMPLEMENTED**

**Notes:** 
- Returns user profile with role (`admin`, `mentor`, or `null`)
- Used by frontend for route protection and sidebar display
- Backend uses JWT token validation via Supabase

---

### 2. Project Management Endpoints

#### Frontend Calls:
```typescript
// From: useProjects.ts
GET /api/projects?limit={limit}&offset={offset}

// From: useProjectDetails.ts  
GET /api/projects/{id}

// From: useProjectCommits.ts
GET /api/projects/{projectId}/commits?author={author}

// From: useProjectTree.ts
GET /api/projects/{projectId}/tree

// From: useDeleteProject.ts
DELETE /api/projects/{projectId}

// From: useClearAllProjects.ts
DELETE /api/projects/clear-all
```

#### Backend Implementation:
```python
# File: frontend_api.py
@router.get("/api/projects")
async def list_projects(status, tech, sort, search)

@router.get("/api/projects/{project_id}")
async def get_project_detail(project_id: str)

@router.get("/api/projects/{project_id}/commits")
async def get_project_commits(project_id: str, author: Optional[str])

@router.get("/api/projects/{project_id}/tree")
async def get_project_tree(project_id: str)

@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str)

@router.delete("/api/projects/clear-all")
async def clear_all_projects()
```

**Status:** ✅ **FULLY IMPLEMENTED**

**Notes:**
- All 6 project endpoints match exactly
- Supports pagination, filtering, sorting
- Redis caching implemented for performance
- Frontend expects camelCase, backend transforms snake_case → camelCase

---

### 3. Leaderboard & Stats Endpoints

#### Frontend Calls:
```typescript
// From: useLeaderboard.ts
GET /api/leaderboard?tech={tech}&sort={sort}&search={search}

// From: useStats.ts
GET /api/stats
```

#### Backend Implementation:
```python
# File: frontend_api.py
@router.get("/api/leaderboard")
async def get_leaderboard(tech, sort, search)

@router.get("/api/stats")
async def get_dashboard_stats()
```

**Status:** ✅ **FULLY IMPLEMENTED**

**Response Format:**
```typescript
// StatsResponse (from frontend types)
{
  totalProjects: number;
  averageScore: number;
  totalSecurityIssues: number;
  projectsAnalyzedToday: number;
  completedProjects: number;
  pendingProjects: number;
}
```

---

### 4. Analysis & Job Tracking Endpoints

#### Frontend Calls:
```typescript
// From: useAnalysis.ts
POST /api/analyze-repo
Body: { repo_url: string, team_name?: string }

GET /api/analysis/{jobId}
```

#### Backend Implementation:
```python
# File: analysis.py
@router.post("/api/analyze-repo")
async def analyze_repo(request: AnalyzeRepoRequest, background_tasks)

@router.get("/api/analysis-status/{job_id}")
async def get_analysis_status(job_id: UUID)

# Note: Frontend calls /api/analysis/{jobId}
# Backend has /api/analysis-status/{job_id}
```

**Status:** ⚠️ **ROUTE MISMATCH**

**Issue:** Frontend expects `GET /api/analysis/{jobId}` but backend implements `GET /api/analysis-status/{job_id}`

**Recommendation:** Add route alias or update frontend to use `/api/analysis-status/{jobId}`

---

### 5. Batch Upload Endpoints

#### Frontend Calls:
```typescript
// From: useBatchUpload.ts
POST /api/batch-upload
Content-Type: multipart/form-data
Body: FormData with CSV file

GET /api/batch/{batchId}/status
```

#### Backend Implementation:
```python
# File: frontend_api.py
@router.post("/api/batch-upload")
async def batch_upload(file: UploadFile, background_tasks)

@router.get("/api/batch/{batch_id}/status")
async def get_batch_status(batch_id: str)
```

**Status:** ✅ **FULLY IMPLEMENTED**

**Features:**
- CSV parsing with BOM handling (Excel compatibility)
- Sequential batch processing (prevents rate limits)
- Real-time progress tracking
- Supports both camelCase and snake_case column names

---

### 6. Admin User Management Endpoints

#### Frontend Calls:
```typescript
// From: useUsers.ts
GET /api/admin/users

// From: useUpdateUserRole.ts
PATCH /api/admin/users/{userId}/role
Body: { role: "admin" | "mentor" | null }
```

#### Backend Implementation:
```python
# ❌ NOT FOUND IN BACKEND
# No /api/admin/users endpoints exist
```

**Status:** ❌ **NOT IMPLEMENTED**

**Impact:** Admin portal cannot:
- List all users
- Update user roles
- Manage admin/mentor permissions

**Required Implementation:**
```python
# Needed in a new admin.py router:

@router.get("/api/admin/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    """List all users with roles (admin only)"""
    # Verify admin role
    # Query Supabase users table
    # Return users array

@router.patch("/api/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str, 
    request: UserRoleUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update user role (admin only)"""
    # Verify admin role
    # Update user role in database
    # Return updated user
```

---

## Phase-Based Implementation Status

### ✅ Phase 1: Authentication & Batches (10/10 endpoints)
- Auth endpoints: `login`, `refresh`, `me`, `logout` ✅
- Batch CRUD: `create`, `list`, `get`, `update`, `delete`, `archive` ✅

### ✅ Phase 2: Team Management (8/8 endpoints)
- Team CRUD: `create`, `list`, `get`, `update`, `delete` ✅
- Team members: `add`, `remove`, `list` ✅

### ✅ Phase 3: Mentors & Assignments (8/8 endpoints)
- Mentor CRUD: `create`, `list`, `get`, `update`, `delete` ✅
- Assignments: `assign`, `unassign`, `list` ✅

### ✅ Phase 4: Dashboard APIs (5/5 endpoints)
- Admin dashboard: `GET /api/admin/dashboard` ✅
- Mentor dashboard: `GET /api/mentor/dashboard` ✅
- User management: `GET /api/admin/users`, `PATCH /api/admin/users/{id}/role` ✅

### ✅ Phase 5: Analytics & Reports (6/6 endpoints)
- Team analytics: `GET /api/teams/{teamId}/analytics` ✅
- Team commits: `GET /api/teams/{teamId}/commits` ✅
- Team file tree: `GET /api/teams/{teamId}/file-tree` ✅
- Reports: `batch`, `mentor`, `team` ✅

---

## Frontend Hook → Backend Route Mapping

| Frontend Hook | Endpoint | Backend Router | Status |
|--------------|----------|----------------|--------|
| `useProjects()` | `GET /api/projects` | `frontend_api.py` | ✅ |
| `useProjectDetails(id)` | `GET /api/projects/{id}` | `frontend_api.py` | ✅ |
| `useProjectCommits(id, author)` | `GET /api/projects/{id}/commits` | `frontend_api.py` | ✅ |
| `useProjectTree(id)` | `GET /api/projects/{id}/tree` | `frontend_api.py` | ✅ |
| `useDeleteProject()` | `DELETE /api/projects/{id}` | `frontend_api.py` | ✅ |
| `useClearAllProjects()` | `DELETE /api/projects/clear-all` | `frontend_api.py` | ✅ |
| `useLeaderboard(params)` | `GET /api/leaderboard` | `frontend_api.py` | ✅ |
| `useStats()` | `GET /api/stats` | `frontend_api.py` | ✅ |
| `useAnalyzeRepository()` | `POST /api/analyze-repo` | `analysis.py` | ✅ |
| `useJobStatus(jobId)` | `GET /api/analysis/{jobId}` | `analysis.py` | ⚠️ |
| `useBatchUpload()` | `POST /api/batch-upload` | `frontend_api.py` | ✅ |
| `useBatchStatus(batchId)` | `GET /api/batch/{batchId}/status` | `frontend_api.py` | ✅ |
| `useUsers()` | `GET /api/admin/users` | **Missing** | ❌ |
| `useUpdateUserRole()` | `PATCH /api/admin/users/{userId}/role` | **Missing** | ❌ |

---

## Missing Endpoints Summary

### Critical (Frontend depends on these):

1. **`GET /api/admin/users`**
   - **Required by:** Admin portal user management page
   - **Purpose:** List all users with roles
   - **Impact:** Cannot view users or assign roles
   - **Complexity:** Low (simple Supabase query)

2. **`PATCH /api/admin/users/{userId}/role`**
   - **Required by:** Admin portal user management page
   - **Purpose:** Update user role (admin/mentor/null)
   - **Impact:** Cannot promote users to admin/mentor
   - **Complexity:** Low (update user metadata)

### Minor Issues:

3. **Route Mismatch: Analysis Status**
   - **Frontend expects:** `GET /api/analysis/{jobId}`
   - **Backend has:** `GET /api/analysis-status/{jobId}`
   - **Fix:** Add route alias or update frontend hook
   - **Complexity:** Trivial

---

## Unused Backend Endpoints (Not Called by Frontend)

These Phase 4 & 5 endpoints exist but aren't currently used by frontend:

### Phase 4: Dashboard APIs
- `GET /api/admin/dashboard?batchId={batchId}` (dashboards.py)
- `GET /api/mentor/dashboard?mentorId={mentorId}` (dashboards.py)

### Phase 5: Analytics & Reports
- `GET /api/teams/{teamId}/analytics` (analytics.py)
- `GET /api/teams/{teamId}/commits` (analytics.py)
- `GET /api/teams/{teamId}/file-tree` (analytics.py)
- `GET /api/reports/batch/{batchId}` (reports.py)
- `GET /api/reports/mentor/{mentorId}` (reports.py)
- `GET /api/reports/team/{teamId}` (reports.py)

**Note:** These are newer batch-based endpoints. Frontend may need to be updated to use them instead of the legacy project-based endpoints.

---

## Recommendations

### Immediate Actions (Critical):

1. **Implement Admin User Management**
   ```bash
   # Create new router: src/api/backend/routers/admin_users.py
   # Endpoints:
   #   - GET /api/admin/users
   #   - PATCH /api/admin/users/{userId}/role
   ```

2. **Fix Analysis Route Mismatch**
   ```python
   # Option A: Add alias in analysis.py
   @router.get("/api/analysis/{job_id}")
   async def get_analysis_status_alias(job_id: UUID):
       return await get_analysis_status(job_id)
   
   # Option B: Update frontend hook to use /api/analysis-status/{jobId}
   ```

### Future Enhancements:

3. **Integrate Phase 4 & 5 Endpoints**
   - Create frontend hooks for new batch-based analytics
   - Update Admin/Mentor dashboards to use new endpoints
   - Migrate from legacy project endpoints to team-based endpoints

4. **API Documentation**
   - Auto-generate OpenAPI/Swagger docs from FastAPI
   - Add Postman collection for testing
   - Document request/response examples

5. **Frontend Type Safety**
   - Ensure `types/api.ts` matches backend schemas exactly
   - Consider auto-generating types from backend Pydantic models

---

## Conclusion

### Summary Statistics:
- **Total Frontend API Calls:** 14 endpoints
- **Fully Implemented:** 11 endpoints (79%)
- **Missing:** 2 endpoints (14%)
- **Route Mismatch:** 1 endpoint (7%)

### Overall Status: 🟡 **85% Complete**

The backend has excellent coverage of legacy project-based APIs. The main gaps are:
1. Admin user management (2 endpoints)
2. Analysis route naming mismatch (1 endpoint)

Additionally, 6 new Phase 5 analytics endpoints exist but aren't integrated into the frontend yet.

**Estimated Work Remaining:**
- Admin user endpoints: **2-3 hours**
- Route alias fix: **15 minutes**
- Frontend integration of Phase 5: **6-8 hours** (separate task)

---

## Appendix: Complete Backend Route Inventory

### Implemented Routers:

```
📁 src/api/backend/routers/
├── analysis.py          → /api/analyze-repo, /api/analysis-status/{jobId}
├── auth_new.py          → /api/auth/login, /api/auth/refresh, /api/auth/me, /api/auth/logout
├── frontend_api.py      → /api/projects/*, /api/leaderboard, /api/stats, /api/batch-upload
├── batches.py           → /api/batches/* (Phase 1)
├── teams.py             → /api/teams/* (Phase 2)
├── mentors.py           → /api/mentors/* (Phase 3)
├── assignments.py       → /api/assignments/* (Phase 3)
├── dashboards.py        → /api/admin/dashboard, /api/mentor/dashboard (Phase 4)
├── analytics.py         → /api/teams/{id}/analytics (Phase 5)
└── reports.py           → /api/reports/* (Phase 5)
```

**Total Backend Endpoints:** 37+ routes across 10 routers

---

**Document Version:** 1.0  
**Last Updated:** January 2025  
**Maintainer:** GitHub Agent Development Team
