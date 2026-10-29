#!/usr/bin/env python3
"""Debug script to check mentor team assignments"""
import json
from src.api.backend.database import get_supabase_admin_client

sb = get_supabase_admin_client()

print("=" * 70)
print("DEBUGGING MENTOR TEAM ASSIGNMENTS")
print("=" * 70)

# Get all teams with mentors
print("\n1. Teams with mentor assignments:")
teams = sb.table('teams').select('id, team_name, mentor_id, batch_id').not_.is_('mentor_id', 'null').execute()
print(f"   Found {len(teams.data)} teams with mentors assigned:")
for team in teams.data:
    print(f"   - {team['team_name']}")
    print(f"     Team ID: {team['id']}")
    print(f"     Mentor ID: {team['mentor_id']}")
    print(f"     Batch ID: {team['batch_id']}")
    print()

# Get mentor users
print("\n2. Mentor users in system:")
mentors = sb.table('users').select('id, email, full_name, role').eq('role', 'mentor').execute()
for m in mentors.data:
    email = m.get('email', 'N/A')
    user_id = m.get('id', 'N/A')
    full_name = m.get('full_name', 'N/A')
    print(f"   {email} ({full_name})")
    print(f"   ID: {user_id}")
    
    # Count teams for this mentor
    mentor_teams = [t for t in teams.data if t['mentor_id'] == user_id]
    print(f"   Assigned teams: {len(mentor_teams)}")
    if mentor_teams:
        for t in mentor_teams:
            print(f"     - {t['team_name']}")
    print()

# Test the query that the API endpoint uses
print("\n3. Testing API query for paragagarwal8131@gmail.com:")
mentor_id = '78b61cf6-042f-4a1f-af25-d9ae75ce622e'

try:
    # Simple query first
    simple_result = sb.table('teams').select('*').eq('mentor_id', mentor_id).execute()
    print(f"   Simple query: Found {len(simple_result.data)} teams")
    
    # Complex query with joins (like the API uses)
    complex_query = '''
    *,
    batches(id, name, semester, year),
    students(count),
    projects(id, total_score, last_analyzed_at, status)
    '''
    complex_result = sb.table('teams').select(complex_query).eq('mentor_id', mentor_id).execute()
    print(f"   Complex query (with joins): Found {len(complex_result.data)} teams")
    
    if complex_result.data:
        print("\n   Full API response:")
        print(json.dumps(complex_result.data, indent=2, default=str))
    
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 70)
