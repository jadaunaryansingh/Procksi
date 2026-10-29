-- Task 1 optimization: speed up teams leaderboard/list query pattern
-- Query pattern optimized:
--   WHERE batch_id = ? AND total_score IS NOT NULL
--   ORDER BY total_score DESC, team_name ASC
--   LIMIT/OFFSET

create index concurrently if not exists idx_teams_batch_score_name
on public.teams (batch_id, total_score desc, team_name asc)
where total_score is not null;
