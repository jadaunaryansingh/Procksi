"""
Background Job Processing
Handles async analysis jobs with sequential batch support
"""
import traceback
import time
from uuid import UUID
from typing import List, Dict
from src.api.backend.services.analyzer_service import AnalyzerService
from src.api.backend.crud import BatchCRUD, AnalysisJobCRUD
from src.api.backend.utils.logger import batch_logger

def run_analysis_job(project_id: str, job_id: str, repo_url: str, team_name: str = None):
    """
    Background task to run repository analysis
    
    Args:
        project_id: Project UUID as string
        job_id: Job UUID as string
        repo_url: GitHub repository URL
        team_name: Optional team name
    """
    try:
        # Convert string UUIDs to UUID objects
        project_uuid = UUID(project_id)
        job_uuid = UUID(job_id)
        
        # Run analysis
        AnalyzerService.analyze_repository(
            team_id=project_uuid,  # Changed from project_id to team_id
            job_id=job_uuid,
            repo_url=repo_url,
            team_name=team_name
        )
        
    except Exception as e:
        batch_logger.error(f"Background job failed: {e}")
        batch_logger.error(f"Project: {project_id}, Job: {job_id}")
        batch_logger.error(traceback.format_exc())


def run_batch_sequential(batch_id: str, repos: List[Dict[str, str]]):
    """
    Process repositories sequentially (one-by-one) to avoid rate limiting.
    
    Args:
        batch_id: Batch UUID as string
        repos: List of dicts with keys: project_id, job_id, repo_url, team_name
    """

    batch_logger.info(f"{'='*60}")
    batch_logger.info(f"🚀 Starting Sequential Batch Processing: {len(repos)} repos")
    batch_logger.info(f"   Batch ID: {batch_id}")
    batch_logger.info(f"{'='*60}")
    
    try:
        for i, repo in enumerate(repos):
            current_index = i + 1
            team_name = repo.get("team_name", f"Repo {current_index}")
            repo_url = repo.get("repo_url", "")
            project_id = repo.get("project_id")
            job_id = repo.get("job_id")
            
            batch_logger.info(f"[{current_index}/{len(repos)}] 📦 Processing: {team_name} | URL: {repo_url}")
            
            # Update batch progress
            try:
                BatchCRUD.update_batch_progress(
                    batch_id=batch_id,
                    current_index=current_index,
                    current_repo_url=repo_url,
                    current_repo_team=team_name
                )
            except Exception as e:
                batch_logger.warning(f"    ⚠️  Failed to update batch progress: {e}")
            
            # Run analysis (blocking - waits for completion)
            try:
                run_analysis_job(
                    project_id=project_id,
                    job_id=job_id,
                    repo_url=repo_url,
                    team_name=team_name
                )
                
                # Mark as completed in batch
                BatchCRUD.increment_completed(batch_id)
                batch_logger.info(f"    ✅ Completed: {team_name}")
                
            except Exception as e:
                # Mark as failed in batch
                BatchCRUD.increment_failed(batch_id)
                batch_logger.error(f"    ❌ Failed: {team_name} - {str(e)}")
            
            # Delay between repos to avoid rate limiting (2 seconds)
            if current_index < len(repos):
                batch_logger.info(f"    ⏳ Waiting 2 seconds before next repo...")
                time.sleep(2)
        
        # Mark batch as completed
        BatchCRUD.complete_batch(batch_id)
        
        batch_logger.info(f"{'='*60}")
        batch_logger.info(f"✅ Batch Complete!")
        batch_logger.info(f"   Total: {len(repos)}")
        batch = BatchCRUD.get_batch(batch_id)
        if batch:
            batch_logger.info(f"   Completed: {batch.get('completed_repos', 0)}")
            batch_logger.info(f"   Failed: {batch.get('failed_repos', 0)}")
        batch_logger.info(f"{'='*60}")
        
    except Exception as e:
        # Mark entire batch as failed
        error_msg = str(e)
        batch_logger.error(f"Batch Processing Failed: {error_msg}")
        batch_logger.error(traceback.format_exc())
        
        try:
            BatchCRUD.fail_batch(batch_id, error_msg)
        except:
            pass

