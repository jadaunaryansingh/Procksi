"""
Test KrishiVaani Repository Analysis
"""
import requests
import time
import json

BASE_URL = "http://localhost:8000"
REPO_URL = "https://github.com/parv18050212/KrishiVaani"

print("="*80)
print("TESTING KRISHIVAANI REPOSITORY")
print("="*80)
print()

# Submit analysis
print(f"📤 Submitting: {REPO_URL}")
payload = {
    "repo_url": REPO_URL,
    "team_name": "KrishiVaani Team"
}

response = requests.post(f"{BASE_URL}/api/analyze-repo", json=payload)

if response.status_code != 202:
    print(f"❌ Failed to submit: {response.status_code}")
    print(response.text)
    exit(1)

data = response.json()
job_id = data["job_id"]
project_id = data["project_id"]

print(f"✅ Submitted!")
print(f"   Job ID: {job_id}")
print(f"   Project ID: {project_id}")
print()

# Monitor progress
print("📊 Monitoring Analysis Progress...")
print("-" * 80)

last_stage = None
start_time = time.time()

while True:
    time.sleep(3)
    
    status_resp = requests.get(f"{BASE_URL}/api/analysis-status/{job_id}")
    if status_resp.status_code != 200:
        print(f"❌ Error checking status: {status_resp.status_code}")
        break
    
    status_data = status_resp.json()
    status = status_data['status']
    progress = status_data.get('progress', 0)
    stage = status_data.get('current_stage', 'N/A')
    
    if stage != last_stage:
        elapsed = int(time.time() - start_time)
        print(f"[{elapsed}s] Progress: {progress}% | Stage: {stage}")
        last_stage = stage
    
    if status == 'completed':
        print()
        print("✅ Analysis Completed Successfully!")
        break
    elif status == 'failed':
        error = status_data.get('error', 'Unknown error')
        print()
        print(f"❌ Analysis Failed: {error}")
        exit(1)
    
    # Safety timeout (5 minutes)
    if time.time() - start_time > 300:
        print()
        print("⏱️ Analysis taking longer than expected...")
        break

print()
print("="*80)
print("RETRIEVING RESULTS")
print("="*80)
print()

# Get results
result_resp = requests.get(f"{BASE_URL}/api/analysis-result/{job_id}")

if result_resp.status_code == 200:
    results = result_resp.json()
    
    print("📊 SCORES:")
    print("-" * 80)
    scores = results.get("scores", {})
    print(f"  Total Score:          {scores.get('total_score', 0):.2f} / 100")
    print(f"  Originality:          {scores.get('originality_score', 0):.2f}")
    print(f"  Quality:              {scores.get('quality_score', 0):.2f}")
    print(f"  Security:             {scores.get('security_score', 0):.2f}")
    print(f"  Effort:               {scores.get('effort_score', 0):.2f}")
    print(f"  Implementation:       {scores.get('implementation_score', 0):.2f}")
    print(f"  Engineering:          {scores.get('engineering_score', 0):.2f}")
    print(f"  Organization:         {scores.get('organization_score', 0):.2f}")
    print(f"  Documentation:        {scores.get('documentation_score', 0):.2f}")
    print()
    
    print(f"🏆 VERDICT: {results.get('verdict', 'N/A')}")
    print(f"👥 Total Commits: {results.get('total_commits', 0)}")
    print()
    
    tech_stack = results.get('tech_stack', [])
    print(f"🛠️  TECH STACK ({len(tech_stack)} items):")
    print("-" * 80)
    for tech in tech_stack[:10]:
        print(f"  • {tech['technology']:30s} ({tech.get('category', 'N/A')})")
    if len(tech_stack) > 10:
        print(f"  ... and {len(tech_stack) - 10} more")
    print()
    
    issues = results.get('issues', [])
    print(f"⚠️  ISSUES DETECTED ({len(issues)} total):")
    print("-" * 80)
    if issues:
        for issue in issues[:5]:
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(issue.get('severity', 'low'), "⚪")
            print(f"  {severity_emoji} [{issue['type'].upper()}] {issue['description']}")
            if issue.get('file_path'):
                print(f"     File: {issue['file_path']}")
        if len(issues) > 5:
            print(f"  ... and {len(issues) - 5} more issues")
    else:
        print("  ✅ No critical issues detected")
    print()
    
    team_members = results.get('team_members', [])
    print(f"👥 TEAM MEMBERS ({len(team_members)} contributors):")
    print("-" * 80)
    for member in team_members:
        contrib = member.get('contribution_pct', 0)
        bar = "█" * int(contrib / 5)
        print(f"  {member['name']:30s} {member['commits']:3d} commits ({contrib:5.1f}%) {bar}")
    print()
    
    print("="*80)
    print("✅ ANALYSIS COMPLETE!")
    print("="*80)
    print(f"View full results at: {BASE_URL}/api/analysis-result/{job_id}")
    print(f"Project ID: {project_id}")
    
elif result_resp.status_code == 425:
    print("⏱️ Results not ready yet. Job is still processing.")
    print(f"Check back at: {BASE_URL}/api/analysis-result/{job_id}")
else:
    print(f"❌ Failed to retrieve results: {result_resp.status_code}")
    print(result_resp.text)
