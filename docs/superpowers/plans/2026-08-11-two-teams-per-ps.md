# Two Teams Per Problem Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let up to 2 teams hold the same Problem Statement (PS), everywhere a PS's "taken" state currently gates behavior — student self-reservation, admin bulk allocation, admin manual allocation, and the "Allocated" badges in both apps — while keeping the two teams fully independent downstream (mentor, panel, evaluation, presentation slot unaffected).

**Architecture:** Every place that currently asks "is this title taken" (a boolean, backed by string-matching `problem_statements.title` against `teams_validation`/`proposals`) is changed to ask "how many teams hold this title, and is that below the cap of 2." No schema change — capacity is a fixed constant (`2`), computed live from existing tables, same as today. Backend and admin-frontend each get one new pure, independently-testable module holding the counting/decision logic, so the capacity rule has a single source of truth per codebase and is tested with real assertions rather than UI rendering.

**Tech Stack:** FastAPI + Supabase REST client (Python, `unittest`) for the backend; React (Vite) for `apps/admin` and `apps/student`, tested with Node's built-in `node:test` (this repo has no component-rendering test runner — existing tests either exercise pure functions directly or regex-match component source, per `apps/admin/tests/proposal-list-serial-number.test.mjs` and `apps/student/tests/project-blueprint-allocation-status.test.mjs`).

## Global Constraints

- Capacity is a fixed constant of 2 for every PS — no per-PS configuration field (per spec, "Every PS, fixed cap of 2").
- The two teams sharing a PS remain fully independent — no changes to mentor assignment, evaluation, panel, or presentation-slot logic.
- No database migration, no new tables/columns.
- Admin bulk allocation must spread teams across distinct PS (count 0) before doubling any PS up to count 1 → 2 (spec: "spread first, then double up").
- A team re-submitting/re-syncing its own already-held PS must never be blocked by its own count.

---

## Task 1: Backend — pure capacity-decision helper

**Files:**
- Modify: `backend/student-api/app/api/student_portal.py` (add near `is_placeholder_title`, currently at line 1922)
- Test: `backend/student-api/tests/test_ps_reservation_capacity.py`

**Interfaces:**
- Produces: `PS_TEAM_CAPACITY: int = 2` and `is_ps_reservation_allowed(team_count: int, current_team_title: str | None, ps_title: str, capacity: int = PS_TEAM_CAPACITY) -> bool`, both importable from `app.api.student_portal`. Later tasks call this to decide whether a reservation may proceed.

- [ ] **Step 1: Write the failing test**

Create `backend/student-api/tests/test_ps_reservation_capacity.py`:

```python
import unittest

from app.api.student_portal import PS_TEAM_CAPACITY, is_ps_reservation_allowed


class PsReservationCapacityTests(unittest.TestCase):
    def test_capacity_constant_is_two(self):
        self.assertEqual(PS_TEAM_CAPACITY, 2)

    def test_allows_reservation_when_no_team_holds_it(self):
        self.assertTrue(is_ps_reservation_allowed(0, None, "Smart Grid"))

    def test_allows_a_second_team(self):
        self.assertTrue(is_ps_reservation_allowed(1, None, "Smart Grid"))

    def test_blocks_a_third_team(self):
        self.assertFalse(is_ps_reservation_allowed(2, None, "Smart Grid"))

    def test_allows_the_current_holder_to_resubmit_even_when_full(self):
        self.assertTrue(is_ps_reservation_allowed(2, "Smart Grid", "Smart Grid"))

    def test_current_holder_check_is_case_and_whitespace_insensitive(self):
        self.assertTrue(is_ps_reservation_allowed(2, "  smart grid  ", "Smart Grid"))

    def test_a_different_team_title_does_not_grant_exemption(self):
        self.assertFalse(is_ps_reservation_allowed(2, "Other Title", "Smart Grid"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: FAIL/ERROR — `ImportError: cannot import name 'PS_TEAM_CAPACITY'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/student-api/app/api/student_portal.py`, immediately above `def is_placeholder_title(...)` (line 1922), add:

```python
PS_TEAM_CAPACITY = 2


def is_ps_reservation_allowed(
    team_count: int,
    current_team_title: str | None,
    ps_title: str,
    capacity: int = PS_TEAM_CAPACITY,
) -> bool:
    if current_team_title and current_team_title.strip().lower() == ps_title.strip().lower():
        return True
    return team_count < capacity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/student-api/app/api/student_portal.py backend/student-api/tests/test_ps_reservation_capacity.py
