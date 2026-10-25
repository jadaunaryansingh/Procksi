-- Reverses phases 1-4. Safe because every change was additive.
-- Does NOT touch the phase-1 minted teams_validation row 'legacy-teams-297' or the
-- phase-4 team_memberships backfills by default (they represent real, previously
-- unrecorded leaders). Uncomment the marked blocks only for a total revert.
begin;

-- phase 3 triggers + functions
do $$ declare tbl text; begin
  foreach tbl in array array['alerts','projects','slots','evaluations','evaluation_drafts','milestones','team_members','results',
                             'conversations','mentor_preferences','presentation_evaluations','presentation_schedule','presentation_submissions'] loop
    execute format('drop trigger if exists trg_sync_team_uid on public.%I', tbl);
  end loop;
end $$;
drop trigger if exists trg_map_new_team on public.teams;
drop trigger if exists trg_heal_team_members on public.team_memberships;
drop function if exists public.sync_team_uid_from_int();
drop function if exists public.sync_team_uid_from_slug();
drop function if exists public.sync_team_members_team_uid();
drop function if exists public.sync_results_team_uid();
drop function if exists public.map_new_team_to_uid();
drop function if exists public.heal_team_members_on_membership();
drop function if exists public.reconcile_team_uid();

-- phase 2 columns + constraints
do $$ declare tbl text; begin
  foreach tbl in array array['alerts','projects','slots','evaluations','evaluation_drafts','milestones','team_members','results',
                             'conversations','mentor_preferences','presentation_evaluations','presentation_schedule','presentation_submissions'] loop
    execute format('alter table public.%I drop constraint if exists %I', tbl, tbl||'_team_uid_fkey');
    execute format('drop index if exists public.%I', 'ix_'||tbl||'_team_uid');
    execute format('alter table public.%I drop column if exists team_uid', tbl);
  end loop;
end $$;
-- NOTE: github_data / github_agent_analysis / proposals / team_join_requests / team_memberships
-- had team_uid BEFORE this migration - their columns are left intact. Only backfilled NULLs there.

-- phase 4 monitor
drop view if exists public.v_team_membership_divergence;

-- phase 1 crosswalk
drop table if exists public.team_uid_map;
-- keep public.team_uid_migration_exceptions for the audit trail

-- === TOTAL REVERT ONLY (normally leave commented) ===
-- delete from public.team_memberships mm using public.teams_validation tv
--   where mm.team_uid = tv.uid and tv.id = 'legacy-teams-297';
-- delete from public.teams_validation where id = 'legacy-teams-297';
-- delete from public.team_memberships where id between 815 and 818;  -- the 4 phase-4 leader backfills

commit;
