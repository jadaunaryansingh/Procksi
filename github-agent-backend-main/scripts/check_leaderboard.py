import requests

r = requests.get('http://localhost:8000/api/leaderboard')
data = r.json()

print(f'Total projects: {data["total"]}')
print('\nLeaderboard:')
for i, p in enumerate(data['leaderboard'][:5], 1):
    print(f'{i}. {p["team_name"]} - Score: {p["total_score"]}')
