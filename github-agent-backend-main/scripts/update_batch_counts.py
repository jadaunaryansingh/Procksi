"""
Update student_count and team_count in batches table
"""
from src.api.backend.database import get_supabase_admin_client
from dotenv import load_dotenv

load_dotenv()

def update_batch_counts():
    supabase = get_supabase_admin_client()
    
    # Get all batches
    batches = supabase.table('batches').select('id, name').execute().data
    
    print("Updating batch counts...\n")
    
    for batch in batches:
        batch_id = batch['id']
        batch_name = batch['name']
        
        # Count teams in this batch
        teams_result = supabase.table('teams').select('id', count='exact').eq('batch_id', batch_id).execute()
        team_count = teams_result.count if teams_result.count else 0
        
        # Get all team IDs in this batch
        teams = supabase.table('teams').select('id, project_id').eq('batch_id', batch_id).execute().data
        
        # Count students across all teams in this batch
        student_count = 0
        project_ids = [t['project_id'] for t in teams if t.get('project_id')]
        
        if project_ids:
            # Count team members for all projects in this batch
            members_result = supabase.table('team_members').select('id', count='exact').in_('project_id', project_ids).execute()
            student_count = members_result.count if members_result.count else 0
        
        print(f"Batch: {batch_name}")
        print(f"  Teams: {team_count}")
        print(f"  Students: {student_count}")
        
        # Update the batch record
        supabase.table('batches').update({
            'team_count': team_count,
            'student_count': student_count
        }).eq('id', batch_id).execute()
        
        print(f"  ✓ Updated!\n")
    
    print("All batches updated successfully!")

if __name__ == "__main__":
    update_batch_counts()
