-- Migration: Give `deadlines` the columns the admin portal already writes.
--
-- apps/admin/src/services/api.js :: updateDeadlines() upserts six fields —
-- id, semester_id, type, title, description, due_date — but the table only ever
-- had the first three plus due_date. PostgREST rejects the whole batch with
--
--     PGRST204  Could not find the 'description' column of 'deadlines'
--
-- and because the rejection is per-request, ONE unknown column discards every
-- deadline in the publish. The net effect is that nothing an admin sets under
-- Governance -> Platform Deadlines ever reaches the database, so the reminder
-- scheduler has nothing to fire on.
--
-- Both columns are nullable with no default: purely additive, existing rows are
-- untouched, and re-running is a no-op.
--
-- `title` also matters downstream. deadline_scheduler_core.notification_title()
-- resolves a display name as title -> name -> label(type) -> type, so without
-- this column a custom deadline is announced to students by its generated key
-- ("custom_0") instead of the name the admin typed.

alter table public.deadlines add column if not exists title text;
alter table public.deadlines add column if not exists description text;

-- PostgREST caches the schema; without this the new columns stay invisible to
-- the REST API (and the 400 above persists) until the next restart.
notify pgrst, 'reload schema';
