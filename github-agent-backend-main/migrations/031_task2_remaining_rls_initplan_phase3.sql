-- Task 2 optimization (phase 3): clear remaining auth_rls_initplan warnings

alter policy "Allow admin read on scheduled_task_health"
on public.scheduled_task_health
using (
  exists (
    select 1
    from public.users
    where users.id = (select auth.uid())
      and users.role = 'admin'
  )
);

alter policy "Allow read access to authenticated users"
on public.celery_beat_overrides
using ((select auth.role()) = 'authenticated');

alter policy "Allow all access to service role"
on public.celery_beat_overrides
using (((select auth.jwt()) ->> 'role') = 'service_role');
