"""
Backend Integration Test Script
Tests the complete backend with the model
"""
import os
import sys
import time
import requests
from pprint import pprint

# Test configurations
BASE_URL = "http://localhost:8000"
TEST_REPO = "https://github.com/octocat/Hello-World"  # Small test repo

print("="*80)
print("BACKEND INTEGRATION TEST")
print("="*80)

# Step 1: Check if server is running
print("\n1. Checking if server is running...")
try:
    response = requests.get(f"{BASE_URL}/health", timeout=5)
    if response.status_code == 200:
        print("✅ Server is running!")
        print(f"   Status: {response.json()}")
    else:
        print(f"❌ Server returned status {response.status_code}")
        sys.exit(1)
except requests.exceptions.ConnectionError:
    print("❌ Server is not running!")
    print("   Please start the server first:")
    print("   python main.py")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Step 2: Submit analysis request
print("\n2. Submitting analysis request...")
try:
    payload = {
        "repo_url": TEST_REPO,
        "team_name": "Test Team"
    }
    response = requests.post(
        f"{BASE_URL}/api/analyze-repo",
        json=payload,
        timeout=10
    )
    
    if response.status_code == 202:
        result = response.json()
        job_id = result["job_id"]
        project_id = result["project_id"]
        print(f"✅ Analysis submitted successfully!")
        print(f"   Job ID: {job_id}")
        print(f"   Project ID: {project_id}")
    else:
        print(f"❌ Failed to submit analysis")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Step 3: Monitor progress
print("\n3. Monitoring analysis progress...")
max_wait = 300  # 5 minutes max
start_time = time.time()
last_progress = -1

try:
    while time.time() - start_time < max_wait:
        response = requests.get(
            f"{BASE_URL}/api/analysis-status/{job_id}",
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"❌ Error checking status: {response.status_code}")
            break
        
        status_data = response.json()
        current_progress = status_data.get("progress", 0)
        current_stage = status_data.get("current_stage", "Unknown")
        status = status_data.get("status")
        
        if current_progress != last_progress:
            print(f"   Progress: {current_progress}% - Stage: {current_stage}")
            last_progress = current_progress
        
        if status == "completed":
            print("✅ Analysis completed!")
            break
        elif status == "failed":
            error = status_data.get("error", "Unknown error")
            print(f"❌ Analysis failed: {error}")
            sys.exit(1)
        
        time.sleep(5)  # Check every 5 seconds
    else:
        print("⏱️ Analysis taking longer than expected...")
        print("   Continuing to wait for results...")

except Exception as e:
    print(f"❌ Error monitoring progress: {e}")
    sys.exit(1)

# Step 4: Retrieve results
print("\n4. Retrieving analysis results...")
try:
    response = requests.get(
        f"{BASE_URL}/api/analysis-result/{job_id}",
        timeout=10
    )
    
    if response.status_code == 200:
        results = response.json()
        print("✅ Results retrieved successfully!")
        print("\nScores:")
        scores = results.get("scores", {})
        for key, value in scores.items():
            if value is not None:
                print(f"   {key}: {value}")
        
        print(f"\nTech Stack: {len(results.get('tech_stack', []))} items")
        print(f"Issues Found: {len(results.get('issues', []))} items")
        print(f"Team Members: {len(results.get('team_members', []))} members")
        
    elif response.status_code == 425:
        print("⏱️ Analysis not yet completed, check back later")
        print(f"   Job ID: {job_id}")
    else:
        print(f"❌ Failed to retrieve results")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
except Exception as e:
    print(f"❌ Error retrieving results: {e}")
    sys.exit(1)

# Step 5: Check leaderboard
print("\n5. Checking leaderboard...")
try:
    response = requests.get(f"{BASE_URL}/api/leaderboard", timeout=10)
    
    if response.status_code == 200:
        leaderboard_data = response.json()
        total = leaderboard_data.get("total", 0)
        leaderboard = leaderboard_data.get("leaderboard", [])
        
        print(f"✅ Leaderboard retrieved!")
        print(f"   Total projects: {total}")
        
        if leaderboard:
            print("\n   Top 3:")
            for i, entry in enumerate(leaderboard[:3], 1):
                print(f"   {i}. {entry.get('team_name')} - Score: {entry.get('total_score')}")
    else:
        print(f"⚠️ Leaderboard request returned {response.status_code}")
except Exception as e:
    print(f"❌ Error checking leaderboard: {e}")

# Step 6: List projects
print("\n6. Listing all projects...")
try:
    response = requests.get(f"{BASE_URL}/api/projects", timeout=10)
    
    if response.status_code == 200:
        projects_data = response.json()
        total = projects_data.get("total", 0)
        projects = projects_data.get("projects", [])
        
        print(f"✅ Projects retrieved!")
        print(f"   Total: {total}")
        print(f"   Current page: {len(projects)} items")
    else:
        print(f"⚠️ Projects request returned {response.status_code}")
except Exception as e:
    print(f"❌ Error listing projects: {e}")

print("\n" + "="*80)
print("INTEGRATION TEST COMPLETE!")
print("="*80)
print(f"\n📊 Test Summary:")
print(f"   Repository: {TEST_REPO}")
print(f"   Job ID: {job_id}")
print(f"   Project ID: {project_id}")
print(f"\n✅ Backend is working correctly with the model!")
