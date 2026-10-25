-- Phase 3: transitional sync. While legacy code still writes team_id (int or slug), keep
-- team_uid populated automatically. Never overrides an explicitly supplied team_uid.
-- Removed in phase 6. Applied to prod: 2026-08-27
begin;

create or replace function public.sync_team_uid_from_int()
returns trigger language plpgsql set search_path = public as $$
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
end $$;

create or replace function public.sync_team_uid_from_slug()
returns trigger language plpgsql set search_path = public as $$
begin
  if NEW.team_uid is null and NEW.team_id is not null then
    select uid into NEW.team_uid from public.teams_validation where id = NEW.team_id;
    if NEW.team_uid is null and NEW.team_id ~ '^[0-9]+$' then
      select uid into NEW.team_uid from public.team_uid_map where old_int_id = NEW.team_id::int;
    end if;
  end if;
  return NEW;
end $$;

-- results keys its team by the column `team` (slug), not `team_id`
create or replace function public.sync_results_team_uid()
returns trigger language plpgsql set search_path = public as $$
begin
  if NEW.team_uid is null and NEW.team is not null then
    select uid into NEW.team_uid from public.teams_validation where id = NEW.team;
    if NEW.team_uid is null and NEW.team ~ '^[0-9]+$' then
      select uid into NEW.team_uid from public.team_uid_map where old_int_id = NEW.team::int;
    end if;
  end if;
  return NEW;
end $$;

create or replace function public.map_new_team_to_uid()
returns trigger language plpgsql set search_path = public as $$
declare v_uid uuid;
begin
  if not exists (select 1 from public.team_uid_map where old_int_id = NEW.id) then
    select tv.uid into v_uid
    from public.teams_validation tv
    where tv.id = NEW.name
       or (tv.semester_id = NEW.semester_id
           and tv.team_number = nullif(coalesce(substring(NEW.name from 'T(\d{1,5})$'),
                                                substring(NEW.name from '-(\d{1,5})$')), '')::int)
    limit 1;
    if v_uid is not null then
      insert into public.team_uid_map(old_int_id, uid, source, confidence)
      values (NEW.id, v_uid, 'teams_insert_trigger', 'medium') on conflict (old_int_id) do nothing;
    end if;
  end if;
  return NEW;
end $$;

-- team_members gets a richer trigger: it can also fall back to the student's
-- canonical team_memberships row (the membership bridge), which self-heals the
-- "invalid placeholder team" rows the portal keeps creating.
create or replace function public.sync_team_members_team_uid()
returns trigger language plpgsql set search_path = public as $$
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
    end if;
    if v_uid is null and NEW.student_id is not null then
      select mm.team_uid into v_uid
      from public.team_memberships mm
      where mm.student_roll = NEW.student_id and mm.team_uid is not null
      order by mm.joined_at desc limit 1;
    end if;
    if v_uid is not null then
      insert into public.team_uid_map(old_int_id, uid, source, confidence)
      values (NEW.team_id, v_uid, 'trigger_membership_bridge', 'medium')
      on conflict (old_int_id) do nothing;
    end if;
    NEW.team_uid := v_uid;
  end if;
  return NEW;
end $$;

do $$
declare tbl text;
begin
  foreach tbl in array array['alerts','projects','slots','evaluations','evaluation_drafts','milestones'] loop
    execute format('drop trigger if exists trg_sync_team_uid on public.%I', tbl);
    execute format('create trigger trg_sync_team_uid before insert or update of team_id, team_uid on public.%I for each row execute function public.sync_team_uid_from_int()', tbl);
  end loop;
  foreach tbl in array array['conversations','mentor_preferences','presentation_evaluations','presentation_schedule','presentation_submissions'] loop
    execute format('drop trigger if exists trg_sync_team_uid on public.%I', tbl);
    execute format('create trigger trg_sync_team_uid before insert or update of team_id, team_uid on public.%I for each row execute function public.sync_team_uid_from_slug()', tbl);
  end loop;
end $$;

drop trigger if exists trg_sync_team_uid on public.team_members;
create trigger trg_sync_team_uid before insert or update of team_id, team_uid, student_id
  on public.team_members for each row execute function public.sync_team_members_team_uid();

drop trigger if exists trg_sync_team_uid on public.results;
create trigger trg_sync_team_uid before insert or update of team, team_uid
  on public.results for each row execute function public.sync_results_team_uid();

drop trigger if exists trg_map_new_team on public.teams;
create trigger trg_map_new_team after insert or update of name, semester_id on public.teams
  for each row execute function public.map_new_team_to_uid();

commit;
