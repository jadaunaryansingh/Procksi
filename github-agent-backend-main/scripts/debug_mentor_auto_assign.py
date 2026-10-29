#!/usr/bin/env python3
"""
Debug script to investigate mentor auto-assignment issues
"""
import json
from uuid import UUID
from datetime import datetime
from src.api.backend.database import get_supabase_admin_client

sb = get_supabase_admin_client()

print("=" * 80)
print("MENTOR AUTO-ASSIGNMENT DEBUG")
print("=" * 80)

# 1. Get all mentor users
print("\n1. MENTOR USERS IN SYSTEM:")
print("-" * 80)
mentors_resp = sb.table("users").select(
    "id, email, full_name, role, is_mentor, created_at"
).or_("role.eq.mentor,is_mentor.eq.true").execute()

if mentors_resp.data:
    for mentor in mentors_resp.data:
        mentor_id = mentor.get("id")
        email = mentor.get("email")
        full_name = mentor.get("full_name")
        role = mentor.get("role")
        print(f"\n  [EMAIL] {email}")
        print(f"     ID: {mentor_id}")
        print(f"     Full Name: {full_name or '(NOT SET - Will require onboarding)'}")
        print(f"     Role: {role}")
else:
    print("  [ERROR] No mentor users found")

# 2. Get teams with unassigned mentors
print("\n\n2. TEAMS WITH UNASSIGNED MENTORS (mentor_id IS NULL):")
print("-" * 80)
unassigned_resp = sb.table("teams").select(
    "id, team_name, batch_id, metadata, created_at"
).is_("mentor_id", "null").limit(100).execute()

unassigned_count = len(unassigned_resp.data or [])
print(f"Found {unassigned_count} unassigned teams")

if unassigned_resp.data:
    for i, team in enumerate(unassigned_resp.data[:10], 1):  # Show first 10
        print(f"\n  Team {i}: {team.get('team_name')}")
        print(f"     Team ID: {team.get('id')}")
        metadata = team.get("metadata") or {}
        ingestion = metadata.get("ingestion") or {}
        
        mentor_name = ingestion.get("mentor")
        mentor_email = ingestion.get("mentor_email")
        suggested_mentor = metadata.get("suggested_mentor")
        
        print(f"     Metadata Mentor (ingestion.mentor): {mentor_name or '(not set)'}")
        print(f"     Metadata Email (ingestion.mentor_email): {mentor_email or '(not set)'}")
        print(f"     Suggested Mentor: {suggested_mentor or '(not set)'}")
    
    if unassigned_count > 10:
        print(f"\n  ... and {unassigned_count - 10} more unassigned teams")

# 3. Get teams with assigned mentors
print("\n\n3. TEAMS WITH ASSIGNED MENTORS (mentor_id IS NOT NULL):")
print("-" * 80)
assigned_resp = sb.table("teams").select(
    "id, team_name, mentor_id"
).not_.is_("mentor_id", "null").limit(100).execute()

assigned_count = len(assigned_resp.data or [])
print(f"Found {assigned_count} assigned teams")

if assigned_resp.data:
    for i, team in enumerate(assigned_resp.data[:10], 1):  # Show first 10
        mentor_id = team.get("mentor_id")
        mentor_info = sb.table("users").select("email, full_name").eq("id", mentor_id).single().execute()
        if mentor_info.data:
            mentor_email = mentor_info.data.get("email")
            mentor_name = mentor_info.data.get("full_name")
        else:
            mentor_email = "?"
            mentor_name = "?"
        
        print(f"  • {team.get('team_name')} → {mentor_name} ({mentor_email})")

# 4. Check mentor_team_assignments table
print("\n\n4. MENTOR-TEAM ASSIGNMENTS:")
print("-" * 80)
assignments_resp = sb.table("mentor_team_assignments").select(
    "mentor_id, team_id, assigned_at, assigned_by"
).limit(100).execute()

assignments_by_mentor = {}
if assignments_resp.data:
    for assignment in assignments_resp.data:
        mentor_id = assignment.get("mentor_id")
        if mentor_id not in assignments_by_mentor:
            assignments_by_mentor[mentor_id] = []
        assignments_by_mentor[mentor_id].append(assignment)
    
    for mentor_id, assignments in assignments_by_mentor.items():
        mentor_info = sb.table("users").select("email, full_name").eq("id", mentor_id).single().execute()
        if mentor_info.data:
            mentor_email = mentor_info.data.get("email")
            mentor_name = mentor_info.data.get("full_name")
        else:
            mentor_email = "?"
            mentor_name = "?"
        
        print(f"\n  {mentor_name} ({mentor_email}):")
        print(f"     Assigned {len(assignments)} team(s) via mentor_team_assignments")
        for i, assignment in enumerate(assignments[:5], 1):
            team_id = assignment.get("team_id")
            team_info = sb.table("teams").select("team_name").eq("id", team_id).single().execute()
            team_name = team_info.data.get("team_name") if team_info.data else "?"
            print(f"       {i}. {team_name} (assigned: {assignment.get('assigned_at')})")
        if len(assignments) > 5:
            print(f"       ... and {len(assignments) - 5} more")
else:
    print("  [ERROR] No assignments found in mentor_team_assignments table")

# 5. Matching analysis - which teams should be assigned to which mentors?
print("\n\n5. NAME MATCHING ANALYSIS:")
print("-" * 80)
if mentors_resp.data:
    for mentor in mentors_resp.data:
        if not mentor.get("full_name"):
            print(f"\n  [WARN] {mentor.get('email')}: No full_name set - cannot match teams")
            continue
        
        mentor_id = mentor.get("id")
        mentor_name = mentor.get("full_name")
        mentor_email = mentor.get("email")
        
        # Find potential matches
        matches = []
        for team in (unassigned_resp.data or []):
            metadata = team.get("metadata") or {}
            ingestion = metadata.get("ingestion") or {}
            
            team_mentor_name = (ingestion.get("mentor") or "").strip().lower()
            team_mentor_email = (ingestion.get("mentor_email") or "").strip().lower()
            team_suggested = (metadata.get("suggested_mentor") or "").strip().lower()
            
            if (team_mentor_name and team_mentor_name == mentor_name.lower()) or \
               (team_mentor_email and team_mentor_email == mentor_email.lower()) or \
               (team_suggested and (team_suggested == mentor_name.lower() or team_suggested == mentor_email.lower())):
                matches.append({
                    "team_name": team.get("team_name"),
                    "team_id": team.get("id"),
                    "match_type": "name" if team_mentor_name else "email" if team_mentor_email else "suggested"
                })
        
        if matches:
            print(f"\n  [OK] {mentor_name} ({mentor_email})")
            print(f"     Should be assigned {len(matches)} team(s):")
            for match in matches:
                print(f"       • {match['team_name']} (match_type: {match['match_type']})")
        else:
            print(f"\n  [NONE] {mentor_name} ({mentor_email})")
            print(f"     No matching unassigned teams found")

print("\n" + "=" * 80)
print("END DEBUG REPORT")
print("=" * 80)
