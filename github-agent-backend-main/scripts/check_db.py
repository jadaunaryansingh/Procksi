from backend.database import get_supabase_client

sb = get_supabase_client()
result = sb.table('projects').select('*').execute()
print(f'Found {len(result.data)} projects')

for p in result.data:
    print(f"  - {p.get('team_name')}: {p.get('total_score')}")
