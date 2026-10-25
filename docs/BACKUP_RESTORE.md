# Database Backup & Restore Runbook

Project: **PMS Admin Portal** (Supabase project ref `rmmkjczuwsuxcnrdtkrh`, org "Aryan's Org", **Pro plan**, region `ap-northeast-1`).

## What backup coverage we have

Supabase Pro plan includes **daily automatic backups by default** (7-day retention, one snapshot per 24h, timing not user-configurable). Some Pro/Team projects instead have **Point-in-Time Recovery (PITR)** enabled — a paid add-on that allows restoring to *any* moment within a configurable window (7/14/28 days), not just once-a-day snapshots.

**Action needed (one-time, ~2 min):** Confirm which of the two this project actually has, since it changes what "go back" means in an incident:

1. Go to the [Supabase Dashboard](https://supabase.com/dashboard/project/rmmkjczuwsuxcnrdtkrh) → **Database → Backups**.
2. If you see a list of dated snapshots → you're on **Daily Backups** (7-day retention).
3. If you see a "restore to timestamp" picker → **PITR is enabled** — note the retention window shown there.
4. Update this doc's checklist below with what you found.

- [ ] Confirmed backup type: ______________
- [ ] Confirmed retention window: ______________
- [ ] Confirmed by: ______________ on ______________

This only covers the **Postgres database**. It does **not** cover:
- `.env` secrets on any app/backend (not stored in the DB)
- Any files in Supabase Storage buckets, if used (check separately under Storage settings)

## How to restore (destructive — read fully before clicking anything)

**This replaces the live database with the backup's contents.** Any writes made after the backup's timestamp are lost. This is not reversible from the dashboard — there's no "undo restore."

1. **Freeze writes first.** Stop or pause the four backend services (`admin-backend`, `panel-backend`, `student-backend`, `mentor-backend`) on the EC2 host, or at minimum tell users the system is down, so nothing writes to the DB mid-restore:
   ```bash
   docker compose stop admin-backend panel-backend student-backend mentor-backend
   ```
2. In the Supabase Dashboard → **Database → Backups**, pick the snapshot (or timestamp, if on PITR) to restore to, and confirm.
3. Wait for the restore to finish — Supabase shows project status as `Restoring` during this. Expect **several minutes of downtime**; larger databases take longer. Do not restart backend services until status returns to `Active Healthy` (verify via the dashboard or `get_project`).
4. Once restored, restart the backend services:
   ```bash
   docker compose start admin-backend panel-backend student-backend mentor-backend
   ```
5. Smoke-test: log into each app (admin/panel/student/mentor) and confirm data looks sane for the timestamp you restored to.
6. Post-incident: note in the team what was restored and why, since anything written between the backup timestamp and the restore is permanently gone unless someone has another copy.

## Who can trigger a restore

Restoring requires access to the Supabase account/org that owns this project ("Aryan's Org"). Only trigger a restore with the project owner's knowledge — treat it the same as a production incident action, not a routine task.
