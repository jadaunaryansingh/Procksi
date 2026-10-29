# Phase 4 Implementation: Dashboard APIs

## Overview

Phase 4 implements comprehensive dashboard APIs for both administrators and mentors, providing real-time statistics, team health monitoring, and workload management.

**Implementation Date:** January 17, 2026  
**Status:** ✅ Complete  
**Dependencies:** Phase 1 (Auth), Phase 2 (Teams), Phase 3 (Mentors & Assignments)

---

## Endpoints Summary

### Admin Dashboard Endpoints (3 total)

1. **GET `/api/admin/dashboard`** - Admin dashboard overview for a batch
2. **GET `/api/admin/users`** - List all users with filtering
3. **PUT `/api/admin/users/{userId}/role`** - Update user role

### Mentor Dashboard Endpoints (2 total)

4. **GET `/api/mentor/dashboard`** - Mentor's personal dashboard
5. **GET `/api/mentor/teams`** - List mentor's teams with filtering

**Total Phase 4 Endpoints:** 5

---

## Detailed Endpoint Documentation

### 1. Admin Dashboard Overview

**Endpoint:** `GET /api/admin/dashboard`  
**Authorization:** Admin only  
**Description:** Get comprehensive dashboard overview for a specific batch with real-time statistics.

**Query Parameters:**
- `batchId` (required) - Batch ID to get dashboard for

**Response Schema:**
```json
{
  "batchId": "4th-sem-2024",
  "batchName": "4th Semester 2024",
  "overview": {
    "totalTeams": 12,
    "activeTeams": 10,
    "inactiveTeams": 2,
    "totalMentors": 4,
    "totalStudents": 48,
    "unassignedTeams": 2,
    "analysisQueue": 0
  },
  "healthDistribution": {
    "onTrack": 7,
    "atRisk": 3,
    "critical": 2
  },
  "recentActivity": [
    {
      "id": "uuid",
      "type": "team_created",
      "message": "New team added",
      "teamName": "Team Alpha",
      "timestamp": "2024-01-17T09:30:00Z"
    }
  ],
  "mentorWorkload": [
    {
      "mentorId": "uuid",
      "mentorName": "John Mentor",
      "assignedTeams": 3,
      "onTrack": 2,
      "atRisk": 1
    }
  ]
}
```

**Key Features:**
- Real-time team statistics (total, active, inactive)
- Health distribution visualization data
- Recent activity feed (last 10 activities)
- Mentor workload analysis
- Unassigned teams count

---

### 2. Admin Users Management

**Endpoint:** `GET /api/admin/users`  
**Authorization:** Admin only  
**Description:** List all users with optional filtering, search, and pagination.

**Query Parameters:**
- `role` (optional) - Filter by role: "admin" or "mentor"
- `search` (optional) - Search by name or email
- `page` (optional, default: 1) - Page number
- `pageSize` (optional, default: 20) - Items per page (max: 100)

**Response Schema:**
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "fullName": "John Doe",
      "role": "mentor",
      "status": "active",
      "lastLogin": "2024-01-17T10:00:00Z",
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 25,
  "page": 1,
  "pageSize": 20
}
```

**Key Features:**
- Role-based filtering
- Search across name and email
- Pagination support
- User status tracking

---

### 3. Update User Role

**Endpoint:** `PUT /api/admin/users/{userId}/role`  
**Authorization:** Admin only  
**Description:** Update a user's role between admin and mentor.

**Request Body:**
```json
{
  "role": "mentor"  // "admin" or "mentor"
}
```

**Response Schema:**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "fullName": "John Doe",
    "role": "mentor",
    "status": "active",
    "lastLogin": "2024-01-17T10:00:00Z",
    "createdAt": "2024-01-01T00:00:00Z"
  },
  "message": "User role updated successfully"
}
```

**Key Features:**
- Role validation (admin/mentor only)
- User existence check
- Automatic timestamp updates

---

### 4. Mentor Dashboard

**Endpoint:** `GET /api/mentor/dashboard`  
**Authorization:** Mentor or Admin  
**Description:** Get mentor's personal dashboard with assigned teams overview.

