#!/usr/bin/env python3
"""
Script to trigger a single team analysis and monitor branch_details flow
"""
import sys
sys.path.insert(0, '.')

from src.api.backend.database import get_supabase
from uuid import UUID
from src.api.backend.services.analyzer_service import AnalyzerService
import traceback

def run_team_analysis_debug(team_id_str: str):
    """Run analysis for a single team and monitor branch_details"""
    
    supabase = get_supabase()
    
    print(f"[*] Running analysis for team: {team_id_str}")
    print("-" * 60)
    
    # Get team data
    try:
        team_id = UUID(team_id_str)
        response = supabase.table("teams").select("id, team_name, repo_url").eq("id", str(team_id)).single().execute()
        
        if not response.data:
            print(f"[ERROR] Team not found: {team_id_str}")
            return
        
        team = response.data
        team_name = team.get("team_name")
        repo_url = team.get("repo_url")
        
        print(f"[OK] Team: {team_name}")
        print(f"[OK] Repo: {repo_url}")
        print()
        print("[*] Running analysis...")
        print("-" * 60)
        
        # Create a dummy job UUID for testing
        from uuid import uuid4
        job_id = uuid4()
        
        # Run analysis
        report = AnalyzerService.analyze_repository(
            team_id=team_id,
            job_id=job_id,
            repo_url=repo_url,
            team_name=team_name
        )
        
        print()
        print("-" * 60)
        print("[OK] Analysis completed")
        
        # Check what was saved to the database
        print()
        print("[*] Checking database...")
        print("-" * 60)
        
        updated_team = supabase.table("teams").select("report_json").eq("id", str(team_id)).single().execute()
        
        if updated_team.data:
            report_json = updated_team.data.get("report_json", {})
            
            if isinstance(report_json, str):
                import json
                try:
                    report_json = json.loads(report_json)
                except:
                    report_json = {}
            
            if isinstance(report_json, dict):
                commit_details = report_json.get("commit_details", {})
                
                print(f"[DB] commit_details keys: {list(commit_details.keys()) if isinstance(commit_details, dict) else 'NOT A DICT'}")
                
                if "branch_details" in commit_details:
                    print(f"[DB] ✓ branch_details found with {len(commit_details.get('branch_details', {}))} branches")
                else:
                    print(f"[DB] ✗ branch_details NOT FOUND in commit_details")
    
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Use the first team we found
        supabase = get_supabase()
        teams = supabase.table('teams').select('id').limit(1).execute()
        if teams.data:
            team_id = teams.data[0]['id']
            print(f"[*] No team ID provided, using first team: {team_id}")
            run_team_analysis_debug(team_id)
        else:
            print("Usage: python run_analysis_debug.py <team_id>")
    else:
        run_team_analysis_debug(sys.argv[1])
