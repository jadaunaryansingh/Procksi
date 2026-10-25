-- Phase 1: canonical crosswalk  legacy public.teams.id (int) -> public.teams_validation.uid (uuid)
-- Idempotent. Applied to prod: 2026-08-27
begin;

create table if not exists public.team_uid_map (
  old_int_id   integer primary key,
  -- ON DELETE CASCADE: the map is transitional and must never block a
  -- teams_validation delete (e.g. the admin "wipe semester" endpoint).
  uid          uuid not null references public.teams_validation(uid) on update cascade on delete cascade,
  source       text not null,
  confidence   text not null default 'high',
  created_at   timestamptz not null default now()
);
comment on table public.team_uid_map is
  'Transitional crosswalk (team-UID migration 2026-08). Maps legacy public.teams.id to canonical teams_validation.uid. Drop in phase 6.';

-- Bridge 1: github_data rows carrying BOTH the legacy int and the canonical uid
insert into public.team_uid_map (old_int_id, uid, source, confidence)
select distinct on (g.team_id) g.team_id, g.team_uid, 'github_data_both_keys', 'high'
from public.github_data g
join public.teams_validation tv on tv.uid = g.team_uid
where g.team_id is not null
order by g.team_id, g.id
on conflict (old_int_id) do nothing;

-- Bridge 2: legacy team_members(team_id) x canonical team_memberships(team_uid) via the shared
--           leader student, only where a given int team maps to exactly one uid
with lm as (
  select tm.team_id, mm.team_uid
  from public.team_members tm
  join public.team_memberships mm on mm.student_roll = tm.student_id
),
single as (select team_id from lm group by team_id having count(distinct team_uid) = 1)
insert into public.team_uid_map (old_int_id, uid, source, confidence)
select s.team_id, (array_agg(distinct lm.team_uid))[1], 'leader_student_bridge', 'high'
from single s join lm on lm.team_id = s.team_id
group by s.team_id
on conflict (old_int_id) do nothing;

-- Bridge 3: (semester_id, team number parsed from teams.name) <-> (semester_id, team_number)
insert into public.team_uid_map (old_int_id, uid, source, confidence)
select tt.id, tv.uid, 'semester_number_match', 'medium'
from (
  select id, semester_id,
         nullif(coalesce(substring(name from 'T(\d{1,5})$'),
                         substring(name from '-(\d{1,5})$')), '')::int as parsed_num
  from public.teams
  where semester_id is not null
) tt
join public.teams_validation tv
  on tv.semester_id = tt.semester_id and tv.team_number = tt.parsed_num
where tt.parsed_num is not null
on conflict (old_int_id) do nothing;

-- Edge case: legacy placeholder team 297 (status=invalid, one leader-only membership,
-- no canonical counterpart). Mint a canonical row so the membership survives unchanged.
with src as (
  select id, coalesce(nullif(project_title,''), name) as title, semester_id, created_at
  from public.teams where id = 297
),
ins_tv as (
  insert into public.teams_validation (id, title, semester_id, team_number, "validationStatus", leader_roll, members)
  select 'legacy-teams-297', src.title, src.semester_id, 194, 'Invalid', '2415500011', '[]'::jsonb
  from src
  on conflict (id) do nothing
  returning uid, semester_id
),
tv_row as (
  select uid, semester_id from ins_tv
  union all select uid, semester_id from public.teams_validation where id = 'legacy-teams-297'
  limit 1
),
ins_map as (
  insert into public.team_uid_map (old_int_id, uid, source, confidence)
  select 297, uid, 'minted_for_legacy_placeholder', 'high' from tv_row
  on conflict (old_int_id) do nothing returning 1
)
insert into public.team_memberships (team_uid, student_roll, semester_id, role, joined_at)
select tv_row.uid, '2415500011', tv_row.semester_id, 'LEADER', coalesce((select created_at from src), now())
from tv_row
where not exists (select 1 from public.team_memberships mm
                  where mm.student_roll = '2415500011' and mm.semester_id = tv_row.semester_id);

-- Exceptions log
create table if not exists public.team_uid_migration_exceptions (
  id bigint generated always as identity primary key,
  table_name text not null,
  row_key text not null,
  reason text not null,
  logged_at timestamptz not null default now()
);
insert into public.team_uid_migration_exceptions (table_name, row_key, reason)
select 'teams', t.id::text,
       'Unmapped legacy placeholder (status=invalid, "Pending" title, zero child rows). Preserved in backup.teams_20260827; archived not dropped in phase 6.'
from public.teams t
where not exists (select 1 from public.team_uid_map m where m.old_int_id = t.id)
  and not exists (select 1 from public.team_uid_migration_exceptions e where e.table_name='teams' and e.row_key=t.id::text);

commit;