git commit -m "feat: add PS reservation capacity helper (cap of 2 teams per PS)"
```

---

## Task 2: Backend — title counts instead of a taken/untaken set

**Files:**
- Modify: `backend/student-api/app/api/student_portal.py:1936` (`get_allocated_project_titles`)
- Test: `backend/student-api/tests/test_ps_reservation_capacity.py` (extend)

**Interfaces:**
- Consumes: nothing new (reuses `supabase_client._request`, `is_placeholder_title` already in this file).
- Produces: `async def get_project_title_counts() -> dict[str, int]` — lower-cased title → number of teams/approved-proposals currently holding it. Replaces `get_allocated_project_titles`. Task 3 consumes this.

- [ ] **Step 1: Write the failing test**

Append to `backend/student-api/tests/test_ps_reservation_capacity.py`:

```python
import unittest
from unittest.mock import AsyncMock, patch

from app.api.student_portal import get_project_title_counts


class ProjectTitleCountsTests(unittest.IsolatedAsyncioTestCase):
    async def test_counts_teams_and_approved_proposals_by_normalized_title(self):
        async def fake_request(path, method="GET", body=None, headers=None):
            if path == "teams_validation?select=title":
                return [{"title": "Smart Grid"}, {"title": " smart grid "}, {"title": "Team 12"}]
            if path == "proposals?status=eq.Approved&select=title":
                return [{"title": "Smart Grid"}, {"title": "Other Topic"}]
            return []

        with patch("app.core.supabase_client.supabase_client._request", new=AsyncMock(side_effect=fake_request)):
            counts = await get_project_title_counts()

        self.assertEqual(counts["smart grid"], 3)
        self.assertEqual(counts["other topic"], 1)
        self.assertNotIn("team 12", counts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_project_title_counts'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/student-api/app/api/student_portal.py`, replace the function at line 1936 (`async def get_allocated_project_titles() -> set:`) — read the current body first (lines 1936-1961+) and change its return type from a `set` accumulator to a `dict[str, int]` counter, keeping every existing source query and the `is_placeholder_title` filtering untouched:

```python
async def get_project_title_counts() -> dict:
    from app.core.supabase_client import supabase_client
    title_counts: dict[str, int] = {}

    def add_title(title):
        if title and not is_placeholder_title(title):
            key = title.strip().lower()
            title_counts[key] = title_counts.get(key, 0) + 1

    # 1. Fetch from teams_validation
    try:
        teams = await supabase_client._request("teams_validation?select=title")
        for t in (teams or []):
            add_title(t.get("title"))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch allocated titles from teams_validation: {e}")

    # 2. Fetch from proposals (status = Approved)
    try:
        proposals = await supabase_client._request("proposals?status=eq.Approved&select=title")
        for p in (proposals or []):
            add_title(p.get("title"))
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch allocated titles from proposals: {e}")

    return title_counts
```

Then rename every call site of `get_allocated_project_titles` in this file (the `GET /problem-statements` handler at line 1965 and `POST /team/reserve-ps` at line 3323 — both edited fully in Task 3) to call `get_project_title_counts`. If the function body originally continued past line 1961 with more sources beyond `teams_validation`/`proposals`, preserve those sources too, converting each to call `add_title(...)` the same way.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: PASS (8 tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/student-api/app/api/student_portal.py backend/student-api/tests/test_ps_reservation_capacity.py
git commit -m "refactor: track PS title allocation counts instead of a taken/untaken set"
```

---

## Task 3: Backend — wire counts into the two endpoints

**Files:**
- Modify: `backend/student-api/app/api/student_portal.py:1965` (`GET /problem-statements`) and `:3323` (`POST /team/reserve-ps`)
- Test: `backend/student-api/tests/test_ps_reservation_capacity.py` (extend)

**Interfaces:**
- Consumes: `PS_TEAM_CAPACITY`, `is_ps_reservation_allowed` (Task 1), `get_project_title_counts` (Task 2).
- Produces: `GET /problem-statements` response items gain `team_count: int`; `is_allocated` now means `team_count >= PS_TEAM_CAPACITY`. `POST /team/reserve-ps` rejects only when full and the requester isn't the current holder.

- [ ] **Step 1: Write the failing test**

Because this repo has no FastAPI `TestClient` usage anywhere (confirmed: no test imports it), endpoint wiring is verified the same way the rest of this file's non-trivial branches are — by asserting the endpoint source uses the new helpers, so a future edit that reverts to boolean set-membership breaks the build. Append to `backend/student-api/tests/test_ps_reservation_capacity.py`:

```python
import inspect
from app.api import student_portal


class EndpointWiringTests(unittest.TestCase):
    def test_get_problem_statements_reports_team_count_and_capacity_based_is_allocated(self):
        source = inspect.getsource(student_portal.get_problem_statements)
        self.assertIn("get_project_title_counts", source)
        self.assertIn("team_count", source)
        self.assertIn("PS_TEAM_CAPACITY", source)

    def test_reserve_problem_statement_uses_the_capacity_helper(self):
        source = inspect.getsource(student_portal.reserve_problem_statement)
        self.assertIn("is_ps_reservation_allowed", source)
        self.assertIn("get_project_title_counts", source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: FAIL — both new assertions fail (old source still says `get_allocated_project_titles` / set membership).

- [ ] **Step 3: Write minimal implementation**

In `GET /problem-statements` (currently lines 1965-1990), replace:

```python
    allocated_titles = await get_allocated_project_titles()
    
    # Do not filter out already booked/allocated problem statements;
    # instead, flag them with an `is_allocated` boolean field.
    for s in (statements or []):
        title = s.get("title")
        s["is_allocated"] = bool(title and title.strip().lower() in allocated_titles)
```

with:

```python
    title_counts = await get_project_title_counts()
    
    # Do not filter out already booked/allocated problem statements;
    # instead, flag them with a `team_count` and an `is_allocated` boolean
    # meaning "at capacity" (PS_TEAM_CAPACITY teams already hold it).
    for s in (statements or []):
        title = s.get("title")
        count = title_counts.get(title.strip().lower(), 0) if title else 0
        s["team_count"] = count
        s["is_allocated"] = count >= PS_TEAM_CAPACITY
```

In `POST /team/reserve-ps` (currently lines 3323-3387), replace:

```python
    # Check if this statement is already reserved by another team
    allocated_titles = await get_allocated_project_titles()
    ps_title = ps.get("title", "")
    if ps_title.strip().lower() in allocated_titles:
        # Check if it was reserved by THIS team
        curr_title = (team.project_title or "").strip().lower()
        if curr_title != ps_title.strip().lower():
            raise HTTPException(status_code=400, detail="This topic has already been reserved by another team.")
```

with:

```python
    # Check if this statement is at capacity (PS_TEAM_CAPACITY teams already hold it)
    title_counts = await get_project_title_counts()
    ps_title = ps.get("title", "")
    team_count = title_counts.get(ps_title.strip().lower(), 0)
    if not is_ps_reservation_allowed(team_count, team.project_title, ps_title):
        raise HTTPException(status_code=400, detail="This topic has already been reserved by the maximum number of teams.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend/student-api && python -m pytest tests/test_ps_reservation_capacity.py -v`
Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/student-api/app/api/student_portal.py backend/student-api/tests/test_ps_reservation_capacity.py
git commit -m "feat: allow up to 2 teams to reserve the same problem statement"
```

---

## Task 4: Admin — pure allocation-capacity module

**Files:**
- Create: `apps/admin/src/lib/psAllocation.js`
- Test: `apps/admin/tests/ps-allocation.test.mjs`

**Interfaces:**
- Produces: `PS_TEAM_CAPACITY`, `normalizePsTitle(title)`, `buildAllocationsByTitle(teams, getHasAllocated)` → `Map<normalizedTitle, teamRow[]>`, `isPsAvailableForTeam(allocationsByTitle, psTitle, teamId, capacity = PS_TEAM_CAPACITY)` → `boolean`, `computeBulkAllocations({ priorityTeams, randomTeams, problemStatements, titleCounts, capacity = PS_TEAM_CAPACITY })` → `Map<item, { title, description, domain }>`. Tasks 5 and 6 import all of these.
- `priorityTeams`/`randomTeams` items have shape `{ prefRecord: { preferences: [{ title, description, domain }], updated_at } | null, teamYear }` (only `prefRecord` and `teamYear` are read).

- [ ] **Step 1: Write the failing test**

Create `apps/admin/tests/ps-allocation.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
    PS_TEAM_CAPACITY,
    normalizePsTitle,
    buildAllocationsByTitle,
    isPsAvailableForTeam,
    computeBulkAllocations,
} from '../src/lib/psAllocation.js';

test('PS_TEAM_CAPACITY is 2', () => {
    assert.equal(PS_TEAM_CAPACITY, 2);
});

test('normalizePsTitle trims and lower-cases', () => {
    assert.equal(normalizePsTitle('  Smart Grid  '), 'smart grid');
    assert.equal(normalizePsTitle(null), '');
});

test('buildAllocationsByTitle groups allocated teams by normalized title and skips unallocated/placeholder ones', () => {
    const teams = [
        { id: 't1', title: 'Smart Grid' },
        { id: 't2', title: ' smart grid ' },
        { id: 't3', title: 'Team 12' },
        { id: 't4', title: '' },
    ];
    const getHasAllocated = (t) => t.id === 't1' || t.id === 't2';
    const map = buildAllocationsByTitle(teams, getHasAllocated);
    assert.deepEqual(map.get('smart grid').map(t => t.id), ['t1', 't2']);
    assert.equal(map.has('team 12'), false);
    assert.equal(map.has(''), false);
});

test('isPsAvailableForTeam allows a 2nd team, blocks a 3rd, and always allows the current holder', () => {
    const oneHolder = buildAllocationsByTitle([{ id: 't1', title: 'Smart Grid' }], () => true);
    assert.equal(isPsAvailableForTeam(oneHolder, 'Smart Grid', 't2'), true);

    const twoHolders = buildAllocationsByTitle(
        [{ id: 't1', title: 'Smart Grid' }, { id: 't2', title: 'Smart Grid' }],
        () => true,
    );
    assert.equal(isPsAvailableForTeam(twoHolders, 'Smart Grid', 't3'), false);
    assert.equal(isPsAvailableForTeam(twoHolders, 'Smart Grid', 't1'), true);
});

test('computeBulkAllocations spreads across distinct PS before doubling any of them up', () => {
    const problemStatements = [
        { title: 'PS A', year: 3 },
        { title: 'PS B', year: 3 },
    ];
    const teams = ['t1', 't2', 't3', 't4'].map(id => ({ id, prefRecord: null, teamYear: 3 }));
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });

    assert.equal(assignments.size, 4);
    const tally = new Map();
    for (const item of teams) {
        const title = assignments.get(item).title;
        tally.set(title, (tally.get(title) || 0) + 1);
    }
    assert.deepEqual([...tally.values()].sort(), [2, 2]);
});

