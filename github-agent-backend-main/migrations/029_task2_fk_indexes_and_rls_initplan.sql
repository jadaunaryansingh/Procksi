-- Task 2 optimization: FK indexes + RLS initplan policy rewrites

-- ============================================================
-- 1) Add covering indexes for foreign keys flagged by advisors
-- ============================================================
create index if not exists idx_issues_team_id on public.issues (team_id);
create index if not exists idx_project_comments_team_id on public.project_comments (team_id);
create index if not exists idx_scheduled_task_health_last_execution_id on public.scheduled_task_health (last_execution_id);
create index if not exists idx_team_members_team_id on public.team_members (team_id);
create index if not exists idx_tech_stack_team_id on public.tech_stack (team_id);

-- ============================================================
-- 2) Rewrite RLS policies to avoid row-by-row auth.jwt() re-eval
--    Pattern: auth.jwt() -> (select auth.jwt())
-- ============================================================

-- batches
alter policy "Admins can manage all batches"
on public.batches
using (((select auth.jwt()) ->> 'role') = 'admin');

-- students
alter policy "Admins can manage all students"
on public.students
using (((select auth.jwt()) ->> 'role') = 'admin');

-- mentor_team_assignments
alter policy "Admins can manage all assignments"
on public.mentor_team_assignments
using (((select auth.jwt()) ->> 'role') = 'admin');

alter policy "Mentors can view their assignments"
on public.mentor_team_assignments
using ((mentor_id)::text = ((select auth.jwt()) ->> 'sub'));

-- teams
alter policy "Admins can manage all teams"
on public.teams
using (((select auth.jwt()) ->> 'role') = 'admin');

alter policy "Mentors can view their assigned teams"
on public.teams
using (
  ((mentor_id)::text = ((select auth.jwt()) ->> 'sub'))
  or exists (
    select 1
    from public.mentor_team_assignments mta
    where mta.team_id = teams.id
      and (mta.mentor_id)::text = ((select auth.jwt()) ->> 'sub')
  )
);