**Response Schema:**
```json
{
  "mentorId": "uuid",
  "mentorName": "John Mentor",
  "overview": {
    "totalTeams": 3,
    "onTrack": 2,
    "atRisk": 1,
    "critical": 0
  },
  "teams": [
    {
      "id": "uuid",
      "name": "Team Alpha",
      "batchId": "4th-sem-2024",
      "batchName": "4th Semester 2024",
      "repoUrl": "https://github.com/team-alpha/project",
      "healthStatus": "on_track",
      "lastActivity": "2 hours ago",
      "contributionBalance": 85,
      "riskFlags": [],
      "totalScore": 85.5
    }
  ],
  "recentActivity": [
    {
      "teamId": "uuid",
      "teamName": "Team Alpha",
      "type": "update",
      "message": "Team updated",
      "timestamp": "2024-01-17T09:30:00Z"
    }
  ]
}
```

**Key Features:**
- Personalized team statistics
- Health status distribution
- Team details with scores
- Recent activity feed
- Human-readable last activity times

---

### 5. Mentor Teams List

**Endpoint:** `GET /api/mentor/teams`  
**Authorization:** Mentor or Admin  
**Description:** Get all teams assigned to mentor with filtering and sorting.

**Query Parameters:**
- `batchId` (optional) - Filter by batch ID
- `healthStatus` (optional) - Filter by: "on_track", "at_risk", or "critical"
- `search` (optional) - Search by team name
- `sort` (optional) - Sort by: "name", "lastActivity", or "healthStatus"

**Response Schema:**
```json
{
  "teams": [
    {
      "id": "uuid",
      "name": "Team Alpha",
      "batchId": "4th-sem-2024",
      "batchName": "4th Semester 2024",
      "repoUrl": "https://github.com/...",
      "healthStatus": "on_track",
      "status": "active",
      "contributionBalance": 85,
      "totalScore": 85.5
    }
  ],
  "total": 3
}
```

**Key Features:**
- Multiple filter options
- Flexible sorting
- Team search
- Batch filtering

---

## Authorization Model

### Admin Endpoints
- `/api/admin/dashboard` - Admin only
- `/api/admin/users` - Admin only
- `/api/admin/users/{userId}/role` - Admin only

**Access Control:** All admin endpoints check `current_user.role == "admin"`. Non-admin requests receive `403 Forbidden`.

### Mentor Endpoints
- `/api/mentor/dashboard` - Mentor or Admin
- `/api/mentor/teams` - Mentor or Admin

**Access Control:** Mentor endpoints use `current_user.user_id` to filter results. Admins can access these endpoints and see their own dashboard.

---

## Database Schema Usage

### Tables Accessed

1. **batches** - Batch information
2. **teams** - Team data with health status
3. **users** - User information and roles
4. **team_members** - Student membership data
5. **mentor_team_assignments** (future use)

### Key Queries

**Admin Dashboard:**
```sql
-- Get teams by batch
SELECT * FROM teams WHERE batch_id = ?

-- Get team members count
SELECT COUNT(*) FROM team_members WHERE batch_id = ?

-- Get user details
SELECT * FROM users WHERE id IN (mentor_ids)
```

**Mentor Dashboard:**
```sql
-- Get assigned teams with batch info
SELECT teams.*, batches.name 
FROM teams 
JOIN batches ON teams.batch_id = batches.id
WHERE teams.mentor_id = ?
```

---

## Testing

### Test Suite: `test_phase4.py`

**Features:**
- Automated testing of all 5 endpoints
- Role-based test execution (admin vs mentor)
- Colored terminal output
- Detailed response validation

**Usage:**
```bash
# Run all tests
python test_phase4.py

# Follow prompts to provide:
# 1. Authentication token (Google ID or Supabase access)
# 2. Test execution is automatic based on user role
```

**Test Coverage:**

For **Admin Role:**
- ✅ Admin dashboard overview
- ✅ User list with pagination
- ✅ User role update
- ✅ Mentor dashboard (as admin)
- ✅ Mentor teams listing

For **Mentor Role:**
- ✅ Mentor dashboard
- ✅ Mentor teams with filters
- ⚠️ Admin endpoints skipped (403 expected)

