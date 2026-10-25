# Dense Team Renumber Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every active-semester team display and resolve through `team_number`, then safely renumber the ten outlier teams into a dense 1–193 sequence.

**Architecture:** Immutable `teams_validation.uid` and `teams_validation.id` remain ownership keys. Portal payloads expose `team_number`, display helpers prefer it, and repository operations use immutable `team_ref`; one guarded SQL transaction backs up and updates the ten display labels plus denormalized GitHub labels.

**Tech Stack:** React/Vite, Node test runner, FastAPI/Python, PostgreSQL/Supabase MCP.

## Global Constraints

- Never modify `teams_validation.uid` or `teams_validation.id`.
- Preserve membership and proposal ownership by immutable UID.
- Back up every changed/deleted production row in `renumber_stale_backup_20260808`.
- Abort the transaction unless the mapping exactly matches the approved ten-row map.
- Do not renumber legacy `teams.id` or its integer foreign keys.

---

### Task 1: Admin display numbers prefer `team_number`

**Files:**
- Modify: `apps/admin/src/pages/TeamValidation.jsx:124-151`
- Modify: `apps/admin/src/lib/teamUtils.js:32-33`
- Create: `apps/admin/tests/dense-team-number-resolution.test.mjs`

**Interfaces:**
- Consumes: raw `teams_validation` rows containing `id` and `team_number`.
- Produces: mapped team objects retaining `team_number`; `teamNumber(value, row)` resolves explicit display labels before immutable-ID suffixes.

- [ ] **Step 1: Write the failing regression test**

```js
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('admin team mapping retains mutable display number', async () => {
  const source = await readFile(new URL('../src/pages/TeamValidation.jsx', import.meta.url), 'utf8');
  assert.match(source, /team_number:\s*t\.team_number/);
});

test('teamNumber prefers an explicit row number', async () => {
  const source = await readFile(new URL('../src/lib/teamUtils.js', import.meta.url), 'utf8');
  assert.match(source, /teamNumber\(teamId,\s*row\s*=\s*null\)/);
  assert.match(source, /resolveTeamNumber\(teamId,\s*row\)/);
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `node --test apps/admin/tests/dense-team-number-resolution.test.mjs`

Expected: both assertions fail because the mapped row discards `team_number` and `teamNumber` accepts only an ID.

- [ ] **Step 3: Implement the minimal admin compatibility change**

Add `team_number: t.team_number` to the mapped object in `TeamValidation.jsx`.

Change `teamUtils.js` to:

```js
export function teamNumber(teamId, row = null) {
    return resolveTeamNumber(teamId, row);
}
```

At call sites operating on a mapped team, pass the row: `teamNumber(team.uuid, team)`.

- [ ] **Step 4: Run focused tests and build**

Run: `node --test apps/admin/tests/dense-team-number-resolution.test.mjs apps/admin/tests/proposal-list-serial-number.test.mjs`

Expected: all tests pass.

Run: `npm run build` from `apps/admin`.

Expected: Vite exits 0; existing chunk-size warnings are acceptable.

- [ ] **Step 5: Commit the admin compatibility change**

```powershell
git add -- apps/admin/src/pages/TeamValidation.jsx apps/admin/src/lib/teamUtils.js apps/admin/tests/dense-team-number-resolution.test.mjs
git commit -m "fix: prefer explicit admin team numbers"
```

---

### Task 2: Student payloads and repository ownership survive renumbering

**Files:**
- Modify: `backend/student-api/app/api/student_deps.py:288-320`
- Modify: `backend/student-api/app/api/student_portal.py:3260-3269`
- Modify: `backend/student-api/app/api/student_portal.py:3391-3485`
- Create: `apps/student/tests/dense-team-number-resolution.test.mjs`

**Interfaces:**
- Consumes: `team_data.id`, `team_data.uid`, and `team_data.team_number` from `teams_validation`.
- Produces: student team objects with `team_number`; repository queries keyed by immutable `team_ref`.

- [ ] **Step 1: Write the failing source-contract regression test**

```js
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('student team payload carries the explicit display number', async () => {
  const source = await readFile(new URL('../../../backend/student-api/app/api/student_deps.py', import.meta.url), 'utf8');
  assert.match(source, /team_number=team_data\.get\("team_number"\)/);
  assert.match(source, /display_number\s*=\s*team_data\.get\("team_number"\)/);
});

