import os
import sys
from dotenv import load_dotenv

# Add parent directory to path so we can import src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.api.backend.database import get_supabase_admin_client
from supabase import create_client, Client

load_dotenv()

def run_migration():
    print("Running migration...")
    
    # We need to execute raw SQL. Supabase data API doesn't support executing arbitrary SQL easily
    # without an RPC function, or using Postgres direct connection.
    # Let's try to see if there's a postgres proxy or use psycopg2 if available.
    
    import psycopg2
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in environment!")
        return
        
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        with open("migrations/create_celery_beat_overrides.sql", "r") as f:
            sql = f.read()
            
        cur.execute(sql)
        print("Migration executed successfully!")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error executing migration: {e}")

if __name__ == "__main__":
    run_migration()
