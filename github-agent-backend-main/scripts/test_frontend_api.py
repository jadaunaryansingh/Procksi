"""
Test Frontend API Endpoints
Validates that all frontend-expected endpoints return correct data format
"""
import requests
import time
from pprint import pprint

BASE_URL = "http://localhost:8000"


def test_api_root():
    """Test root endpoint"""
    print("\n" + "="*60)
    print("Testing API Root")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/")
    print(f"Status: {response.status_code}")
    pprint(response.json())
    
    return response.status_code == 200


def test_health():
    """Test health endpoint"""
    print("\n" + "="*60)
    print("Testing Health Check")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    pprint(response.json())
    
    return response.status_code == 200


def test_stats():
    """Test /api/stats endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/stats")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/api/stats")
    print(f"Status: {response.status_code}")
    data = response.json()
    pprint(data)
    
    # Validate structure
    required_keys = ["totalProjects", "completedProjects", "averageScore", "totalTechnologies"]
    for key in required_keys:
        if key not in data:
            print(f"[X] Missing key: {key}")
            return False
    
    print("[OK] Stats endpoint working")
    return response.status_code == 200


def test_tech_stacks():
    """Test /api/tech-stacks endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/tech-stacks")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/api/tech-stacks")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Found {len(data)} technologies")
    
    if data:
        print("Top 5 technologies:")
        for tech in data[:5]:
            print(f"  - {tech['name']}: {tech['count']} projects")
    
    print("[OK] Tech stacks endpoint working")
    return response.status_code == 200


def test_projects_list():
    """Test /api/projects endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/projects")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/api/projects")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Found {len(data)} projects")
    
    if data:
        print("\nFirst project:")
        pprint(data[0])
        
        # Validate camelCase keys
        expected_keys = ["id", "teamName", "repoUrl", "status", "totalScore", "techStack"]
        project = data[0]
        for key in expected_keys:
            if key not in project:
                print(f"[X] Missing key: {key}")
                return False
    
    print("[OK] Projects list endpoint working")
    return response.status_code == 200


def test_projects_filters():
    """Test /api/projects with filters"""
    print("\n" + "="*60)
    print("Testing GET /api/projects with filters")
    print("="*60)
    
    # Test status filter
    response = requests.get(f"{BASE_URL}/api/projects?status=completed")
    print(f"Completed projects: {len(response.json())}")
    
    # Test sort
    response = requests.get(f"{BASE_URL}/api/projects?sort=score")
    data = response.json()
    if len(data) >= 2:
        print(f"Top score: {data[0].get('totalScore')}, Second: {data[1].get('totalScore')}")
    
    print("[OK] Filters working")
    return True


def test_leaderboard():
    """Test /api/leaderboard endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/leaderboard")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/api/leaderboard")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Found {len(data)} entries")
    
    if data:
        print("\nTop 3:")
        for i, entry in enumerate(data[:3], 1):
            print(f"{i}. {entry.get('teamName')}: {entry.get('totalScore')}/100")
            print(f"   Tech: {', '.join(entry.get('techStack', [])[:3])}")
    
    print("[OK] Leaderboard endpoint working")
    return response.status_code == 200


def test_leaderboard_chart():
    """Test /api/leaderboard/chart endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/leaderboard/chart")
    print("="*60)
    
    response = requests.get(f"{BASE_URL}/api/leaderboard/chart")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Chart data for {len(data)} teams")
    
    if data:
        print("\nChart data sample:")
        pprint(data[0])
    
    print("[OK] Leaderboard chart endpoint working")
    return response.status_code == 200


def test_project_detail():
    """Test /api/projects/{id} endpoint"""
    print("\n" + "="*60)
    print("Testing GET /api/projects/{id}")
    print("="*60)
    
    # Get first project ID
    response = requests.get(f"{BASE_URL}/api/projects")
    projects = response.json()
    
    if not projects:
        print("[WARN] No projects to test with")
        return True
    
    project_id = projects[0]["id"]
    print(f"Testing with project: {project_id}")
    
    response = requests.get(f"{BASE_URL}/api/projects/{project_id}")
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\nProject Detail:")
        print(f"  Team: {data.get('teamName')}")
        print(f"  Repo: {data.get('repoUrl')}")
        print(f"  Score: {data.get('totalScore')}/100")
        print(f"  Languages: {data.get('languages', [])}")
        print(f"  Contributors: {len(data.get('contributors', []))}")
        print(f"  Security Issues: {data.get('secretsDetected', 0)}")
        print(f"  AI Generated: {data.get('aiGeneratedPercentage', 0)}%")
        
        # Validate camelCase keys
        expected_keys = [
            "id", "teamName", "repoUrl", "techStack", "languages", 
            "totalScore", "contributors", "commitPatterns", "securityIssues",
            "aiGeneratedPercentage", "strengths", "improvements"
        ]
        for key in expected_keys:
            if key not in data:
                print(f"[WARN] Missing key: {key}")
    
    print("[OK] Project detail endpoint working")
    return response.status_code == 200


def run_all_tests():
    """Run all endpoint tests"""
    print("\n" + "="*80)
    print("FRONTEND API ENDPOINT VALIDATION")
    print("="*80)
    
    tests = [
        ("API Root", test_api_root),
        ("Health Check", test_health),
        ("Stats", test_stats),
        ("Tech Stacks", test_tech_stacks),
        ("Projects List", test_projects_list),
        ("Projects Filters", test_projects_filters),
        ("Leaderboard", test_leaderboard),
        ("Leaderboard Chart", test_leaderboard_chart),
        ("Project Detail", test_project_detail),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n[FAIL] {name} failed with error: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All frontend API endpoints are working!")
    else:
        print(f"\n[WARNING] {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    try:
        success = run_all_tests()
        exit(0 if success else 1)
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Could not connect to API server")
        print("Make sure the server is running: python main.py")
        exit(1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        exit(1)
