"""
Data Mapper Service
Maps agent.py output to Supabase database format
"""
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime
from backend.crud import TeamCRUD, TechStackCRUD, IssueCRUD, TeamMemberCRUD
from backend.utils.cache import cache
from backend.utils.logger import batch_logger
from backend.utils.report_storage import ReportStorageManager


class DataMapper:
    """Map analysis results to database format"""

    @staticmethod
    def _stabilize_implementation_with_history(
        team_id: UUID,
        scores: Dict[str, float],
        report: Dict[str, Any],
    ) -> Dict[str, float]:
        """Dampen large implementation score jumps against last saved team score.

        This keeps score movement realistic across consecutive analyses while still
        allowing genuine trends to appear over time.
        """
        try:
            previous_team = TeamCRUD.get_team(team_id)
            if not previous_team:
                return scores

            previous_raw = previous_team.get("implementation_score")
            current_raw = scores.get("implementation_score")
            previous = float(previous_raw) if previous_raw is not None else None
            current = float(current_raw) if current_raw is not None else None

            if previous is None or current is None:
                return scores

            delta = abs(current - previous)
            # Stabilize only significant one-run jumps.
            if delta > 25.0:
                stabilized = round((previous * 0.7) + (current * 0.3), 1)
                scores["implementation_score"] = DataMapper._clamp_score(stabilized)
                scores["total_score"] = DataMapper.calculate_total_score(scores)

                report["score_stability"] = {
                    "applied": True,
                    "dimension": "implementation",
                    "previous": round(previous, 1),
                    "raw_current": round(current, 1),
                    "stabilized_current": scores["implementation_score"],
                    "reason": "large_run_to_run_delta",
                }
            else:
                report["score_stability"] = {
                    "applied": False,
                    "dimension": "implementation",
                    "previous": round(previous, 1),
                    "raw_current": round(current, 1),
                    "reason": "delta_within_threshold",
                }

            return scores
        except Exception as stability_error:
            print(f"[DATA_MAPPER] Stability guard skipped: {stability_error}")
            return scores

    @staticmethod
    def _clamp_score(value: Any) -> float:
        """Clamp score values to database-safe range [0, 100]."""
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return round(max(0.0, min(100.0, numeric)), 1)
    
    @staticmethod
    def calculate_total_score(scores: Dict[str, float]) -> float:
        """Calculate weighted total score"""
        weights = {
            "originality": 0.20,
            "quality": 0.15,
            "security": 0.10,
            "effort": 0.10,
            "implementation": 0.25,
            "engineering": 0.10,
            "organization": 0.05,
            "documentation": 0.05
        }
        
        total = 0.0
        for key, weight in weights.items():
            score = scores.get(f"{key}_score", 0) or 0
            total += score * weight
        
        return round(total, 2)
    
    @staticmethod
    def map_scores(report: Dict[str, Any]) -> Dict[str, float]:
        """Extract and map scores from report"""
        scores = report.get("scores", {})
        
        mapped_scores = {
            "originality_score": DataMapper._clamp_score(scores.get("originality", 0)),
            "quality_score": DataMapper._clamp_score(scores.get("quality", 0)),
            "security_score": DataMapper._clamp_score(scores.get("security", 0)),
            "effort_score": DataMapper._clamp_score(scores.get("effort", 0)),
            "implementation_score": DataMapper._clamp_score(scores.get("implementation", 0)),
            "engineering_score": DataMapper._clamp_score(scores.get("engineering", 0)),
            "organization_score": DataMapper._clamp_score(scores.get("organization", 0)),
            "documentation_score": DataMapper._clamp_score(scores.get("documentation", 0))
        }
        
        # Calculate total score
        mapped_scores["total_score"] = DataMapper.calculate_total_score(mapped_scores)
        
        return mapped_scores
    
    @staticmethod
    def map_tech_stack(report: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract tech stack from report"""
        stack = report.get("stack", [])
        
        if isinstance(stack, str):
            # If stack is a comma-separated string
            stack = [s.strip() for s in stack.split(",")]
        
        technologies = []
        for tech in stack:
            if not tech:
                continue
            
            # Try to categorize
            tech_lower = tech.lower()
            category = None
            
            if any(lang in tech_lower for lang in ["python", "javascript", "java", "typescript", "go", "rust", "cpp", "c++"]):
                category = "language"
            elif any(fw in tech_lower for fw in ["react", "vue", "angular", "django", "flask", "fastapi", "express", "next"]):
                category = "framework"
            elif any(db in tech_lower for db in ["postgres", "mysql", "mongo", "redis", "sqlite", "supabase"]):
                category = "database"
            else:
                category = "tool"
            
            technologies.append({
                "technology": tech,
                "category": category
            })
        
        return technologies
    
    @staticmethod
    def map_issues(report: Dict[str, Any], project_id: UUID) -> List[Dict[str, Any]]:
        """Extract issues from report"""
        issues = []
        
        # Security issues
        security = report.get("security", {})
        if security.get("leaked_keys"):
            for leak in security.get("leaked_keys", []):
                issues.append({
                    "type": "security",
                    "severity": "high",
                    "file_path": leak.get("file"),
                    "description": f"Secret detected: {leak.get('type', 'Unknown')}",
                    "ai_probability": None,
                    "plagiarism_score": None
                })
        
        # AI-generated code issues
        files = report.get("files", [])
        for file_info in files:
            ai_pct = file_info.get("ai_pct", 0)
            plag_pct = file_info.get("plag_pct", 0)
            
            if ai_pct > 50:  # More than 50% AI-generated
                issues.append({
                    "type": "plagiarism",
                    "severity": "high" if ai_pct > 80 else "medium",
                    "file_path": file_info.get("name"),
                    "description": f"High AI-generated probability detected",
                    "ai_probability": ai_pct / 100,
                    "plagiarism_score": None
                })
            
            if plag_pct > 50:  # More than 50% plagiarized
                match = file_info.get("match", "")
                issues.append({
                    "type": "plagiarism",
                    "severity": "high" if plag_pct > 80 else "medium",
                    "file_path": file_info.get("name"),
                    "description": f"High similarity with: {match}",
                    "ai_probability": None,
                    "plagiarism_score": plag_pct / 100
                })
        
        # Quality issues (low maintainability)
        quality = report.get("quality_metrics", {})
        mi = quality.get("maintainability_index", 100)
        if mi < 50:
            issues.append({
                "type": "quality",
                "severity": "medium" if mi > 20 else "high",
                "file_path": None,
                "description": f"Low maintainability index: {mi:.1f}",
                "ai_probability": None,
                "plagiarism_score": None
            })
        
        return issues
    
    @staticmethod
    def map_team_members(report: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract team members from report"""
        team = report.get("team", {})
        members = []
        
        if isinstance(team, dict):
            # Team is author_stats dict
            for author, stats in team.items():
                commits = stats if isinstance(stats, int) else stats.get("commits", 0)
                members.append({
                    "name": author,
                    "commits": commits,
                    "contribution_pct": None  # Will be calculated if needed
                })
        
        # Calculate contribution percentages
        total_commits = sum(m["commits"] for m in members)
        if total_commits > 0:
            for member in members:
                member["contribution_pct"] = round((member["commits"] / total_commits) * 100, 2)
        
        return members
    
    @staticmethod
    def save_analysis_results(project_id: UUID, report: Dict[str, Any]) -> bool:
        """
        Save complete analysis results to database
        
        Note: project_id parameter name kept for backward compatibility with Celery tasks,
        but it now operates on the teams table (project_id == team_id after migration)
        """
        import traceback
        
        try:
            # 1. Update team with scores (project_id is now team_id)
            scores = DataMapper.map_scores(report)
            scores = DataMapper._stabilize_implementation_with_history(project_id, scores, report)
            
            judge = report.get("judge", {}) or {}
            verdict = judge.get("verdict", "Unknown")
            ai_pros = judge.get("positive_feedback", "")
            ai_cons = judge.get("constructive_feedback", "")
            
            # Extract token usage from judge (if available)
            # Try both locations: judge.token_usage (new) and report.token_usage (fallback)
            token_usage = judge.get("token_usage", {}) or report.get("token_usage", {})

            # Retrieve existing metadata to avoid losing ingestion information
            existing_team = TeamCRUD.get_team(project_id) or {}
            existing_metadata = existing_team.get("metadata") or {}
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}

            # Extract project profile and context from the judge's report
            project_profile = judge.get("project_profile") or report.get("project_profile") or {}
            project_context = judge.get("project_context") or report.get("project_context") or {}

            # Keep manual archetype override if it exists in the database already
            db_project_profile = existing_metadata.get("project_profile") or {}
            if isinstance(db_project_profile, dict):
                db_manual = db_project_profile.get("manual_archetype")
                if db_manual and "manual_archetype" not in project_profile:
                    project_profile["manual_archetype"] = db_manual

            # Merge project profile and context into existing metadata
            updated_metadata = {**existing_metadata}
            updated_metadata["project_profile"] = {
                **(updated_metadata.get("project_profile") or {}),
                **project_profile
            }
            updated_metadata["project_context"] = {
                **(updated_metadata.get("project_context") or {}),
                **project_context
            }
            
            # Map to actual database column names (teams table schema)
            # Note: ai_pros and ai_cons are array columns in the database
            team_data = {
                **scores,
                "total_commits": report.get("total_commits", 0),
                "verdict": str(verdict)[:255] if verdict else None,
                # Convert strings to arrays for array columns
                "ai_pros": [str(ai_pros)[:5000]] if ai_pros else [],
                "ai_cons": [str(ai_cons)[:5000]] if ai_cons else [],
                "status": "completed",
                "last_analyzed_at": datetime.now().isoformat(),  # Track when analysis completed
                # Token usage tracking
                "openai_prompt_tokens": token_usage.get("prompt_tokens", 0),
                "openai_completion_tokens": token_usage.get("completion_tokens", 0),
                "openai_total_tokens": token_usage.get("total_tokens", 0),
                "openai_cost_usd": token_usage.get("total_cost_usd", 0.0),
                "metadata": updated_metadata
            }
            
            # [DEBUG] Log token usage mapping
            print(f"[DATA_MAPPER] Mapping token usage for DB:")
            print(f"  - prompt: {team_data['openai_prompt_tokens']}")
            print(f"  - completion: {team_data['openai_completion_tokens']}")
            print(f"  - total: {team_data['openai_total_tokens']}")
            print(f"  - cost_usd: {team_data['openai_cost_usd']}")
            print(f"  - token_usage dict keys: {list(token_usage.keys())}")
            
            # Try to add report_json (may fail if too large or invalid)
            try:
                # Get full commit details with all commits
                commit_details = report.get("commit_details", {})
                
                # [DEBUG] Log commit_details for branch tracking diagnosis
                print(f"[DATA_MAPPER] commit_details keys: {list(commit_details.keys()) if isinstance(commit_details, dict) else 'NOT A DICT'}")
                if "branch_details" in commit_details:
                    print(f"[DATA_MAPPER] ✓ branch_details found with {len(commit_details.get('branch_details', {}))} branches")
                else:
                    print(f"[DATA_MAPPER] ✗ branch_details NOT FOUND in commit_details")
                
                report_json = {
                    "scores": report.get("scores", {}),
                    "stack": report.get("stack", []),
                    "languages": report.get("languages", {}),
                    "files": report.get("files", [])[:30],  # Limit to avoid size issues
                    "judge": judge,
                    "project_profile": project_profile,
                    "project_context": project_context,
                    "token_usage": token_usage,
                    "api_call_tracking": report.get("api_call_tracking", {}),
                    "team": report.get("team", {}),
                    "security": report.get("security", {}),  # Fixed: extracted correctly from report generated by `agent.py`
                    "maturity": report.get("maturity", {}),
                    "structure": report.get("structure", {}),
                    "repo_tree": report.get("repo_tree", ""),  # Add repository tree structure
                    "total_commits": report.get("total_commits", 0),
                    "commit_details": commit_details,  # Include full commit details with all_commits
                    "project_statement": report.get("project_statement"),  # Project context for reports
                    "forensics": {
                        "author_stats": report.get("team", {}),
                        "total_commits": report.get("total_commits", 0)
                    }
                }
                
                # NEW: Add branchTracking transformation for frontend (built from commit_details)
                branch_details = commit_details.get("branch_details", {})
                if branch_details:
                    main_branch = commit_details.get("main_branch", "main")
                    branches_list = commit_details.get("branches", [])
                    
                    # Build branchDetails array
                    branch_details_array = [
                        {
                            "name": branch_info.get("name"),
                            "totalCommits": branch_info.get("totalCommits", 0),
                            "primaryAuthor": branch_info.get("primaryAuthor", "Unknown"),
                            "authors": branch_info.get("authors", {}),
                            "lastCommitDate": branch_info.get("lastCommitDate"),
                            "firstCommitDate": branch_info.get("firstCommitDate"),
                            "isActive": branch_info.get("isActive", False),
                            "daysSinceLastCommit": branch_info.get("daysSinceLastCommit"),
                            "mergeStatus": branch_info.get("mergeStatus", "Unknown"),
                            "isMerged": branch_info.get("isMerged", False),
                            "isMainBranch": branch_info.get("isMainBranch", False)
                        }
                        for branch_name, branch_info in branch_details.items()
                    ]
                    
                    # Build teamBranchActivity
                    all_authors = set()
                    for branch_info in branch_details.values():
                        all_authors.update(branch_info.get("authors", {}).keys())
                    
                    team_branch_activity = {
                        "byMember": [
                            {
                                "memberName": author_name,
                                "branches": [
                                    {
                                        "branchName": branch_name,
                                        "commits": branch_info["authors"][author_name]
                                    }
                                    for branch_name, branch_info in branch_details.items()
                                    if author_name in branch_info.get("authors", {})
                                ]
                            }
                            for author_name in sorted(all_authors)
                        ],
                        "summary": {
                            "activeBranches": len([b for b in branch_details.values() if b.get("isActive", False)]),
                            "mergedBranches": len([b for b in branch_details.values() if b.get("isMerged", False)]),
                            "unmergedBranches": len([b for b in branch_details.values() if b.get("mergeStatus") == "Unmerged"]),
                            "staleBranches": len([b for b in branch_details.values() if not b.get("isActive", False) and not b.get("isMainBranch", False)])
                        }
                    }
                    
                    # Add branchTracking to report_json
                    report_json["branchTracking"] = {
                        "totalBranches": len(branches_list),
                        "mainBranch": main_branch,
                        "branches": branches_list,
                        "branchDetails": branch_details_array,
                        "teamBranchActivity": team_branch_activity,
                        "insights": {
                            "branchingStrategy": {
                                "assessment": "Good" if len(branches_list) >= 2 and any(b.get("isMerged") for b in branch_details.values()) else "Basic" if len(branches_list) >= 2 else "Poor",
                                "description": f"Team has {len(branches_list)} branches."
                            }
                        }
                    }
                    batch_logger.info(f"[DATA_MAPPER] Added branchTracking with {len(branch_details_array)} branches to report_json")

                
                # Sanitize null bytes (\u0000) which PostgreSQL jsonb cannot store
                def _sanitize_for_postgres(obj):
                    """Recursively strip \\u0000 null bytes from all strings."""
                    if isinstance(obj, str):
                        return obj.replace("\x00", "")
                    elif isinstance(obj, dict):
                        return {k: _sanitize_for_postgres(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [_sanitize_for_postgres(item) for item in obj]
                    return obj
                
                report_json = _sanitize_for_postgres(report_json)
                
                # 🚀 CRITICAL FIX: Save to STORAGE instead of database
                batch_logger.info(f"Saving report to Supabase Storage (not database)...")
                storage_result = ReportStorageManager.save_report_to_storage(
                    team_id=project_id,
                    report_json=report_json
                )
                
                # ✅ Add storage path to team_data (NOT full JSON)
                team_data["report_path"] = storage_result["report_path"]
                # Note: report_summary is not stored in DB - it's returned for potential use
                # but we fetch full data from storage when needed
                
                # Extract key metrics to columns for fast queries
                team_data["ai_percentage"] = report_json.get("judge", {}).get("aiGeneratedPercentage", 0)
                security_issues = report_json.get("security", {}).get("issues", [])
                team_data["security_issues_count"] = len(security_issues)
                team_data["high_severity_issues"] = sum(1 for i in security_issues if i.get("severity") == "high")
                team_data["medium_severity_issues"] = sum(1 for i in security_issues if i.get("severity") == "medium")
                team_data["frameworks"] = report_json.get("stack", [])[:10]  # Top 10 frameworks
                
                if commit_details:
                    team_data["last_commit_date"] = commit_details.get("last_commit_date")
                    team_data["branch_count"] = len(commit_details.get("branches", []))
                
                batch_logger.info(f"✅ Report saved to storage: {storage_result['report_path']} ({storage_result['report_size']} bytes)")
                
            except Exception as json_err:
                batch_logger.warning(f"Could not save report to storage: {json_err}")
                # Fallback: Save minimal data without report
            
            # Save team data (WITHOUT 300KB report_json)
            batch_logger.info(f"Saving team data for {project_id}...")
            try:
                TeamCRUD.update_team(project_id, team_data)
                batch_logger.info(f"Team data saved successfully (storage-backed)")
            except Exception as save_err:
                batch_logger.error(f"Failed to save team data: {save_err}")
                raise
            
            # 2. Save tech stack
            try:
                tech_stack = DataMapper.map_tech_stack(report)
                if tech_stack:
                    batch_logger.info(f"Saving {len(tech_stack)} tech stack items...")
                    TechStackCRUD.add_technologies(project_id, tech_stack)
            except Exception as e:
                batch_logger.error(f"Failed to save tech stack: {e}")
            
            # 3. Save issues  
            try:
                issues = DataMapper.map_issues(report, project_id)
                if issues:
                    batch_logger.info(f"Saving {len(issues)} issues...")
                    IssueCRUD.add_issues(project_id, issues)
            except Exception as e:
                batch_logger.error(f"Failed to save issues: {e}")
            
            # 4. Save team members
            try:
                team_members = DataMapper.map_team_members(report)
                if team_members:
                    batch_logger.info(f"Saving {len(team_members)} team members...")
                    TeamMemberCRUD.add_members(project_id, team_members)
            except Exception as e:
                batch_logger.error(f"Failed to save team members: {e}")
            
            # 5. Create analysis snapshot if this is part of a batch run or manual run
            try:
                from src.api.backend.database import get_supabase_admin_client
                supabase = get_supabase_admin_client()
                
                # Get team details to check for batch_run metadata (project_id is now team_id after migration)
                team_result = supabase.table("teams").select("id, batch_id").eq("id", str(project_id)).execute()
                
                if team_result.data and len(team_result.data) > 0:
                    team = team_result.data[0]
                    team_id = team.get("id")  # team_id is the same as project_id after migration
                    batch_id = team.get("batch_id")
                    
                    if team_id and batch_id:
                        batch_run_id = None
                        run_number = None

                        # Prefer job metadata (manual or batch) if available
                        job_result = supabase.table("analysis_jobs")\
                            .select("metadata, run_number")\
                            .eq("team_id", str(project_id))\
                            .order("started_at", desc=True)\
                            .limit(1)\
                            .execute()

                        if job_result.data:
                            job = job_result.data[0]
                            metadata = job.get("metadata") or {}
                            batch_run_id = metadata.get("batch_run_id")
                            run_number = metadata.get("run_number") or job.get("run_number")

                        # Fallback to the latest running batch run if metadata is missing
                        if not batch_run_id or not run_number:
                            run_result = supabase.table("batch_analysis_runs")\
                                .select("id, run_number")\
                                .eq("batch_id", batch_id)\
                                .eq("status", "running")\
                                .order("run_number", desc=True)\
                                .limit(1)\
                                .execute()
                            if run_result.data:
                                batch_run = run_result.data[0]
                                batch_run_id = batch_run["id"]
                                run_number = batch_run["run_number"]
                        
                        if batch_run_id and run_number:
                            
                            # Create snapshot
                            snapshot_data = {
                                "team_id": team_id,
                                "batch_run_id": batch_run_id,
                                "run_number": run_number,
                                "total_score": scores.get("total_score"),
                                "originality_score": scores.get("originality_score"),
                                "quality_score": scores.get("quality_score"),
                                "security_score": scores.get("security_score"),
                                "effort_score": scores.get("effort_score"),
                                "implementation_score": scores.get("implementation_score"),
                                "engineering_score": scores.get("engineering_score"),
                                "organization_score": scores.get("organization_score"),
                                "documentation_score": scores.get("documentation_score"),
                                "commit_count": report.get("total_commits", 0),
                                "file_count": len(report.get("files", [])),
                                "lines_of_code": sum(f.get("lines", 0) for f in report.get("files", [])),
                                "tech_stack_count": len(report.get("stack", [])),
                                "issue_count": len(report.get("security", {}).get("issues", [])),
                                "analyzed_at": datetime.now().isoformat()
                            }
                            
                            # Insert or update snapshot (in case of re-analysis)
                            existing_snapshot = supabase.table("analysis_snapshots")\
                                .select("id")\
                                .eq("team_id", team_id)\
                                .eq("run_number", run_number)\
                                .execute()
                            
                            if existing_snapshot.data and len(existing_snapshot.data) > 0:
                                # Update existing snapshot
                                supabase.table("analysis_snapshots")\
                                    .update(snapshot_data)\
                                    .eq("id", existing_snapshot.data[0]["id"])\
                                    .execute()
                                batch_logger.info(f"Updated analysis snapshot for team {team_id}, run {run_number}")
                            else:
                                # Create new snapshot
                                supabase.table("analysis_snapshots").insert(snapshot_data).execute()
                                batch_logger.info(f"Created analysis snapshot for team {team_id}, run {run_number}")
                            
                            # Update batch run statistics
                            completed_count = supabase.table("analysis_snapshots")\
                                .select("id", count="exact")\
                                .eq("batch_run_id", batch_run_id)\
                                .execute()
                            
                            completed = completed_count.count if completed_count.count else 0
                            
                            # Get all snapshots for average score
                            all_snapshots = supabase.table("analysis_snapshots")\
                                .select("total_score")\
                                .eq("batch_run_id", batch_run_id)\
                                .execute()
                            
                            if all_snapshots.data:
                                avg_score = sum(s.get("total_score") or 0 for s in all_snapshots.data) / len(all_snapshots.data)
                            else:
                                avg_score = None
                            
                            # Update run progress
                            run_update = {
                                "completed_teams": completed,
                                "avg_score": avg_score
                            }
                            
                            # Check if all teams completed
                            run_info = supabase.table("batch_analysis_runs").select("total_teams, batch_id").eq("id", batch_run_id).execute()
                            if run_info.data and completed >= run_info.data[0]["total_teams"]:
                                run_update["status"] = "completed"
                                run_update["completed_at"] = datetime.now().isoformat()
                                
                                # Send batch completion notification
                                try:
                                    batch_id_for_notification = run_info.data[0].get("batch_id")
                                    
                                    # Get batch name for better notification
                                    batch_info = supabase.table("batches").select("name, semester, year").eq("id", batch_id_for_notification).execute()
                                    if batch_info.data:
                                        batch_name = f"{batch_info.data[0].get('name', 'Batch')} ({batch_info.data[0].get('semester', '')} {batch_info.data[0].get('year', '')})"
                                    else:
                                        batch_name = f"Batch {batch_id_for_notification}"
                                    
                                    # Create batch completion notification
                                    supabase.table('notifications').insert({
                                        'type': 'success',
                                        'title': f'Batch Analysis Complete: {batch_name}',
                                        'message': f'All {completed} teams have been analyzed successfully. Average score: {avg_score:.1f}/100' if avg_score else f'All {completed} teams have been analyzed successfully.',
                                        'metadata': {
                                            'batch_id': batch_id_for_notification,
                                            'batch_run_id': batch_run_id,
                                            'total_teams': completed,
                                            'avg_score': avg_score
                                        },
                                        'is_read': False
                                    }).execute()
                                    batch_logger.info(f"📧 Batch completion notification sent for {batch_name}")
                                    
                                    # Automatically run repository privacy check after batch completes
                                    try:
                                        from ..routers.repo_privacy import check_batch_repo_privacy_internal
                                        batch_logger.info(f"🔍 Starting automatic repository privacy check for batch {batch_id_for_notification}")
                                        privacy_result = check_batch_repo_privacy_internal(batch_id_for_notification)
                                        batch_logger.info(f"✅ Repository privacy check completed: {privacy_result.get('privateRepos', 0)} private, {privacy_result.get('invalidRepos', 0)} invalid, {privacy_result.get('missingRepos', 0)} missing")
                                    except Exception as privacy_error:
                                        batch_logger.warning(f"Failed to run automatic repository privacy check: {privacy_error}")
                                    
                                except Exception as notif_error:
                                    batch_logger.warning(f"Failed to send batch completion notification: {notif_error}")
                            
                            supabase.table("batch_analysis_runs").update(run_update).eq("id", batch_run_id).execute()
                            batch_logger.info(f"Updated batch run statistics: {completed} teams completed")
                        
            except Exception as e:
                batch_logger.warning(f"Failed to create analysis snapshot: {e}")
                # Don't fail the whole save if snapshot creation fails
            
            # 6. Invalidate cache for this project and related team views
            try:
                from src.api.backend.database import get_supabase_admin_client
                supabase = get_supabase_admin_client()
                
                # Get batch_id for this team to invalidate batch-level caches
                team_result = supabase.table("teams").select("batch_id").eq("id", str(project_id)).execute()
                batch_id = team_result.data[0].get("batch_id") if team_result.data else None
                
                cache.invalidate_project(str(project_id))

                # Clear team-scoped caches (analytics/report endpoints)
                # Note: project_id is now team_id after migration, so we can use it directly
                cache.delete_pattern(f"hackeval:analytics:{project_id}")
                cache.delete_pattern(f"hackeval:report:team:{project_id}")
                cache.delete_pattern(f"hackeval:analysis:{project_id}*")  # Clear analysis status cache
                cache.delete_pattern(f"hackeval:mentor:team_report:*:{project_id}")  # Clear mentor team reports
                
                # Clear batch-level caches (leaderboard, stats, etc.)
                if batch_id:
                    cache.delete_pattern(f"report:batch:{batch_id}")
                    cache.delete_pattern(f"report:mentor:*:{batch_id}")
                    cache.delete_pattern(f"leaderboard:*:{batch_id}:*")  # Clear all leaderboard variants
                
                # Clear global caches (stats, tech stacks, leaderboard chart)
                cache.delete_pattern("stats")
                cache.delete_pattern("tech-stacks")
                cache.delete_pattern("leaderboard:chart")
                cache.delete_pattern("leaderboard:")  # Clear ALL leaderboard cache entries

                batch_logger.info(f"Cache invalidated for team {project_id} and batch {batch_id}")
            except Exception as e:
                batch_logger.warning(f"Failed to invalidate cache: {e}")
            
            return True
            
        except Exception as e:
            batch_logger.error(f"Error saving results: {e}")
            batch_logger.error(f"Traceback: {traceback.format_exc()}")
            return False
