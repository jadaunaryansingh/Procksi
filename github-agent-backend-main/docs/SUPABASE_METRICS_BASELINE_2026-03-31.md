# Supabase Metrics Baseline (2026-03-31)

Project: Github-agent  
Project ref: masdxqkwxjzhwqrrvtpe  
Captured at (UTC): 2026-03-31 00:47:00

## Purpose

This is the post-optimization baseline snapshot. Re-check after 72 hours and compare against this file.

## A) Top Queries by Mean Time (pg_stat_statements)

Note: pg_stat_statements is cumulative since last reset/restart, so old query shapes may still appear.

1. queryid -2736964596202726002
- calls: 10
- total_ms: 18068.0
- mean_ms: 1806.8
- shared_blks_read: 175
- shared_blks_hit: 25175
- sample: teams list with total_score + metadata + report_json

2. queryid -6338745166615224527
- calls: 1
- total_ms: 1541.8
- mean_ms: 1541.8
- shared_blks_read: 0
- shared_blks_hit: 2427
- sample: teams by batch selecting report_json

3. queryid -7726440967385220442
- calls: 8
- total_ms: 7755.3
- mean_ms: 969.4
- shared_blks_read: 0
- shared_blks_hit: 0
- sample: SELECT name FROM pg_timezone_names

4. queryid -3591150600835024252
- calls: 1
- total_ms: 374.8
- mean_ms: 374.8
- shared_blks_read: 45
- shared_blks_hit: 2429
- sample: VACUUM ANALYZE scheduled_task_executions

5. queryid -5208969012607651293
- calls: 2
- total_ms: 669.8
- mean_ms: 334.9
- shared_blks_read: 211
- shared_blks_hit: 1698
- sample: EXPLAIN ANALYZE teams leaderboard pattern

## B) Largest Tables (public schema)

1. public.teams: 37 MB
2. public.scheduled_task_executions: 4168 kB
3. public.notifications: 2672 kB
4. public.analysis_jobs: 2504 kB
5. public.analysis_snapshots: 1000 kB

## C) JSON Payload Pressure (teams.report_json)

- avg_report_json_bytes: 55252.7
- p95_report_json_bytes: 253327.6
- max_report_json_bytes: 1288335.0

## D) Dead Tuple Snapshot

After manual maintenance, dead tuples are effectively cleared on main churn tables.

- notifications: n_dead_tup = 0
- scheduled_task_executions: n_dead_tup = 0
- scheduled_task_health: n_dead_tup = 0

## E) What Was Already Applied Before This Baseline

1. Composite leaderboard index on teams:
- (batch_id, total_score desc, team_name asc) where total_score is not null

2. Leaderboard/list payload optimization:
- report_json removed from leaderboard hot path
- DB-level pagination and keyset support added in API

3. FK index fixes and RLS initplan policy rewrites

4. Scheduled task endpoints:
- duplicate count query removed
- short-lived caching added for monitoring endpoints

## F) 72-Hour Comparison Checklist

At +72h, collect the same metrics and compare:

1. Supabase Disk IO dashboards
- Daily Disk IO trend
- Hourly Disk IO spikes

2. Query health
- top 10 by mean_exec_time
- top 10 by shared_blks_read
- whether old report_json-heavy queryids still dominate

3. Latency stability
- p95 and max latency on leaderboard and scheduled-task APIs

4. Table health
- n_dead_tup on notifications/scheduled_task_executions/scheduled_task_health

## G) Pass/Fail Rule for Compute Upgrade

- Keep current compute if hourly Disk IO remains mostly under 70-80% and p95 is stable.
- Consider upgrade if Disk IO repeatedly stays above 90% after these fixes and p95 continues to degrade.
