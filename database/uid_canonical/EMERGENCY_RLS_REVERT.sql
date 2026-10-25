-- ============================================================================
-- RUN THIS once SUPABASE_SERVICE_ROLE_KEY is restored in GitHub Actions secrets
-- AND the EC2 backend has been redeployed (so the backends use the service key
-- again and bypass RLS).
--
-- It undoes every emergency RLS widening made during the 2026-08-28 outage.
-- ============================================================================
begin;

-- 1. pull `anon` back off the policies that were {authenticated} before
do $$
declare r record;
begin
  for r in
    select schemaname, tablename, policyname
    from pg_policies
    where schemaname = 'public'
      and roles = '{anon,authenticated}'
      and policyname <> 'team_uid_map_read'   -- keep this one (crosswalk, non-sensitive)
  loop
    execute format('alter policy %I on %I.%I to authenticated', r.policyname, r.schemaname, r.tablename);
  end loop;
end $$;

-- 2. drop the emergency_anon_access policies added to the no-policy tables
do $$
declare r record;
begin
  for r in
    select tablename from pg_policies
    where schemaname = 'public' and policyname = 'emergency_anon_access'
  loop
    execute format('drop policy emergency_anon_access on public.%I', r.tablename);
  end loop;
end $$;

-- 3. reconcile_team_uid back to service-role only
revoke execute on function public.reconcile_team_uid() from anon, authenticated;

commit;

-- sanity: no public table should list `anon` except team_uid_map
select tablename, policyname, roles::text
from pg_policies
where schemaname='public' and 'anon' = any(roles)
order by tablename;
