
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def check_batches():
    from src.api.backend.database import get_supabase_client
    supabase = get_supabase_client()
    
    print("\n=== Recent Batches (Last 3) ===")
    batches = supabase.table("batches") \
        .select("*") \
        .order("created_at", desc=True) \
        .limit(3) \
        .execute()
        
    for batch in batches.data:
        print(f"Batch ID: {batch['id']}")
        print(f"Created: {batch['created_at']}")
        print(f"Status: {batch['status']}")
        print(f"Stats: {batch['completed_repos']}/{batch['total_repos']} (Failed: {batch['failed_repos']})")
        print(f"Error: {batch.get('error_message')}")
        print("-" * 40)

if __name__ == "__main__":
    try:
        check_batches()
    except Exception as e:
        print(f"Error: {e}")
