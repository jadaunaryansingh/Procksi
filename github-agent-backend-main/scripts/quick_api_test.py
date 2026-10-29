import requests

r = requests.get('http://localhost:8000/api/projects')
print(f'Status: {r.status_code}')

data = r.json()
print(f'Projects: {len(data)}')

for p in data[:3]:
    print(f'  - {p.get("teamName")}: {p.get("totalScore")}')
