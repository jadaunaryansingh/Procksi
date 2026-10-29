#!/bin/bash
# Script to create indexes individually (supports CONCURRENTLY)
# This avoids transaction block issues with CREATE INDEX CONCURRENTLY
# Run with: bash migrations/create_indexes.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Creating database indexes...${NC}"
echo ""

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL environment variable not set${NC}"
    exit 1
fi

# Function to create index with error handling
create_index() {
    local index_name=$1
    local sql=$2
    
    echo -e "Creating ${YELLOW}${index_name}${NC}..."
    
    if psql "$DATABASE_URL" -c "$sql" 2>&1 | tee /tmp/index_output.txt; then
        if grep -q "already exists" /tmp/index_output.txt; then
            echo -e "  ${YELLOW}⚠️  Already exists (skipped)${NC}"
        else
            echo -e "  ${GREEN}✅ Created successfully${NC}"
        fi
    else
        echo -e "  ${RED}❌ Failed${NC}"
        echo "  Check error above for details"
    fi
    echo ""
}

echo "============================================================"
echo "TEAMS TABLE INDEXES"
echo "============================================================"

create_index "idx_teams_mentor_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_mentor_id ON teams(mentor_id) WHERE mentor_id IS NOT NULL;"

create_index "idx_teams_batch_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_batch_id ON teams(batch_id) WHERE batch_id IS NOT NULL;"

create_index "idx_teams_status" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_status ON teams(status);"

create_index "idx_teams_batch_status" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_batch_status ON teams(batch_id, status) WHERE batch_id IS NOT NULL;"

create_index "idx_teams_last_analyzed" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_last_analyzed ON teams(last_analyzed_at DESC NULLS LAST);"

create_index "idx_teams_created_at" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_created_at ON teams(created_at DESC);"

echo "============================================================"
echo "ANALYSIS_JOBS TABLE INDEXES"
echo "============================================================"

create_index "idx_analysis_jobs_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_team_id ON analysis_jobs(team_id);"

create_index "idx_analysis_jobs_status" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);"

create_index "idx_analysis_jobs_team_status" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_team_status ON analysis_jobs(team_id, status);"

create_index "idx_analysis_jobs_started_at" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_started_at ON analysis_jobs(started_at DESC);"

echo "============================================================"
echo "RELATED TABLES INDEXES"
echo "============================================================"

create_index "idx_tech_stack_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tech_stack_team_id ON tech_stack(team_id);"

create_index "idx_issues_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_team_id ON issues(team_id);"

create_index "idx_issues_severity" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_severity ON issues(severity);"

create_index "idx_issues_type" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_type ON issues(type);"

create_index "idx_team_members_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_members_team_id ON team_members(team_id);"

create_index "idx_students_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_team_id ON students(team_id);"

create_index "idx_students_email" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_email ON students(email);"

create_index "idx_mentor_assignments_mentor_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mentor_assignments_mentor_id ON mentor_team_assignments(mentor_id);"

create_index "idx_mentor_assignments_team_id" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mentor_assignments_team_id ON mentor_team_assignments(team_id);"

create_index "idx_batches_status" \
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_batches_status ON batches(status);"

echo "============================================================"
echo "VERIFYING INDEXES"
echo "============================================================"

psql "$DATABASE_URL" -c "
SELECT 
    tablename,
    indexname
FROM pg_indexes 
WHERE schemaname = 'public' 
    AND tablename IN ('teams', 'analysis_jobs', 'tech_stack', 'issues', 'team_members', 'students', 'mentor_team_assignments', 'batches')
ORDER BY tablename, indexname;
"

echo ""
echo -e "${GREEN}✅ Index creation complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Run ANALYZE on tables: psql \$DATABASE_URL -c 'ANALYZE;'"
echo "2. Test query performance with EXPLAIN ANALYZE"
echo "3. Monitor slow query log"