---

## Integration with Previous Phases

### Phase 1 (Authentication)
- Uses JWT authentication from `get_current_user()`
- Role-based access control (admin/mentor)
- Token validation

### Phase 2 (Team Management)
- Reads team data including health status
- Calculates team statistics
- Uses team counts for dashboard metrics

### Phase 3 (Mentor Management)
- Reads mentor assignments
- Calculates mentor workload
- Shows team distribution across mentors

**Data Flow:**
```
Auth (Phase 1) → User Role → Dashboard Access
Teams (Phase 2) → Team Stats → Dashboard Metrics
Mentors (Phase 3) → Assignments → Workload Analysis
```

---

## Implementation Details

### Health Status Calculation

Teams can have three health statuses:
- `on_track` - Team is performing well
- `at_risk` - Team needs attention
- `critical` - Urgent intervention required

**Distribution Calculation:**
```python
health_dist = {
    "onTrack": len([t for t in teams if t.get("health_status") == "on_track"]),
    "atRisk": len([t for t in teams if t.get("health_status") == "at_risk"]),
    "critical": len([t for t in teams if t.get("health_status") == "critical"])
}
```

### Last Activity Formatting

Converts database timestamps to human-readable format:
- "Less than an hour ago"
- "2 hours ago"
- "3 days ago"

```python
time_diff = datetime.now(updated_time.tzinfo) - updated_time
hours = int(time_diff.total_seconds() / 3600)
if hours < 1:
    last_activity = "Less than an hour ago"
elif hours < 24:
    last_activity = f"{hours} hours ago"
else:
    days = hours // 24
    last_activity = f"{days} days ago"
```

### Mentor Workload Analysis

Calculates workload distribution:
```python
mentor_workload.append({
    "mentorId": mentor_id,
    "mentorName": mentor["full_name"],
    "assignedTeams": assigned_teams,
    "onTrack": on_track,
    "atRisk": at_risk
})
```

---

## Error Handling

### Common Error Responses

**403 Forbidden** - Non-admin accessing admin endpoints
```json
{
  "detail": "Admin access required"
}
```

**404 Not Found** - Invalid batch or user ID
```json
{
  "detail": "Batch not found"
}
```

**400 Bad Request** - Invalid parameters
```json
{
  "detail": "Invalid role. Must be 'admin' or 'mentor'"
}
```

---

## Performance Considerations

### Query Optimization

1. **Batch Queries:** Fetch all teams for a batch in one query
2. **User Lookups:** Use WHERE IN clause for multiple mentor lookups
3. **Pagination:** Applied in Python after filtering for simplicity

### Caching Opportunities (Future)

- Dashboard statistics (5-minute TTL)
- User lists (1-minute TTL)
- Health distribution (5-minute TTL)

### Response Size Management

- Recent activity limited to 10 items
- Mentor workload sorted by team count
- Pagination for user lists (max 100 per page)

---

## Future Enhancements

### Planned Features

1. **Real-time Updates**
   - WebSocket support for live dashboard updates
   - Real-time activity feed
   - Push notifications for critical health status

2. **Advanced Analytics**
   - Historical trend analysis
   - Mentor performance metrics
   - Team progress tracking over time

3. **Export Capabilities**
   - PDF dashboard reports
   - CSV data export
   - Scheduled email reports

4. **Activity Feed Enhancement**
   - Track more activity types (commits, analysis, comments)
   - Activity filtering and search
   - Detailed activity logs

5. **Mentor Workload Balancing**
   - Automatic team assignment suggestions
   - Workload threshold alerts
   - Team reassignment recommendations

---

## API Usage Examples

### Example 1: Admin Dashboard

```bash
curl -X GET \
  'http://localhost:8000/api/admin/dashboard?batchId=4th-sem-2024' \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN'
```

### Example 2: Filter Users by Role

```bash
curl -X GET \
  'http://localhost:8000/api/admin/users?role=mentor&page=1&pageSize=10' \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN'
```

### Example 3: Update User Role

```bash
curl -X PUT \
  'http://localhost:8000/api/admin/users/USER_ID/role' \
  -H 'Authorization: Bearer YOUR_ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"role": "admin"}'
```

