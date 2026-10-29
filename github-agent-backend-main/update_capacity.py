import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')
client = create_client(url, key)

# Update existing users max_teams from 5 to 15
result = client.table('users').update({'max_teams': 15}).eq('max_teams', 5).execute()
print(f'Updated {len(result.data)} users from max_teams=5 to 15')

# Also update any with NULL
result2 = client.table('users').update({'max_teams': 15}).is_('max_teams', 'null').execute()
print(f'Updated {len(result2.data)} users from max_teams=NULL to 15')

print('Done! Mentor capacity updated to 15.')
