import asyncio
from src.api.backend.database import get_supabase_admin_client

async def main():
    supabase = get_supabase_admin_client()
    
    # 1. Find the batch ID for "aiml 6th sem" (case-insensitive)
    batch_response = supabase.table("batches").select("id, name").ilike("name", "%aiml 6th sem%").execute()
    
    if not batch_response.data:
         print("Batch 'aiml 6th sem' not found.")
         return
         
    batch_id = batch_response.data[0]["id"]
    batch_name = batch_response.data[0]["name"]
    print(f"Found batch: {batch_name} (ID: {batch_id})")
    
    # 2. Get all teams in this batch
    teams_response = supabase.table("teams").select("id, team_name").eq("batch_id", str(batch_id)).execute()
    teams = teams_response.data or []
    
    if not teams:
        print(f"No teams found in batch {batch_name}.")
        return
        
    print(f"Total teams in batch: {len(teams)}")
    
    # 3. For each team, check if they have students
    teams_without_students = []
    
    for team in teams:
        students_response = supabase.table("students").select("id").eq("team_id", team["id"]).execute()
        students = students_response.data or []
        
        if len(students) == 0:
            teams_without_students.append(team["team_name"])
            
    # 4. Print results
    print("-" * 30)
    print(f"Teams without students ({len(teams_without_students)} out of {len(teams)}):")
    if not teams_without_students:
        print("None! All teams have at least one student.")
    else:
        for name in sorted(teams_without_students):
            print(f"- {name}")

if __name__ == "__main__":
    asyncio.run(main())
