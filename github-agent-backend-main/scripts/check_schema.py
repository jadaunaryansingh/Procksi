import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def main():
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(env_path)

    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_SERVICE_KEY")

    try:
        supabase: Client = create_client(url, key)
        print("Checking database schema for 'students' table...")
        
        # Try to select just one record with all columns * wildcard
        # This doesn't list columns directly but we can inspect keys if it works
        # or if we get an error on specific column selection
        
        try:
            print("Attempting to select 'grading_details'...")
            supabase.table("students").select("grading_details").limit(1).execute()
            print("SUCCESS: 'grading_details' column EXISTS.")
        except Exception as e:
            print(f"FAILURE: 'grading_details' column DOES NOT EXIST or is inaccessible.")
            print(f"Error details: {e}")

        # List keys from a valid row
        print("\nListing available columns from a sample row (select *):")
        response = supabase.table("students").select("*").limit(1).execute()
        if response.data:
            print("Columns found:", list(response.data[0].keys()))
        else:
            print("Table is empty, cannot verify columns using select *")

    except Exception as e:
        print(f"Top level error: {e}")

if __name__ == "__main__":
    main()
