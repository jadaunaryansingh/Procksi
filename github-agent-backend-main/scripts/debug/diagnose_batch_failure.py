
import os
import sys
from dotenv import load_dotenv
from pprint import pprint

# Add src to path
sys.path.append(os.getcwd())

load_dotenv()

# Check for API key first
print(f"OPENAI_API_KEY present: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")

try:
    from src.api.backend.crud import AnalysisJobCRUD, BatchCRUD
    from src.api.backend.database import get_supabase_client
    
    def inspect_failed_jobs():
        supabase = get_supabase_client()
        
        print("\n=== Failed Analysis Jobs (Last 5) ===")
        jobs = supabase.table("analysis_jobs") \
            .select("*") \
            .eq("status", "failed") \
            .order("completed_at", desc=True) \
            .limit(5) \
            .execute()
        
        if not jobs.data:
            print("No failed jobs found.")
            return

        for job in jobs.data:
            print(f"Job ID: {job['id']}")
            print(f"Project ID: {job['project_id']}")
            print(f"Status: {job.get('status')}")
            print(f"Error: {job.get('error_message')}")
            print(f"Timestamp: {job.get('completed_at')}")
            print("-" * 40)

    def inspect_batches():
        supabase = get_supabase_client()
        
        print("\n=== Recent Batches (Last 3) ===")
        batches = supabase.table("batches") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(3) \
            .execute()
            
        if not batches.data:
            print("No batches found.")
            return

        for batch in batches.data:
            print(f"Batch ID: {batch['id']}")
            print(f"Status: {batch['status']}")
            print(f"Stats: {batch['completed_repos']} completed, {batch['failed_repos']} failed")
            print(f"Error: {batch.get('error_message')}")
            print("-" * 40)

    if __name__ == "__main__":
        try:
            inspect_failed_jobs()
            inspect_batches()
        except Exception as e:
            print(f"Error running diagnostic logic: {e}")
            import traceback
            traceback.print_exc()
            
except ImportError as e:
    print(f"Import Error (check path): {e}")

