#!/usr/bin/env python3
"""Check projects table schema"""
import json
from src.api.backend.database import get_supabase

sb = get_supabase()
result = sb.table('projects').select('*').limit(1).execute()

print('Projects table columns:')
if result.data:
    columns = list(result.data[0].keys())
    print(json.dumps(columns, indent=2))
    print('\nSample row:')
    print(json.dumps(result.data[0], indent=2, default=str))
