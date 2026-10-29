
import os
import sys
from uuid import uuid4
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

# Repo that failed
REPO_URL = "https://github.com/Preshit22/chatbot"

def reproduce():
    from src.api.backend.services.analyzer_service import AnalyzerService
    from src.api.backend.crud import ProjectCRUD, AnalysisJobCRUD
    
    print(f"🚀 Reproducing failure for {REPO_URL}...")
    
    # Create dummy project/job to avoid messing with real data if possible,
    # or just use a new UUID.
    project_id = uuid4()
    job_id = uuid4()
    
    print(f"Generated Project ID: {project_id}")
    print(f"Generated Job ID: {job_id}")
    
    # We need to create the project in DB first usually?
    # AnalyzerService.analyze_repository expects project to exist?
    # backend.py: ProjectCRUD.create_project is called BEFORE AnalyzerService.
    
    try:
        print("Checking for existing project...")
        p = ProjectCRUD.get_project_by_url(REPO_URL)
        if not p:
            print("Creating test project...")
            ProjectCRUD.create_project(repo_url=REPO_URL, team_name="Reproduction Team")
            p = ProjectCRUD.get_project_by_url(REPO_URL)
        
        real_project_id = p['id']
        print(f"Using Project ID: {real_project_id}")
        
        # Create job
        print("Creating analysis job...")
        job = AnalysisJobCRUD.create_job(real_project_id)
        real_job_id = job['id']
        
        print("Running analysis...")
        AnalyzerService.analyze_repository(
            team_id=real_project_id,  # Changed from project_id to team_id
            job_id=real_job_id,
            repo_url=REPO_URL,
            team_name="Reproduction Team"
        )
        print("✅ Analysis finished successfully (Unexpected!)")
        
    except Exception as e:
        print(f"\n❌ Captured Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    reproduce()
