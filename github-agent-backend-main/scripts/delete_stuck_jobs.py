"""
Delete Stuck Analysis Jobs
Removes all analysis jobs that are stuck in 'queued' status without celery_task_id
Also resets team status back to 'pending'
"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

def get_supabase_admin_client() -> Client:
    """Get Supabase admin client"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    
    return create_client(url, key)


def delete_stuck_jobs():
    """Delete all stuck jobs and reset team status"""
    supabase = get_supabase_admin_client()
    
    print("🔍 Finding stuck jobs...")
    
    # Find jobs queued > 5 minutes ago
    five_min_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    
    stuck_jobs = supabase.table('analysis_jobs')\
        .select('id, team_id, status, started_at, metadata')\
        .eq('status', 'queued')\
        .lt('started_at', five_min_ago)\
        .execute()
    
    # Filter by missing celery_task_id
    truly_stuck = []
    team_ids_to_reset = set()
    
    for job in (stuck_jobs.data or []):
        metadata = job.get('metadata', {})
        if not metadata.get('celery_task_id'):
            truly_stuck.append(job['id'])
            team_ids_to_reset.add(job['team_id'])
    
    print(f"📊 Found {len(truly_stuck)} stuck jobs affecting {len(team_ids_to_reset)} teams")
    
    if not truly_stuck:
        print("✅ No stuck jobs found!")
        return
    
    # Confirm deletion
    print(f"\n⚠️  This will DELETE {len(truly_stuck)} stuck jobs from the database")
    print(f"⚠️  And reset {len(team_ids_to_reset)} teams to 'pending' status")
    
    confirm = input("\nType 'DELETE' to confirm: ")
    
    if confirm != "DELETE":
        print("❌ Deletion cancelled")
        return
    
    print("\n🗑️  Deleting stuck jobs...")
    
    # Delete jobs in batches of 100
    batch_size = 100
    deleted_count = 0
    
    for i in range(0, len(truly_stuck), batch_size):
        batch = truly_stuck[i:i + batch_size]
        
        try:
            supabase.table('analysis_jobs').delete().in_('id', batch).execute()
            deleted_count += len(batch)
            print(f"   Deleted {deleted_count}/{len(truly_stuck)} jobs...")
        except Exception as e:
            print(f"❌ Error deleting batch: {e}")
    
    print(f"✅ Deleted {deleted_count} stuck jobs")
    
    # Reset team status
    print(f"\n🔄 Resetting {len(team_ids_to_reset)} teams to 'pending' status...")
    
    reset_count = 0
    team_ids_list = list(team_ids_to_reset)
    
    for i in range(0, len(team_ids_list), batch_size):
        batch = team_ids_list[i:i + batch_size]
        
        try:
            supabase.table('teams').update({
                'status': 'pending'
            }).in_('id', batch).execute()
            
            reset_count += len(batch)
            print(f"   Reset {reset_count}/{len(team_ids_to_reset)} teams...")
        except Exception as e:
            print(f"❌ Error resetting teams: {e}")
    
    print(f"✅ Reset {reset_count} teams to 'pending' status")
    
    print("\n✨ Cleanup complete!")
    print(f"   - Deleted: {deleted_count} stuck jobs")
    print(f"   - Reset: {reset_count} teams")
    print("\nYou can now trigger fresh analysis for these teams.")


if __name__ == "__main__":
    try:
        delete_stuck_jobs()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
