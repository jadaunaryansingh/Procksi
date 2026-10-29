"""
Export Top 5 Teams from 3rd Year Batch to Excel
Includes all metadata and analysis scores
"""
import os
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.backend.database import get_supabase_admin_client

def export_top_teams_to_excel(batch_name="3rd Year", limit=10, output_file=None):
    """
    Export top teams from specified batch to Excel
    
    Args:
        batch_name: Name of the batch (e.g., "3rd Year")
        limit: Number of top teams to export
        output_file: Output Excel file path (optional)
    """
    try:
        supabase = get_supabase_admin_client()
        
        # Find the batch
        print(f"🔍 Searching for batch: {batch_name}")
        batch_result = supabase.table("batches")\
            .select("id, name, semester, year")\
            .ilike("name", f"%{batch_name}%")\
            .execute()
        
        if not batch_result.data:
            print(f"❌ Batch '{batch_name}' not found")
            print("\n📋 Available batches:")
            all_batches = supabase.table("batches").select("name, semester, year").execute()
            for b in all_batches.data:
                print(f"   - {b['name']} ({b['semester']} {b['year']})")
            return
        
        batch = batch_result.data[0]
        batch_id = batch["id"]
        print(f"✅ Found batch: {batch['name']} (ID: {batch_id})")
        
        # Get top teams from this batch
        print(f"\n📊 Fetching top {limit} teams...")
        teams_result = supabase.table("teams")\
            .select("*")\
            .eq("batch_id", batch_id)\
            .not_.is_("total_score", "null")\
            .order("total_score", desc=True)\
            .limit(limit)\
            .execute()
        
        if not teams_result.data:
            print(f"❌ No analyzed teams found in batch '{batch_name}'")
            return
        
        teams = teams_result.data
        print(f"✅ Found {len(teams)} teams")
        
        # Prepare data for Excel
        excel_data = []
        
        for idx, team in enumerate(teams, 1):
            print(f"\n📦 Processing Team {idx}: {team.get('team_name', 'Unknown')}")
            
            # Basic Info
            row = {
                "Rank": idx,
                "Team Name": team.get("team_name", ""),
                "Repository URL": team.get("repo_url", ""),
                "Status": team.get("status", ""),
                "Batch": batch["name"],
                "Semester": batch["semester"],
                "Year": batch["year"],
            }
            
            # Scores
            row.update({
                "Total Score": round(team.get("total_score", 0), 2),
                "Quality Score": round(team.get("quality_score", 0), 2),
                "Security Score": round(team.get("security_score", 0), 2),
                "Engineering Score": round(team.get("engineering_score", 0), 2),
                "Documentation Score": round(team.get("documentation_score", 0), 2),
                "Originality Score": round(team.get("originality_score", 0), 2),
                "Implementation Score": round(team.get("implementation_score", 0), 2),
                "Organization Score": round(team.get("organization_score", 0), 2),
                "Effort Score": round(team.get("effort_score", 0), 2),
            })
            
            # Verdict and Health
            row.update({
                "Verdict": team.get("verdict", ""),
                "Health Status": team.get("health_status", ""),
            })
            
            # Repository Metrics
            row.update({
                "Commit Count": team.get("commit_count", 0),
                "File Count": team.get("file_count", 0),
                "Lines of Code": team.get("lines_of_code", 0),
                "Contributors": team.get("contributors", 0),
            })
            
            # Commit Quality Metrics (from fake commit detection)
            row.update({
                "Real Commits": team.get("real_commits", 0),
                "Fake Commits": team.get("fake_commits", 0),
                "Fake Commit Ratio": round(team.get("fake_commit_ratio", 0) * 100, 1) if team.get("fake_commit_ratio") else 0,
                "Real Additions": team.get("real_additions", 0),
                "Fake Additions": team.get("fake_additions", 0),
                "Inflation Ratio": round(team.get("inflation_ratio", 0), 2) if team.get("inflation_ratio") else 0,
                "Commit Health": team.get("commit_health", ""),
            })
            
            # Analysis Timestamps
            row.update({
                "Last Analyzed": team.get("last_analyzed_at", ""),
                "Created At": team.get("created_at", ""),
                "Updated At": team.get("updated_at", ""),
            })
            
            # Team Members
            members_result = supabase.table("team_members")\
                .select("name, commits, contribution_pct")\
                .eq("team_id", team["id"])\
                .execute()
            
            if members_result.data:
                member_names = [m.get("name", "") for m in members_result.data if m.get("name")]
                member_commits = [str(m.get("commits", 0)) for m in members_result.data]
                member_contributions = [f"{m.get('contribution_pct', 0):.1f}%" for m in members_result.data]
                
                row["Team Members"] = ", ".join(member_names)
                row["Member Commits"] = ", ".join(member_commits)
                row["Member Contributions"] = ", ".join(member_contributions)
                row["Team Size"] = len(members_result.data)
            else:
                row["Team Members"] = ""
                row["Member Commits"] = ""
                row["Member Contributions"] = ""
                row["Team Size"] = 0
            
            # Mentor Info
            if team.get("mentor_id"):
                # Get mentor's user info
                mentor_result = supabase.table("mentors")\
                    .select("user_id, users(full_name)")\
                    .eq("id", team["mentor_id"])\
                    .execute()
                
                if mentor_result.data and mentor_result.data[0].get("users"):
                    user_data = mentor_result.data[0]["users"]
                    row["Mentor Name"] = user_data.get("full_name", "") if isinstance(user_data, dict) else ""
                else:
                    row["Mentor Name"] = ""
            else:
                row["Mentor Name"] = ""
            
            excel_data.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(excel_data)
        
        # Generate output filename if not provided
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"top_{limit}_teams_{batch_name.replace(' ', '_')}_{timestamp}.xlsx"
        
        # Export to Excel with formatting
        print(f"\n💾 Exporting to Excel: {output_file}")
        
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Top Teams', index=False)
            
            # Get the worksheet
            worksheet = writer.sheets['Top Teams']
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # Cap at 50
                worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # Freeze the header row
            worksheet.freeze_panes = 'A2'
        
        print(f"✅ Excel file created successfully!")
        print(f"\n📊 Summary:")
        print(f"   - Batch: {batch['name']}")
        print(f"   - Teams Exported: {len(excel_data)}")
        print(f"   - Output File: {output_file}")
        print(f"\n📈 Top 5 Teams:")
        for idx, team in enumerate(teams, 1):
            print(f"   {idx}. {team.get('team_name', 'Unknown')} - Score: {team.get('total_score', 0):.2f}")
        
        return output_file
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export top teams from a batch to Excel")
    parser.add_argument("--batch", default="3rd Year", help="Batch name (default: '3rd Year')")
    parser.add_argument("--limit", type=int, default=5, help="Number of top teams to export (default: 5)")
    parser.add_argument("--output", help="Output Excel file path (optional)")
    
    args = parser.parse_args()
    
    print("="*60)
    print("📊 Top Teams Excel Export")
    print("="*60)
    
    export_top_teams_to_excel(
        batch_name=args.batch,
        limit=args.limit,
        output_file=args.output
    )
