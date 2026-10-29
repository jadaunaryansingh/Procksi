"""
Progress Tracking Utility for Analysis Jobs
Maps the 10-stage pipeline to progress percentages
"""
from typing import Optional
from uuid import UUID
from src.api.backend.crud import AnalysisJobCRUD


class ProgressTracker:
    """Track and update analysis job progress"""
    
    # Map pipeline stages to progress percentages
    STAGE_PROGRESS = {
        "starting": 0,
        "cloning": 10,
        "stack_detection": 20,
        "structure_analysis": 30,
        "maturity_check": 40,
        "commit_forensics": 50,
        "quality_check": 60,
        "security_scan": 70,
        "forensic_analysis": 80,
        "ai_judge": 90,
        "aggregation": 95,
        "completed": 100
    }
    
    def __init__(self, job_id: UUID):
        self.job_id = job_id
    
    def update(self, stage: str, custom_progress: Optional[int] = None):
        """Update job progress with stage name"""
        progress = custom_progress if custom_progress is not None else self.STAGE_PROGRESS.get(stage, 0)
        
        try:
            AnalysisJobCRUD.update_job_progress(
                job_id=self.job_id,
                progress=progress,
                stage=stage
            )
            print(f"      📊 Progress: {progress}% - {stage}")
        except Exception as e:
            print(f"      ⚠️  Failed to update progress: {e}")
    
    def complete(self):
        """Mark job as completed"""
        try:
            AnalysisJobCRUD.complete_job(self.job_id)
            print(f"      ✅ Job completed!")
        except Exception as e:
            print(f"      ⚠️  Failed to complete job: {e}")
    
    def fail(self, error_message: str):
        """Mark job as failed"""
        try:
            AnalysisJobCRUD.fail_job(self.job_id, error_message)
            print(f"      ❌ Job failed: {error_message}")
        except Exception as e:
            print(f"      ⚠️  Failed to mark job as failed: {e}")
