# Two Teams Per Problem Statement Design

## Goal

Allow a Problem Statement (PS) to be selected by up to **2 teams** instead of exactly 1, across both the student self-service reservation flow and admin allocation, with no change to how the two teams' work is tracked afterward (they remain fully independent — separate mentor, panel, evaluation, and presentation slot).

## Current Behavior

A PS's "taken" state is derived at read-time by string-matching `problem_statements.title` against titles already present in `teams_validation.title` and `proposals.title` (status = Approved). There is no dedicated allocation table and no DB-level uniqueness constraint — the check is purely application-level, evaluated fresh on every request. Three call sites currently treat this as boolean (taken vs. not taken):

1. `backend/student-api/app/api/student_portal.py:1936` — `get_allocated_project_titles()` returns a `set` of taken titles (lower-cased), built from `teams_validation` + approved `proposals`.
2. `backend/student-api/app/api/student_portal.py:1965` (`GET /problem-statements`) — sets `is_allocated = title in allocated_titles` per PS returned to students.
3. `backend/student-api/app/api/student_portal.py:3323` (`POST /team/reserve-ps`) — rejects reservation if the title is in `allocated_titles`, unless it's the reserving team's own current title.
4. `apps/admin/src/pages/ProjectAllocation.jsx:302` (`handleBulkAllocate`) and `handleAllocate` (line 255) — build an `allocatedTitles` `Set` and exclude any PS already in it from the assignable pool.

## Behavior Change

Replace "is this title taken" with "does this title have fewer than 2 teams." The cap (2) is a fixed constant, not a per-PS field — every PS gets the same limit, no admin configuration required.

### Backend

- `get_allocated_project_titles()` returns a `dict[str, int]` — lower-cased title → count of teams/approved-proposals currently holding it — instead of a `set`. Rename to `get_project_title_counts()`; keep call sites updated.
- `GET /problem-statements`: `team_count = counts.get(title_lower, 0)`; `is_allocated = team_count >= 2` (now means "full," not "taken"). Add `team_count` to the response payload for each PS.
- `POST /team/reserve-ps`: reject only when `team_count >= 2` **and** the reserving team's current `project_title` does not already equal the target title — this is the existing self-reservation carve-out (`student_portal.py:3357-3359`), unchanged, just re-evaluated against `>= 2` instead of "title in set."

### Admin bulk/manual allocation (`apps/admin/src/pages/ProjectAllocation.jsx`)

- Replace the `allocatedTitles` `Set` with a title → count map, seeded from the current `teams_validation` snapshot.
- `handleBulkAllocate` runs two passes over the unallocated-teams list (priority/preference teams first, then the rest, same ordering as today):
  - **Pass 1:** assign only from PS currently at count 0, incrementing the map as each team is assigned.
  - **Pass 2:** for any teams still unassigned after pass 1, assign from PS currently at count 1 (bringing them to 2).
  - Teams still unassigned after both passes (more unallocated teams than 2× PS pool) are left unallocated, matching current overflow behavior.
- `handleAllocate` (manual single-team assignment): the PS picker must allow selecting a PS at count 1 (not just count 0), and must continue to exclude PS at count 2.

### Student UI

- `apps/student/src/pages/PreferencesView.jsx`: reserve button continues to key off `is_allocated` (now "full" at count 2) — no logic change. Add a small text/badge using the new `team_count` field so a partially-filled PS (count 1) reads as "1 team already selected this — 1 spot left" rather than looking identical to an untouched PS.
- `apps/student/src/components/PsArchitecturePlanModal.jsx:753`: the "Allocated to X" badge currently assumes a single team. Update to handle 0, 1, or 2 teams holding the PS — e.g., list each team's label, or show "1/2 teams allocated" alongside team names when more than one holds it.

## Scope

Changes are confined to:
- `backend/student-api/app/api/student_portal.py` (title-count logic + the two endpoints above)
- `apps/admin/src/pages/ProjectAllocation.jsx` (bulk + manual allocation)
- `apps/student/src/pages/PreferencesView.jsx` and `apps/student/src/components/PsArchitecturePlanModal.jsx` (display only)

No database migration, no new tables/columns, no changes to mentor assignment, evaluation, panel, or presentation-slot logic — the two teams sharing a PS remain otherwise fully independent.

## Verification

- Backend test: reserving a PS already held by 1 team succeeds for a 2nd team; reserving a PS already held by 2 teams is rejected for a 3rd; a team re-submitting its own already-held PS is not blocked by its own count.
- Backend test: `GET /problem-statements` returns `team_count` and `is_allocated` (true only at count ≥ 2) consistent with current `teams_validation`/`proposals` state.
- Frontend/admin test: `handleBulkAllocate` assigns every currently-unallocated team a PS at count 0 before any PS is brought to count 2 (spread-then-double-up), given a mix of teams and PS pool sizes.
- Admin and student frontend production builds succeed.
