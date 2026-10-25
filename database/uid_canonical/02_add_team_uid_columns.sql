-- Phase 2: add + backfill team_uid on every team-referencing table. Additive, idempotent.
-- Applied to prod: 2026-08-27
--
-- FK rule is ON DELETE SET NULL (not RESTRICT): deleting a teams_validation row
-- (student "disband team", admin delete) must not be blocked by child rows, and
-- the child rows must be preserved (marks, evaluations, github data) with a NULL
-- link rather than deleted. team_memberships (CASCADE) and team_uid_map (CASCADE)
-- are the deliberate exceptions.  [RESTRICT -> SET NULL hotfix: 2026-08-28]
begin;

-- 2A. legacy int-keyed tables -> resolve via team_uid_map
do $$
declare tbl text;
begin
  foreach tbl in array array['alerts','projects','slots','evaluations','evaluation_drafts','milestones','team_members'] loop
    execute format('alter table public.%I add column if not exists team_uid uuid', tbl);
    execute format($f$update public.%1$I t set team_uid = m.uid
                      from public.team_uid_map m
                      where m.old_int_id = t.team_id and t.team_uid is distinct from m.uid$f$, tbl);
    execute format('alter table public.%I drop constraint if exists %I', tbl, tbl||'_team_uid_fkey');
    execute format('alter table public.%I add constraint %I foreign key (team_uid) references public.teams_validation(uid) on update cascade on delete set null not valid', tbl, tbl||'_team_uid_fkey');
    execute format('alter table public.%I validate constraint %I', tbl, tbl||'_team_uid_fkey');
    execute format('create index if not exists %I on public.%I(team_uid)', 'ix_'||tbl||'_team_uid', tbl);
  end loop;
end $$;

-- 2B. text-slug-keyed tables -> resolve via teams_validation.id (bare-int fallback via map)
do $$
declare tbl text;
begin
  foreach tbl in array array['conversations','mentor_preferences','presentation_evaluations','presentation_schedule','presentation_submissions'] loop
    execute format('alter table public.%I add column if not exists team_uid uuid', tbl);
    execute format($f$update public.%1$I t set team_uid = tv.uid
                      from public.teams_validation tv
                      where t.team_uid is null and t.team_id is not null and tv.id = t.team_id$f$, tbl);
    execute format($f$update public.%1$I t set team_uid = m.uid
                      from public.team_uid_map m
                      where t.team_uid is null and t.team_id ~ '^[0-9]+$' and m.old_int_id = t.team_id::int$f$, tbl);
    execute format('alter table public.%I drop constraint if exists %I', tbl, tbl||'_team_uid_fkey');
    execute format('alter table public.%I add constraint %I foreign key (team_uid) references public.teams_validation(uid) on update cascade on delete set null not valid', tbl, tbl||'_team_uid_fkey');
    execute format('alter table public.%I validate constraint %I', tbl, tbl||'_team_uid_fkey');
    execute format('create index if not exists %I on public.%I(team_uid)', 'ix_'||tbl||'_team_uid', tbl);
  end loop;
end $$;

-- 2B-bis. results holds marks and is keyed by a teams_validation.id slug in the
-- column `team` (not `team_id`) — give it a canonical team_uid too.
alter table public.results add column if not exists team_uid uuid;
update public.results r set team_uid = tv.uid
  from public.teams_validation tv where r.team_uid is null and r.team is not null and tv.id = r.team;
update public.results r set team_uid = m.uid
  from public.team_uid_map m where r.team_uid is null and r.team ~ '^[0-9]+$' and m.old_int_id = r.team::int;
alter table public.results drop constraint if exists results_team_uid_fkey;
alter table public.results add constraint results_team_uid_fkey
  foreign key (team_uid) references public.teams_validation(uid) on update cascade on delete set null not valid;
alter table public.results validate constraint results_team_uid_fkey;
create index if not exists ix_results_team_uid on public.results(team_uid);

-- 2C. tables that already have team_uid -> just fill the gaps
update public.team_join_requests r set team_uid = tv.uid
  from public.teams_validation tv where r.team_uid is null and tv.id = r.team_id;
update public.team_join_requests r set team_uid = tv.uid
  from public.teams_validation tv where r.team_uid is null and tv.id = r.team_name;

update public.github_data g set team_uid = tv.uid
  from public.teams_validation tv where g.team_uid is null and g.team_ref = tv.id;
update public.github_data g set team_uid = m.uid
  from public.team_uid_map m where g.team_uid is null and m.old_int_id = g.team_id;

update public.github_agent_analysis a set team_uid = tv.uid
  from public.teams_validation tv where a.team_uid is null and a.team_ref = tv.id;
update public.github_agent_analysis a set team_uid = m.uid
  from public.team_uid_map m
 where a.team_uid is null and a.team_id between 1 and 2147483647 and m.old_int_id = a.team_id::int;

-- log rows that genuinely have no team to link to (pre-existing, preserved as-is)
insert into public.team_uid_migration_exceptions (table_name, row_key, reason)
select 'github_data', g.id::text,
       'Pre-existing orphan: no team_id/team_ref/team_uid. Row preserved with team_uid NULL for manual review.'
from public.github_data g
where g.team_uid is null
  and not exists (select 1 from public.team_uid_migration_exceptions e where e.table_name='github_data' and e.row_key=g.id::text);

commit;
