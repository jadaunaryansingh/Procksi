def main():
    print("=" * 60)
    print("MANUAL MIGRATION REQUIRED")
    print("=" * 60)
    print("Due to security restrictions, this script cannot directly modify the database schema.")
    print("Please execute the following SQL in your Supabase Dashboard SQL Editor:")
    print("-" * 60)
    print("""
    -- Add grading_details column to students table
    ALTER TABLE students ADD COLUMN IF NOT EXISTS grading_details JSONB DEFAULT '{}'::jsonb;
    """)
    print("-" * 60)
    print("1. Go to Supabase Dashboard > SQL Editor")
    print("2. Paste the SQL above")
    print("3. Click Run")
    print("=" * 60)

if __name__ == "__main__":
    main()
