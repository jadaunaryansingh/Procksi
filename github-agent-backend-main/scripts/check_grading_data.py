import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add the parent directory to sys.path to ensure we can find modules if needed
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def main():
    # Load environment variables from .env file in the parent directory
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        
        print(f"Connecting to Supabase at {url}...")
        
        # Fetch all students with grading details
        response = supabase.table("students").select("id, name, mentor_grade, grading_details").execute()
        
        students = response.data
        print(f"\nFound {len(students)} students in the database.")
        print("-" * 60)
        print(f"{'Name':<30} | {'Legacy Grade':<15} | {'Grading Details'}")
        print("-" * 60)
        
        has_grading_details = False
        for student in students:
            grading_details = student.get('grading_details')
            mentor_grade = student.get('mentor_grade')
            
            # Convert None to string for printing
            grade_display = str(mentor_grade) if mentor_grade is not None else "None"
            details_display = str(grading_details) if grading_details else "Empty/None"
            
            if grading_details:
                has_grading_details = True
                
            print(f"{student.get('name', 'Unknown'):<30} | {grade_display:<15} | {details_display}")

        print("-" * 60)
        if has_grading_details:
            print("\nSUCCESS: Found students with data in the 'grading_details' column.")
        else:
            print("\nWARNING: No 'grading_details' data found for any student.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
