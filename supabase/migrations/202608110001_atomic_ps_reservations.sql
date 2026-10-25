alter table public.teams_validation
  add column if not exists problem_statement_id text
  references public.problem_statements(id) on delete set null;

create index if not exists teams_validation_problem_statement_id_idx
  on public.teams_validation(problem_statement_id)
  where problem_statement_id is not null;

with unique_titles as (
  select lower(btrim(title)) as normalized_title, min(id) as ps_id
  from public.problem_statements
  group by lower(btrim(title))
  having count(*) = 1
)
update public.teams_validation tv
set problem_statement_id = u.ps_id
from unique_titles u
where tv.problem_statement_id is null
  and lower(btrim(tv.title)) = u.normalized_title;

create or replace function public.reserve_problem_statement_atomic(
  p_team_id text, p_problem_statement_id text, p_capacity integer default 2
)
returns table (team_count integer, held_by_current_team boolean)
language plpgsql security invoker set search_path = public
as $$
declare
  v_title text; v_description text; v_domain text;
  v_count integer; v_current_ps text;
begin
  if p_capacity < 1 then raise exception 'capacity must be positive' using errcode = '22023'; end if;
  select title, description, domain into v_title, v_description, v_domain
  from public.problem_statements where id = p_problem_statement_id for update;
  if not found then raise exception 'problem statement not found' using errcode = 'P0002'; end if;
  select problem_statement_id into v_current_ps
  from public.teams_validation where id = p_team_id for update;
  if not found then raise exception 'team not found' using errcode = 'P0002'; end if;
  if v_current_ps is distinct from p_problem_statement_id then
    select count(*)::integer into v_count from public.teams_validation
    where id <> p_team_id
      and (problem_statement_id = p_problem_statement_id
        or (problem_statement_id is null and lower(btrim(title)) = lower(btrim(v_title))));
    if v_count >= p_capacity then raise exception 'problem statement is at capacity' using errcode = 'P0001'; end if;
    update public.teams_validation
    set problem_statement_id = p_problem_statement_id, title = v_title,
        description = v_description, domain = v_domain
    where id = p_team_id;
  end if;
  return query select count(*)::integer, bool_or(id = p_team_id)
  from public.teams_validation where problem_statement_id = p_problem_statement_id;
end;
$$;

revoke all on function public.reserve_problem_statement_atomic(text, text, integer) from public;
grant execute on function public.reserve_problem_statement_atomic(text, text, integer) to service_role;
