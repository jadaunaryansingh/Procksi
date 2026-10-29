"""
Commit Quality Service
Extracts and analyzes commit quality metrics from forensics data
"""
import logging
from typing import List, Optional
from ..database import get_supabase_admin_client
from ..utils.report_storage import ReportStorageManager
from ..models.quality_models import (
    ForensicsData, FakeCommit, SuspiciousCommit,
    QualityEvaluation, QualityReport, TeamQualityRanking
)

logger = logging.getLogger(__name__)


class CommitQualityService:
    """Service for analyzing commit quality from forensics data"""
    
    @staticmethod
    def extract_forensics_data(team_id: str) -> Optional[ForensicsData]:
        """
        Extract forensics metrics from teams.report_json
        
        Args:
            team_id: Team UUID
            
        Returns:
            ForensicsData object or None if no forensics data available
            
        Raises:
            ValueError: If team not found or forensics data is invalid
        """
        supabase = get_supabase_admin_client()
        
        try:
            # Fetch team with report_json and report_path
            response = supabase.table("teams").select(
                "id, team_name, report_json, report_path"
            ).eq("id", team_id).single().execute()
            
            if not response.data:
                raise ValueError(f"Team {team_id} not found")
            
            # Get report from storage if migrated
            report_json = ReportStorageManager.get_report_for_team(response.data)
            if not report_json or not isinstance(report_json, dict):
                logger.warning(f"No report_json for team {team_id}")
                return None
            
            forensics = report_json.get("forensics")
            if not forensics or not isinstance(forensics, dict):
                logger.warning(f"No forensics data in report_json for team {team_id}")
                return None
            
            # Extract fake commits
            fake_commits_raw = forensics.get("fake_commits", [])
            fake_commits = [
                FakeCommit(
                    hash=fc.get("hash", ""),
                    author=fc.get("author", "Unknown"),
                    message=fc.get("msg", ""),
                    date=fc.get("date", ""),
                    reasons=fc.get("reasons", []),
                    additions=fc.get("additions", 0),
                    fake_additions=fc.get("fake_additions", 0)
                )
                for fc in fake_commits_raw
            ]
            
            # Extract suspicious commits
            suspicious_raw = forensics.get("suspicious_list", [])
            suspicious_list = [
                SuspiciousCommit(
                    hash=sc.get("hash", ""),
                    author=sc.get("author", "Unknown"),
                    message=sc.get("msg", ""),
                    reasons=sc.get("reasons", [])
                )
                for sc in suspicious_raw
            ]
            
            return ForensicsData(
                fake_commit_count=forensics.get("fake_commit_count", 0),
                fake_commit_ratio=forensics.get("fake_commit_ratio", 0.0),
                commit_health=forensics.get("commit_health", "Unknown"),
                fake_commits=fake_commits,
                dummy_commits=forensics.get("dummy_commits", 0),
                suspicious_list=suspicious_list,
                total_commits=forensics.get("total_commits", 0),
                total_real_additions=forensics.get("total_real_additions", 0),
                total_fake_additions=forensics.get("total_fake_additions", 0),
                real_commit_count=forensics.get("real_commit_count", 0),
                inflation_ratio=forensics.get("inflation_ratio", 1.0),
                suspicious_authors=forensics.get("suspicious_authors", {"has_suspicious": False, "suspicious_authors": []})
            )
            
        except Exception as e:
            logger.error(f"Error extracting forensics for team {team_id}: {e}")
            raise
    
    @staticmethod
    def evaluate_quality_threshold(
        forensics: ForensicsData,
        threshold: float = 30.0
    ) -> QualityEvaluation:
        """
        Evaluate if team exceeds quality thresholds
        
        Args:
            forensics: Extracted forensics data
            threshold: Fake commit ratio threshold (0-100)
            
        Returns:
            QualityEvaluation with alert decision
            
        Raises:
            ValueError: If threshold is out of range
        """
        if not (0 <= threshold <= 100):
            raise ValueError(f"Threshold must be between 0 and 100, got {threshold}")
        
        # Check if threshold is exceeded
        threshold_exceeded = forensics.fake_commit_ratio > threshold
        
        # Check if health is critical
        critical_health = forensics.commit_health == "Critical"
        
        # Alert required if either condition is true
        requires_alert = threshold_exceeded or critical_health
        
        # Determine priority
        if critical_health:
            alert_priority = "High"
        elif forensics.fake_commit_ratio > 50:
            alert_priority = "High"
        elif forensics.fake_commit_ratio > 30:
            alert_priority = "Medium"
        else:
            alert_priority = "Low"
        
        return QualityEvaluation(
            requires_alert=requires_alert,
            threshold_exceeded=threshold_exceeded,
            critical_health=critical_health,
            alert_priority=alert_priority,
            fake_commit_ratio=forensics.fake_commit_ratio,
            commit_health=forensics.commit_health
        )
    
    @staticmethod
    def generate_quality_report(
        team_id: str,
        forensics: ForensicsData,
        threshold: float = 30.0
    ) -> QualityReport:
        """
        Generate comprehensive quality report for a team
        
        Args:
            team_id: Team UUID
            forensics: Extracted forensics data
            threshold: Threshold used for evaluation
            
        Returns:
            QualityReport with all metrics and evaluation
        """
        supabase = get_supabase_admin_client()
        
        # Get team name
        team_response = supabase.table("teams").select("team_name").eq("id", team_id).single().execute()
        team_name = team_response.data.get("team_name", "Unknown") if team_response.data else "Unknown"
        
        evaluation = CommitQualityService.evaluate_quality_threshold(forensics, threshold)
        
        return QualityReport(
            team_id=team_id,
            team_name=team_name,
            forensics=forensics,
            evaluation=evaluation,
            threshold_used=threshold
        )
    
    @staticmethod
    def rank_teams_by_quality(batch_id: str) -> List[TeamQualityRanking]:
        """
        Rank all teams in batch by commit quality
        
        Args:
            batch_id: Batch UUID
            
        Returns:
            List of teams sorted by fake_commit_ratio (descending)
        """
        supabase = get_supabase_admin_client()
        
        try:
            # Get all teams in batch
            response = supabase.table("teams").select(
                "id, team_name, report_json"
            ).eq("batch_id", batch_id).execute()
            
            if not response.data:
                logger.warning(f"No teams found in batch {batch_id}")
                return []
            
            rankings = []
            
            for team in response.data:
                team_id = team["id"]
                team_name = team["team_name"]
                
                # Extract forensics
                forensics = CommitQualityService.extract_forensics_data(team_id)
                
                if forensics:
                    rankings.append({
                        "team_id": team_id,
                        "team_name": team_name,
                        "fake_commit_ratio": forensics.fake_commit_ratio,
                        "commit_health": forensics.commit_health,
                        "fake_commit_count": forensics.fake_commit_count,
                        "total_commits": forensics.total_commits
                    })
            
            # Sort by fake_commit_ratio descending
            rankings.sort(key=lambda x: x["fake_commit_ratio"], reverse=True)
            
            # Add rank numbers
            result = [
                TeamQualityRanking(
                    rank=idx + 1,
                    **ranking
                )
                for idx, ranking in enumerate(rankings)
            ]
            
            return result
            
        except Exception as e:
            logger.error(f"Error ranking teams in batch {batch_id}: {e}")
            raise
