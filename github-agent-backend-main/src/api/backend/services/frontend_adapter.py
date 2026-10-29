"""
Frontend Adapter Service
Transforms backend data to match frontend expectations
"""
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
from collections import defaultdict


class FrontendAdapter:
    """Adapts backend responses to frontend format"""
    
    @staticmethod
    def _extract_scores(project_data: Dict[str, Any], report_json: Dict[str, Any] = None) -> Dict[str, float]:
        """Extract and normalize scores from project data"""
        # Use 0 as default - no artificial score inflation
        scores = {
            "totalScore": round(project_data.get("total_score") or 0, 2),
            "qualityScore": round(project_data.get("quality_score") or 0, 2),
            "securityScore": round(project_data.get("security_score") or 0, 2),
            "originalityScore": round(project_data.get("originality_score") or project_data.get("llm_score") or 0, 2),
            "architectureScore": round(project_data.get("engineering_score") or project_data.get("architecture_score") or project_data.get("organization_score") or 0, 2),
            "documentationScore": round(project_data.get("documentation_score") or 0, 2)
        }
        
        # Try to extract from report_json if available
        if report_json and "scores" in report_json:
            report_scores = report_json["scores"]
            score_mapping = {
                "totalScore": "total",
                "qualityScore": "quality", 
                "securityScore": "security",
                "originalityScore": "originality",
                "architectureScore": "engineering",  # Maps to engineering/organization
                "documentationScore": "documentation"
            }
            
            for ui_key, report_key in score_mapping.items():
                if report_key in report_scores and report_scores[report_key]:
                    scores[ui_key] = report_scores[report_key]
        
        # Calculate total if not set
        if scores["totalScore"] == 0:
            component_scores = [
                scores["qualityScore"],
                scores["securityScore"], 
                scores["originalityScore"],
                scores["architectureScore"],
                scores["documentationScore"]
            ]
            valid_scores = [s for s in component_scores if s and s > 0]
            if valid_scores:
                scores["totalScore"] = round(sum(valid_scores) / len(valid_scores), 1)
        
        return scores
    
    @staticmethod
    def _extract_commit_patterns(report_json: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Extract commit patterns from forensics data"""
        patterns = []
        if not report_json or "forensics" not in report_json:
            return patterns
        
        forensics = report_json.get("forensics", {})
        
        # Try to build timeline from daily/weekly activity
        if "daily_activity" in forensics:
            daily = forensics["daily_activity"]
            for date, commits_count in daily.items():
                patterns.append({
                    "date": date,
                    "commits": commits_count if isinstance(commits_count, int) else sum(commits_count.values()),
                    "additions": 0,  # Not tracked in current forensics
                    "deletions": 0
                })
        
        return sorted(patterns, key=lambda x: x["date"])
    
    @staticmethod
    def transform_project_response(project_data: Dict[str, Any], 
                                   tech_stack: List[Dict], 
                                   issues: List[Dict],
                                   team_members: List[Dict],
                                   report_json: Dict[str, Any] = None) -> Dict[str, Any]:
        """Transform to frontend ProjectEvaluation format"""
        
        # Extract scores (flat structure, not nested)
        scores = FrontendAdapter._extract_scores(project_data, report_json)
        
        # Extract languages from report or tech stack
        languages = []
        if report_json and "stack" in report_json:
            # Stack contains language/framework info
            stack = report_json.get("stack", [])
            # Create language breakdown from stack
            lang_mapping = {"Python": 0, "JavaScript": 0, "TypeScript": 0, "Java": 0, "Go": 0, "C++": 0, "Rust": 0}
            for item in stack:
                item_str = str(item).lower() if item else ""
                if "python" in item_str:
                    lang_mapping["Python"] = 70
                elif "javascript" in item_str or "node" in item_str:
                    lang_mapping["JavaScript"] = 70
                elif "typescript" in item_str:
                    lang_mapping["TypeScript"] = 70
                elif "java" in item_str:
                    lang_mapping["Java"] = 70
                elif "go" in item_str:
                    lang_mapping["Go"] = 70
            
            for lang, pct in lang_mapping.items():
                if pct > 0:
                    languages.append({"name": lang, "percentage": pct})
        
        if not languages and report_json and "languages" in report_json:
            lang_data = report_json.get("languages", {})
            for lang, pct in lang_data.items():
                languages.append({"name": lang, "percentage": pct})
        
        # Extract tech stack names (as strings, not objects)
        tech_names = [t.get("technology") for t in tech_stack if t.get("technology")]
        
        # Extract frameworks
        frameworks = [t.get("technology") for t in tech_stack 
                     if t.get("category") in ["framework", "library"]]
        
        # Architecture pattern detection
        architecture = "Monolithic"
        if report_json and "structure" in report_json:
            struct = report_json["structure"]
            if "microservice" in str(struct).lower():
                architecture = "Microservices"
            elif any(word in str(struct).lower() for word in ["api", "client", "server"]):
                architecture = "Client-Server"
        
        # Transform contributors with enhanced data
        contributors = []
        if report_json and "forensics" in report_json:
            forensics = report_json["forensics"]
            author_stats = forensics.get("author_stats", {})
            
            for name, stats in author_stats.items():
                commits = stats.get("commits", 0)
                lines_changed = stats.get("lines_changed", 0)
                
                # Calculate percentage
                total_commits = forensics.get("total_commits", 1)
                percentage = round((commits / total_commits) * 100, 1) if total_commits > 0 else 0
                
                contributors.append({
                    "name": name,
                    "commits": commits,
                    "additions": lines_changed // 2,  # Estimate (actual split not tracked)
                    "deletions": lines_changed // 2,
                    "percentage": percentage
                })
        else:
            # Fallback to team_members table
            for member in team_members:
                contributors.append({
                    "name": member.get("name"),
                    "commits": member.get("commits", 0),
                    "additions": 0,
                    "deletions": 0,
                    "percentage": member.get("contribution_pct", 0)
                })
        
        # Sort by commits descending
        contributors = sorted(contributors, key=lambda x: x["commits"], reverse=True)
        
        # Commit patterns timeline
        commit_patterns = FrontendAdapter._extract_commit_patterns(report_json)
        
        # Analyze for burst commits and last-minute activity
        burst_warning = False
        last_minute_commits = 0
        
        if commit_patterns:
            # Check for burst (>50% commits in last 20% of timeline)
            total_commits_in_patterns = sum(p["commits"] for p in commit_patterns)
            if len(commit_patterns) > 5:
                last_20_percent = int(len(commit_patterns) * 0.2)
                last_period_commits = sum(p["commits"] for p in commit_patterns[-last_20_percent:])
                if last_period_commits > (total_commits_in_patterns * 0.5):
                    burst_warning = True
                    last_minute_commits = last_period_commits
        
        # Transform security issues with enhanced details
        security_issues = []
        secrets_count = 0
        
        for issue in issues:
            if issue.get("type") == "security":
                issue_type = issue.get("description", "")
                if "secret" in issue_type.lower() or "password" in issue_type.lower() or "key" in issue_type.lower():
                    secrets_count += 1
                    issue_label = "Hardcoded Secret"
                elif "injection" in issue_type.lower():
                    issue_label = "Injection Vulnerability"
                elif "xss" in issue_type.lower():
                    issue_label = "XSS Vulnerability"
                else:
                    issue_label = "Security Issue"
                
                security_issues.append({
                    "type": issue_label,
                    "severity": issue.get("severity", "medium"),
                    "file": issue.get("file_path", "Unknown"),
                    "line": issue.get("line_number"),  # May be None
                    "description": issue.get("description", "")
                })
        
        # Calculate AI percentage and extract analysis
        ai_percentage = 0.0
        ai_verdict = None
        strengths = []
        improvements = []
        
        if report_json:
            # AI percentage from LLM detector
            if "llm_detection" in report_json:
                llm_data = report_json["llm_detection"]
                ai_percentage = llm_data.get("overall_percentage", 0.0)
            elif "files" in report_json:
                files = report_json.get("files", [])
                if files:
                    total_ai = sum(f.get("ai_pct", 0) for f in files)
                    ai_percentage = round(total_ai / len(files), 2)
            
            # AI verdict from judge/evaluator
            if "judge" in report_json:
                judge = report_json.get("judge", {})
                positive = judge.get("positive_feedback", "")
                constructive = judge.get("constructive_feedback", "")
                
                if positive or constructive:
                    ai_verdict = f"{positive}\n\n{constructive}".strip()
                
                # Parse strengths (from positive feedback)
                if positive:
                    # Try splitting by period, newline, or bullet points
                    parts = positive.replace("\n-", ".").replace("\n*", ".").replace("\n", ". ").split(".")
                    strengths = [s.strip() for s in parts if s.strip() and len(s.strip()) > 10]
                    strengths = strengths[:5]  # Top 5
                
                # Parse improvements (from constructive feedback)
                if constructive:
                    # Try splitting by period, newline, or bullet points
                    parts = constructive.replace("\n-", ".").replace("\n*", ".").replace("\n", ". ").split(".")
                    improvements = [s.strip() for s in parts if s.strip() and len(s.strip()) > 10]
                    improvements = improvements[:5]  # Top 5
        
        # Calculate project stats
        total_files = 0
        total_loc = 0
        test_coverage = 0
        
        if report_json:
            if "files" in report_json:
                files = report_json.get("files", [])
                total_files = len(files)
                # Estimate LOC from file count (rough estimate)
                total_loc = total_files * 100
            
            if "structure" in report_json:
                structure = report_json["structure"]
                # Use folder_count as proxy for total files if files not available
                if total_files == 0:
                    total_files = structure.get("folder_count", 0) * 5  # Estimate 5 files per folder
                
                # Look for test coverage data
                if "test_coverage" in structure:
                    test_coverage = structure["test_coverage"]
                elif "tests" in structure:
                    # Estimate from test count
                    test_count = structure.get("tests", 0)
                    if total_files > 0:
                        test_coverage = min(100, (test_count / total_files) * 100)
            
            # Get maturity info for test coverage
            if "maturity" in report_json and test_coverage == 0:
                maturity = report_json["maturity"]
                if maturity.get("has_tests"):
                    test_files = maturity.get("test_files", 0)
                    test_coverage = min(100, test_files * 10)  # Rough estimate
        
        # Architecture from structure analysis
        if report_json and "structure" in report_json:
            arch = report_json["structure"].get("architecture", "")
            if arch:
                architecture = arch
        
        # Return flat structure matching frontend expectations
        return {
            # Identity
            "id": str(project_data.get("id")),
            "teamName": project_data.get("team_name"),
            "repoUrl": project_data.get("repo_url"),
            "submittedAt": project_data.get("created_at"),
            "status": project_data.get("status", "completed"),
            
            # Tech Stack (strings, not objects)
            "techStack": tech_names,
            "languages": languages,
            "architecturePattern": architecture,
            "frameworks": frameworks,
            
            # Scores (FLAT - not nested under 'latestScore')
            "totalScore": scores["totalScore"],
            "qualityScore": scores["qualityScore"],
            "securityScore": scores["securityScore"],
            "originalityScore": scores["originalityScore"],
            "architectureScore": scores["architectureScore"],
            "documentationScore": scores["documentationScore"],
            
            # Commit Forensics
            "totalCommits": project_data.get("total_commits", 0),
            "contributors": contributors,
            "commitPatterns": commit_patterns,
            "burstCommitWarning": burst_warning,
            "lastMinuteCommits": last_minute_commits,
            
            # Security
            "securityIssues": security_issues,
            "secretsDetected": secrets_count,
            
            # AI Analysis
            "aiGeneratedPercentage": ai_percentage,
            "aiVerdict": ai_verdict,
            "strengths": strengths,
            "improvements": improvements,
            
            # Project Stats
            "totalFiles": total_files,
            "totalLinesOfCode": total_loc,
            "testCoverage": test_coverage
        }
    
    @staticmethod
    def transform_project_list_item(project: Dict[str, Any], tech_stack: List[Dict] = None, issues_count: int = 0) -> Dict[str, Any]:
        """Transform for project list/dashboard - with all 6 scores"""
        tech_names = []
        if tech_stack:
            tech_names = [t.get("technology") for t in tech_stack if t.get("technology")][:5]  # Top 5
        
        # Extract scores
        scores = FrontendAdapter._extract_scores(project)
        
        return {
            "id": str(project.get("id")),
            "teamName": project.get("team_name"),
            "repoUrl": project.get("repo_url"),
            "status": project.get("status"),
            "totalScore": scores["totalScore"],
            "qualityScore": scores["qualityScore"],
            "securityScore": scores["securityScore"],
            "originalityScore": scores["originalityScore"],
            "architectureScore": scores["architectureScore"],
            "documentationScore": scores["documentationScore"],
            "techStack": tech_names,
            "securityIssues": issues_count,
            "submittedAt": project.get("created_at")
        }
    
    @staticmethod
    def transform_leaderboard_item(project: Dict[str, Any], tech_stack: List[Dict] = None) -> Dict[str, Any]:
        """Transform for leaderboard with all scores, including project_name from metadata if available"""
        tech_names = []
        if tech_stack:
            tech_names = [t.get("technology") for t in tech_stack if t.get("technology")][:5]

        # Extract scores
        scores = FrontendAdapter._extract_scores(project)

        # Extract project_name from metadata.ingestion.project_statement if available
        project_name = None
        metadata = project.get("metadata")
        if metadata and isinstance(metadata, dict):
            ingestion = metadata.get("ingestion")
            if ingestion and isinstance(ingestion, dict):
                project_name = ingestion.get("project_statement")

        # Return snake_case field names to match frontend LeaderboardItem interface
        return {
            "id": str(project.get("id")),
            "team_id": str(project.get("team_id")) if project.get("team_id") else None,
            "team_name": project.get("team_name"),
            "repo_url": project.get("repo_url"),
            "tech_stack": tech_names,
            "total_score": scores["totalScore"],
            "quality_score": scores["qualityScore"],
            "security_score": scores["securityScore"],
            "originality_score": scores["originalityScore"],
            "architecture_score": scores["architectureScore"],
            "documentation_score": scores["documentationScore"],
            "verdict": project.get("verdict"),
            "project_name": project_name
        }
