from backend.crud import ProjectCRUD
from backend.database import get_supabase_client

sb = get_supabase_client()
projects, total = ProjectCRUD.list_projects(sb)

print(f"Total: {total}")
print(f"Projects: {len(projects)}")

for p in projects:
    print(f"  - {p.get('team_name')}: {p.get('total_score')}")
