-- Task 2 optimization (phase 2): clear remaining auth_rls_initplan warnings

-- analysis_jobs
alter policy "Admins can manage analysis_jobs"
on public.analysis_jobs
using (((select auth.jwt()) ->> 'role') = 'admin')
with check (((select auth.jwt()) ->> 'role') = 'admin');

-- user_teams
alter policy "admins_manage_teams"
on public.user_teams
using (
  exists (
    select 1
    from public.users u2
    where u2.id = (select auth.uid())
      and u2.role = 'admin'
  )
);

alter policy "mentors_read_teams"
on public.user_teams
using (
  exists (
    select 1
    from public.mentors m
    where m.user_id = (select auth.uid())
      and m.id = user_teams.mentor_id
  )
);

-- users
alter policy "admins_manage_users"
on public.users
using (
  exists (
    select 1
    from public.users u2
    where u2.id = (select auth.uid())
      and u2.role = 'admin'
  )
);

alter policy "users_select_self"
on public.users
using ((select auth.uid()) = id);

-- project_comments
alter policy "project_comments_delete"
on public.project_comments
using (
  (user_id = (select auth.uid()))
  or exists (
    select 1
    from public.users u
    where u.id = (select auth.uid())
      and u.role = 'admin'
  )
);

alter policy "project_comments_insert"
on public.project_comments
with check (
  exists (
    select 1
    from public.users u
    where u.id = (select auth.uid())
      and u.role = any (array['admin'::text, 'mentor'::text])
  )
  or ((select auth.uid()) = user_id)
);

alter policy "project_comments_select"
on public.project_comments
using (
  exists (
    select 1
    from public.users u
    where u.id = (select auth.uid())
      and u.role = 'admin'
  )
  or (user_id = (select auth.uid()))
  or (not is_private)
);

alter policy "project_comments_update"
on public.project_comments
using (
  (user_id = (select auth.uid()))
  or exists (
    select 1
    from public.users u
    where u.id = (select auth.uid())
      and u.role = 'admin'
  )
)
with check (
  (user_id = (select auth.uid()))
  or exists (
    select 1
    from public.users u
    where u.id = (select auth.uid())
      and u.role = 'admin'
  )
);

-- team_memberships
alter policy "team_memberships_insert"
on public.team_memberships
with check ((select auth.uid()) = user_id);

alter policy "team_memberships_read"
on public.team_memberships
using ((select auth.uid()) = user_id);

-- scheduled_task_executions
alter policy "Allow admin read on scheduled_task_executions"
on public.scheduled_task_executions
using (
  exists (
    select 1
    from public.users
    where users.id = (select auth.uid())
      and users.role = 'admin'
  )
);
