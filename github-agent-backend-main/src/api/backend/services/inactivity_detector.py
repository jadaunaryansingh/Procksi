"""
Inactivity Detection Service
Detects teams that haven't been committing code recently
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class InactivityResult:
    """Result of inactivity detection for a team"""
    team_id: str
    team_name: str
    is_inactive: bool
    days_inactive: int
    last_commit_date: Optional[str]
    severity: str  # "warning" or "critical"
    reason: str
    has_repo_issues: bool  # True if team has repo privacy issues


class InactivityDetector:
    """Detects inactive teams based on commit activity"""
    
    # Configurable thresholds (in days)
    WARNING_THRESHOLD = 7  # 7 days = warning
    CRITICAL_THRESHOLD = 14  # 14 days = critical
    ALERT_COOLDOWN = 3  # Don't send duplicate alerts within 3 days
    
    @staticmethod
    def detect_team_inactivity(
        team: Dict[str, Any],
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD
    ) -> InactivityResult:
        """
        Detect if a single team is inactive.
        Escalates severity based on previous alert count.
        
        Args:
            team: Team data from database (must include last_commit_date, is_private, status, inactivity_alert_count)
            warning_threshold: Days before warning alert (default: 7)
            critical_threshold: Days before critical alert (default: 14)
            
        Returns:
            InactivityResult with detection details
        """
        team_id = team.get("id")
        team_name = team.get("team_name", "Unknown")
        last_commit_date = team.get("last_commit_date")
        is_private = team.get("is_private")
        status = team.get("status", "pending")
        alert_count = team.get("inactivity_alert_count", 0) or 0
        
        # Check if team has repo issues (exclude from inactivity checks)
        has_repo_issues = (
            is_private is not None or  # Has privacy status set (private/not_found/invalid)
            status == "failed"  # Analysis failed
        )
        
        # If team has repo issues, they get separate alerts
        if has_repo_issues:
            return InactivityResult(
                team_id=team_id,
                team_name=team_name,
                is_inactive=False,
                days_inactive=0,
                last_commit_date=None,
                severity="info",
                reason="Team has repository issues (handled by separate alerts)",
                has_repo_issues=True
            )
        
        # If no commit date, team has never been analyzed or has no commits
        if not last_commit_date:
            return InactivityResult(
                team_id=team_id,
                team_name=team_name,
                is_inactive=True,
                days_inactive=999,  # Arbitrary large number
                last_commit_date=None,
                severity="critical",
                reason="No commits found or team never analyzed",
                has_repo_issues=False
            )
        
        # Calculate days since last commit
        if isinstance(last_commit_date, str):
            last_commit_dt = datetime.fromisoformat(last_commit_date.replace('Z', '+00:00'))
        else:
            last_commit_dt = last_commit_date
        
        now = datetime.now(last_commit_dt.tzinfo) if last_commit_dt.tzinfo else datetime.utcnow()
        days_inactive = (now - last_commit_dt).days
        
        # Determine base severity from days inactive
        base_severity = None
        if days_inactive >= critical_threshold:
            base_severity = "critical"
        elif days_inactive >= warning_threshold:
            base_severity = "warning"
        else:
            # Team is active
            return InactivityResult(
                team_id=team_id,
                team_name=team_name,
                is_inactive=False,
                days_inactive=days_inactive,
                last_commit_date=last_commit_date,
                severity="info",
                reason=f"Team is active ({days_inactive} days since last commit)",
                has_repo_issues=False
            )
        
        # ESCALATION LOGIC: Increase severity based on alert count
        # - 0 alerts: Use base severity (warning or critical)
        # - 1+ alerts: Always escalate to critical (team ignored previous warnings)
        final_severity = base_severity
        escalation_reason = ""
        
        if alert_count >= 1 and base_severity == "warning":
            # Team received warning before but still inactive - escalate to critical
            final_severity = "critical"
            escalation_reason = f" (escalated from warning - {alert_count} previous alert{'s' if alert_count > 1 else ''})"
        elif alert_count >= 2:
            # Team received multiple alerts - add urgency note
            escalation_reason = f" (URGENT - {alert_count} previous alerts ignored)"
        elif alert_count == 1:
            escalation_reason = f" ({alert_count} previous alert)"
        
        reason = f"No commits for {days_inactive} days{escalation_reason}"
        
        return InactivityResult(
            team_id=team_id,
            team_name=team_name,
            is_inactive=True,
            days_inactive=days_inactive,
            last_commit_date=last_commit_date,
            severity=final_severity,
            reason=reason,
            has_repo_issues=False
        )
    
    @staticmethod
    def should_send_alert(
        team: Dict[str, Any],
        cooldown_days: int = ALERT_COOLDOWN
    ) -> bool:
        """
        Check if an inactivity alert should be sent to this team.
        Prevents duplicate alerts within cooldown period.
        
        Args:
            team: Team data (must include last_inactivity_alert)
            cooldown_days: Minimum days between alerts (default: 3)
            
        Returns:
            True if alert should be sent, False if in cooldown period
        """
        last_alert = team.get("last_inactivity_alert")
        
        # No previous alert - OK to send
        if not last_alert:
            return True
        
        # Parse last alert timestamp
        if isinstance(last_alert, str):
            last_alert_dt = datetime.fromisoformat(last_alert.replace('Z', '+00:00'))
        else:
            last_alert_dt = last_alert
        
        # Check if cooldown period has passed
        now = datetime.now(last_alert_dt.tzinfo) if last_alert_dt.tzinfo else datetime.utcnow()
        days_since_alert = (now - last_alert_dt).days
        
        return days_since_alert >= cooldown_days
    
    @staticmethod
    def detect_batch_inactivity(
        teams: List[Dict[str, Any]],
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD
    ) -> Dict[str, Any]:
        """
        Detect inactivity for all teams in a batch.
        
        Args:
            teams: List of team data from database
            warning_threshold: Days before warning alert
            critical_threshold: Days before critical alert
            
        Returns:
            Dict with summary and detailed results
        """
        results = []
        warning_count = 0
        critical_count = 0
        excluded_count = 0
        
        for team in teams:
            result = InactivityDetector.detect_team_inactivity(
                team,
                warning_threshold,
                critical_threshold
            )
            
            if result.is_inactive and not result.has_repo_issues:
                results.append(result)
                if result.severity == "critical":
                    critical_count += 1
                elif result.severity == "warning":
                    warning_count += 1
            elif result.has_repo_issues:
                excluded_count += 1
        
        return {
            "total_teams": len(teams),
            "inactive_teams": len(results),
            "warning_count": warning_count,
            "critical_count": critical_count,
            "excluded_count": excluded_count,
            "results": results
        }
