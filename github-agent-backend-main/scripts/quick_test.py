"""
Quick Backend Test - Submit and Check
"""
import requests
import time

BASE_URL = "http://localhost:8000"

print("Testing backend with model...")
print()

# Submit a small test repo
payload = {
    "repo_url": "https://github.com/octocat/Hello-World",
    "team_name": "Test Team"
}

print(f"1. Submitting: {payload['repo_url']}")
response = requests.post(f"{BASE_URL}/api/analyze-repo", json=payload)

if response.status_code == 202:
    data = response.json()
    job_id = data["job_id"]
    print(f"✅ Submitted! Job ID: {job_id}")
    print()
    
    # Check status a few times
    print("2. Monitoring progress...")
    for i in range(10):
        time.sleep(3)
        status_resp = requests.get(f"{BASE_URL}/api/analysis-status/{job_id}")
        if status_resp.status_code == 200:
            status_data = status_resp.json()
            print(f"   [{i+1}] Status: {status_data['status']}, Progress: {status_data.get('progress', 0)}%, Stage: {status_data.get('current_stage', 'N/A')}")
            
            if status_data['status'] == 'completed':
                print("\n✅ Analysis completed!")
                break
            elif status_data['status'] == 'failed':
                print(f"\n❌ Failed: {status_data.get('error', 'Unknown')}")
                break
    
    print()
    print(f"3. Job ID for reference: {job_id}")
    print(f"   Check results at: {BASE_URL}/api/analysis-result/{job_id}")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
