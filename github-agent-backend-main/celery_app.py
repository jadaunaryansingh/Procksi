"""
Celery Application Configuration
Distributed task queue for repository analysis jobs
"""
from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

# Redis broker from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Convert to rediss:// for Upstash Redis (TLS required)
if 'upstash.io' in REDIS_URL:
    REDIS_URL = REDIS_URL.replace('redis://', 'rediss://')
    if '?ssl_cert_reqs=' not in REDIS_URL:
        REDIS_URL = REDIS_URL.rstrip('/') + '?ssl_cert_reqs=required'

# Create Celery app
celery_app = Celery(
    'hackeval',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['celery_worker']
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_expires=3600 * 24,  # Keep results for 24 hours
    
    # Timezone — crontab hours are interpreted in Asia/Kolkata (IST)
    timezone='Asia/Kolkata',
    enable_utc=False,
    
    # Task execution
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit
    
    # Worker configuration
    worker_prefetch_multiplier=1,  # One task at a time (sequential processing)
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks
    
    # Acknowledgment
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Re-queue if worker dies
    
    # Disable events to prevent Redis connection spam (Upstash compatibility)
    worker_send_task_events=False,
    task_send_sent_event=False,
    
    # Redis connection settings (fix Upstash TLS issues)
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_pool_limit=None,  # No connection pool limit
    
    # Task priority support (0-9, higher = more priority)
    # This allows fair distribution when multiple batches run concurrently
    task_default_priority=5,
    task_inherit_parent_priority=True,
)

# Task routes (separate queues)
celery_app.conf.task_routes = {
    'celery_worker.analyze_single_repository_task': {'queue': 'single_analysis'},  # Single repo analysis (dedicated worker)
    'celery_worker.analyze_repository_task': {'queue': 'batch'},  # Batch repo analysis (called by process_batch_sequential)
    'celery_worker.process_batch_sequential': {'queue': 'batch'},
    'celery_worker.move_to_dlq': {'queue': 'dlq'},
    'celery_worker.update_team_health_status': {'queue': 'default'},
}

# Celery Beat Schedule (Periodic Tasks)
from celery.schedules import crontab

# Automation kill-switches (default OFF for safety during incident handling)
ENABLE_WEEKLY_BATCH_ANALYSIS = os.getenv('ENABLE_WEEKLY_BATCH_ANALYSIS', 'false').lower() == 'true'
ENABLE_AUTO_RESUME_PAUSED_BATCHES = os.getenv('ENABLE_AUTO_RESUME_PAUSED_BATCHES', 'false').lower() == 'true'

celery_app.conf.beat_schedule = {
    # Retry DLQ jobs - Every night at 2 AM IST
    'retry-dlq-nightly': {
        'task': 'celery_worker.retry_dlq_jobs',
        'schedule': crontab(hour=2, minute=0),
    },
    
    # Update team health status - Every 2 hours
    'update-health-status': {
        'task': 'celery_worker.update_team_health_status',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
    },
    
    # NOTE: Automatic weekly student report emails DISABLED.
    # Emails are now sent manually via admin panel: POST /notifications/send-student-reports
    # 'weekly-student-reports': {
    #     'task': 'celery_worker.send_weekly_student_reports',
    #     'schedule': crontab(day_of_week=1, hour=15, minute=0),
    # },

    # NOTE: Recovery task also disabled since emails are manual-only now.
    # 'recover-weekly-student-reports': {
    #     'task': 'celery_worker.recover_interrupted_weekly_student_reports',
    #     'schedule': crontab(day_of_week=3, hour=12, minute=30),
    # },
    
    # Cleanup stuck analysis jobs - Every 15 minutes
    'cleanup-stuck-jobs': {
        'task': 'celery_worker.cleanup_stuck_analysis_jobs',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
    
    # Monitor scheduled task health - Every 30 minutes
    'monitor-task-health': {
        'task': 'celery_worker.monitor_scheduled_task_health',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    # Check for completed batches and send consolidated mentor alerts - Every 5 minutes
    'check-batch-completion-for-consolidation': {
        'task': 'celery_worker.check_and_consolidate_batch_alerts',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}

# Add weekly automation tasks only when explicitly enabled.
if ENABLE_WEEKLY_BATCH_ANALYSIS:
    celery_app.conf.beat_schedule['weekly-batch-analysis'] = {
        'task': 'celery_worker.auto_trigger_batch_analysis',
        'schedule': crontab(day_of_week=1, hour=10, minute=40),  # TEMP: Testing - revert to hour=9, minute=0
        'args': (False,),  # force=False (respect 7-day interval)
    }

if ENABLE_AUTO_RESUME_PAUSED_BATCHES:
    celery_app.conf.beat_schedule['auto-resume-paused-batches'] = {
        'task': 'celery_worker.auto_resume_paused_batches',
        'schedule': crontab(day_of_week=1, hour=9, minute=5),
    }

# Timezone already set in conf.update() above — Asia/Kolkata (IST), enable_utc=False

def load_schedule_overrides():
    """
    Load scheduled task overrides from the database and apply them to the beat_schedule.
    Called at startup to apply any overrides configured from the admin panel.
    """
    try:
        from src.api.backend.database import get_supabase_admin_client
        logger = celery_app.log.get_default_logger()
        
        supabase = get_supabase_admin_client()
        result = supabase.table('celery_beat_overrides').select('*').execute()
        overrides = result.data or []
        
        applied_count = 0
        for override in overrides:
            key = override['schedule_key']
            
            # If task doesn't exist in our conf, skip it
            if key not in celery_app.conf.beat_schedule:
                logger.warning(f"Found override for unknown task '{key}', skipping.")
                continue
                
            if not override['enabled']:
                logger.info(f"Disabling scheduled task '{key}' due to DB override.")
                del celery_app.conf.beat_schedule[key]
                applied_count += 1
                continue
                
            # It's enabled, let's update the schedule
            task_def = celery_app.conf.beat_schedule[key]
            current_schedule = task_def['schedule']
            
            # Extract current values as defaults if override is missing a field
            day = override.get('day_of_week')
            hour = override.get('hour')
            minute = override.get('minute')
            
            # We only know how to override crontab schedules
            if isinstance(current_schedule, crontab):
                # Update the crontab schedule with overridden string values if present
                kwargs = {}
                if day is not None: kwargs['day_of_week'] = day
                if hour is not None: kwargs['hour'] = hour
                if minute is not None: kwargs['minute'] = minute
                
                if kwargs:
                    task_def['schedule'] = crontab(**kwargs)
                    logger.info(f"Applied schedule override for '{key}': {kwargs}")
                    applied_count += 1
            else:
                logger.warning(f"Cannot override non-crontab schedule for '{key}'.")
                
        if applied_count > 0:
            logger.info(f"Successfully applied {applied_count} task schedule overrides from database.")
    except Exception as e:
        # Don't fail the startup if DB is unavailable, just use default schedule
        logger = celery_app.log.get_default_logger()
        logger.error(f"Failed to load schedule overrides from database: {e}")

# Load overrides when this module is imported (e.g. when celery beat starts)
load_schedule_overrides()

if __name__ == '__main__':
    celery_app.start()
