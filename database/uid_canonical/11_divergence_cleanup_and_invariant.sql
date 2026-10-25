-- ============================================================================
-- Phase 11 — eliminate the team_members <-> team_memberships divergence class
--            and enforce "canonical team_memberships is authoritative" in the DB
-- ============================================================================
-- Run AFTER 10_remove_membership_bridge.sql. Idempotent-ish (guards + backups).
--
-- Background
-- ---------
-- v_team_membership_divergence reported 98 rows status='team_mismatch', all in
-- the 3rd-year cohort (c1707ba6...). Investigation (per-row):
--   * teams_validation.members / leader_roll listed the student in the CANONICAL
--     team for 98/98, in the legacy team for 0/98.
--   * proposals, github_data, results and team_memberships all agreed with the
--     canonical team. Only legacy team_members disagreed — its integer team_id
--     values are scrambled relative to the real teams (e.g. student leads tv#100
--     "PharmaGraph-AI" but their team_members row has team_id=61 -> tv#61
--     "FinScale AI", another team entirely).
-- Conclusion: canonical team_memberships is authoritative; the 98 legacy
-- team_members.team_uid values are wrong.
--
-- ---------------------------------------------------------------------------
-- 11a. Realign the 98 legacy team_members.team_uid to canonical (lossless:
--      only the denormalised column changes; id / team_id / student_id / role
--      are untouched; team_members becomes a view over team_memberships at
--      Phase 6 anyway).
-- ---------------------------------------------------------------------------
create schema if not exists backup;

create table if not exists backup.team_members_20260828 as
  select * from public.team_members;

create table if not exists public.phase10b_team_members_realign (
  team_members_id text primary key,
  student_id text,
  legacy_team_id int,
  old_team_uid uuid,
  new_team_uid uuid,
  applied_at timestamptz default now()
);
alter table public.phase10b_team_members_realign enable row level security;

insert into public.phase10b_team_members_realign
      (team_members_id, student_id, legacy_team_id, old_team_uid, new_team_uid)
select tm.id, tm.student_id, tm.team_id, tm.team_uid, mm.team_uid
from public.team_members tm
join public.team_memberships mm on mm.student_roll = tm.student_id
where mm.team_uid is not null
  and tm.team_uid is distinct from mm.team_uid
  and tm.student_id in (
    select distinct student_id from public.v_team_membership_divergence
    where status = 'team_mismatch'
  )
  -- only students with exactly one canonical membership (no ambiguity)
  and (select count(*) from public.team_memberships x where x.student_roll = tm.student_id) = 1
on conflict (team_members_id) do nothing;

update public.team_members tm
set team_uid = r.new_team_uid
from public.phase10b_team_members_realign r
where tm.id = r.team_members_id
  and tm.team_uid is distinct from r.new_team_uid;
-- expect: v_team_membership_divergence has 0 rows with status='team_mismatch'

-- ---------------------------------------------------------------------------
-- 11b. Close the remaining team_uid coverage gaps.
-- ---------------------------------------------------------------------------
create table if not exists backup.results_20260828     as select * from public.results     where false;
create table if not exists backup.github_data_20260828 as select * from public.github_data where false;

insert into backup.results_20260828
  select * from public.results where team = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T961';
insert into backup.github_data_20260828
  select * from public.github_data where id = 366;

-- results "Team 2" (7681fe4a...-T2): real tv row #2 exists; link it (empty shell).
update public.results
set team_uid = 'b86730dd-0ba7-41f2-9580-7fa60e342848'
where team = '7681fe4a-4055-4b4c-8512-62771f4a77f0-T2' and team_uid is null;

-- results "Team 186" (c1707ba6...-T961): no team_number 186 exists in that
-- cohort; every mark column is NULL. Orphan shell -> remove (backed up).
delete from public.results
where team = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T961'
  and coalesce("proposalMarks","midMarks","finalMarks","totalScore") is null;

-- github_data id 366: exact duplicate repository_url of id 386
-- (SamyaArora/IAMShield_AI), which is correctly linked to team T197. 366 is an
-- earlier unlinked scrape -> remove (backed up).
delete from public.github_data where id = 366;
-- after: results / github_data have 0 rows with a team but NULL team_uid.
-- (conversations rows 10-15 keep NULL team_uid legitimately: they are
--  broadcasts / mentor / panel threads, not team threads.)

-- ---------------------------------------------------------------------------
-- 11c. Enforce the invariant: canonical team_memberships wins for
--      team_members.team_uid, by construction. No team_uid_map writes from the
--      canonical path (that was the Phase 10 bug).
-- ---------------------------------------------------------------------------
create or replace function public.sync_team_members_team_uid()
 returns trigger
 language plpgsql
 set search_path to 'public'
as $function$
declare v_uid uuid;
begin
  -- 1. canonical team_memberships is the source of truth when it exists
  select mm.team_uid into v_uid
  from public.team_memberships mm
  where mm.student_roll = NEW.student_id and mm.team_uid is not null
  order by mm.joined_at desc nulls last
  limit 1;

  -- 2. no canonical row yet -> resolve the legacy int via the crosswalk
  if v_uid is null and NEW.team_id is not null then
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
  end if;

  if v_uid is not null then
    NEW.team_uid := v_uid;
  end if;
  return NEW;
end $function$;

create or replace function public.sync_team_members_from_membership()
 returns trigger
 language plpgsql
 set search_path to 'public'
as $function$
begin
  if NEW.team_uid is not null then
    update public.team_members tm
       set team_uid = NEW.team_uid
     where tm.student_id = NEW.student_roll
       and tm.team_uid is distinct from NEW.team_uid;
  end if;
  return NEW;
end $function$;

drop trigger if exists trg_sync_team_members_from_membership on public.team_memberships;
create trigger trg_sync_team_members_from_membership
  after insert or update of team_uid on public.team_memberships
  for each row execute function public.sync_team_members_from_membership();

-- ---------------------------------------------------------------------------
-- Verify
-- ---------------------------------------------------------------------------
-- select status, count(*) from public.v_team_membership_divergence group by 1;
--   -> only 'ok'.
-- Corruption self-heals:
--   begin;
--     update public.team_members set team_uid = gen_random_uuid()
--      where student_id = (select student_roll from public.team_memberships limit 1);
--     -- BEFORE trigger forces it back to the canonical uid
--   rollback;
