#!/usr/bin/env python3
"""
Migration Script: Populate missing mentor metadata for teams

This script helps recover mentor assignment information for teams that don't have
metadata.ingestion.mentor populated. It uses historical assignment data to infer
the correct mentor.

Usage:
    python scripts/migrate_populate_mentor_metadata.py --dry-run
    python scripts/migrate_populate_mentor_metadata.py --execute
"""

import sys
import json
from uuid import UUID
from datetime import datetime
from src.api.backend.database import get_supabase_admin_client

def normalize_name(name: str) -> str:
    """Normalize name for comparison"""
    if not name:
        return ""
    return name.lower().strip()

def main():
    """Main migration function"""
    execute = "--execute" in sys.argv
    dry_run = "--dry-run" in sys.argv
    
    if not execute and not dry_run:
        print("Usage: python scripts/migrate_populate_mentor_metadata.py [--dry-run|--execute]")
        print("  --dry-run: Show what would be changed (DEFAULT)")
        print("  --execute: Actually update the database")
        sys.exit(1)
    
    sb = get_supabase_admin_client()
    
    print("=" * 80)
    print("MENTOR METADATA POPULATION MIGRATION")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    print()
    
    # 1. Get all mentors
    mentors_resp = sb.table("users").select(
        "id, email, full_name"
    ).or_("role.eq.mentor,is_mentor.eq.true").execute()
    
    mentor_map = {}
    for mentor in mentors_resp.data or []:
        mentor_id = mentor.get("id")
        email = mentor.get("email", "")
        full_name = mentor.get("full_name", "")
        
        if email:
            mentor_map[normalize_name(email)] = {
                "id": mentor_id,
                "email": email,
                "full_name": full_name
            }
        if full_name:
            mentor_map[normalize_name(full_name)] = {
                "id": mentor_id,
                "email": email,
                "full_name": full_name
            }
    
    print(f"Found {len(mentor_map)} mentor name/email entries\n")
    
    # 2. Find teams without mentor metadata
    teams_resp = sb.table("teams").select(
        "id, team_name, batch_id, metadata, created_at"
    ).execute()
    
    teams_without_mentor_meta = []
    teams_with_mentor_meta = []
    
    for team in teams_resp.data or []:
        metadata = team.get("metadata") or {}
        ingestion = metadata.get("ingestion") or {}
        
        has_mentor_meta = bool(ingestion.get("mentor"))
        
        if has_mentor_meta:
            teams_with_mentor_meta.append(team)
        else:
            teams_without_mentor_meta.append(team)
    
    print(f"Teams WITH mentor metadata: {len(teams_with_mentor_meta)}")
    print(f"Teams WITHOUT mentor metadata: {len(teams_without_mentor_meta)}")
    print()
    
    # 3. Try to recover mentor info from suggested_mentor or historical assignments
    updates_to_make = []
    recoverable = 0
    
    for team in teams_without_mentor_meta:
        team_id = team.get("id")
        team_name = team.get("team_name")
        metadata = team.get("metadata") or {}
        ingestion = metadata.get("ingestion") or {}
        
        # Check suggested_mentor
        suggested_mentor = metadata.get("suggested_mentor", "").strip()
        mentor_to_use = None
        match_type = None
        
        if suggested_mentor:
            norm_suggested = normalize_name(suggested_mentor)
            if norm_suggested in mentor_map:
                mentor_to_use = mentor_map[norm_suggested]
                match_type = "suggested_mentor"
        
        # Check historical assignment (if the team was ever assigned)
        if not mentor_to_use:
            assignment_resp = sb.table("mentor_team_assignments").select(
                "mentor_id"
            ).eq("team_id", team_id).limit(1).execute()
            
            if assignment_resp.data:
                mentor_id = assignment_resp.data[0].get("mentor_id")
                mentor_info = sb.table("users").select(
                    "id, email, full_name"
                ).eq("id", mentor_id).single().execute()
                
                if mentor_info.data:
                    mentor_to_use = mentor_info.data
                    match_type = "historical_assignment"
        
        if mentor_to_use:
            recoverable += 1
            mentor_full_name = mentor_to_use.get("full_name") or mentor_to_use.get("email")
            
            updates_to_make.append({
                "team_id": team_id,
                "team_name": team_name,
                "mentor_full_name": mentor_full_name,
                "match_type": match_type,
                "metadata": metadata
            })
    
    print(f"Recoverable teams: {recoverable}")
    print(f"Teams that cannot be recovered: {len(teams_without_mentor_meta) - recoverable}")
    print()
    
    if not updates_to_make:
        print("✅ No teams to update!")
        return
    
    # 4. Show what would be updated
    print(f"Teams to update ({len(updates_to_make)}):")
    print("-" * 80)
    for i, update in enumerate(updates_to_make[:10], 1):
        print(f"\n{i}. Team: {update['team_name']}")
        print(f"   Mentor: {update['mentor_full_name']}")
        print(f"   Match Type: {update['match_type']}")
    
    if len(updates_to_make) > 10:
        print(f"\n... and {len(updates_to_make) - 10} more")
    
    print("\n" + "=" * 80)
    
    # 5. Execute if requested
    if execute:
        print("EXECUTING UPDATES...")
        print("-" * 80)
        
        successful = 0
        failed = 0
        
        for update in updates_to_make:
            try:
                team_id = update["team_id"]
                metadata = update["metadata"]
                mentor_name = update["mentor_full_name"]
                
                # Populate the metadata.ingestion.mentor field
                if "ingestion" not in metadata:
                    metadata["ingestion"] = {}
                
                metadata["ingestion"]["mentor"] = mentor_name
                
                # Update the team
                sb.table("teams").update({
                    "metadata": metadata
                }).eq("id", team_id).execute()
                
                successful += 1
                print(f"✓ Updated: {update['team_name']} → {mentor_name}")
                
            except Exception as e:
                failed += 1
                print(f"✗ Failed: {update['team_name']} - {str(e)}")
        
        print("\n" + "=" * 80)
        print(f"MIGRATION COMPLETE")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        
        if successful > 0:
            print("\nNext steps:")
            print("1. Mentors who login now will have auto-assignment triggered")
            print("2. Or use /api/assignments/auto-assign/{batch_id} to batch assign")
            print("3. Teams should appear on mentor portals")
    else:
        print("\n📋 DRY RUN - No changes made")
        print("To apply changes, run: python scripts/migrate_populate_mentor_metadata.py --execute")

if __name__ == "__main__":
    main()
