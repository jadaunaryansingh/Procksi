# Celery Beat - Automated Weekly Analysis

## Overview

Celery Beat has been configured to automatically trigger batch analysis every Monday at 9 AM IST for all active batches.

## What It Does

### Scheduled Tasks

1. **Weekly Batch Analysis** - Monday 9 AM IST
   - Runs `auto_trigger_batch_analysis` task
   - Analyzes all active batches
   - Respects 7-day re-analysis interval
   - Sends completion notification

2. **DLQ Retry** - Daily 2 AM IST
   - Runs `retry_dlq_jobs` task
   - Auto-retries failed jobs from Dead Letter Queue

## How to Run

### Development - Windows

**Option 1: Use the startup script**
```bash
.\start_celery.bat
```

**Option 2: Manual command**
```bash
celery -A celery_app worker --pool=solo --loglevel=info -Q analysis,batch,dlq --beat
```

### Production - Linux/Docker

**Separate processes (recommended):**
```bash
# Terminal 1: Worker
celery -A celery_app worker -Q analysis,batch,dlq

# Terminal 2: Beat Scheduler
celery -A celery_app beat --loglevel=info
```

## Testing

### Manual Test (Before Monday)

```python
# Test the auto-trigger task
from celery_worker import auto_trigger_batch_analysis

# Run immediately with force=True
result = auto_trigger_batch_analysis.delay(force=True)
print(f"Task ID: {result.id}")
```

### Check Schedule

```bash
celery -A celery_app inspect scheduled
```

### View Beat Status

When Beat is running, you'll see:
```
[2026-01-21 09:00:00,000] Scheduler: Sending due task weekly-batch-analysis
[2026-01-21 09:00:00,001] Received task: celery_worker.auto_trigger_batch_analysis
```

## Configuration

### Schedule (in celery_app.py)

```python
'weekly-batch-analysis': {
    'task': 'celery_worker.auto_trigger_batch_analysis',
    'schedule': crontab(day_of_week=1, hour=9, minute=0),  # Monday 9 AM
    'args': (False,),  # Respect 7-day interval
}
```

### Timezone

```python
celery_app.conf.timezone = 'Asia/Kolkata'  # IST
```

## Notifications

Current: Logs to console
Future: Email notifications (TODO in `send_completion_notification`)

### Example Output

```
============================================================
📧 Weekly Analysis Summary
============================================================
Total Batches: 3
Triggered: 2
Skipped: 1
Failed: 0

  ✓ 4th Sem 2024: 15 teams queued
  ✓ 6th Sem 2024: 12 teams queued
============================================================
```

## Troubleshooting

**Beat not running?**
- Check if `--beat` flag is included in celery command
- Or run Beat as separate process

**Tasks not executing?**
- Verify timezone matches your server
- Check `celery -A celery_app inspect scheduled`
- Review Beat logs for errors

**Windows issues?**
- Use `--pool=solo` flag
- Run `start_celery.bat` script

## Next Steps

- [ ] Add email notifications
- [ ] Add Slack webhook integration
- [ ] Create admin dashboard for schedules
- [ ] Make schedule configurable via UI
