# Legacy team registry — mentor & panel portals

**Status:** known broken, deliberately deferred. Not scheduled.
**Recorded:** 2026-08-08

## Summary

There are two team registries in this database. The mentor and panel portals read
the wrong one, so **they currently show seed/demo teams and one-person stubs
instead of the real 192 teams.**

| | Authoritative | Legacy |
|---|---|---|
| Tables | `teams_validation` + `team_memberships` | `teams` + `team_members` |
| Teams | 192 real | 250 (seed rows + per-student stubs) |
| Memberships | 496 students | 193, **every team exactly 1 member** |
| Read by | admin portal, student portal | **mentor-api, panel-api** |

Members per team:

| Members | `team_members` (legacy) | `team_memberships` (authoritative) |
|---|---|---|
| 1 | **193 teams** | 18 |
| 2 | 0 | 45 |
| 3 | 0 | 128 |
| 4 | 0 | 1 |

## Why it looks like "two batches are mixed"

The two registries share an integer number space but identify **different groups**.
`teams.id = 57` is Deepak Singh's stub; `teams_validation` team 57 is Jyoti /
Meenal / Parnika. Same "team 57", different people, depending on which portal you
are looking at.

There is **no mapping** between them: zero `teams.name` values match any
`teams_validation.id`. The only usable join is via the single member each stub
carries — all 193 map to authoritative teams that way (191 distinct, 0 unmapped).

## What is in the legacy tables

- `teams` ids 1–11: seed/demo rows created 2026-06-28 — "Delta Force", "Echo
  Systems", "Falcon Stack", "Gridline AI", "Helix Coders". No members, no titles.
- `teams` ids 57–295: one stub per student, named `2026-2027-<n>`. Exactly one
  member each. Not real teams.
- 16 rows whose `name` embeds semester UUIDs that no longer exist
  (`be44b4fe…`, `fbda379f…`, `397f2910…`) — residue from three deleted batches.

## Dependent tables are 100% seed data

Every row in all five points at a seed team with no members. Nothing real would be
lost by clearing them:

| Table | Rows | Real rows |
|---|---|---|
| `alerts` | 52 | 0 |
| `projects` | 25 | 0 |
| `slots` | 10 | 0 |
| `evaluations` | 1 | 0 |
| `evaluation_drafts` | 0 | 0 |

Sample project titles: "Peer Learning Network", "Smart Attendance Analytics",
"Adaptive Timetable Optimizer", "Lab Equipment Tracker".

## Why it has not been fixed

Six foreign keys point at `teams(id)` — `alerts`, `evaluation_drafts`,
`evaluations`, `projects`, `slots`, `team_members` — and roughly 45 files across
three services import the `Team` ORM model. panel-api both reads and *writes* the
table (`client.table("teams").insert(...)`, `app/routers/admin.py:322`);
mentor-api has ~17 ORM query sites across `mentor_service`, `result_service`,
`schedule_service` and `team_service`.

**mentor-api, panel-api and admin-api have zero tests.** A rewrite of their team
access layer cannot be verified here, which is why this was deferred rather than
attempted during an active evaluation cycle.

## Recommended fix when it is picked up

1. Drop the 6 FKs and clear the seed rows — verifiable in SQL, loses nothing real.
2. Replace `teams` / `team_members` with **views** over `teams_validation` /
   `team_memberships`. This corrects both portals with no application changes;
   writes need `INSTEAD OF` triggers (panel-api insert, mentor `team_service`).
3. Retire the ORM models afterwards, with the portals already serving correct data.

Doing (2) before (3) means the risky untested rewrite is optional cleanup rather
than the thing standing between mentors and correct data.

## Related

The student portal is unaffected: `app/api/student_deps.py` builds
`student.team_membership` from `teams_validation` over REST (see the
`RESTObject(...)` construction near the end of `_fetch_student_profile_uncached`),
so it never reads the legacy tables for membership.
