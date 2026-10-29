# Fake Commit Email Consolidation - Testing Guide

## Overview
This guide helps you test the newly implemented fake commit email consolidation system. Instead of receiving individual emails for each team's fake commits, mentors now receive ONE consolidated email listing all their teams with fake commits.

## Implementation Summary
The system works as follows:
1. **Batch Analysis Completes** - Teams are analyzed for fake commits
2. **Periodic Check** - Every 5 minutes, a task checks if batches are complete
3. **Consolidation Triggered** - When all teams in a batch are analyzed, consolidated emails are sent to mentors
4. **Email Contents** - Mentor receives one email with a table listing all their teams' fake commits and "View Details" links

## Files Modified
- `celery_app.py` - Added periodic task to beat_schedule
- `celery_worker.py` - Added `check_and_consolidate_batch_alerts()` task
- `src/api/backend/templates/email_templates.py` - Updated email template with team links

## Testing Steps

### Phase 1: Setup Verification

#### 1.1 Verify Database Tables
```sql
-- Check batch_analysis_runs table exists
SELECT * FROM batch_analysis_runs LIMIT 1;

-- Check teams table has required columns
SELECT id, batch_id, team_name, mentor_id FROM teams LIMIT 1;

-- Check users table has mentor email
SELECT id, email, role, full_name FROM users WHERE role = 'mentor' LIMIT 1;
```

#### 1.2 Verify Code Deployment
- Confirm `celery_app.py` has the new beat schedule entry:
  ```python
  'check-batch-completion-for-consolidation': {
      'task': 'celery_worker.check_and_consolidate_batch_alerts',
      'schedule': crontab(minute='*/5'),  # Every 5 minutes
  }
  ```
- Confirm `celery_worker.py` has `check_and_consolidate_batch_alerts()` function
- Confirm email template has "View Details" links

#### 1.3 Restart Services
```bash
# Restart Celery worker
docker compose restart celery

# Restart Celery Beat scheduler
docker compose restart celery-beat
```

### Phase 2: Manual Testing

#### 2.1 Create Test Batch (if not available)
If no active batch is running, you can create one manually:

```python
# In Python terminal or test script
from src.api.backend.database import get_supabase_admin_client

supabase = get_supabase_admin_client()

# Create a batch
batch = supabase.table('batches').insert({
    'name': 'Test Batch - Consolidation',
    'semester': 'Spring',
    'year': 2024
}).execute()

batch_id = batch.data[0]['id']
print(f"Created batch: {batch_id}")
```

#### 2.2 Manually Trigger Analysis for a Team
```python
from celery_app import celery_app
from celery_worker import analyze_repository_task
from uuid import uuid4

# Get a team from the batch
team = supabase.table('teams').select('id, team_name').eq('batch_id', batch_id).limit(1).execute()

if team.data:
    team_id = team.data[0]['id']
    team_name = team.data[0]['team_name']
    
    # Get repo_url (this needs to be a valid GitHub repo with potential fake commits)
    team_data = supabase.table('teams').select('repo_url').eq('id', team_id).single().execute()
    repo_url = team_data.data['repo_url']
    
    # Create analysis job
    job = supabase.table('analysis_jobs').insert({
        'id': str(uuid4()),
        'team_id': team_id,
        'batch_id': batch_id,
        'repo_url': repo_url,
        'status': 'pending',
        'metadata': {'batch_id': batch_id}
    }).execute()
    
    job_id = job.data[0]['id']
    
    # Trigger analysis
    task = analyze_repository_task.delay(team_id, job_id, repo_url, team_name)
    print(f"Analysis queued: {task.id}")
```

#### 2.3 Monitor Task Execution
```bash
# Check Celery worker logs
docker compose logs -f celery

# Look for these log messages:
# "Starting analysis for [team_name]"
# "Analysis completed for [team_name]"
# "Snapshot created for team [team_id]"
```

#### 2.4 Wait for Consolidation Check
The periodic task runs every 5 minutes. Wait for it to execute:

```bash
# Check Celery Beat logs
docker compose logs -f celery-beat

# Look for these log messages:
# "check_and_consolidate_batch_alerts" task execution
# "Batch [batch_id] analysis complete! Triggering consolidation..."
```

### Phase 3: Email Verification

#### 3.1 Check Email Logs
```bash
# Search for mentor alert emails in logs
docker compose logs celery | grep -i "mentor.*email\|📧 Critical fake commit alert"
```

