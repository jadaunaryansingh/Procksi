"""
Test Script for Backend API
"""
import requests
import time
import json
from datetime import datetime


BASE_URL = "http://localhost:8000"


def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_health_check():
    """Test health check endpoint"""
    print_section("1. Testing Health Check")
    
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 200


def test_analyze_repo(repo_url, team_name=None):
    """Test repository analysis endpoint"""
    print_section("2. Testing Repository Analysis")
    
    payload = {
        "repo_url": repo_url,
        "team_name": team_name
    }
    
    print(f"Analyzing: {repo_url}")
    print(f"Team: {team_name}\n")
    
    response = requests.post(
        f"{BASE_URL}/api/analyze-repo",
        json=payload
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 202:
        result = response.json()
        print(f"Job ID: {result['job_id']}")
        print(f"Project ID: {result['project_id']}")
        print(f"Status: {result['status']}")
        return result
    else:
        print(f"Error: {response.json()}")
        return None


def test_analysis_status(job_id):
    """Test analysis status endpoint"""
    print_section("3. Polling Analysis Status")
    
    print(f"Job ID: {job_id}\n")
    
    max_attempts = 60  # Max 5 minutes (60 * 5 seconds)
    attempt = 0
    
    while attempt < max_attempts:
        response = requests.get(f"{BASE_URL}/api/analysis-status/{job_id}")
        
        if response.status_code == 200:
            status = response.json()
            progress = status['progress']
            current_status = status['status']
            stage = status.get('current_stage', 'N/A')
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Progress: {progress}% | Status: {current_status} | Stage: {stage}")
            
            if current_status in ['completed', 'failed']:
                print(f"\n✅ Analysis {current_status}!")
                return status
            
            time.sleep(5)  # Poll every 5 seconds
            attempt += 1
        else:
            print(f"Error: {response.status_code}")
            return None
    
    print("\n⏱️ Timeout: Analysis took too long")
    return None


def test_analysis_result(job_id):
    """Test analysis result endpoint"""
    print_section("4. Fetching Analysis Results")
    
    response = requests.get(f"{BASE_URL}/api/analysis-result/{job_id}")
    
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        result = response.json()
        
        print(f"Repository: {result['repo_url']}")
        print(f"Team: {result.get('team_name', 'N/A')}")
        print(f"Verdict: {result.get('verdict', 'N/A')}")
        print(f"\nScores:")
        scores = result['scores']
        for key, value in scores.items():
            if value is not None:
                print(f"  {key}: {value:.2f}")
        
        print(f"\nTech Stack: {len(result['tech_stack'])} technologies")
        print(f"Issues: {len(result['issues'])} found")
        print(f"Team Members: {len(result['team_members'])}")
        
        return result
    else:
        print(f"Error: {response.json()}")
        return None


def test_list_projects():
    """Test list projects endpoint"""
    print_section("5. Listing All Projects")
    
    response = requests.get(f"{BASE_URL}/api/projects?page=1&page_size=10")
    
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Total Projects: {result['total']}")
        print(f"Page: {result['page']} / {result['total_pages']}")
        print(f"\nProjects:")
        
        for project in result['projects']:
            print(f"  - {project['repo_url']} | Status: {project['status']} | Score: {project.get('total_score', 'N/A')}")
        
        return result
    else:
        print(f"Error: {response.json()}")
        return None


def test_leaderboard():
    """Test leaderboard endpoint"""
    print_section("6. Fetching Leaderboard")
    
    response = requests.get(
        f"{BASE_URL}/api/leaderboard?sort_by=total_score&order=desc&page=1&page_size=10"
    )
    
    print(f"Status Code: {response.status_code}\n")
    
    if response.status_code == 200:
        result = response.json()
        print(f"Total Completed Projects: {result['total']}")
        print(f"\nTop Projects:")
        
        for item in result['leaderboard']:
            print(f"  #{item['rank']} - {item.get('team_name', 'Unknown')} | Score: {item['total_score']:.2f} | {item['repo_url']}")
        
        return result
    else:
        print(f"Error: {response.json()}")
        return None


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  🧪 Backend API Test Suite")
    print("="*60)
    
    # Test 1: Health Check
    if not test_health_check():
        print("\n❌ Health check failed! Is the server running?")
        return
    
    # Test 2: Analyze a repository (use a small test repo)
    # CHANGE THIS TO A REAL GITHUB REPO URL
    test_repo = "https://github.com/your-username/test-repo"
    test_team = "Test Team"
    
    print(f"\n⚠️  Update test_repo URL in test_backend.py before running")
    print(f"Current test repo: {test_repo}")
    
    # Uncomment below to run full analysis test
    # analysis_job = test_analyze_repo(test_repo, test_team)
    # 
    # if analysis_job:
    #     job_id = analysis_job['job_id']
    #     
    #     # Test 3: Poll status
    #     final_status = test_analysis_status(job_id)
    #     
    #     if final_status and final_status['status'] == 'completed':
    #         # Test 4: Get results
    #         test_analysis_result(job_id)
    
    # Test 5: List projects
    test_list_projects()
    
    # Test 6: Leaderboard
    test_leaderboard()
    
    print_section("✅ Tests Complete")


if __name__ == "__main__":
    main()
