# `team_uid` canonical migration — runbook

## Where things stand (2026-08-27)

**Database (phases 0–4): DONE, applied to production, verified, zero rows lost.**

- Every team-referencing table now has a `team_uid uuid` column, backfilled,
  FK-enforced against `teams_validation(uid)`, and indexed:
  `alerts, projects, slots, evaluations, evaluation_drafts, milestones,
  team_members, conversations, mentor_preferences, presentation_evaluations,
  presentation_schedule, presentation_submissions` (plus `github_data`,
  `github_agent_analysis`, `proposals`, `team_join_requests`, `team_memberships`
  which already had it — nulls backfilled).
- `public.team_uid_map` maps every legacy `teams.id` → canonical `uid`
  (398 rows; 100% of referenced legacy ids covered).
- Sync triggers (`trg_sync_team_uid`, `trg_map_new_team`) keep `team_uid`
  populated no matter which legacy key current app code writes — **so the apps
  keep working unchanged and the code can be migrated incrementally with no
  freeze.**
- Legacy `team_members` leaders merged into canonical `team_memberships`
  (4 genuinely-missing leaders added; 0 rows lost).
- Preserved-but-unlinkable rows recorded in
  `public.team_uid_migration_exceptions` (112 rows: 14 empty invalid placeholder
  teams, 1 orphan github repo, 97 pre-existing team_members↔team_memberships
  disagreements) and `backup.*_20260827` snapshots (14 tables).

Re-run `04_membership_merge_and_verify.sql` (bottom half) any time — every
"want 0" must stay 0, every row-count delta vs `migration_audit` must stay ≥ 0.

## INCIDENT 2026-08-28 — portal outage (resolved)

Not caused by the migration logic. A push to `main` auto-triggered `deploy-ec2.yml`,
which recreated the backend containers. They came up with a stale/disabled
`SUPABASE_SERVICE_KEY` (a legacy `service_role` JWT Supabase had since disabled),
so `SupabaseRESTClient` fell through to the publishable key -> PostgREST treated
every request as `anon` -> RLS (which is `to authenticated` on every table)
returned zero rows -> "Student record not found" across all portals.

