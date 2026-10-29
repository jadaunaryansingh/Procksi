"""
Update existing team names to format "T## - Project Name"
Run with: python scripts/update_team_names.py
"""

import sys
import os
from pathlib import Path
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.api.backend.database import get_supabase_admin_client


def main():
    """Update team names in existing batch"""
    excel_path = Path(__file__).parent.parent.parent / "top projects 3rd year.xlsx"
    
    if not excel_path.exists():
        print(f"❌ Excel file not found: {excel_path}")
        return
    
    print("📖 Reading Excel file...")
    df = pd.read_excel(excel_path)
    
    supabase = get_supabase_admin_client()
    
    # Get the batch
    batch_response = supabase.table("batches")\
        .select("id, name")\
        .eq("name", "3rd Year Top Projects 2024")\
        .execute()
    
    if not batch_response.data:
        print("❌ Batch '3rd Year Top Projects 2024' not found")
        return
    
    batch_id = batch_response.data[0]["id"]
    print(f"✓ Found batch: {batch_response.data[0]['name']}")
    print(f"  Batch ID: {batch_id}\n")
    
    # Get all teams in batch
    teams_response = supabase.table("teams")\
        .select("id, team_name")\
        .eq("batch_id", batch_id)\
        .execute()
    
    if not teams_response.data:
        print("❌ No teams found in batch")
        return
    
    print(f"Found {len(teams_response.data)} teams to update\n")
    print("=" * 80)
    
    updated_count = 0
    skipped_count = 0
    
    # Build mapping from team ID to project name
    team_mapping = {}
    for idx, row in df.iterrows():
        try:
            team_id = str(row.get('Team Number', row.iloc[0])).strip()
            project_name = str(row.get('Project Name', '')).strip()
            
            if team_id and team_id != 'nan' and project_name and project_name != 'nan':
                team_mapping[team_id] = project_name
        except:
            continue
    
    print(f"Extracted {len(team_mapping)} team names from Excel\n")
    
    # Update teams
    for team in teams_response.data:
        current_name = team["team_name"]
        team_id = team["id"]
        
        # Extract team number from current name
        # Could be "Team T18" or "T18 - Some Name" or just "T18"
        team_number = None
        if current_name.startswith("Team "):
            team_number = current_name.split()[1].split(" -")[0]
        elif current_name.startswith("T"):
            team_number = current_name.split(" -")[0].split()[0]
        
        if not team_number or team_number not in team_mapping:
            print(f"  ⊙ {current_name} - No matching project name found")
            skipped_count += 1
            continue
        
        # Build new name
        project_name = team_mapping[team_number]
        new_name = f"{team_number} - {project_name}"
        
        # Skip if already correct
        if current_name == new_name:
            print(f"  ⊙ {current_name} - Already correct")
            skipped_count += 1
            continue
        
        # Update team name
        try:
            supabase.table("teams")\
                .update({"team_name": new_name})\
                .eq("id", team_id)\
                .execute()
            
            print(f"  ✓ {current_name}")
            print(f"    → {new_name}")
            updated_count += 1
        except Exception as e:
            print(f"  ✗ Failed to update {current_name}: {e}")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  ✓ Updated: {updated_count} teams")
    print(f"  ⊙ Skipped: {skipped_count} teams")
    print("=" * 80)


if __name__ == "__main__":
    main()
