-- ============================================================================
-- Phase 12 — presentation flow: cohort-scoped team_uid + data cleanup
-- ============================================================================
-- Companion to the panel-api code change that makes resolve_team_uid() /
-- resolve_results_team_key() / slot_service / admin.upsert_slots resolve the
-- team WITHIN the cycle's semester instead of through the cross-cohort
-- team_uid_map.
--
-- Why: teams_validation.id slugs "<sem>-T<n>" and their trailing numbers are
-- NOT unique across the two concurrently-active B.Tech years —
--   7681fe4a-… (2nd yr): T1..T125
--   c1707ba6-… (3rd yr): T1..T197
-- team_uid_map holds ONE uid per integer and, for old_int_id 1..197, every row
-- currently points at the 3rd-yr cohort. panel-api derived a bare int from the
-- schedule slug and fed it to resolve_team_uid(), so every 2nd-yr presentation
-- evaluation / result would have been written against the 3rd-yr team's uid /
-- results row. The code fix scopes resolution to the semester; this script only
-- does the small data cleanups and the re-runnable verification.
--
-- Applied to prod: 2026-08-31
begin;

-- ---------------------------------------------------------------------------
-- 12a. Remove the empty orphan results shell.
--   c1707ba6-…-T197 : every mark column NULL, team_uid NULL, no live evaluation.
--   Backed up first. (Mirrors the Phase 11b treatment of the -T961 shell.)
-- ---------------------------------------------------------------------------
create schema if not exists backup;
create table if not exists backup.results_20260831 as select * from public.results where false;

insert into backup.results_20260831
  select * from public.results
  where team = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T197'
    and team_uid is null
    and coalesce("proposalMarks","midMarks","finalMarks","totalScore") is null;

delete from public.results
  where team = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T197'
    and team_uid is null
    and coalesce("proposalMarks","midMarks","finalMarks","totalScore") is null;

-- ---------------------------------------------------------------------------
-- 12b. Close the one gap in team_uid_map for the legacy (no-semester) path.
--   old_int_id 42 is missing (41 and 43 are present, both -> 3rd-yr). Add 42
--   pointing at 3rd-yr T42 so the legacy fallback is contiguous. This does NOT
--   affect the presentation flow any more — that path is now semester-scoped —
--   it only tidies the best-effort cross-cohort map other callers still use.
-- ---------------------------------------------------------------------------
insert into public.team_uid_map (old_int_id, uid, source, confidence)
select 42, tv.uid, 'phase12_gap_fill', 'medium'
from public.teams_validation tv
where tv.semester_id = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9'
  and tv.id = 'c1707ba6-d426-4dcb-a23f-aa22c1bb11c9-T42'
on conflict (old_int_id) do nothing;

commit;

-- ===========================================================================
-- VERIFICATION — re-run any time; every "want 0" must stay 0.
-- ===========================================================================

-- V1. No team-scoped presentation row with a team ref but NULL team_uid.
--     (all four tables are empty pre-1st-presentation; must stay 0 after too)
-- want: zero rows
select 'slots'                    as tbl, count(*) as null_uid_with_ref
  from public.slots                    where team_uid is null and team_id is not null
union all
select 'presentation_evaluations', count(*)
  from public.presentation_evaluations where team_uid is null and team_id is not null
union all
select 'presentation_schedule',    count(*)
  from public.presentation_schedule    where team_uid is null and team_id is not null
union all
select 'evaluations',              count(*)
  from public.evaluations              where team_uid is null and team_id is not null
union all
select 'results',                  count(*)
  from public.results                  where team_uid is null and team is not null;

-- V2. No presentation/eval/results row whose team_uid belongs to a DIFFERENT
--     semester than the one its slug / cycle says it is in. This is the
--     cross-cohort misattribution check — the whole point of the fix.
-- want: zero rows
with pe as (
  select pe.id, pe.team_uid, pe.team_id as slug,
         c.semester_id as cycle_sem,
         tv_uid.semester_id as uid_sem
  from public.presentation_evaluations pe
  left join public.presentation_cycles c on c.id = pe.cycle_id
  left join public.teams_validation tv_uid on tv_uid.uid = pe.team_uid
)
select 'presentation_evaluations' as tbl, id::text as row_id, slug, cycle_sem, uid_sem
from pe
where team_uid is not null and cycle_sem is not null and uid_sem is not null
  and cycle_sem <> uid_sem
union all
select 'results', r.team, r.team::text,
       r.semester_id, tv_uid.semester_id
from public.results r
left join public.teams_validation tv_uid on tv_uid.uid = r.team_uid
where r.team_uid is not null and r.semester_id is not null and tv_uid.semester_id is not null
  and r.semester_id <> tv_uid.semester_id
union all
select 'slots', s.id::text, s.team_id::text,
       c.semester_id, tv_uid.semester_id
from public.slots s
left join public.presentation_cycles c on c.id = s.cycle_id
left join public.teams_validation tv_uid on tv_uid.uid = s.team_uid
where s.team_uid is not null and c.semester_id is not null and tv_uid.semester_id is not null
  and c.semester_id <> tv_uid.semester_id;

-- V3. results rows still consistent: team slug and team_uid name the same team.
-- want: zero rows
select r.team, r.team_uid, tv_slug.uid as uid_from_slug
from public.results r
join public.teams_validation tv_slug on tv_slug.id = r.team
where r.team_uid is not null
  and r.team_uid <> tv_slug.uid;
