-- Phase 4: merge legacy team_members leaders into canonical team_memberships (zero-loss),
-- plus the verification harness. Applied to prod: 2026-08-27
begin;

with tm_ext as (
  select tm.team_uid, tm.student_id, tm.role::text as role,
         coalesce(t.semester_id, s.semester_id) as sem_id,
         coalesce(t.created_at, now()) as joined
  from public.team_members tm
  left join public.teams t on t.id = tm.team_id
  left join public.students s on s.id = tm.student_id
),
to_add as (
  select distinct on (student_id, sem_id) team_uid, student_id, sem_id, role, joined
  from tm_ext e
  where sem_id is not null and team_uid is not null
    and not exists (select 1 from public.team_memberships mm
                    where mm.student_roll = e.student_id and mm.semester_id = e.sem_id)
  order by student_id, sem_id, joined
)
insert into public.team_memberships (team_uid, student_roll, semester_id, role, joined_at)
select team_uid, student_id, sem_id,
       case when upper(role) like 'LEAD%' then 'LEADER' else 'MEMBER' end, joined
from to_add;

-- monitor view for the pre-existing team_members <-> team_memberships disagreements
create or replace view public.v_team_membership_divergence as
select tm.id as team_members_id, tm.student_id, tm.team_id, tm.team_uid as legacy_team_uid,
       mm.team_uid as canonical_team_uid, mm.semester_id,
       case when mm.student_roll is null then 'missing_in_team_memberships'
            when mm.team_uid is distinct from tm.team_uid then 'team_mismatch'
            else 'ok' end as status
from public.team_members tm
left join public.teams t on t.id = tm.team_id
left join public.students s on s.id = tm.student_id
left join public.team_memberships mm
       on mm.student_roll = tm.student_id and mm.semester_id = coalesce(t.semester_id, s.semester_id);

create table if not exists backup.team_membership_divergence_20260827 as
select d.*, now() as captured_at from public.v_team_membership_divergence d where d.status <> 'ok';

insert into public.team_uid_migration_exceptions (table_name, row_key, reason)
select 'team_members', tm.id::text,
       format('Pre-existing split-brain: legacy leader row (team_id=%s) vs different canonical team for student %s. Legacy preserved in backup.*; team_memberships is authoritative.', tm.team_id, tm.student_id)
from public.team_members tm
join public.v_team_membership_divergence d on d.team_members_id = tm.id
where d.status = 'team_mismatch'
  and not exists (select 1 from public.team_uid_migration_exceptions e where e.table_name='team_members' and e.row_key=tm.id::text);

-- Self-healing from the canonical side: when a team_memberships row is written,
-- backfill team_uid on any legacy team_members rows for the same student. This
-- closes the race where the portal creates a team_members row against an
-- "invalid placeholder" team before the real membership exists.
create or replace function public.heal_team_members_on_membership()
returns trigger language plpgsql set search_path = public as $$
begin
  update public.team_members tm
     set team_uid = NEW.team_uid
   where tm.student_id = NEW.student_roll and tm.team_uid is null and NEW.team_uid is not null;
  insert into public.team_uid_map(old_int_id, uid, source, confidence)
  select tm.team_id, NEW.team_uid, 'membership_heal_trigger', 'medium'
  from public.team_members tm
  where tm.student_id = NEW.student_roll and tm.team_id is not null
  on conflict (old_int_id) do nothing;
  return NEW;
end $$;

drop trigger if exists trg_heal_team_members on public.team_memberships;
create trigger trg_heal_team_members after insert or update of team_uid, student_roll
  on public.team_memberships for each row execute function public.heal_team_members_on_membership();

-- Idempotent full reconciler. Call from any existing scheduler (student-api
-- github_sync_scheduler / admin-api deadline_scheduler) every few minutes as a
-- belt-and-braces safety net. Returns counts.
create or replace function public.reconcile_team_uid() returns jsonb
language plpgsql set search_path = public as $$
declare healed_tm int; added_mm int;
begin
  update public.team_members tm set team_uid = mm.team_uid
  from public.team_memberships mm
  where tm.team_uid is null and mm.student_roll = tm.student_id and mm.team_uid is not null;
  get diagnostics healed_tm = row_count;

  with tm_ext as (
    select tm.team_uid, tm.student_id, tm.role::text as role,
           coalesce(t.semester_id, s.semester_id) as sem_id, coalesce(t.created_at, now()) as joined
    from public.team_members tm
    left join public.teams t on t.id = tm.team_id
    left join public.students s on s.id = tm.student_id
  ),
  to_add as (
    select distinct on (student_id, sem_id) team_uid, student_id, sem_id, role, joined
    from tm_ext e where sem_id is not null and team_uid is not null
      and not exists (select 1 from public.team_memberships mm
                      where mm.student_roll = e.student_id and mm.semester_id = e.sem_id)
    order by student_id, sem_id, joined
  )
  insert into public.team_memberships (team_uid, student_roll, semester_id, role, joined_at)
  select team_uid, student_id, sem_id,
         case when upper(role) like 'LEAD%' then 'LEADER' else 'MEMBER' end, joined
  from to_add;
  get diagnostics added_mm = row_count;

  return jsonb_build_object('team_members_healed', healed_tm, 'memberships_added', added_mm, 'at', now());
end $$;

-- mutating function: keep it off the anon/authenticated API surface
revoke all on function public.reconcile_team_uid() from public, anon, authenticated;
grant execute on function public.reconcile_team_uid() to service_role;

commit;

-- ---------------------------------------------------------------------------
-- VERIFICATION (read-only; run any time). Every "want 0" must be 0.
-- ---------------------------------------------------------------------------
select a.table_name,
  format('baseline %s -> now %s (delta %s)', a.exact_count, cur.c, cur.c - a.exact_count) as parity
from public.migration_audit a
cross join lateral (
  select (xpath('/row/c/text()', query_to_xml(format('select count(*) c from public.%I', a.table_name), false, true, '')))[1]::text::bigint c
) cur
where cur.c < a.exact_count;   -- ANY row here = rows lost = STOP

select 'alerts'  t, count(*) unresolved from public.alerts where team_id is not null and team_uid is null
union all select 'projects', count(*) from public.projects where team_id is not null and team_uid is null
union all select 'slots', count(*) from public.slots where team_id is not null and team_uid is null
union all select 'evaluation_drafts', count(*) from public.evaluation_drafts where team_id is not null and team_uid is null
union all select 'team_members', count(*) from public.team_members where team_id is not null and team_uid is null
union all select 'conversations', count(*) from public.conversations where team_id is not null and team_uid is null
union all select 'team_join_requests', count(*) from public.team_join_requests where team_uid is null
union all select 'proposals', count(*) from public.proposals where team_uid is null
union all select 'team_members not in team_memberships', count(*) from public.team_members tm
   left join public.teams t on t.id=tm.team_id left join public.students s on s.id=tm.student_id
   where not exists (select 1 from public.team_memberships mm
     where mm.student_roll=tm.student_id and mm.semester_id=coalesce(t.semester_id,s.semester_id));
