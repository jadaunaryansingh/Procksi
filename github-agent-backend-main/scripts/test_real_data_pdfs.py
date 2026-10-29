import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env vars
load_dotenv()

from src.api.backend.database import get_supabase_client
from src.api.backend.utils.pdf_generator import generate_team_report_pdf
from src.api.backend.utils.leaderboard_pdf_generator import generate_leaderboard_pdf
import json

def test_real_pdfs():
    supabase = get_supabase_client()
    
    # 1. Test Report PDF with a real team (e.g., Team 4)
    print("Fetching Team 4 report...")
    team_data = supabase.table('teams').select('*, students(*)').eq('team_name', 'Team 4').execute()
    
    if team_data.data:
        team = team_data.data[0]
        report_json = team.get('report_json') or {}
        
        # We need to construct the report_data dict that the PDF generator expects
        # Look at src/api/backend/routers/reports.py for how it's done
        report_data = {
            "teamName": team.get('team_name', 'Unknown Team'),
            "projectName": team.get('team_name', ''), # fallback
            "repoUrl": team.get('repo_url', ''),
            "generatedAt": team.get('updated_at', ''),
            "healthStatus": team.get('health_status', 'on_track'),
            "teamMembers": team.get('students', []),
            "analysis": report_json.get('scores', {}),
            "codeMetrics": report_json.get('code_metrics', {}),
            "maturity": report_json.get('maturity', {}),
            "commits": report_json.get('commit_details', {}),
            "aiAnalysis": report_json.get('ai_analysis', {}),
            "security": report_json.get('security', {}),
            "riskyFiles": report_json.get('ai_analysis', {}).get('risky_files', []),
            "riskFlags": report_json.get('risk_flags', []),
            "problemStatement": '',
            "productAnalysis": report_json.get('product_analysis', {})
        }
        
        pdf_bytes = generate_team_report_pdf(report_data)
        
        out_path = os.path.join(os.path.dirname(__file__), 'real_team4_report.pdf')
        with open(out_path, 'wb') as f:
            f.write(pdf_bytes)
        print(f"✅ Real Team Report PDF generated: {out_path} ({len(pdf_bytes)} bytes)")
    else:
        print("❌ Team 4 not found in database")

    # 2. Test Leaderboard PDF with real top teams
    print("\nFetching real leaderboard data...")
    all_teams = supabase.table('teams').select('*').order('total_score', desc=True).limit(50).execute()
    
    if all_teams.data:
        entries = []
        for i, t in enumerate(all_teams.data):
            # Only include if they have a decent score
            score = t.get('total_score', 0)
            
            entries.append({
                "rank": i + 1,
                "team_id": t.get('id'),
                "team_name": t.get('name'),
                # projects not joined here, so let's just use empty string or try to fetch
                "project_name": "", 
                "overall_score": score,
                "report_json": t.get('report_json', {})
            })
            
        leaderboard_data = {
            "batch_name": "CEA - AIML & Hons Project",
            "generated_at": all_teams.data[0].get('updated_at', ''),
            "total_teams": len(all_teams.data),
            "entries": entries
        }
        
        lb_pdf_bytes = generate_leaderboard_pdf(leaderboard_data, recipient_team_id=all_teams.data[3].get('id'))
        lb_out_path = os.path.join(os.path.dirname(__file__), 'real_leaderboard.pdf')
        with open(lb_out_path, 'wb') as f:
            f.write(lb_pdf_bytes)
        print(f"✅ Real Leaderboard PDF generated: {lb_out_path} ({len(lb_pdf_bytes)} bytes)")
    else:
        print("❌ No teams found for leaderboard")

if __name__ == '__main__':
    test_real_pdfs()
