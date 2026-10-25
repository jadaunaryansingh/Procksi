-- ============================================================================
-- Phase 10 — remove the unsound "membership bridge" self-healing
-- ============================================================================
-- Context
-- -------
-- 03_sync_triggers.sql / 04_membership_merge_and_verify.sql shipped three
-- pieces that tried to keep legacy team_members and canonical team_memberships
-- in lock-step by assuming "a student's canonical team == their legacy team":
--
--   1. trg_heal_team_members / heal_team_members_on_membership()
--        AFTER INSERT on team_memberships: back-filled team_members.team_uid
--        AND inserted team_uid_map(old_int_id -> NEW.team_uid) for every
--        team_members row the student had.
--   2. sync_team_members_team_uid()  — "membership bridge" branch:
--        when a team_members row could not be resolved via the crosswalk or a
--        slug/number match, it took the student's latest team_memberships.team_uid
--        and wrote it into team_uid_map with source 'trigger_membership_bridge'.
--   3. reconcile_team_uid()  — second half:
--        inserted team_memberships rows from stale legacy team_members rows for
--        any student missing a canonical membership in that semester. Runs every
--        60s from backend/student-api/app/core/github_sync_scheduler.py.
--
-- Why it is unsound
-- -----------------
-- The assumption is false for the 3rd-year cohort (semester c1707ba6…): there,
-- 98 students have a legacy team_members row pointing at one teams_validation
-- row and a canonical team_memberships row pointing at a DIFFERENT, fully
-- populated teams_validation row (both have their own roster, proposal, github
-- and results). The bridge would have permanently cemented the wrong mapping
-- into team_uid_map — the crosswalk that every other table resolves through.
--
-- Impact of this change
-- ---------------------
-- None on existing data. Verified before applying:
--   * reconcile_team_uid() second half would insert 0 rows right now (every
--     student with a legacy team_members row already has a canonical membership).
--   * The 23 existing 'trigger_membership_bridge' / 'membership_heal_trigger' /
--     'membership_bridge_backfill' rows in team_uid_map were checked one by one
--     and all match the student's canonical team_memberships — left in place.
--   * 0 team_members / team_memberships FK orphans after the change.
--
-- Rollback
-- --------
-- Prior definitions are captured in public.phase10_rollback (obj, prior_def).
-- To revert: re-run each prior_def, then
--   CREATE TRIGGER trg_heal_team_members AFTER INSERT OR UPDATE ON
--     public.team_memberships FOR EACH ROW EXECUTE FUNCTION
--     public.heal_team_members_on_membership();
-- ============================================================================

create table if not exists public.phase10_rollback (
  id serial primary key,
  obj text not null,
  prior_def text,
  captured_at timestamptz default now()
);
alter table public.phase10_rollback enable row level security;

insert into public.phase10_rollback (obj, prior_def)
select p.proname, pg_get_functiondef(p.oid)
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in ('heal_team_members_on_membership','reconcile_team_uid','sync_team_members_team_uid');

insert into public.phase10_rollback (obj, prior_def)
select 'trigger:' || tgname, pg_get_triggerdef(t.oid)
from pg_trigger t
where tgname = 'trg_heal_team_members' and not tgisinternal;

-- 1. drop the AFTER-INSERT heal trigger + function on team_memberships
drop trigger if exists trg_heal_team_members on public.team_memberships;
drop function if exists public.heal_team_members_on_membership();

-- 2. sync_team_members_team_uid: keep crosswalk lookup + live slug/number
--    resolve; drop the membership-bridge branch and its team_uid_map write.
create or replace function public.sync_team_members_team_uid()
 returns trigger
 language plpgsql
 set search_path to 'public'
as $function$
declare v_uid uuid;
begin
  if NEW.team_uid is null and NEW.team_id is not null then
    select uid into v_uid from public.team_uid_map where old_int_id = NEW.team_id;

    if v_uid is null then
      select tv.uid into v_uid
      from public.teams t
      join public.teams_validation tv
        on tv.id = t.name
        or (tv.semester_id = t.semester_id
            and tv.team_number = nullif(coalesce(substring(t.name from 'T(\d{1,5})$'),
                                                 substring(t.name from '-(\d{1,5})$')), '')::int)
      where t.id = NEW.team_id
      limit 1;

      if v_uid is not null then
        insert into public.team_uid_map(old_int_id, uid, source, confidence)
        values (NEW.team_id, v_uid, 'trigger_live_resolve', 'medium')
        on conflict (old_int_id) do nothing;
      end if;
    end if;

    NEW.team_uid := v_uid;
  end if;
  return NEW;
end $function$;

-- 3. reconcile_team_uid: keep only the safe direction (fill blank
--    team_members.team_uid FROM canonical team_memberships).
create or replace function public.reconcile_team_uid()
 returns jsonb
 language plpgsql
 set search_path to 'public'
as $function$
declare healed_tm int;
begin
  update public.team_members tm set team_uid = mm.team_uid
  from public.team_memberships mm
  where tm.team_uid is null and mm.student_roll = tm.student_id and mm.team_uid is not null;
  get diagnostics healed_tm = row_count;
  return jsonb_build_object('team_members_healed', healed_tm, 'memberships_added', 0, 'at', now());
end $function$;

-- ============================================================================
-- Verify
-- ============================================================================
-- select tgname, tgrelid::regclass::text, p.proname
--   from pg_trigger t join pg_proc p on p.oid = t.tgfoid
--  where not t.tgisinternal and p.proname like 'sync_team%';
--   -> trg_sync_team_uid on team_members still present; no trg_heal_team_members.
-- select public.reconcile_team_uid();
--   -> {"team_members_healed": 0, "memberships_added": 0, ...}
