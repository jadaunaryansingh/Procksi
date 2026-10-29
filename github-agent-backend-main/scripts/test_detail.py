import requests
import json

# Get first project
r = requests.get('http://localhost:8000/api/projects')
projects = r.json()

if projects:
    project_id = projects[0]['id']
    print(f"Testing project: {projects[0]['teamName']}\n")
    
    # Get detailed view
    r = requests.get(f'http://localhost:8000/api/projects/{project_id}')
    detail = r.json()
    
    print("=" * 80)
    print(f"Team: {detail['teamName']}")
    print(f"Repo: {detail['repoUrl']}")
    print(f"Score: {detail['totalScore']}/100")
    print(f"Status: {detail['status']}")
    print()
    
    print(f"Tech Stack: {', '.join(detail['techStack'][:5])}")
    print(f"Languages: {len(detail['languages'])} detected")
    for lang in detail['languages'][:3]:
        print(f"  - {lang['name']}: {lang['percentage']}%")
    print()
    
    print(f"Contributors: {len(detail['contributors'])}")
    for contrib in detail['contributors']:
        print(f"  - {contrib['name']}: {contrib['commits']} commits ({contrib['percentage']}%)")
    print()
    
    print(f"Security Issues: {detail['secretsDetected']}")
    print(f"AI Generated: {detail['aiGeneratedPercentage']}%")
    print(f"Total Files: {detail['totalFiles']}")
    print(f"Lines of Code: {detail['totalLinesOfCode']}")
    print()
    
    print(f"Strengths ({len(detail['strengths'])}):")
    for s in detail['strengths'][:3]:
        print(f"  - {s}")
    print()
    
    print(f"Improvements ({len(detail['improvements'])}):")
    for i in detail['improvements'][:3]:
        print(f"  - {i}")
    
    print("=" * 80)
    print("\n✅ All frontend format fields present!")
    
else:
    print("No projects found")
