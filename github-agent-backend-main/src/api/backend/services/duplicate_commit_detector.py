"""
Duplicate Commit Detection Service
Detects commits that appear in multiple team repositories
"""
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DuplicateCommitDetector:
    """Detect duplicate commits across teams"""
    
    @staticmethod
    def extract_commits_from_report(report_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract commit information from analysis report
        
        Returns list of commits with: hash, message, author, date, files_changed
        """
        commits = []
        
        if not report_json or not isinstance(report_json, dict):
            return commits
        
        try:
            # Try to get commits from forensics
            forensics = report_json.get("forensics", {})
            commit_details = report_json.get("commit_details", {})
            
            # Ensure they are dicts
            if not isinstance(forensics, dict):
                forensics = {}
            if not isinstance(commit_details, dict):
                commit_details = {}
            
            # Get recent commits
            recent_commits = commit_details.get("recent_commits", [])
            if recent_commits and isinstance(recent_commits, list):
                for commit in recent_commits:
                    if not isinstance(commit, dict):
                        continue
                    commits.append({
                        "hash": commit.get("hash", ""),
                        "message": commit.get("message", ""),
                        "author": commit.get("author", ""),
                        "date": commit.get("date", ""),
                        "files_changed": commit.get("files_changed", [])
                    })
            
            # Also check forensics for commit data
            forensics_commits = forensics.get("commits", [])
            if forensics_commits and isinstance(forensics_commits, list):
                for commit in forensics_commits:
                    if not isinstance(commit, dict):
                        continue
                    commits.append({
                        "hash": commit.get("hash", commit.get("sha", "")),
                        "message": commit.get("message", ""),
                        "author": commit.get("author", commit.get("author_name", "")),
                        "date": commit.get("date", commit.get("timestamp", "")),
                        "files_changed": commit.get("files", [])
                    })
        except Exception as e:
            logger.error(f"Error extracting commits from report: {e}")
            return []
        
        return commits
    
    @staticmethod
    def find_duplicate_commits(
        teams_data: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Find commits that appear in multiple teams
        
        Args:
            teams_data: List of dicts with keys: team_id, team_name, report_json
        
        Returns:
            Dict mapping commit_hash to list of teams that have it
        """
        commit_to_teams = defaultdict(list)
        
        for team in teams_data:
            team_id = team.get("id")
            team_name = team.get("team_name")
            report_json = team.get("report_json")
            
            # Skip teams without analysis results
            if not report_json:
                logger.debug(f"Team {team_name} has no report_json, skipping")
                continue
            
            # Parse JSON string if needed
            if isinstance(report_json, str):
                import json
                try:
                    report_json = json.loads(report_json)
                except Exception as e:
                    logger.warning(f"Failed to parse report_json for team {team_name}: {e}")
                    continue
            
            # Ensure report_json is a dict
            if not isinstance(report_json, dict):
                logger.warning(f"Invalid report_json type for team {team_name}: {type(report_json)}")
                continue
            
            try:
                commits = DuplicateCommitDetector.extract_commits_from_report(report_json)
                
                for commit in commits:
                    commit_hash = commit.get("hash", "")
                    if commit_hash and len(commit_hash) >= 7:  # Valid commit hash
                        commit_to_teams[commit_hash].append({
                            "team_id": team_id,
                            "team_name": team_name,
                            "commit": commit
                        })
            except Exception as e:
                logger.error(f"Error extracting commits for team {team_name}: {e}")
                continue
        
        # Filter to only duplicates (appears in 2+ teams)
        duplicates = {
            commit_hash: teams
            for commit_hash, teams in commit_to_teams.items()
            if len(teams) > 1
        }
        
        return duplicates
    
    @staticmethod
    def analyze_duplicate_severity(
        duplicate_commits: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze duplicate commits and categorize by severity
        
        Returns list of duplicate incidents with severity levels
        """
        incidents = []
        
        for commit_hash, teams in duplicate_commits.items():
            if len(teams) < 2:
                continue
            
            # Get commit details from first occurrence
            first_commit = teams[0]["commit"]
            
            # Determine severity based on number of teams
            team_count = len(teams)
            if team_count >= 5:
                severity = "critical"
            elif team_count >= 3:
                severity = "high"
            else:
                severity = "medium"
            
            incidents.append({
                "commit_hash": commit_hash,
                "commit_message": first_commit.get("message", ""),
                "commit_author": first_commit.get("author", ""),
                "commit_date": first_commit.get("date", ""),
                "files_changed": first_commit.get("files_changed", []),
                "team_count": team_count,
                "teams": [
                    {
                        "team_id": t["team_id"],
                        "team_name": t["team_name"]
                    }
                    for t in teams
                ],
                "severity": severity
            })
        
        # Sort by severity and team count
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        incidents.sort(key=lambda x: (severity_order[x["severity"]], -x["team_count"]))
        
        return incidents
    
    @staticmethod
    def generate_alert_summary(incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary of duplicate commit incidents"""
        if not incidents:
            return {
                "total_incidents": 0,
                "total_commits": 0,
                "total_teams_affected": 0,
                "by_severity": {},
                "incidents": []
            }
        
        teams_affected = set()
        for incident in incidents:
            for team in incident["teams"]:
                teams_affected.add(team["team_id"])
        
        by_severity = defaultdict(int)
        for incident in incidents:
            by_severity[incident["severity"]] += 1
        
        return {
            "total_incidents": len(incidents),
            "total_commits": len(incidents),
            "total_teams_affected": len(teams_affected),
            "by_severity": dict(by_severity),
            "incidents": incidents
        }
