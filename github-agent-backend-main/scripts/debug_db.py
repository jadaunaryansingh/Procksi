
import os
import sys
import time
from dotenv import load_dotenv

# Add src to path
# Assuming we are in project root or scripts/..
# If running from project root
sys.path.append(os.getcwd())

load_dotenv()

def get_failed_jobs_with_retry(retries=3):
    from src.api.backend.database import get_supabase_client
    
    for i in range(retries):
        try:
            supabase = get_supabase_client()
            print(f"Attempt {i+1} to connect to Supabase...")
            
            # Fetch last 5 failed jobs
            jobs = supabase.table("analysis_jobs") \
                .select("id, project_id, status, error_message, completed_at") \
                .eq("status", "failed") \
                .order("completed_at", desc=True) \
                .limit(5) \
                .execute()
                
            return jobs.data
        except Exception as e:
            print(f"Connection failed: {e}")
            time.sleep(2)
    return None

if __name__ == "__main__":
    try:
        print("Fetching failed jobs...")
        jobs = get_failed_jobs_with_retry()
        
        if jobs:
            print(f"Found {len(jobs)} failed jobs:")
            for job in jobs:
                print(f"ID: {job['id']}")
                print(f"Project: {job['project_id']}")
                print(f"Error: {job['error_message']}")
                print(f"Time: {job['completed_at']}")
                print("-" * 50)
        else:
            print("No failed jobs found or connection failed.")
            
    except Exception as e:
        print(f"Script error: {e}")
