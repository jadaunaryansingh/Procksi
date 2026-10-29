
import os
from dotenv import load_dotenv

def check_env():
    load_dotenv(r"d:\Coding\Github-Agent\proj-github agent\.env")
    
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if key:
        print(f"SUPABASE_SERVICE_KEY is SET (Length: {len(key)})")
    else:
        print("SUPABASE_SERVICE_KEY is MISSING in .env")

    url = os.getenv("SUPABASE_URL")
    if url:
        print(f"SUPABASE_URL is SET")
    else:
        print("SUPABASE_URL is MISSING")

if __name__ == "__main__":
    check_env()
