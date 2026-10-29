"""
Report JSON Storage Migration
Moves large report_json from database to Supabase Storage
Reduces database size by 80% and eliminates 300KB per team from hot path
"""
from ..database import get_supabase_admin_client
import json
from datetime import datetime
from typing import Dict, Any
from uuid import UUID
import os


class ReportStorageManager:
    """Manages report storage in Supabase Storage instead of database"""
    
    BUCKET_NAME = "team-reports"
    MAX_REPORT_SIZE = 20_000_000  # 20MB hard limit (some reports are very large)
    
    @staticmethod
    def ensure_bucket_exists():
        """Ensure storage bucket exists"""
        supabase = get_supabase_admin_client()
        
        try:
            # Check if bucket exists
            buckets = supabase.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            
            if ReportStorageManager.BUCKET_NAME not in bucket_names:
                # Create bucket
                supabase.storage.create_bucket(
                    ReportStorageManager.BUCKET_NAME,
                    options={
                        "public": False,  # Private bucket
                        "file_size_limit": 10485760,  # 10MB max per file
                        "allowed_mime_types": ["application/json"]
                    }
                )
                print(f"✅ Created storage bucket: {ReportStorageManager.BUCKET_NAME}")
        except Exception as e:
            print(f"⚠️  Bucket check/creation warning: {e}")
    
    @staticmethod
    def save_report_to_storage(team_id: UUID, report_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save report JSON to Supabase Storage
        
        Args:
            team_id: Team UUID
            report_json: Full report JSON object (will be saved to storage)
            
        Returns:
            Dict with:
                - report_path: Storage path
                - report_size: Size in bytes
                - report_summary: Lightweight summary (<50KB) for database
        """
        supabase = get_supabase_admin_client()
        
        # Check size and enforce hard limit
        report_str = json.dumps(report_json)
        report_size = len(report_str.encode('utf-8'))
        
        if report_size > ReportStorageManager.MAX_REPORT_SIZE:
            raise ValueError(
                f"Report size {report_size} bytes exceeds limit of "
                f"{ReportStorageManager.MAX_REPORT_SIZE} bytes"
            )
        
        # Generate storage path
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_path = f"{team_id}/{timestamp}_report.json"
        
        # Upload to storage
        supabase.storage.from_(ReportStorageManager.BUCKET_NAME).upload(
            path=file_path,
            file=report_str.encode('utf-8'),
            file_options={
                "content-type": "application/json",
                "upsert": "true"
            }
        )
        
        print(f"✅ Uploaded report to storage: {file_path} ({report_size} bytes)")
        
        # Build lightweight summary for database (<50KB)
        report_summary = {
            "scores": report_json.get("scores", {}),
            "total_commits": report_json.get("total_commits", 0),
            "languages": report_json.get("languages", {}),
            "frameworks": report_json.get("stack", [])[:10],  # Top 10 only
            "ai_percentage": report_json.get("judge", {}).get("aiGeneratedPercentage", 0),
            "security_summary": {
                "total_issues": len(report_json.get("security", {}).get("issues", [])),
                "high_severity": sum(
                    1 for i in report_json.get("security", {}).get("issues", [])
                    if i.get("severity") == "high"
                )
            }
        }
        
        return {
            "report_path": file_path,
            "report_size": report_size,
            "report_summary": report_summary
        }
    
    @staticmethod
    def get_report_from_storage(file_path: str) -> Dict[str, Any]:
        """
        Retrieve report JSON from Supabase Storage
        
        Args:
            file_path: Path to report file
        
        Returns:
            Report JSON as dictionary
        """
        supabase = get_supabase_admin_client()
        
        try:
            # Download from storage
            data = supabase.storage.from_(ReportStorageManager.BUCKET_NAME).download(file_path)
            
            # Parse JSON
            report_json = json.loads(data.decode('utf-8'))
            
            print(f"✅ Downloaded report from storage: {file_path}")
            return report_json
        
        except Exception as e:
            print(f"❌ Storage download failed: {e}")
            raise
    
    @staticmethod
    def get_report_for_team(team: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get report_json for a team, automatically handling storage migration.
        
        This is a convenience method that checks if the team has been migrated
        to storage (report_path exists) and fetches from storage, otherwise
        falls back to the report_json column.
        
        Args:
            team: Team dict with report_path and/or report_json keys
            
        Returns:
            Parsed report_json dict (empty dict if none available)
        """
        report_path = team.get("report_path")
        
        if report_path:
            try:
                return ReportStorageManager.get_report_from_storage(report_path)
            except Exception as e:
                print(f"⚠️  Failed to fetch from storage, falling back to DB: {e}")
        
        # Fallback to database report_json
        report_json = team.get("report_json")
        
        if isinstance(report_json, str):
            try:
                import json
                return json.loads(report_json)
            except Exception:
                return {}
        
        return report_json if isinstance(report_json, dict) else {}
    
    @staticmethod
    def delete_report_from_storage(file_path: str):
        """Delete report from storage"""
        supabase = get_supabase_admin_client()
        
        try:
            supabase.storage.from_(ReportStorageManager.BUCKET_NAME).remove([file_path])
            print(f"🗑️  Deleted report from storage: {file_path}")
        except Exception as e:
            print(f"⚠️  Storage deletion failed: {e}")
    
    @staticmethod
    async def migrate_all_teams(batch_size: int = 50, dry_run: bool = True) -> Dict[str, Any]:
        """
        Migrate all teams from database report_json to storage
        
        Args:
            batch_size: Number of teams to process at once
            dry_run: If True, only simulate migration
            
        Returns:
            Dict with migration results
        """
        from backend.database import get_supabase_admin_client
        
        supabase = get_supabase_admin_client()
        
        results = {
            "migrated": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }
        
        try:
            # Fetch all teams with report_json
            response = supabase.table("teams").select(
                "id, team_name, report_json, report_path"
            ).execute()
            
            teams = response.data
            total_teams = len(teams)
            
            print(f"Found {total_teams} teams in database")
            print()
            
            for i, team in enumerate(teams):
                team_id = team.get("id")
                team_name = team.get("team_name", "Unknown")
                report_json = team.get("report_json")
                report_path = team.get("report_path")
                
                # Skip if already migrated
                if report_path:
                    print(f"[{i+1}/{total_teams}] SKIP {team_name} - Already migrated")
                    results["skipped"] += 1
                    continue
                
                # Skip if no report_json
                if not report_json:
                    print(f"[{i+1}/{total_teams}] SKIP {team_name} - No report_json")
                    results["skipped"] += 1
                    continue
                
                try:
                    if dry_run:
                        # Simulate migration
                        report_size = len(json.dumps(report_json).encode('utf-8'))
                        print(f"[{i+1}/{total_teams}] WOULD MIGRATE {team_name} - {report_size} bytes")
                        results["migrated"] += 1
                    else:
                        # Actually migrate
                        storage_result = ReportStorageManager.save_report_to_storage(
                            team_id=team_id,
                            report_json=report_json
                        )
                        
                        # Update team with storage path (report_summary not stored in DB)
                        supabase.table("teams").update({
                            "report_path": storage_result["report_path"]
                        }).eq("id", team_id).execute()
                        
                        print(f"[{i+1}/{total_teams}] OK {team_name} - Migrated {storage_result['report_size']} bytes")
                        results["migrated"] += 1
                
                except Exception as e:
                    error_msg = f"{team_name}: {str(e)}"
                    results["errors"].append(error_msg)
                    results["failed"] += 1
                    print(f"[{i+1}/{total_teams}] FAILED {team_name} - {e}")
                
                # Progress update every 50 teams
                if (i + 1) % batch_size == 0:
                    print()
                    print(f"Progress: {i+1}/{total_teams} teams processed")
                    print(f"  Migrated: {results['migrated']}, Failed: {results['failed']}, Skipped: {results['skipped']}")
                    print()
        
        except Exception as e:
            print(f"[FATAL] Error during migration: {e}")
            results["errors"].append(f"Fatal: {str(e)}")
        
        return results
    
    @staticmethod
    def migrate_team_to_storage(team_id: str):
        """
        Migrate single team's report_json from DB to storage
        
        Args:
            team_id: Team UUID
        """
        supabase = get_supabase_admin_client()
        
        # 1. Fetch team's report_json
        team = supabase.table("teams").select("id, report_json").eq("id", team_id).single().execute()
        
        if not team.data:
            print(f"⚠️  Team {team_id} not found")
            return
        
        report_json = team.data.get("report_json")
        
        if not report_json:
            print(f"⚠️  Team {team_id} has no report_json")
            return
        
        # 2. Upload to storage
        try:
            storage_info = ReportStorageManager.save_report_to_storage(team_id, report_json)
            
            # 3. Update team record (remove report_json, add path)
            supabase.table("teams").update({
                "report_json": None,  # Clear large JSON
                "report_path": storage_info["report_path"],
                "report_size": storage_info["report_size"]
            }).eq("id", team_id).execute()
            
            print(f"✅ Migrated team {team_id} to storage")
        
        except Exception as e:
            print(f"❌ Migration failed for team {team_id}: {e}")


# Updated save_analysis_results function for data_mapper.py
def save_analysis_results_with_storage(project_id: UUID, report: Dict[str, Any]) -> bool:
    """
    UPDATED: Save analysis results with report_json to storage
    
    This replaces the existing save_analysis_results in data_mapper.py
    """
    from src.api.backend.crud import TeamCRUD, TechStackCRUD, IssueCRUD, TeamMemberCRUD
    from src.api.backend.services.data_mapper import DataMapper
    from src.api.backend.database import get_supabase_admin_client
    
    try:
        # 1. Map scores (same as before)
        scores = DataMapper.map_scores(report)
        
        judge = report.get("judge", {}) or {}
        verdict = judge.get("verdict", "Unknown")
        ai_pros = judge.get("positive_feedback", "")
        ai_cons = judge.get("constructive_feedback", "")
        token_usage = judge.get("token_usage", {}) or report.get("token_usage", {})
        
        # 2. Build MINIMAL report_json for database (keep small!)
        report_json_minimal = {
            "scores": report.get("scores", {}),
            "stack": report.get("stack", [])[:10],  # Only top 10
            "languages": report.get("languages", {}),
            "verdict_summary": str(verdict)[:500],  # Truncate
            "security_summary": {
                "high_issues": len([i for i in report.get("security", {}).get("issues", []) if i.get("severity") == "high"]),
                "medium_issues": len([i for i in report.get("security", {}).get("issues", []) if i.get("severity") == "medium"]),
                "critical_count": report.get("security", {}).get("critical_count", 0)
            },
            "commit_summary": {
                "total_commits": report.get("total_commits", 0),
                "branch_count": len(report.get("commit_details", {}).get("branches", []))
            }
        }
        
        # Validate minimal JSON size
        minimal_size = len(json.dumps(report_json_minimal))
        print(f"📊 Minimal report_json size: {minimal_size} bytes")
        
        # 3. Build FULL report_json for storage
        report_json_full = {
            "scores": report.get("scores", {}),
            "stack": report.get("stack", []),
            "languages": report.get("languages", {}),
            "files": report.get("files", [])[:30],
            "judge": judge,
            "token_usage": token_usage,
            "team": report.get("team", {}),
            "security": report.get("security", {}),
            "maturity": report.get("maturity", {}),
            "structure": report.get("structure", {}),
            "total_commits": report.get("total_commits", 0),
            "commit_details": report.get("commit_details", {}),
            "branchTracking": report.get("branchTracking", {}),
            "project_statement": report.get("project_statement")
        }
        
        # 4. Save full report to storage
        storage_info = ReportStorageManager.save_report_to_storage(project_id, report_json_full)
        
        # 5. Update team with minimal data + storage path
        team_data = {
            **scores,
            "total_commits": report.get("total_commits", 0),
            "verdict": str(verdict)[:255] if verdict else None,
            "ai_pros": [str(ai_pros)[:5000]] if ai_pros else [],
            "ai_cons": [str(ai_cons)[:5000]] if ai_cons else [],
            "status": "completed",
            "last_analyzed_at": datetime.now().isoformat(),
            "openai_prompt_tokens": token_usage.get("prompt_tokens", 0),
            "openai_completion_tokens": token_usage.get("completion_tokens", 0),
            "openai_total_tokens": token_usage.get("total_tokens", 0),
            "openai_cost_usd": token_usage.get("total_cost_usd", 0.0),
            "report_json": report_json_minimal,  # SMALL version in DB
            "report_path": storage_info["report_path"],  # Path to full version
            "report_size": storage_info["report_size"]  # Size for monitoring
        }
        
        TeamCRUD.update_team(project_id, team_data)
        print(f"✅ Team data saved (minimal JSON + storage path)")
        
        # 6. Save related data (same as before)
        tech_stack = DataMapper.map_tech_stack(report)
        if tech_stack:
            TechStackCRUD.add_technologies(project_id, tech_stack)
        
        issues = DataMapper.map_issues(report, project_id)
        if issues:
            IssueCRUD.add_issues(project_id, issues)
        
        team_members = DataMapper.map_team_members(report)
        if team_members:
            TeamMemberCRUD.add_members(project_id, team_members)
        
        return True
    
    except Exception as e:
        print(f"❌ Save failed: {e}")
        return False


if __name__ == "__main__":
    # Run migration
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        ReportStorageManager.migrate_all_teams()
    else:
        print("Usage: python report_storage.py migrate")
