# Script to backfill project_statement in team metadata for all existing teams
# This script updates the metadata.ingestion.project_statement field for all teams where it is missing,
# setting it to the team_name. This ensures the leaderboard always has a project name.

import os
import supabase
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Please set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Fetch all teams
data = supabase.table("teams").select("id, team_name, metadata").execute()
print(f"Fetched {len(data.data)} teams from database.")
missing_count = 0
missing_teams = []

for team in data.data:
    metadata = team.get("metadata") or {}
    ingestion = metadata.get("ingestion") or {}
    project_statement = ingestion.get("project_statement")
    if not project_statement:
        # Set project_statement to team_name
        ingestion["project_statement"] = team["team_name"]
        metadata["ingestion"] = ingestion
        # Update the team record
        supabase.table("teams").update({"metadata": metadata}).eq("id", team["id"]).execute()
        print(f"Updated team {team['id']} with project_statement: {team['team_name']}")
        missing_count += 1
        missing_teams.append((team["id"], team["team_name"]))

print(f"Total teams missing project_statement: {missing_count}")
if missing_teams:
    print("Teams updated:")
    for tid, tname in missing_teams:
        print(f"- ID: {tid}, Name: {tname}")

print("Backfill complete.")
