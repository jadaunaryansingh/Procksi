"""
Leaderboard Service for weekly report rankings
"""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from uuid import UUID

from ..database import get_supabase_admin_client
from ..utils.cache import cache, RedisCache

logger = logging.getLogger(__name__)


@dataclass
class LeaderboardEntry:
    """Single entry in the leaderboard"""
    rank: int
    team_id: str
    team_name: str
    overall_score: float
    project_name: Optional[str] = None


@dataclass
class LeaderboardData:
    """Complete leaderboard data for a batch"""
    entries: List[LeaderboardEntry]
    recipient_entry: Optional[LeaderboardEntry]
    batch_name: str
    generated_at: datetime
    total_teams: int


class LeaderboardService:
    """Service for retrieving and processing leaderboard data"""
    
    def __init__(self):
        self.supabase = get_supabase_admin_client()

    def _get_batch_name(self, batch_id: str) -> Optional[str]:
        """Fetch batch name with short cache to avoid repeated metadata reads."""
        cache_key = f"hackeval:leaderboard:batch_name:{batch_id}"
        cached_name = cache.get(cache_key)
        if cached_name:
            return str(cached_name)

        batch_response = self.supabase.table("batches").select("name").eq("id", batch_id).execute()
        if not batch_response.data:
            return None

        batch_name = batch_response.data[0]["name"]
        cache.set(cache_key, batch_name, RedisCache.TTL_MEDIUM)
        return batch_name
    
    async def get_batch_leaderboard(
        self,
        batch_id: str,
        recipient_team_id: str,
        top_n: int = 10,
        timeout_seconds: int = 5
    ) -> Optional[LeaderboardData]:
        """
        Retrieve leaderboard for a batch with recipient's position
        
        Args:
            batch_id: UUID of the batch
            recipient_team_id: UUID of the team receiving the report
            top_n: Number of top teams to include (default 10)
            timeout_seconds: Query timeout (default 5)
        
        Returns:
            LeaderboardData if successful, None if error or insufficient data
        """
        try:
            batch_name = self._get_batch_name(batch_id)
            if not batch_name:
                logger.warning(f"Batch {batch_id} not found")
                return None
            
            # Query teams with scores in this batch
            # Order by total_score DESC, then team_name ASC for tie-breaking
            teams_response = self.supabase.table("teams").select(
                "id, team_name, total_score, metadata"
            ).eq("batch_id", batch_id).not_.is_("total_score", "null").order(
                "total_score", desc=True
            ).order("team_name", desc=False).execute()
            
            if not teams_response.data:
                logger.info(f"No teams with scores found for batch {batch_id}")
                return None
            
            all_teams = teams_response.data
            total_teams = len(all_teams)
            
            # Validate and filter entries
            valid_entries = []
            for idx, team in enumerate(all_teams):
                # Extract project name from metadata or report_json
                project_name = self._extract_project_name(team)
                
                entry_dict = {
                    "team_id": team["id"],
                    "team_name": team["team_name"],
                    "overall_score": team["total_score"],
                    "project_name": project_name
                }
                
                if self.validate_leaderboard_entry(entry_dict):
                    valid_entries.append(LeaderboardEntry(
                        rank=idx + 1,
                        team_id=team["id"],
                        team_name=team["team_name"],
                        overall_score=team["total_score"],
                        project_name=project_name
                    ))
                else:
                    logger.warning(f"Invalid leaderboard entry excluded: {entry_dict}")
            
            # Check minimum threshold (at least 1 team with a score)
            if len(valid_entries) < 1:
                logger.info(f"No valid entries for batch {batch_id}")
                return None
            
            # Get top N entries
            top_entries = valid_entries[:top_n]
            
            # Find recipient's position
            recipient_entry = None
            recipient_in_top_n = False
            
            for entry in valid_entries:
                if entry.team_id == recipient_team_id:
                    if entry.rank <= top_n:
                        recipient_in_top_n = True
                    else:
                        recipient_entry = entry
                    break
            
            return LeaderboardData(
                entries=top_entries,
                recipient_entry=recipient_entry,
                batch_name=batch_name,
                generated_at=datetime.utcnow(),
                total_teams=total_teams
            )
            
        except Exception as e:
            logger.error(f"Error generating leaderboard for batch {batch_id}: {e}")
            return None
    
    async def get_full_batch_leaderboard(
        self,
        batch_id: str,
        limit: Optional[int] = None
    ) -> Optional[LeaderboardData]:
        """
        Retrieve full leaderboard for a batch (for PDF reports)
        
        Args:
            batch_id: UUID of the batch
            limit: Optional limit on number of teams (None = all teams)
        
        Returns:
            LeaderboardData with all teams if successful, None if error
        """
        try:
            batch_name = self._get_batch_name(batch_id)
            if not batch_name:
                logger.warning(f"Batch {batch_id} not found")
                return None
            
            # Query all teams with scores in this batch
            teams_response = self.supabase.table("teams").select(
                "id, team_name, total_score, metadata"
            ).eq("batch_id", batch_id).not_.is_("total_score", "null").order(
                "total_score", desc=True
            ).order("team_name", desc=False).execute()
            
            if not teams_response.data:
                logger.info(f"No teams with scores found for batch {batch_id}")
                return None
            
            all_teams = teams_response.data
            if limit:
                all_teams = all_teams[:limit]
            
            total_teams = len(all_teams)
            
            # Validate and filter entries
            valid_entries = []
            for idx, team in enumerate(all_teams):
                # Extract project name from metadata or report_json
                project_name = self._extract_project_name(team)
                
                entry_dict = {
                    "team_id": team["id"],
                    "team_name": team["team_name"],
                    "overall_score": team["total_score"],
                    "project_name": project_name
                }
                
                if self.validate_leaderboard_entry(entry_dict):
                    valid_entries.append(LeaderboardEntry(
                        rank=idx + 1,
                        team_id=team["id"],
                        team_name=team["team_name"],
                        overall_score=team["total_score"],
                        project_name=project_name
                    ))
                else:
                    logger.warning(f"Invalid leaderboard entry excluded: {entry_dict}")
            
            # Check minimum threshold (at least 1 team with a score)
            if len(valid_entries) < 1:
                logger.info(f"No valid entries for batch {batch_id}")
                return None
            
            return LeaderboardData(
                entries=valid_entries,
                recipient_entry=None,  # No recipient for full leaderboard
                batch_name=batch_name,
                generated_at=datetime.utcnow(),
                total_teams=total_teams
            )
            
        except Exception as e:
            logger.error(f"Error generating full leaderboard for batch {batch_id}: {e}")
            return None
    
    def _extract_project_name(self, team: Dict[str, Any]) -> Optional[str]:
        """
        Extract project name from team metadata.
        
        Args:
            team: Team dictionary with metadata and report_json fields
        
        Returns:
            Project name string or None
        """
        try:
            # Try metadata.ingestion.project_statement first
            metadata = team.get("metadata")
            if metadata and isinstance(metadata, dict):
                ingestion = metadata.get("ingestion", {})
                if isinstance(ingestion, dict):
                    project_statement = ingestion.get("project_statement")
                    if project_statement and isinstance(project_statement, str):
                        return project_statement.strip()
            
            # Fallback to team name
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting project name for team {team.get('id')}: {e}")
            return None
    
    def validate_leaderboard_entry(self, entry: Dict[str, Any]) -> bool:
        """
        Validate a single leaderboard entry
        
        Args:
            entry: Dictionary with team_id, team_name, overall_score
        
        Returns:
            True if valid, False otherwise
        """
        try:
            # Verify team_id is a valid UUID
            team_id = entry.get("team_id")
            if not team_id or not isinstance(team_id, str):
                return False
            
            try:
                UUID(team_id)
            except (ValueError, AttributeError):
                return False
            
            # Verify team_name is non-empty string
            team_name = entry.get("team_name")
            if not team_name or not isinstance(team_name, str) or not team_name.strip():
                return False
            
            # Verify score is between 0 and 100
            score = entry.get("overall_score")
            if score is None:
                return False
            
            try:
                score_float = float(score)
                if score_float < 0 or score_float > 100:
                    return False
            except (ValueError, TypeError):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating leaderboard entry: {e}")
            return False