test('project repository reads use immutable team_ref', async () => {
  const source = await readFile(new URL('../../../backend/student-api/app/api/student_portal.py', import.meta.url), 'utf8');
  assert.match(source, /WHERE team_ref = :team_ref/);
  assert.doesNotMatch(source, /SELECT repository_url FROM github_data WHERE team_id = :team_id/);
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `node --test apps/student/tests/dense-team-number-resolution.test.mjs`

Expected: fails because student objects derive their display label from the immutable ID and repository reads use numeric `team_id`.

- [ ] **Step 3: Implement display and immutable repository resolution**

In `student_deps.py`, compute:

```python
display_number = team_data.get("team_number")
display_name = (
    f"Team {display_number}"
    if display_number is not None
    else get_clean_team_name(team_id=raw_id, raw_name=tv_title, tv_id=raw_id)
)
```

Include both `uid=team_data.get("uid")` and `team_number=display_number` in the `RESTObject`.

In both project-details handlers, query/upsert `github_data` through the full immutable team reference (`str(team.id)`) and persist the denormalized numeric `team_id` from `team.team_number` only as an auxiliary label.

- [ ] **Step 4: Run focused tests and syntax validation**

Run: `node --test apps/student/tests/dense-team-number-resolution.test.mjs apps/student/tests/project-blueprint-approved-proposal-fallback.test.mjs apps/student/tests/project-blueprint-allocation-status.test.mjs`

Expected: all tests pass.

Run:

```powershell
py -c "import ast,pathlib; files=['backend/student-api/app/api/student_deps.py','backend/student-api/app/api/student_portal.py']; [ast.parse(pathlib.Path(f).read_text(encoding='utf-8')) for f in files]; print('Python syntax OK')"
```

Expected: `Python syntax OK`.

- [ ] **Step 5: Commit the student compatibility change**

```powershell
git add -- backend/student-api/app/api/student_deps.py backend/student-api/app/api/student_portal.py apps/student/tests/dense-team-number-resolution.test.mjs
git commit -m "fix: keep student team ownership stable across renumbering"
```

---

### Task 3: Back up and execute the production renumber

**Files:**
- No repository files modified.
- Production tables: `teams_validation`, `github_data`, `github_agent_analysis`, `team_join_requests`, `renumber_stale_backup_20260808`.

**Interfaces:**
- Consumes: the approved old→new mapping and immutable team UIDs.
- Produces: dense active-semester display labels 1–193 with unchanged IDs, UIDs, memberships, and proposal ownership.

- [ ] **Step 1: Re-run the read-only preflight immediately before mutation**

Use a CTE ordered by `team_number, uid`; assert 193 rows, ten changes, free targets 184–193, and the exact mapping from the design document.

- [ ] **Step 2: Execute one guarded transaction**

The transaction must:

1. Acquire `pg_advisory_xact_lock(hashtextextended('dense-team-renumber:c1707ba6-d426-4dcb-a23f-aa22c1bb11c9',0))`.
2. Lock the ten `teams_validation` rows.
3. Back up the ten teams, linked GitHub rows, linked analysis rows, and the mapping manifest.
4. Back up and delete the stale Team 964 analysis containing `Nikhil-cloudexpert/BeanVision_AI`.
5. Update the ten `team_number` values by immutable UID.
6. Rename only placeholder titles matching `^Team <old>$`.
7. Update `github_data.team_id` and `github_agent_analysis.team_id` by immutable UID/reference.
8. Change the declined historical request's display-only `team_name` from `Team 958` to `Team 184` while preserving `team_id` and `team_uid`.
9. Insert a completion manifest and commit.

- [ ] **Step 3: Verify invariants in fresh queries**

Verify:

```sql
select count(*),min(team_number),max(team_number),count(distinct team_number)
from teams_validation
where semester_id='c1707ba6-d426-4dcb-a23f-aa22c1bb11c9';
```

Expected: `193, 1, 193, 193`.

Also assert:

- zero mismatches between GitHub numeric labels and their immutable team rows;
- zero proposal UID/team-ID ownership mismatches;
- membership counts and team UIDs unchanged from the backup manifest;
- Team 193 is Nikhil's team with the coffee-bean proposal and its newly uploaded repository;
- Team 189 is Nishant's team with no proposal/repository and no stale Nikhil analysis.

- [ ] **Step 4: Record the verified result**

Do not create a schema migration: this is a backed-up data correction, not DDL. Report the mapping, backup tags, verification results, application deployment requirement, and rollback method.
