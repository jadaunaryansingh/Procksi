# Canonical `team_uid` migration

Goal: make `teams_validation.uid` (uuid) the **only** join key for "team" across the
whole system, with **zero data loss** and no change to any team assignment.

## Status

| Phase | What | State |
|-------|------|-------|
| 0 | Baseline row-count audit + full table snapshots into `backup` schema | **applied to prod 2026-08-27** |
| 1 | `team_uid_map` crosswalk (legacy `teams.id` int → `teams_validation.uid`) | **applied** |
| 2 | `team_uid` column added + backfilled + FK + index on every team-referencing table | **applied** |
| 3 | Transitional sync triggers (legacy write → `team_uid` auto-filled) | **applied** |
| 4 | `team_members` leaders merged into canonical `team_memberships` | **applied** |
| 5 | Application code cutover (read/write `team_uid` only) | **in progress — per service** |
| 6 | Drop legacy columns / demote `public.teams` to a view | **held** until Phase 5 done + 2-week soak |

Files 00–04 in this directory are the exact SQL applied to production, kept for
reproducibility on branches / other environments. They are idempotent.

`99_phase6_drop_legacy.sql` is **not** to be run until the code cutover is complete
and has soaked. `ROLLBACK.sql` reverses phases 1–4 (all additive).

## Guarantees

- Every phase 1–4 change is **additive**. No column dropped, no row deleted.
- Row-count parity is asserted against `public.migration_audit` after every phase —
  all tables only grew.
- Rows that genuinely cannot be linked to a team (14 empty `status=invalid`
  placeholder teams, 1 orphan `github_data` repo row, 97 pre-existing
  `team_members` ↔ `team_memberships` disagreements) are preserved untouched and
  recorded in `public.team_uid_migration_exceptions` +
  `backup.team_membership_divergence_20260827`.

## Verification

Run `04_verify.sql` any time. Every "want 0" line must be 0; every row-count delta
vs baseline must be ≥ 0.

## The transitional objects (removed in phase 6)

- `public.team_uid_map` — crosswalk table
- `public.sync_team_uid_from_int()` / `sync_team_uid_from_slug()` + `trg_sync_team_uid` triggers
- `public.map_new_team_to_uid()` + `trg_map_new_team` on `public.teams`
- `public.v_team_membership_divergence` — monitor view
- `public.team_uid_migration_exceptions` — keep for audit; safe to archive
