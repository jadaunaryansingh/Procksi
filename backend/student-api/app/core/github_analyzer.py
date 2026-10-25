import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

# Sentinel returned when a team already exists in the remote batch
DUPLICATE_TEAM_SENTINEL = "__DUPLICATE_TEAM__"

class GitHubAnalyzerClient:
    @staticmethod
    async def trigger_analysis(repo_url: str, team_name: str, force: bool = False) -> str:
        """
        Triggers repository analysis on the remote Repository Analysis API.
        Returns the job_id (UUID) representing the analysis run, or
        DUPLICATE_TEAM_SENTINEL if the team already exists in the remote batch.
        Pass force=True to bypass the 7-day cache and force a fresh analysis.
        """
        import re
        
        # Clean repo_url: strip whitespace
        repo_url = repo_url.strip()
            
        # Normalize team_name but preserve suffixes
        team_name = team_name.strip()
        match = re.match(r"^[tT]eam\s*[-_]?\s*(\d+)(.*)$", team_name, re.IGNORECASE)
        if not match:
            match = re.match(r"^[tT](\d+)(.*)$", team_name)
            
        if match:
            num = match.group(1)
            suffix = match.group(2).strip()
            team_name = f"Team {num}"
            if suffix:
                team_name = f"Team {num} {suffix}"

        url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/analyze-repo"
        payload = {
            "repo_url": repo_url,
            "team_name": team_name,
            "force": force
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=20.0)
                if response.status_code in (200, 202):
                    data = response.json()
                    # Expecting response payload similar to {"job_id": "...", "status": "queued"}
                    return data.get("job_id")
                elif response.status_code == 409:
                    logger.info(f"Team '{team_name}' was already analyzed or is in progress (409 Conflict). Resolving job ID...")
                    job_id = await GitHubAnalyzerClient.get_team_job_id(team_name)
                    if job_id:
                        return job_id
                    return DUPLICATE_TEAM_SENTINEL
                elif response.status_code == 500:
                    body_text = response.text
                    # Detect duplicate key constraint violation — team already queued in this batch
                    if "duplicate key" in body_text or "unique_team_in_batch" in body_text or "unique constraint" in body_text:
                        logger.warning(f"Team '{team_name}' already exists in remote batch. Will look up existing job.")
                        return DUPLICATE_TEAM_SENTINEL
                    logger.error(f"Failed to trigger analysis. Status: {response.status_code}, Body: {body_text}")
                    return None
                else:
                    logger.error(f"Failed to trigger analysis. Status: {response.status_code}, Body: {response.text}")
                    return None
            except Exception as e:
                logger.error(f"Exception when calling remote analyze-repo: {str(e)}")
                return None

    @staticmethod
    async def get_team_job_id(team_name: str) -> str:
        """
        Looks up the most recent analysis job for a team by name from the remote API.
        Returns job_id string or None.
        """
        import re
        team_name = team_name.strip()
        match = re.match(r"^[tT]eam\s*[-_]?\s*(\d+)(.*)$", team_name, re.IGNORECASE)
        if not match:
            match = re.match(r"^[tT](\d+)(.*)$", team_name)
            
        if match:
            num = match.group(1)
            suffix = match.group(2).strip()
            team_name = f"Team {num}"
            if suffix:
                team_name = f"Team {num} {suffix}"
        
        url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/leaderboard"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params={"page_size": 500}, timeout=15.0)
                if response.status_code == 200:
                    data = response.json()
                    entries = data.get("leaderboard", [])
                    for entry in entries:
                        t_name = entry.get("teamName") or entry.get("team_name") or entry.get("name") or ""
                        if t_name.strip().lower() == team_name.strip().lower():
                            job_id = entry.get("id") or entry.get("uuid")
                            if job_id:
                                logger.info(f"Found existing remote job_id '{job_id}' for team '{team_name}' in leaderboard")
                                return job_id
                logger.warning(f"Could not find existing remote job for team '{team_name}' in leaderboard (status {response.status_code})")
                return None
            except Exception as e:
                logger.error(f"Exception when looking up team job: {str(e)}")
                return None

    @staticmethod
    async def check_status(job_id: str) -> dict:
        """
        Queries the remote API for the status of the analysis job.
        """
        url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/analysis/job/{job_id}/status"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=10.0)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to fetch job status. Status: {response.status_code}, Body: {response.text}")
                    return None
            except Exception as e:
                logger.error(f"Exception when checking job status: {str(e)}")
                return None

    @staticmethod
    async def get_results(job_id: str) -> dict:
        """
        Queries the remote API for the completed analysis results.
        """
        url = f"{settings.REPOSITORY_ANALYSIS_API_URL}/api/analysis-result/{job_id}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=15.0)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 425:
                    logger.warning(f"Analysis results not ready yet (425 Too Early) for job_id {job_id}")
                    return None
                else:
                    logger.error(f"Failed to fetch results. Status: {response.status_code}, Body: {response.text}")
                    return None
            except Exception as e:
                logger.error(f"Exception when getting analysis results: {str(e)}")
                return None
