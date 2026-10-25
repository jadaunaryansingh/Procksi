-- Phase 0: baseline audit + full snapshots. Idempotent-ish (drops/recreates audit;
-- backup snapshots are date-stamped so re-runs on the same day error — that is intentional).
-- Applied to prod: 2026-08-27

create schema if not exists backup;

drop table if exists public.migration_audit;
create table public.migration_audit as
select
  c.relname as table_name,
  c.reltuples::bigint as planner_estimate,
  (xpath('/row/c/text()',
     query_to_xml(format('select count(*) as c from public.%I', c.relname), false, true, '')))[1]::text::bigint as exact_count,
  now() as captured_at
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname <> 'migration_audit';

create table backup.teams_20260827                 as table public.teams;
create table backup.teams_validation_20260827      as table public.teams_validation;
create table backup.team_members_20260827          as table public.team_members;
create table backup.team_memberships_20260827      as table public.team_memberships;
create table backup.github_data_20260827           as table public.github_data;
create table backup.github_agent_analysis_20260827 as table public.github_agent_analysis;
create table backup.proposals_20260827             as table public.proposals;
create table backup.team_join_requests_20260827    as table public.team_join_requests;
create table backup.projects_20260827              as table public.projects;
create table backup.slots_20260827                 as table public.slots;
create table backup.alerts_20260827                as table public.alerts;
create table backup.evaluation_drafts_20260827     as table public.evaluation_drafts;
create table backup.conversations_20260827         as table public.conversations;