#### 3.2 Check Email Service Logs
If using a test email service (MailHog, etc.):
- Navigate to email service UI (usually http://localhost:1025)
- Look for emails with subject: "🚨 Fake Commits Alert – X Teams"
- Verify:
  - **To**: Mentor's email address
  - **Subject**: Shows count of affected teams
  - **Body**: Contains a table with all affected teams
  - **Links**: Each team has a "View Details" link

#### 3.3 Sample Email Content Check
The consolidated email should contain:

```
FROM: [Sender email configured in system]
TO: [Mentor's email]
SUBJECT: 🚨 Fake Commits Alert – 2 Teams

Body Contents:
- Greeting with mentor name
- "Affected Teams" heading with a table
- Table columns: Team Name | Project | Repository | Fake Commits | Health
- Each team row includes a "View Details →" link
- Action Required section
- View Mentor Dashboard button
```

### Phase 4: Link Verification

#### 4.1 Test Team Dashboard Links
- Open an email from a mentor
- Click "View Details →" link on a team row
- Expected URL format: `http://[FRONTEND_URL]/admin/teams/[team_id]`
- Verify it navigates to the team dashboard

#### 4.2 Test Dashboard Button Link
- Click "View Mentor Dashboard" button
- Expected URL: `http://[FRONTEND_URL]/admin/mentor-portal`
- Verify it navigates to mentor portal dashboard

### Phase 5: Production Testing

#### 5.1 Verify with Real Batch Analysis
- Wait for the scheduled weekly batch analysis to run
- Or trigger it manually:
  ```python
  from celery_worker import auto_trigger_batch_analysis
  task = auto_trigger_batch_analysis.delay(force=True)
  ```

#### 5.2 Monitor the Full Flow
1. Batch analysis triggers
2. Teams are queued for analysis (check analysis_jobs table)
3. Each team is analyzed and reports generated
4. After 5 minutes, consolidation check runs
5. Mentors receive consolidated emails

#### 5.3 Check for Duplicates
Verify mentors DON'T receive multiple emails for the same batch:
- Check metadata field in batch_analysis_runs
- Should have `consolidation_triggered: True` and `consolidation_triggered_at` timestamp
- This prevents the consolidation from running multiple times

### Phase 6: Edge Cases

#### 6.1 Single Mentor Multiple Teams
```python
# Check if mentor has multiple teams with fake commits
teams_with_fake = supabase.table('teams').select(
    'id, team_name, mentor_id, metadata'
).eq('batch_id', batch_id).execute()

# Verify mentor gets ONE email with all teams listed
```

#### 6.2 Multiple Mentors in Same Batch
```python
# Verify each mentor gets their own email with only their teams
# Not a consolidated email for all mentors
```

#### 6.3 No Fake Commits Found
```python
# If no teams have fake commits, consolidation shouldn't trigger
# Check that mentors don't receive emails
```

#### 6.4 Batch with Failed Analyses
```python
# If some teams fail analysis, consolidation should still work for completed ones
# Failed teams should not appear in the consolidated email
```

## Troubleshooting

### Issue: Consolidation Task Not Running
**Solution:**
1. Check Celery Beat is running: `docker compose ps celery-beat`
2. Verify beat_schedule in celery_app.py
3. Check Beat logs: `docker compose logs celery-beat`
4. Restart: `docker compose restart celery-beat`

### Issue: Mentors Not Receiving Emails
**Solution:**
1. Verify SMTP configuration in environment variables
2. Check mentor email exists in users table: `SELECT * FROM users WHERE role = 'mentor'`
3. Check analysis jobs are marked as 'completed'
4. Check celery worker logs for email sending errors
5. Manually test email sending:
   ```python
   from src.api.backend.utils.email import send_alert_email
   send_alert_email(
       subject="Test",
       body_text="Test email",
       to_email="mentor@example.com",
       html_body="<p>Test</p>"
   )
   ```

### Issue: Wrong Email Links
**Solution:**
1. Verify FRONTEND_URL environment variable is set correctly
2. Check the link format in email template
3. Expected format: `{FRONTEND_URL}/admin/teams/{team_id}`
4. Test link manually in browser

### Issue: Consolidation Runs Multiple Times
**Solution:**
1. Check metadata in batch_analysis_runs for duplicates
2. Verify consolidation_triggered flag is being set
3. Check logs for "consolidation already triggered" message

## Database Queries for Debugging

```sql
-- Check batch_analysis_runs status
SELECT id, batch_id, run_number, status, metadata 
FROM batch_analysis_runs 
WHERE batch_id = '[batch_id]'
ORDER BY created_at DESC;

-- Check analysis jobs completion
SELECT id, team_id, status, completed_at 
FROM analysis_jobs 
WHERE batch_id = '[batch_id]';

-- Check teams and mentors
SELECT t.id, t.team_name, t.mentor_id, u.full_name, u.email 
FROM teams t
LEFT JOIN users u ON t.mentor_id = u.id
WHERE t.batch_id = '[batch_id]';

-- Check fake commit data
SELECT team_id, metadata 
FROM teams 
WHERE batch_id = '[batch_id]' 
AND metadata->>'fake_commit_count' > '0';
```

## Performance Notes
- Periodic task runs every 5 minutes (configurable in celery_app.py)
- Only processes batches in 'in_progress' status
- Duplicate prevention via metadata to avoid repeated emails
- Efficient database queries with proper indexing

## Rollback Plan
If issues arise:
1. Disable periodic task: Remove from beat_schedule or set `enabled=False`
2. Keep individual mentor alerts in `check_and_notify_fake_commits()` active
3. Individual emails will continue as fallback
4. Fix issues and re-enable consolidation

## Success Criteria
✅ Mentors receive ONE email per batch instead of individual emails per team
✅ Email contains all affected teams in a formatted table
✅ Each team has a "View Details" link to team dashboard
✅ No duplicate emails sent for same batch
✅ Email links navigate correctly
✅ Consolidation triggers within 5 minutes of batch completion
