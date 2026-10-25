# Proposals Serial Number Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add contiguous visible-row serial numbers to the admin Project Proposals table.

**Architecture:** Keep numbering entirely in `ProposalList.jsx` by using the index produced by `filtered.map`. Add a lightweight Node source-contract test because the admin app has no component-test framework, then verify the Vite production build.

**Tech Stack:** React 19, Vite 8, Node built-in test runner

## Global Constraints

- The serial-number column is first.
- Numbering restarts at 1 for the current filtered result.
- No API or database changes.

---

### Task 1: Add visible proposal serial numbers

**Files:**
- Create: `apps/admin/tests/proposal-list-serial-number.test.mjs`
- Modify: `apps/admin/src/pages/ProposalList.jsx`

**Interfaces:**
- Consumes: existing `filtered` proposal array
- Produces: first-column `S. No.` header and `index + 1` row value

- [ ] **Step 1: Write the failing source-contract test**

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('proposal table numbers visible filtered rows from one', async () => {
  const source = await readFile(new URL('../src/pages/ProposalList.jsx', import.meta.url), 'utf8');
  assert.match(source, /<th[^>]*>S\. No\.<\/th>/);
  assert.match(source, /filtered\.map\(\(p, index\)\s*=>/);
  assert.match(source, /<td[^>]*>\{index \+ 1\}<\/td>/);
  assert.match(source, /colSpan="7"/);
});
```

- [ ] **Step 2: Run the test and verify RED**

Run: `node --test tests/proposal-list-serial-number.test.mjs` from `apps/admin`.
Expected: FAIL because the `S. No.` header is absent.

- [ ] **Step 3: Implement the minimal table change**

Add the first header cell, change `filtered.map(p =>` to `filtered.map((p, index) =>`, add the first body cell containing `{index + 1}`, and change the empty-state `colSpan` from `6` to `7`.

- [ ] **Step 4: Verify GREEN and build**

Run from `apps/admin`:

```powershell
node --test tests/proposal-list-serial-number.test.mjs
npm run build
```

Expected: one passing test and a successful Vite build.

- [ ] **Step 5: Commit implementation**

```powershell
git add apps/admin/tests/proposal-list-serial-number.test.mjs apps/admin/src/pages/ProposalList.jsx docs/superpowers/plans/2026-08-08-proposals-serial-number.md
git commit -m "feat: number proposal rows"
```