test('computeBulkAllocations leaves teams unallocated once every PS is at capacity', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }];
    const teams = ['t1', 't2', 't3'].map(id => ({ id, prefRecord: null, teamYear: 3 }));
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });
    assert.equal(assignments.size, 2);
});

test('computeBulkAllocations honors a priority team preference before any random fallback', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }, { title: 'PS B', year: 3 }];
    const priorityItem = { id: 'p1', prefRecord: { preferences: [{ title: 'PS B' }], updated_at: null }, teamYear: 3 };
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [priorityItem], randomTeams: [], problemStatements, titleCounts });
    assert.equal(assignments.get(priorityItem).title, 'PS B');
});

test('computeBulkAllocations only assigns a 2nd team to a PS once no zero-count PS remains for that team', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }];
    const titleCounts = new Map([['ps a', 1]]);
    const teams = [{ id: 't1', prefRecord: null, teamYear: 3 }];
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });
    assert.equal(assignments.get(teams[0]).title, 'PS A');
    assert.equal(titleCounts.get('ps a'), 2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/admin/tests/ps-allocation.test.mjs`
Expected: FAIL — `Cannot find module '../src/lib/psAllocation.js'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/admin/src/lib/psAllocation.js`:

```js
export const PS_TEAM_CAPACITY = 2;

export function normalizePsTitle(title) {
    return (title || '').trim().toLowerCase();
}

export function buildAllocationsByTitle(teams, getHasAllocated) {
    const map = new Map();
    for (const team of teams) {
        if (!team.title || !getHasAllocated(team)) continue;
        const key = normalizePsTitle(team.title);
        if (key === '' || key === 'custom team') continue;
        const existing = map.get(key);
        if (existing) existing.push(team);
        else map.set(key, [team]);
    }
    return map;
}

export function isPsAvailableForTeam(allocationsByTitle, psTitle, teamId, capacity = PS_TEAM_CAPACITY) {
    const holders = allocationsByTitle.get(normalizePsTitle(psTitle)) || [];
    if (holders.some(t => t.id === teamId)) return true;
    return holders.length < capacity;
}

export function computeBulkAllocations({ priorityTeams, randomTeams, problemStatements, titleCounts, capacity = PS_TEAM_CAPACITY }) {
    const assignments = new Map();

    const availableForYear = (year, ceiling) => problemStatements.filter(ps => {
        const matchesYear = (ps.year === null || ps.year === undefined || Number(ps.year) === Number(year));
        if (!matchesYear) return false;
        const count = titleCounts.get(normalizePsTitle(ps.title)) || 0;
        return count < ceiling;
    });

    const hasPreferences = (item) => item.prefRecord && Array.isArray(item.prefRecord.preferences) && item.prefRecord.preferences.length > 0;

    const tryAssignFromPreferences = (item, ceiling) => {
        for (const pref of item.prefRecord.preferences) {
            const prefTitle = normalizePsTitle(pref.title);
            const count = titleCounts.get(prefTitle) || 0;
            if (count >= ceiling) continue;
            const matchedPS = problemStatements.find(ps => normalizePsTitle(ps.title) === prefTitle);
            const matchesYear = !matchedPS || matchedPS.year === null || matchedPS.year === undefined || Number(matchedPS.year) === Number(item.teamYear);
            if (!matchesYear) continue;
            titleCounts.set(prefTitle, count + 1);
            assignments.set(item, { title: pref.title, description: pref.description || '', domain: pref.domain || 'General' });
            return true;
        }
        return false;
    };

    const tryAssignRandom = (item, ceiling) => {
        const pool = availableForYear(item.teamYear, ceiling);
        if (pool.length === 0) return false;
        const chosenPS = pool[Math.floor(Math.random() * pool.length)];
        const title = normalizePsTitle(chosenPS.title);
        titleCounts.set(title, (titleCounts.get(title) || 0) + 1);
        assignments.set(item, { title: chosenPS.title, description: chosenPS.description || '', domain: chosenPS.domain || 'General' });
        return true;
    };

    // Pass 1: only PS with zero current teams (ceiling 1 => count must be < 1).
    const unresolved = [];
    for (const item of priorityTeams) {
        if (!tryAssignFromPreferences(item, 1)) unresolved.push(item);
    }
    for (const item of randomTeams) {
        if (!tryAssignRandom(item, 1)) unresolved.push(item);
    }

    // Pass 2: PS with one existing team may now take a second.
    for (const item of unresolved) {
        if (hasPreferences(item) && tryAssignFromPreferences(item, capacity)) continue;
        tryAssignRandom(item, capacity);
    }

    return assignments;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/admin/tests/ps-allocation.test.mjs`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/lib/psAllocation.js apps/admin/tests/ps-allocation.test.mjs
git commit -m "feat: add pure PS-capacity allocation module for the admin app"
```

---

## Task 5: Admin — wire `ProjectAllocation.jsx` to the capacity module

**Files:**
- Modify: `apps/admin/src/pages/ProjectAllocation.jsx` (imports at line 1-13; `handleBulkAllocate` lines 292-365; `allocatedPsTitleMap`/`getPsAllocation` lines 568-582; `teamAllowedPsMap` lines 626-638; call sites at lines 866, 1123, 1133, 1141, 1190-1191, 1425)
- Test: `apps/admin/tests/ps-allocation-integration.test.mjs`

**Interfaces:**
- Consumes: everything from Task 4's `apps/admin/src/lib/psAllocation.js`.
- Produces: `getPsAllocations(psTitle)` (plural, returns an array) replaces `getPsAllocation`. `apps/admin/src/components/PsArchitecturePlanModal.jsx` (Task 6) is called with an `allocations` array prop instead of a single `allocation` object.

- [ ] **Step 1: Write the failing test**

Create `apps/admin/tests/ps-allocation-integration.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('ProjectAllocation.jsx uses the shared PS capacity module instead of a single-team allocated-titles set', async () => {
    const source = await readFile(new URL('../src/pages/ProjectAllocation.jsx', import.meta.url), 'utf8');

    assert.match(source, /from ['"]\.\.\/lib\/psAllocation['"]/);
    assert.match(source, /computeBulkAllocations\(/);
    assert.match(source, /isPsAvailableForTeam\(/);
    assert.match(source, /buildAllocationsByTitle\(/);
    assert.doesNotMatch(source, /new Set\(\s*\n?\s*teams\s*\n?\s*\.filter\(t => getHasAllocated\(t\)\)/);
    assert.match(source, /getPsAllocations\(/);
    assert.match(source, /allocations=\{getPsAllocations\(selectedPsForAnalysis\.title\)\}/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/admin/tests/ps-allocation-integration.test.mjs`
Expected: FAIL — none of the new symbols are present yet.

- [ ] **Step 3: Write minimal implementation**

In `apps/admin/src/pages/ProjectAllocation.jsx`:

1. Add the import (after the existing `PsArchitecturePlanModal` import at line 13):

```js
import { PS_TEAM_CAPACITY, normalizePsTitle, buildAllocationsByTitle, isPsAvailableForTeam, computeBulkAllocations } from '../lib/psAllocation';
```

2. Replace the body of `handleBulkAllocate` from `const allocatedTitles = new Set(` (line 302) through the closing of the `for (const item of toRandomize) { ... }` loop (line 365) with:

```js
            const titleCounts = new Map(
                Array.from(buildAllocationsByTitle(teams, getHasAllocated)).map(([title, holders]) => [title, holders.length])
            );

            const teamsWithMeta = unallocatedList.map(team => {
                const memberIds = (team.members || []).map(m => String(m.id || m.student_id || m).trim());
                const leaderId = String(team.leader).trim();
                const allIds = [...new Set([leaderId, ...memberIds].filter(Boolean))];
                const prefRecord = preferences.find(p => allIds.includes(String(p.student_id).trim()));
                const teamYear = getTeamYear(team);
                return { team, prefRecord, teamYear, allIds, allocatedProject: null };
            });

            const priorityTeams = teamsWithMeta.filter(item => item.prefRecord && Array.isArray(item.prefRecord.preferences) && item.prefRecord.preferences.length > 0);
            const randomTeams = teamsWithMeta.filter(item => !item.prefRecord || !Array.isArray(item.prefRecord.preferences) || item.prefRecord.preferences.length === 0);

            priorityTeams.sort((a, b) => {
                const timeA = a.prefRecord.updated_at ? new Date(a.prefRecord.updated_at).getTime() : 0;
                const timeB = b.prefRecord.updated_at ? new Date(b.prefRecord.updated_at).getTime() : 0;
                return timeA - timeB;
            });

            const assignments = computeBulkAllocations({ priorityTeams, randomTeams, problemStatements, titleCounts });
            teamsWithMeta.forEach(item => {
                if (assignments.has(item)) item.allocatedProject = assignments.get(item);
            });
```

Note: `teamsWithMeta` was previously defined before the priority/random split and is now defined once above it — remove the old duplicate `teamsWithMeta` declaration that followed `allocatedTitles` in the original code so it isn't declared twice. Everything from the original line 367 onward (`const allocatedTeamsMeta = ...`) is unchanged and still works, since `item.allocatedProject` has the same shape.

3. Replace `allocatedPsTitleMap` (lines 568-576) and `getPsAllocation` (lines 578-582) with:

```js
    const allocationsByTitle = useMemo(
        () => buildAllocationsByTitle(teams, getHasAllocated),
        [teams, proposals]
    );

    const getPsAllocations = (psTitle) => allocationsByTitle.get(normalizePsTitle(psTitle)) || [];
```

4. Replace `teamAllowedPsMap` (lines 626-638):

```js
    const teamAllowedPsMap = useMemo(() => {
        const result = new Map();
        for (const team of teams) {
            const teamYear = getTeamYear(team);
            const allowed = allPsTitlesPool.filter(ps => {
                if (ps.year !== null && ps.year !== undefined && Number(ps.year) !== Number(teamYear)) return false;
                return isPsAvailableForTeam(allocationsByTitle, ps.title, team.id);
            });
            result.set(team.id, allowed);
        }
        return result;
    }, [teams, allPsTitlesPool, allocationsByTitle]);
```

5. At line 866, replace `const isTaken = getPsAllocation(pref.title);` with:

```js
                                                const isTaken = !isPsAvailableForTeam(allocationsByTitle, pref.title, team.id);
```

6. At lines 1123-1124, replace `const allocation = getPsAllocation(ps.title);` with:

```js
                                const psAllocations = getPsAllocations(ps.title);
                                const isPsFull = psAllocations.length >= PS_TEAM_CAPACITY;
```

7. At line 1133, replace the `allocation` reference in the className ternary with `isPsFull`:

```js
                                        className={`p-4 md:p-5 rounded-2xl transition-all duration-300 group cursor-pointer relative overflow-hidden border ${isPsFull
```

8. At line 1141, replace `{!allocation && (` with `{!isPsFull && (`.

9. At lines 1190-1194, replace:

```jsx
                                                         {allocation && (
                                                             <span className="text-[9px] md:text-[10px] font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2 md:px-2.5 py-1 rounded-lg flex items-center gap-1 border border-rose-100 dark:border-rose-900/50" title={teamLabel(allocation.id, allocation, semesterMap)}>
                                                                 <Lock className="w-3 h-3" /> Allocated
                                                             </span>
                                                         )}
```

with:

```jsx
                                                         {psAllocations.length > 0 && (
                                                             <span className="text-[9px] md:text-[10px] font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2 md:px-2.5 py-1 rounded-lg flex items-center gap-1 border border-rose-100 dark:border-rose-900/50" title={psAllocations.map(t => teamLabel(t.id, t, semesterMap)).join(', ')}>
                                                                 <Lock className="w-3 h-3" /> {isPsFull ? 'Allocated' : `${psAllocations.length}/${PS_TEAM_CAPACITY} Allocated`}
                                                             </span>
                                                         )}
```

10. At line 1425, replace `allocation={getPsAllocation(selectedPsForAnalysis.title)}` with `allocations={getPsAllocations(selectedPsForAnalysis.title)}`.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/admin/tests/ps-allocation-integration.test.mjs`
Expected: PASS.

Also re-run Task 4's test to confirm nothing broke: `node --test apps/admin/tests/ps-allocation.test.mjs` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/pages/ProjectAllocation.jsx apps/admin/tests/ps-allocation-integration.test.mjs
git commit -m "feat: allow admin bulk/manual allocation to assign up to 2 teams per PS"
```

---

## Task 6: Admin — `PsArchitecturePlanModal.jsx` multi-team badge

**Files:**
- Modify: `apps/admin/src/components/PsArchitecturePlanModal.jsx:562` (prop signature), `:604-606` (label computation), `:767-776` (badge JSX)
- Test: `apps/admin/tests/ps-architecture-modal-multi-team.test.mjs`

**Interfaces:**
- Consumes: `allocations` array prop (each item shaped like a `teams_validation` row plus optional `team_label`), supplied by Task 5's `ProjectAllocation.jsx`.

- [ ] **Step 1: Write the failing test**

Create `apps/admin/tests/ps-architecture-modal-multi-team.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('admin PsArchitecturePlanModal renders a multi-team allocation badge', async () => {
    const source = await readFile(new URL('../src/components/PsArchitecturePlanModal.jsx', import.meta.url), 'utf8');

    assert.match(source, /allocations\s*=\s*\[\]/);
    assert.match(source, /allocations\.length > 0/);
    assert.match(source, /allocationLabels\.join\(', '\)/);
    assert.doesNotMatch(source, /allocation\s*=\s*null/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/admin/tests/ps-architecture-modal-multi-team.test.mjs`
Expected: FAIL — component still takes a single `allocation` prop.

- [ ] **Step 3: Write minimal implementation**

In `apps/admin/src/components/PsArchitecturePlanModal.jsx`:

1. Line 562, replace:

```js
export default function PsArchitecturePlanModal({ ps, onClose, onGenerateAi, aiGenerating = false, allocation = null, isStudent = false }) {
```

with:

```js
export default function PsArchitecturePlanModal({ ps, onClose, onGenerateAi, aiGenerating = false, allocations = [], isStudent = false }) {
```

2. Lines 601-606, replace:

```js
    // Callers pass the allocated team row, which carries `id`/`title` — not the
    // `team_id`/`team_name` this badge originally read, so it rendered an empty
    // "Allocated to Team ". `team_label` is the caller-resolved display name.
    const allocationLabel = allocation
        ? String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id || '').trim()
        : '';
```

with:

```js
    // Callers pass the allocated team rows, which carry `id`/`title` — not the
    // `team_id`/`team_name` this badge originally read. `team_label` is the
    // caller-resolved display name. Up to PS_TEAM_CAPACITY teams may hold a PS.
    const allocationLabels = allocations
        .map(a => String(a.team_label || a.team_name || a.team_id || a.id || '').trim())
        .filter(Boolean);
```

3. Lines 767-776, replace:

```jsx
                                    {allocation ? (
                                        <div className="px-2.5 py-1 bg-[#6C3CE1]/10 border border-[#6C3CE1]/30 text-[#8B5CF6] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <Users className="w-3 h-3" />
                                            {allocationLabel ? `Allocated to ${allocationLabel}` : 'Allocated'}
                                        </div>
                                    ) : (
                                        <div className="px-2.5 py-1 bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3" /> Available for Selection
                                        </div>
                                    )}
```

with:

```jsx
                                    {allocations.length > 0 ? (
                                        <div className="px-2.5 py-1 bg-[#6C3CE1]/10 border border-[#6C3CE1]/30 text-[#8B5CF6] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <Users className="w-3 h-3" />
                                            {allocationLabels.length > 0 ? `Allocated to ${allocationLabels.join(', ')}` : 'Allocated'} ({allocations.length}/2)
                                        </div>
                                    ) : (
                                        <div className="px-2.5 py-1 bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3" /> Available for Selection
                                        </div>
                                    )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/admin/tests/ps-architecture-modal-multi-team.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/components/PsArchitecturePlanModal.jsx apps/admin/tests/ps-architecture-modal-multi-team.test.mjs
git commit -m "feat: show multiple teams on the admin PS allocation badge"
```

---

## Task 7: Student — partial-fill indicator in `PreferencesView.jsx`

**Files:**
- Modify: `apps/student/src/pages/PreferencesView.jsx:1100-1104`
- Test: `apps/student/tests/preferences-ps-partial-fill.test.mjs`

**Interfaces:**
- Consumes: `ps.team_count` and `ps.is_allocated` from the `GET /problem-statements` response (Task 3). `is_allocated` now means "full" (`team_count >= 2`).

- [ ] **Step 1: Write the failing test**

Create `apps/student/tests/preferences-ps-partial-fill.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('preferences list shows a partial-fill indicator when one team already holds a PS', async () => {
    const source = await readFile(new URL('../src/pages/PreferencesView.jsx', import.meta.url), 'utf8');

    assert.match(source, /!ps\.is_allocated\s*&&\s*Number\(ps\.team_count\)\s*>\s*0/);
    assert.match(source, /Team Already Selected/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/student/tests/preferences-ps-partial-fill.test.mjs`
Expected: FAIL — no partial-fill branch exists yet.

- [ ] **Step 3: Write minimal implementation**

In `apps/student/src/pages/PreferencesView.jsx`, lines 1100-1104, replace:

```jsx
                                                                {ps.is_allocated && (
                                                                    <span className="text-xs font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                                                                        <Lock className="w-3 h-3" /> Allocated
                                                                    </span>
                                                                )}
```

with:

```jsx
                                                                {ps.is_allocated && (
                                                                    <span className="text-xs font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                                                                        <Lock className="w-3 h-3" /> Fully Booked
                                                                    </span>
                                                                )}
                                                                {!ps.is_allocated && Number(ps.team_count) > 0 && (
                                                                    <span className="text-xs font-black uppercase tracking-wider text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                                                                        <Users className="w-3 h-3" /> 1 Team Already Selected
                                                                    </span>
                                                                )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/student/tests/preferences-ps-partial-fill.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/student/src/pages/PreferencesView.jsx apps/student/tests/preferences-ps-partial-fill.test.mjs
git commit -m "feat: show a partial-fill indicator when one team already selected a PS"
```

---

## Task 8: Student — `PsArchitecturePlanModal.jsx` capacity-aware badge

**Files:**
- Modify: `apps/student/src/components/PsArchitecturePlanModal.jsx:753-768`
- Test: `apps/student/tests/project-blueprint-capacity-badge.test.mjs`

**Interfaces:**
- Consumes: `currentPs.team_count`, `currentPs.is_allocated` (Task 3). Neither call site in this app passes an `allocation` prop (confirmed at `PreferencesView.jsx:867` and `:1450`), so the badge is driven entirely by `currentPs` fields.

- [ ] **Step 1: Write the failing test**

Create `apps/student/tests/project-blueprint-capacity-badge.test.mjs`:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('student PS blueprint modal shows team_count in its allocation badge', async () => {
    const source = await readFile(
        new URL('../src/components/PsArchitecturePlanModal.jsx', import.meta.url),
        'utf8',
    );

    assert.match(source, /currentPs\.team_count/);
    assert.match(source, /Fully Booked \(\$\{currentPs\.team_count\}\/2 teams\)/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/student/tests/project-blueprint-capacity-badge.test.mjs`
Expected: FAIL — `currentPs.team_count` is not referenced yet.

- [ ] **Step 3: Write minimal implementation**

In `apps/student/src/components/PsArchitecturePlanModal.jsx`, lines 753-768, replace:

```jsx
                                    {(allocation || currentPs.is_allocated) ? (
                                        <div className="px-2.5 py-1 bg-[#6C3CE1]/10 border border-[#6C3CE1]/30 text-[#8B5CF6] rounded-lg text-xs font-medium flex items-center gap-1">
                                            {/* `allocation` is a team row, so its identifier may be team_label,
                                                team_name, team_id or id; `is_allocated` means it is the viewing
                                                student's own team and carries no row. */}
                                            <Users className="w-3 h-3" /> {allocation
                                                ? (String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id || '').trim()
                                                    ? `Allocated to ${String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id).trim()}`
                                                    : 'Allocated')
                                                : 'Allocated to Your Team'}
                                        </div>
                                    ) : (
                                        <div className="px-2.5 py-1 bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3" /> Available for Selection
                                        </div>
                                    )}
```

with:

```jsx
                                    {(allocation || currentPs.is_allocated) ? (
                                        <div className="px-2.5 py-1 bg-[#6C3CE1]/10 border border-[#6C3CE1]/30 text-[#8B5CF6] rounded-lg text-xs font-medium flex items-center gap-1">
                                            {/* `allocation` is a team row, so its identifier may be team_label,
                                                team_name, team_id or id. `is_allocated` means capacity (2 teams)
                                                is reached and no specific team row was passed in. */}
                                            <Users className="w-3 h-3" /> {allocation
                                                ? (String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id || '').trim()
                                                    ? `Allocated to ${String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id).trim()}`
                                                    : 'Allocated')
                                                : `Fully Booked (${currentPs.team_count}/2 teams)`}
                                        </div>
                                    ) : (
                                        <div className="px-2.5 py-1 bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3" /> {Number(currentPs.team_count) > 0
                                                ? `Available (${currentPs.team_count}/2 teams selected)`
                                                : 'Available for Selection'}
                                        </div>
                                    )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test apps/student/tests/project-blueprint-capacity-badge.test.mjs`
Expected: PASS.

Also re-run the pre-existing regression test to confirm it still passes: `node --test apps/student/tests/project-blueprint-allocation-status.test.mjs` — Expected: PASS (its `Allocated to Your Team` assertion still matches, since that branch is untouched — only the `else` case of the inner ternary changed).

- [ ] **Step 5: Commit**

```bash
git add apps/student/src/components/PsArchitecturePlanModal.jsx apps/student/tests/project-blueprint-capacity-badge.test.mjs
git commit -m "feat: show remaining PS capacity in the student blueprint modal badge"
```

---

## Final Verification

- [ ] Run the full backend suite: `cd backend/student-api && python -m pytest tests -v` — all tests pass.
- [ ] Run all new/updated frontend tests: `node --test apps/admin/tests/*.test.mjs apps/student/tests/*.test.mjs` — all tests pass.
- [ ] Admin frontend production build succeeds: `cd apps/admin && npm run build`.
- [ ] Student frontend production build succeeds: `cd apps/student && npm run build`.
- [ ] Manual smoke test: as one team, reserve a PS; as a second team (same year), reserve the same PS — succeeds. As a third team, attempt the same PS — rejected with "already been reserved by the maximum number of teams." In the admin Project Allocation page, run bulk-allocate with more unallocated teams than problem statements and confirm PS get a 2nd team only after every PS has at least one.
