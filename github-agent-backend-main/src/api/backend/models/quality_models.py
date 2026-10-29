"""
Data models for commit quality analysis and alerts
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class FakeCommit:
    """Represents a single fake/low-quality commit"""
    hash: str
    author: str
    message: str
    date: str
    reasons: List[str]
    additions: int
    fake_additions: int


@dataclass
class SuspiciousCommit:
    """Represents a suspicious commit pattern"""
    hash: str
    author: str
    message: str
    reasons: List[str]


@dataclass
class ForensicsData:
    """Complete forensics analysis data for a repository"""
    fake_commit_count: int
    fake_commit_ratio: float  # Percentage (0-100)
    commit_health: str  # "Healthy", "At Risk", "Critical"
    fake_commits: List[FakeCommit]
    dummy_commits: int
    suspicious_list: List[SuspiciousCommit]
    total_commits: int
    total_real_additions: int
    total_fake_additions: int
    real_commit_count: int = 0
    inflation_ratio: float = 1.0
    suspicious_authors: dict = field(default_factory=lambda: {"has_suspicious": False, "suspicious_authors": []})


@dataclass
class QualityEvaluation:
    """Evaluation result for commit quality threshold check"""
    requires_alert: bool
    threshold_exceeded: bool
    critical_health: bool
    alert_priority: str  # "High", "Medium", "Low"
    fake_commit_ratio: float
    commit_health: str


@dataclass
class QualityReport:
    """Comprehensive quality report for a team"""
    team_id: str
    team_name: str
    forensics: ForensicsData
    evaluation: QualityEvaluation
    threshold_used: float
    generated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TeamQualityRanking:
    """Team ranking by commit quality"""
    rank: int
    team_id: str
    team_name: str
    fake_commit_ratio: float
    commit_health: str
    fake_commit_count: int
    total_commits: int


@dataclass
class AlertResult:
    """Result of sending a quality alert"""
    team_id: str
    team_name: str
    status: str  # "sent", "skipped", "failed"
    reason: Optional[str] = None
    fake_commit_ratio: Optional[float] = None
    email_count: int = 0


@dataclass
class AlertSummary:
    """Summary of batch alert sending operation"""
    requested: int
    sent: int
    skipped: int
    failed: int
    results: List[AlertResult]
