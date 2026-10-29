# PowerShell script to create indexes individually
# Run with: powershell -ExecutionPolicy Bypass -File migrations/create_indexes.ps1

$ErrorActionPreference = "Stop"

Write-Host "Creating database indexes..." -ForegroundColor Yellow
Write-Host ""

# Check if DATABASE_URL is set
if (-not $env:DATABASE_URL) {
    Write-Host "ERROR: DATABASE_URL environment variable not set" -ForegroundColor Red
    exit 1
}

# Function to create index
function Create-Index {
    param(
        [string]$IndexName,
        [string]$Sql
    )
    
    Write-Host "Creating $IndexName..." -ForegroundColor Yellow
    
    try {
        $output = psql $env:DATABASE_URL -c $Sql 2>&1
        
        if ($output -match "already exists") {
            Write-Host "  ⚠️  Already exists (skipped)" -ForegroundColor Yellow
        }
        elseif ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Created successfully" -ForegroundColor Green
        }
        else {
            Write-Host "  ❌ Failed: $output" -ForegroundColor Red
        }
    }
    catch {
        Write-Host "  ❌ Failed: $_" -ForegroundColor Red
    }
    
    Write-Host ""
}

Write-Host "============================================================"
Write-Host "TEAMS TABLE INDEXES"
Write-Host "============================================================"

Create-Index "idx_teams_mentor_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_mentor_id ON teams(mentor_id) WHERE mentor_id IS NOT NULL;"

Create-Index "idx_teams_batch_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_batch_id ON teams(batch_id) WHERE batch_id IS NOT NULL;"

Create-Index "idx_teams_status" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_status ON teams(status);"

Create-Index "idx_teams_batch_status" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_batch_status ON teams(batch_id, status) WHERE batch_id IS NOT NULL;"

Create-Index "idx_teams_last_analyzed" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_last_analyzed ON teams(last_analyzed_at DESC NULLS LAST);"

Create-Index "idx_teams_created_at" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_teams_created_at ON teams(created_at DESC);"

Write-Host "============================================================"
Write-Host "ANALYSIS_JOBS TABLE INDEXES"
Write-Host "============================================================"

Create-Index "idx_analysis_jobs_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_team_id ON analysis_jobs(team_id);"

Create-Index "idx_analysis_jobs_status" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);"

Create-Index "idx_analysis_jobs_team_status" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_team_status ON analysis_jobs(team_id, status);"

Create-Index "idx_analysis_jobs_started_at" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_jobs_started_at ON analysis_jobs(started_at DESC);"

Write-Host "============================================================"
Write-Host "RELATED TABLES INDEXES"
Write-Host "============================================================"

Create-Index "idx_tech_stack_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tech_stack_team_id ON tech_stack(team_id);"

Create-Index "idx_issues_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_team_id ON issues(team_id);"

Create-Index "idx_issues_severity" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_severity ON issues(severity);"

Create-Index "idx_issues_type" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_issues_type ON issues(type);"

Create-Index "idx_team_members_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_members_team_id ON team_members(team_id);"

Create-Index "idx_students_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_team_id ON students(team_id);"

Create-Index "idx_students_email" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_students_email ON students(email);"

Create-Index "idx_mentor_assignments_mentor_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mentor_assignments_mentor_id ON mentor_team_assignments(mentor_id);"

Create-Index "idx_mentor_assignments_team_id" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mentor_assignments_team_id ON mentor_team_assignments(team_id);"

Create-Index "idx_batches_status" `
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_batches_status ON batches(status);"

Write-Host "============================================================"
Write-Host "VERIFYING INDEXES"
Write-Host "============================================================"

psql $env:DATABASE_URL -c @"
SELECT 
    tablename,
    indexname
FROM pg_indexes 
WHERE schemaname = 'public' 
    AND tablename IN ('teams', 'analysis_jobs', 'tech_stack', 'issues', 'team_members', 'students', 'mentor_team_assignments', 'batches')
ORDER BY tablename, indexname;
"@

Write-Host ""
Write-Host "✅ Index creation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Run ANALYZE on tables: psql `$env:DATABASE_URL -c 'ANALYZE;'"
Write-Host "2. Test query performance with EXPLAIN ANALYZE"
Write-Host "3. Monitor slow query log"
