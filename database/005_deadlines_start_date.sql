-- Migration: Add start_date column to `deadlines` table.
--
-- apps/admin/src/pages/Governance.jsx and apps/admin/src/services/api.js update
-- deadlines with start_date (allowed_from), title, description, and due_date.
-- Without this column, PostgREST returns HTTP 400 (PGRST204: Could not find the
-- 'start_date' column of 'deadlines') when publishing deadlines, causing start_date
-- settings to disappear upon refresh.

ALTER TABLE public.deadlines ADD COLUMN IF NOT EXISTS start_date text;

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';