Fix: the `SUPABASE_SERVICE_ROLE_KEY` GitHub secret was already correct
(`sb_secret_...`); re-ran **Deploy EC2** (run #307) to recreate the containers so
they pick it up. Confirmed working.

Emergency mitigation while it was down (all reverted after #307):
- extended ~20 `qual=true` policies to `anon`, added `emergency_anon_access` to 24
  operational tables, granted `reconcile_team_uid` to anon
- `EMERGENCY_RLS_REVERT.sql` undid all of it — verified `0` public tables expose
  `anon` now.

Two real migration bugs found + fixed during the incident:
1. the new `*_team_uid_fkey` were `ON DELETE RESTRICT` -> 409 on "disband team".
   All switched to `ON DELETE SET NULL` (`team_memberships`/`team_uid_map` stay
   CASCADE). Migration script 02 updated.
2. an earlier ad-hoc multi-statement `execute_sql` dropped
   `v_team_membership_divergence` mid-batch. Recreated as `SECURITY INVOKER`.
   `migration_audit` / `team_uid_map` / `team_uid_migration_exceptions` now have
   RLS enabled (service-role only; `team_uid_map` has no anon policy).

## Self-healing layer (DB) — ADDED 2026-08-28

Because the portals keep creating `status=invalid` placeholder `teams` rows and
legacy `team_members` rows faster than a point-in-time backfill, the DB now
self-heals `team_uid` from **both** directions and offers a reconciler:

| Object | What it does |
|---|---|
| `trg_sync_team_uid` (10 tables) | fills `team_uid` from `team_uid_map` / live slug+number resolve on any legacy write |
| `sync_team_members_team_uid()` + trigger on `team_members` | `team_uid_map` lookup + live slug/number resolve on any legacy write (the membership-bridge branch was removed in Phase 10 — see below) |
| `trg_map_new_team` on `teams` | registers every new legacy team in `team_uid_map` |
| `reconcile_team_uid()` | idempotent heal-only sweep: fills any still-NULL `team_members.team_uid` from the student's canonical `team_memberships`. Called every 60s from student-api `github_sync_scheduler`. As of Phase 10 it never inserts `team_memberships` or `team_uid_map`. |
| `team_uid_map.uid` FK | now `ON DELETE CASCADE` so it never blocks the admin "wipe semester" endpoint |
| all `*_team_uid_fkey` | **`ON DELETE SET NULL`** (hotfix 2026-08-28). They were `RESTRICT`, which 409'd the student "disband team" delete of a `teams_validation` row while a legacy `team_members` row still pointed at it. SET NULL: delete succeeds, child rows (marks, evals, github) preserved with a null link. `team_memberships` / `team_uid_map` stay CASCADE. |

Verification stays green: 0 rows lost vs baseline, 0 `team_uid` FK orphans, 0
`team_members` unrepresented in `team_memberships`. Transient placeholder rows
appear and resolve within seconds.

## Phase 10 — removed the membership bridge (2026-08-28, `10_remove_membership_bridge.sql`)

**Trigger:** recurring student-portal split-brain ("you don't belong to a team"
next to "you are already in Team 102"). Investigation showed the *portal* symptom
was a front-end race at team-creation time (the `/team` GET returns null for the
few ms before the new `team_memberships` row commits, then a second create POST
409s) — fixed in `apps/student/src/pages/TeamProposalView.jsx` by refetching on
that 409. But the investigation also found three self-healing pieces that assume
**"a student's canonical team == their legacy team"**, which is false for the
3rd-year cohort (`c1707ba6…`): 98 students there have a legacy `team_members`
row pointing at one `teams_validation` row and a canonical `team_memberships`
row pointing at a *different, fully-populated* one (each side has its own roster,
proposal, github and results). The bridge would have cemented the wrong mapping
into `team_uid_map` — the crosswalk every table resolves through.

Removed:
- `trg_heal_team_members` + `heal_team_members_on_membership()` — dropped.
- `sync_team_members_team_uid()` — membership-bridge branch + its
  `trigger_membership_bridge` map write removed; crosswalk lookup + live
  slug/number resolve kept.
- `reconcile_team_uid()` — the half that inserted `team_memberships` from stale
  legacy `team_members` removed; heal-only direction (fill NULL
  `team_members.team_uid` from canonical) kept. Still called every 60s.

**Impact on data: none.** Verified before applying: `reconcile_team_uid()`
second half would have inserted 0 rows (every student with a legacy row already
has a canonical membership); the 23 existing `membership_bridge*` /
`membership_heal_trigger` rows in `team_uid_map` were each checked against the
student's canonical `team_memberships` and all match — left in place; 0 FK
orphans after. Prior definitions saved in `public.phase10_rollback`.

## Phase 11 — divergence eliminated + DB invariant (2026-08-28, `11_divergence_cleanup_and_invariant.sql`)

**The 98 3rd-year divergences: resolved.** Deeper investigation (per-row, not
aggregate) settled which side is authoritative:

| Signal | Points at |
|---|---|
| `teams_validation.members` / `leader_roll` roster | **canonical** for 98/98, legacy for 0/98 |
| `proposals`, `github_data`, `results`, `team_memberships` | all agree with **canonical** |
| legacy `team_members.team_id` (int) | scrambled — e.g. a student who leads tv#100 "PharmaGraph-AI" had `team_id=61` → tv#61 "FinScale AI", a different team |

So canonical `team_memberships` is authoritative and the 98 legacy
`team_members.team_uid` values were wrong. **11a** realigns them to canonical —
lossless (only the denormalised `team_uid` column changes; `id` / `team_id` /
`student_id` / `role` untouched; full-table snapshot in
`backup.team_members_20260828`, per-row ledger in
`public.phase10b_team_members_realign`). Result: `v_team_membership_divergence`
has **0** `team_mismatch` rows.

**11b — coverage gaps closed.** `results` "Team 2" linked to the real tv row;
one all-NULL orphan `results` shell (`…-T961`, points at a nonexistent team
#186) and one duplicate `github_data` row (id 366, same repo URL as the linked
id 386) removed — both backed up to `backup.*_20260828`. Every team-scoped table
is now 100 % `team_uid`-populated; remaining NULLs are correct
(`conversations` broadcasts, `github_agent_analysis` job-history rows).

**11c — invariant enforced.** `sync_team_members_team_uid()` (BEFORE on
`team_members`) now resolves `team_uid` from the student's canonical
`team_memberships` FIRST, crosswalk/slug only as fallback for students with no
canonical row yet — and never writes `team_uid_map` from the canonical path.
New `sync_team_members_from_membership()` (AFTER on `team_memberships`)
propagates canonical → legacy. Tested: setting a `team_members.team_uid` to a
bogus value inside a txn is silently corrected back to canonical by the BEFORE
trigger. The `team_members` ↔ `team_memberships` split-brain class cannot recur.

**Still legacy-only (documented, not a correctness risk):** the
`/api/admin/teams/*` router (`app/api/team.py`, mirrored in student-api /
mentor-api / backend/app) still has `bulk-assign` / `force-assign` /
`create-custom` / `assign-to-team` handlers that write legacy `teams` +
`team_members` only. **No frontend calls them** (the admin portal manages teams
via `admin-api` + `teams_validation`). If ever reactivated they must dual-write
`teams_validation` + `team_memberships`, or be removed.

## Post-incident hardening (2026-08-28, commits 0079fea)

- **Startup service-key check** in all 4 backends: on boot each reads
  `students?select=id&limit=1` via its service client; an empty result logs a
  LOUD error. This is the exact 2026-08-28 signature and was previously silent.
- **panel-api reads -> team_uid**: `get_project_title`,
  `get_batch_project_titles`, `resolve_team_semester_id`,
  `resolve_results_team_key` now resolve via `team_uid_map` ->
  `teams_validation.uid` first; `sync_team_results_from_evaluations` writes
  `results.team_uid`. The remaining ~40 `teams` (int) reads in panel routers are
  display-only team names and keep working until Phase 6.
- **admin Views.jsx**: proposal<->team match uses `sameTeam()` (canonical
  `team_uid`) before id/number fallback.
- **admin-api**: already ~fully on `teams_validation`; its `.eq("id", <slug>)`
  calls use the real unique slug key — no change needed. github-analysis
  endpoints were already made uid-first.
- **mentor-api `mentor_portal.py`**: NOT rewired. Its mentor->team link is
  `teams_validation.mentor` (a name array that is ~99% empty) — a pre-existing
  data-model hole. Rewiring 63 number sites there has no value until that field
  is populated.
- **3 orphaned `results` rows** (renumbered team slugs, all marks NULL): 2
  attached to their matched team, 1 empty shell left NULL. Logged.

## Phase 5 — progress (2026-08-28, pass 1 on every service; syntax-verified, NOT test-run)

**18 tables now carry `team_uid`** (added `results` — it holds marks and was keyed
by a `teams_validation.id` slug in a `team` column). Verification stays green:
0 data loss, 0 FK orphans, 0 membership gaps, 7/7 self-healing functions.

### Multi-active-semester (different B.Tech years) — swept
- `backend/*/services/governance_service.py` (×3): `get_system_status` now counts
  teams from **`teams_validation`** (was the legacy `teams` int table, full of
  invalid placeholders) and joins all active batch years for the label.
- `mentor-api/app/main.py` + `admin-api/app/main.py`: freeze/lock middleware now
  blocks only on a **true system-wide** freeze (every active batch locked),
  not whichever batch sorted first.
- `panel-api/app/routers/panel.py`: `procksi_chat_panel` toggle aggregates across
  active batches. `panel-api/app/db_helpers.py::sync_team_results_from_evaluations`
  resolves the semester from the team, not "first active".
- `student-api/app/api/student_portal.py`: proposal-submit no longer overrides the
  student's own batch with "first active". The other ~7 `is_active&limit=1` sites
  in student_portal are safe — they only fire when a student has *no* batch.
- Left as-is: `semester_repo.get_active()` (`.limit(1)`) — used by many callers
  that legitimately need "a" semester; changing its return type is a separate
  refactor. `admin-api` team **renumber** picks first-active when unspecified —
  fine now, since the number is display-only post-migration.



### backend/student-api — PASS 1 DONE (2026-08-28, needs test run + review)
Edited: `app/core/supabase_client.py`, `app/api/student_deps.py`, `app/api/student_portal.py`.
- `extract_numeric_id`: removed the "last 3 digits of the UUID = team number"
  fallback — it invented team numbers from uuids. Returns 0 now; callers already
  handle 0.
- Added `SupabaseRESTClient.resolve_team_uid(identifier)` — uuid / slug / legacy
  int → canonical `teams_validation.uid`, cached 30s.
- `get_proposal_by_team_id`, `get_latest_approved_proposal_by_team_id`,
  `get_evaluations_by_team`, `update_team_proposal_details`, `save_proposal`:
  canonical `team_uid` path first, legacy string match kept as fallback.
- `student_deps.py`: `team_membership.team_uid` now populated; role read from
  `team_memberships` (authoritative) instead of the name/position heuristic.
- `student_portal.py`: GitHub-data filter, `/proposals` list, `/proposals/{id}`
  ownership check, and `POST /proposals` all key off exact `team_uid` when
  available (no post-filter needed — uuid equality can't leak across teams).
- `POST /proposals`: stopped collapsing to "first active semester" — uses the
  student's own (already validated) `semester_id`. **~8 more
  `semester_config?is_active=eq.true&limit=1` sites remain in student_portal.py
  — that is the separate multi-active-semester bug, tracked below, not the
  team_uid migration.**

Not yet touched in student-api: the remaining ~45 `extract_numeric_id` /
`TEAM-{n}` display sites in `student_portal.py` (schedule, results, github sync
scheduler). They still work via the fallbacks; migrate opportunistically.

### backend/admin-api — PASS 1 (2026-08-28, needs test run + review)
- Added `app/team_uid.py` (`resolve_team_uid`, `team_by_uid`, `members_for_team`).
- `GET /api/admin/github/team-analysis/{team_id}` and
  `GET /api/admin/github/teams-analysis`: team fetch + analysis/github_data
  lookups now try `team_uid` first; number/slug matching is fallback only and
  is suppressed once a uid is known (was pulling other teams' repos).
Not touched: ~80 other `teams_validation.eq("id", slug)` sites (slug is a real
unique key, they work); the legacy `teams` int writes in the "wipe semester"
endpoint (destructive by design, DB CASCADE now handles the crosswalk); the
`mentor_allocation_agent` updates by slug/title.

### backend/panel-api — PASS 1 (2026-08-28, needs test run + review)
- Added `resolve_team_uid()` to `app/db_helpers.py`.
- `evaluations`, `evaluation_drafts`, `presentation_evaluations` inserts now set
  `team_uid` explicitly (belt-and-braces with `trg_sync_team_uid`).
Not touched: the read paths (`to_numeric_id` / `resolve_team_string_id` /
`from_numeric_id`) — they still resolve correctly and the sync trigger keeps
`team_uid` consistent; flip them to `team_uid` in a tested pass. **panel-api
handles marks — do this one carefully with its pytest suite.**

### backend/mentor-api — PASS 1 (2026-08-28)
- Lock middleware fixed for multiple active batches (above).
- `governance_service` fixed (above).
- NOT rewired: `mentor_portal.py`'s `to_numeric` / alloc-id web. The mentor↔team
  link is `teams_validation.mentor` (name array), **~99% empty at the data
  level** — a pre-existing data-model hole (audit finding F-13), not something
  this migration can fix. `mentor_portal.py` is already multi-active-semester
  aware (`rest_active_semester_ids`, `wanted_semesters`). Works via the compat
  layer. Rewiring it needs the team→mentor assignment to actually be stored
  first.

### frontends — PASS 1 (2026-08-28)
- `teamUid.js` (`teamUidOf`, `sameTeam`, `teamDisplayNumber`, `indexTeamsByUid`,
  `isUuid`) copied into all 5 apps' `src/lib/`.
- `apps/admin/src/lib/teamUtils.js::findMatchingTeam` — added a canonical
  `team_uid` fast path at the top; the 6-level fuzzy cascade now only runs when
  neither side has a uid.
- `globalFilters.js` in admin / panel / mentor — removed the
  "last-3-digits-of-the-uuid = team number" fallback in `teamNumberFromId`
  (returns `null` now). Display labels + filters otherwise unchanged.
- NOT done: rewiring individual pages (`TeamValidation.jsx`, `Views.jsx`,
  `ProposalList/Viewer.jsx`, `Schedule.jsx`, `Results.jsx`, `MentorAllocation.jsx`,
  `MilestonesManager.jsx`, `Evaluations.jsx`, …) to join on `teamUidOf()`
  directly. They inherit the `findMatchingTeam` fast path; a direct pass is
  opportunistic.

## Phase 5 — application code cutover (remaining, opportunistic)

Do this **per service, as its own PR, with that service's test suite run.** The DB
compatibility layer means each can ship independently and be rolled back
independently. Order: student-api → admin-api → panel-api → mentor-api →
backend/app → frontends.

For each service: copy `team_uid_resolver.py` (backends) or `teamUid.js`
(frontends) into the service, then:

### backend/student-api  (`app/api/student_portal.py` ~54 sites, `app/core/supabase_client.py`, `app/core/github_sync_scheduler.py`)
- Replace `parse_numeric_team_id`, `extract_numeric_id`, the `raw_team_id_str /
  canonical_team_id / team_uid_val` "variants" logic, and the
  `teamId`/`team_uid` dual-column searches with a single
  `uid = resolve_team_uid(client, student.team_membership.team_id)`.
- `gh_filter` (line ~353): always `team_uid=eq.{uid}`, never
  `team_id=eq.{numeric_team_id}`.
- API responses: add `team_uid`; keep `team_id` as an alias = the uid string;
  add `team_display_number`.
- `supabase_client.get_team_by_student_id`: query `team_memberships` by
  `student_roll` then `team_by_uid`, instead of scanning `teams_validation.members`.

### backend/admin-api  (`app/main.py` ~29 heuristic + ~60 `teams_validation` sites, `app/mentor_allocation_agent/agent.py`, `presentation_reminder_service.py`, `services/chat_report.py`)
- Every `.table("teams_validation").eq("id", <x>)` → resolve `<x>` to a uid then
  `.eq("uid", uid)`. `.update(...).eq("id", id)` likewise.
- `main.py:2642` reconciliation of `teams` vs `teams_validation` by `team_number`
  → delete; use `team_uid_map` / `resolve_team_uid`.
- `main.py:268`, `main.py:2001-2059` title/number renumbering → keep (numbers are
  display), but stop treating the number as identity anywhere else.
- Stop writing `public.teams` (int) — write `teams_validation` only. The
  `trg_map_new_team` trigger keeps the crosswalk fresh in the meantime.

### backend/panel-api  (`app/db_helpers.py` ~21 sites, `routers/panel.py` 6, `routers/evaluation.py` 13, `routers/admin.py` 7, `slot_service.py` 8, `scheduler.py`, `routers/mentor.py`)
- **Biggest behavioural change**: this service is 100% on the legacy int
  `teams` table. `to_numeric_id` / `from_numeric_id` / `resolve_team_string_id`
  → replace with `resolve_team_uid` + `team_by_uid`.
- `client.table("teams").select(...).eq("id", team_id)` → `team_by_uid`.
- `client.table("teams").insert/upsert(...)` (`slot_service.py:128`, `seed.py:63`,
  `routers/admin.py:322`) → write `teams_validation`; never create `teams` rows.
- multi-active-semester: `db_helpers.py` already fetches `active_sem_ids` as a
  set — keep that; it is correct.

### backend/mentor-api  (`app/api/mentor_portal.py` ~16, `app/main.py:183`, `services/team_progress.py`, `services/chat_report.py`, `core/auth.py`)
- `app/main.py:183` `semester_config?is_active=eq.true&limit=1` → fetch ALL
  active, iterate (multiple active semesters is by design — different B.Tech
  years).
- team lookups → `resolve_team_uid` / `team_by_uid`.

### backend/app  (`app/services/governance_service.py:24`, `app/api/student_portal.py`, `app/api/student_deps.py`)
- `governance_service.py:24` `.where(is_active == True).limit(1)` → aggregate
  across all active semesters.

### frontends  (apps/admin, apps/main, apps/panel, apps/student, apps/mentor)
- `apps/admin/src/lib/teamUtils.js` `findMatchingTeam` → replace the 6-level
  fuzzy cascade with `sameTeam()` / `indexTeamsByUid()` on `team_uid`.
- `apps/admin/src/lib/globalFilters.js` `teamNumberFromId` / `resolveTeamNumber`
  → keep ONLY inside `teamDisplayLabel`; remove every identity use. Delete the
  "last 3 digits of the UUID as a team number" fallback.
- `cleanUUIDsFromText` becomes unnecessary once the API stops sending
  `<uuid>-Team N` display strings — remove after the API side lands.
- `apps/panel/src/lib/globalFilters.js`, `apps/mentor/src/lib/globalFilters.js`
  same treatment (they are copies).
- Pages: `TeamValidation.jsx`, `Views.jsx`, `ProposalList.jsx`,
  `ProposalViewer.jsx`, `MentorAllocation.jsx`, `Schedule.jsx`, `Results.jsx`,
  `StudentList.jsx`, `MilestonesManager.jsx`, `ProcksiChat.jsx` — join teams by
  `teamUidOf()` from API objects, show `teamDisplayNumber()` for the label.

## Phase 12 — presentation flow cohort-scoping (2026-08-31, `12_presentation_flow_cohort_scoping.sql`)

**Trigger:** pre-check before the first supervised 1st-presentation run. `panel-api`
identifies a team by the bare int `to_numeric_id("<sem>-T<n>")` and fed it to
`db_helpers.resolve_team_uid(int)` / `resolve_results_team_key()`, which resolve
through `team_uid_map` — one uid per int. T1..T125 exist in **both** active
cohorts; `team_uid_map` old_int_id 1..197 are **all** the 3rd-yr cohort. So every
2nd-yr presentation evaluation / result would have been written against the
3rd-yr team's uid, and `sync_team_results_from_evaluations` (results PK = `team`
slug) would have silently overwritten the 3rd-yr team's `results` row. The
`trg_sync_team_uid` triggers only fill NULL `team_uid`, so they don't catch a
wrong non-null value. Nothing was corrupted yet — `schedule_slots` /
`presentation_evaluations` / `evaluations` were still empty.

**Code fix (panel-api only, this repo):** `resolve_team_uid(client, team_id,
semester_id=None)` — new `_semester_team_uid_map()` resolves within one semester
(keys: exact slug, `to_numeric_id(slug)`, `team_number`); with `semester_id` and
no hit it returns `None` and never falls through to the cross-cohort map.
`resolve_results_team_key` / `sync_team_results_from_evaluations` /
`routers/evaluation.py` (×3) / `slot_service.py` / `routers/admin.py`
(`upsert_slots` + `_merge_and_build_eval_results` labelling) all pass / resolve
the semester now. Tests: `backend/panel-api/tests/test_team_uid_cohort_scoping.py`
(+ new `backend/panel-api/pytest.ini`). SQL sim over all 324 active teams: 100%
resolve to their own uid, 0 cross-cohort.

**DB (this script):** deleted 1 empty orphan `results` shell
(`c1707ba6…-T197`, backed up `backup.results_20260831`); added the missing
`team_uid_map` old_int_id 42 (legacy fallback contiguity only). Re-runnable
verification V1–V3 at the bottom of the script — every "want 0" is 0.

## Phase 6 — drop legacy

Rename `99_phase6_drop_legacy.sql.HOLD` → `.sql` and run only after Phase 5 is
fully deployed and has soaked ≥ 2 weeks with a clean verification run. It:
archives the 14 unmapped placeholder teams, drops the sync triggers, drops the
legacy `team_id`/`team_ref`/`teamId` columns, turns `team_members` into a
leader-only view over `team_memberships`, and demotes `public.teams` to a view
over `teams_validation`.

## Rollback

`ROLLBACK.sql` reverses phases 1–4 (all additive). It intentionally keeps the
minted `legacy-teams-297` row and the 4 phase-4 leader backfills (real data);
uncomment the marked block for a total revert.