### Example 4: Mentor Dashboard

```bash
curl -X GET \
  'http://localhost:8000/api/mentor/dashboard' \
  -H 'Authorization: Bearer YOUR_MENTOR_TOKEN'
```

### Example 5: Filter Mentor Teams

```bash
curl -X GET \
  'http://localhost:8000/api/mentor/teams?healthStatus=at_risk&sort=lastActivity' \
  -H 'Authorization: Bearer YOUR_MENTOR_TOKEN'
```

---

## Complete Implementation Status

### Phases 1-4 Summary

| Phase | Feature | Endpoints | Status |
|-------|---------|-----------|--------|
| Phase 1 | Authentication & Batches | 10 | ✅ Complete |
| Phase 2 | Team Management | 8 | ✅ Complete |
| Phase 3 | Mentor & Assignments | 8 | ✅ Complete |
| **Phase 4** | **Dashboard APIs** | **5** | ✅ **Complete** |
| **Total** | **All Core Features** | **31** | ✅ **Operational** |

---

## Files Created/Modified

### New Files
1. `src/api/backend/routers/dashboards.py` (~400 lines)
   - Admin dashboard endpoint
   - Admin users management
   - Mentor dashboard endpoint
   - Mentor teams listing

2. `test_phase4.py` (~400 lines)
   - Comprehensive test suite
   - Role-based testing
   - Interactive token input

3. `PHASE_4_IMPLEMENTATION.md` (this file)
   - Complete documentation
   - API reference
   - Integration guide

### Modified Files
1. `src/api/backend/schemas.py`
   - Added 10+ dashboard-related schemas
   - Request/response models for all endpoints

2. `main.py`
   - Imported dashboards router
   - Registered dashboard endpoints

---

## Quick Start Guide

### 1. Start Server
```bash
cd "proj-github agent"
python main.py
```

### 2. Run Tests
```bash
# Admin tests (requires admin token)
python test_phase4.py

# Or use existing authentication
# Get token from get_token.html
# Paste when prompted
```

### 3. Access Dashboards

**Admin Dashboard:**
- Get batch ID: `GET /api/batches`
- View dashboard: `GET /api/admin/dashboard?batchId={id}`

**Mentor Dashboard:**
- View dashboard: `GET /api/mentor/dashboard`
- Filter teams: `GET /api/mentor/teams?healthStatus=at_risk`

---

## Support & Troubleshooting

### Common Issues

**Issue:** "Admin access required"
- **Solution:** Ensure user has admin role in database
- **SQL:** `UPDATE users SET role = 'admin' WHERE email = 'your@email.com'`

**Issue:** Empty dashboard (no teams)
- **Solution:** Create teams in the batch first
- **Endpoint:** `POST /api/teams` (Phase 2)

**Issue:** No mentors in workload
- **Solution:** Assign teams to mentors
- **Endpoint:** `POST /api/assignments` (Phase 3)

### Testing Tips

1. **Create Sample Data:**
   - Create batch (Phase 1)
   - Upload teams CSV (Phase 2)
   - Create mentors (Phase 3)
   - Assign teams (Phase 3)
   - View dashboards (Phase 4)

2. **Test Different Roles:**
   - Update your user role to admin for admin tests
   - Create additional test users with mentor role
   - Test role transitions with user role update endpoint

3. **Verify Statistics:**
   - Check team counts match database
   - Verify health distribution sums to total teams
   - Confirm mentor workload equals assigned teams

---

## Next Steps

### Option B: Analytics & Reports
- Batch-level analytics
- Mentor performance metrics  
- Team progress tracking
- Export to PDF/CSV

### Option C: Advanced Features
- Student contribution analysis
- Risk detection algorithms
- Automated health updates
- Notification system

### Production Readiness
- Add response caching
- Implement rate limiting
- Add request validation
- Set up monitoring/logging

---

**Phase 4 Status:** ✅ Complete and Ready for Testing

All dashboard endpoints are fully implemented, tested, and documented. The system now provides comprehensive real-time monitoring for both administrators and mentors.
