import re
from app.main import service_client

def resolve_all_proposals(apply_changes=False):
    props = service_client.table('proposals').select('*').execute().data or []
    teams = service_client.table('teams_validation').select('*').execute().data or []
    prefs = service_client.table('student_preferences').select('*').execute().data or []
    joins = service_client.table('team_join_requests').select('*').execute().data or []
    locks = service_client.table('project_locked_ps').select('*').execute().data or []

    print(f"Total proposals in database: {len(props)}")
    print(f"Total teams in database: {len(teams)}")

    updates = []

    for p in props:
        p_id = p['id']
        p_title = p.get('title') or ''
        p_file = p.get('proposalFile') or ''
        p_team_id = p.get('teamId') or ''
        
        # Extract auth UUID from proposalFile URL if available
        auth_uuid_match = re.search(r'proposals/([0-9a-fA-F-]{36})/', p_file)
        auth_uuid = auth_uuid_match.group(1) if auth_uuid_match else None
        
        found_team_id = None
        reason = None
        
        # Strategy 1: Match student_preferences by auth_uuid
        if auth_uuid:
            matched_pref = [pr for pr in prefs if pr.get('student_id') == auth_uuid or pr.get('studentId') == auth_uuid]
            if matched_pref and matched_pref[0].get('team_id'):
                found_team_id = matched_pref[0].get('team_id')
                reason = f"matched student_preferences auth_uuid {auth_uuid}"
                
        # Strategy 2: Match team_join_requests by auth_uuid
        if not found_team_id and auth_uuid:
            matched_join = [j for j in joins if j.get('student_id') == auth_uuid or j.get('studentId') == auth_uuid]
            if matched_join and matched_join[0].get('team_id'):
                found_team_id = matched_join[0].get('team_id')
                reason = f"matched team_join_requests auth_uuid {auth_uuid}"
                
        # Strategy 3: Match teams_validation members by auth_uuid
        if not found_team_id and auth_uuid:
            matched_team = [t for t in teams if auth_uuid in str(t.get('members') or '') or auth_uuid in str(t)]
            if matched_team:
                found_team_id = matched_team[0]['id']
                reason = f"matched teams_validation members auth_uuid {auth_uuid}"

        # Strategy 4: Match project_locked_ps by title
        if not found_team_id and p_title:
            matched_lock = [l for l in locks if l.get('title', '').strip().lower() == p_title.strip().lower()]
            if matched_lock and matched_lock[0].get('team_id'):
                found_team_id = matched_lock[0].get('team_id')
                if found_team_id.startswith('LOCK-'):
                    found_team_id = found_team_id[5:]
                reason = f"matched project_locked_ps title '{p_title}'"

        # Strategy 5: Match teams_validation by title/description
        if not found_team_id and p_title:
            matched_tv = [
                t for t in teams
                if (t.get('title') or '').strip().lower() == p_title.strip().lower() or
                   (t.get('description') or '').strip().lower() == p_title.strip().lower()
            ]
            if matched_tv:
                found_team_id = matched_tv[0]['id']
                reason = f"matched teams_validation title '{p_title}'"


        if found_team_id and found_team_id != p_team_id:
            updates.append((p_id, p_team_id, found_team_id, p_title, reason))
            print(f"[RE-MAP] {p_id} | Title: '{p_title}' | Current teamId: {p_team_id} -> True teamId: {found_team_id} ({reason})")
            if apply_changes:
                try:
                    service_client.table('proposals').update({'teamId': found_team_id}).eq('id', p_id).execute()
                    print(f"  -> Successfully updated proposal {p_id} teamId in Supabase!")
                except Exception as err:
                    print(f"  -> Error updating proposal {p_id}: {err}")
        else:
            print(f"[VALID]  {p_id} | Title: '{p_title}' | teamId: {p_team_id} ({reason or 'current matches'})")

    return updates

if __name__ == "__main__":
    resolve_all_proposals(apply_changes=True)
