# Delegate Conversations Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the admin portal's Delegate page a two-pane dashboard for holding threaded, semester-scoped conversations with three fixed audiences across the mentor, student, and panel portals.

**Architecture:** Two new Supabase tables (`conversations`, `conversation_messages`) reached through the existing `apiFetchTable`/`apiUpsertTable` helpers. All channel and unread logic lives in two pure, dependency-free modules under `apps/admin/src/lib/` so it is unit-testable with `node --test`; the React page is a thin renderer over them. Sending a message also fans out rows into the existing `notifications` table, which every portal already reads.

**Tech Stack:** React 18 + Vite, Tailwind, framer-motion, lucide-react, `react-router-dom` (`useSearchParams`), Supabase Postgres, `node --test` with `node:assert/strict`.

**Spec:** `docs/superpowers/specs/2026-08-14-delegate-conversations-design.md`

## Global Constraints

- Channel ids are exactly `mentor_student`, `panel_team`, `all`. No others.
- `sender_role` values are exactly `admin`, `mentor`, `student`, `panel`.
- Migration filename format is `YYYYMMDD` + 4-digit sequence, e.g. `202608140001_delegate_conversations.sql`.
- Tests live in `apps/admin/tests/*.test.mjs`, import from `../src/lib/*.js`, and use `import test from 'node:test'` + `import assert from 'node:assert/strict'`.
- Run tests with `node --test tests/` from `apps/admin`. There is no `test` script in `package.json`; do not add one.
- Pure modules under `src/lib/` must not import React, framer-motion, or anything from `src/lib/api.js`.
- Indentation in `apps/admin/src` is 4 spaces.

---

### Task 1: Database migration

**Files:**
- Create: `supabase/migrations/202608140001_delegate_conversations.sql`

**Interfaces:**
- Consumes: nothing.
- Produces: tables `public.conversations` and `public.conversation_messages` with the columns every later task reads.

- [ ] **Step 1: Write the migration**

```sql
create table if not exists public.conversations (
  id          bigint generated always as identity primary key,
  channel     text not null check (channel in ('mentor_student', 'panel_team', 'all')),
  subject     text not null,
  created_by  text not null,
  semester_id text,
  status      text not null default 'open' check (status in ('open', 'closed')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists conversations_channel_semester_idx
  on public.conversations(channel, semester_id);

create index if not exists conversations_updated_at_idx
  on public.conversations(updated_at desc);

create table if not exists public.conversation_messages (
  id              bigint generated always as identity primary key,
  conversation_id bigint not null references public.conversations(id) on delete cascade,
  sender_role     text not null check (sender_role in ('admin', 'mentor', 'student', 'panel')),
  sender_id       text not null,
  body            text not null,
  read_by         text[] not null default '{}',
  created_at      timestamptz not null default now()
);

create index if not exists conversation_messages_thread_idx
  on public.conversation_messages(conversation_id, created_at);
```

- [ ] **Step 2: Apply the migration**

Apply via the Supabase SQL editor for project `rmmkjczuwsuxcnrdtkrh`, or `supabase db push` if the CLI is linked.

**Note:** direct Postgres (ports 5432/6543) was unreachable from this machine at time of writing — outbound TCP was blocked. If `db push` times out, use the SQL editor in the browser.

- [ ] **Step 3: Verify both tables exist**

```bash
curl -s -o /dev/null -w "conversations %{http_code}\n" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "https://rmmkjczuwsuxcnrdtkrh.supabase.co/rest/v1/conversations?select=id&limit=1"
curl -s -o /dev/null -w "conversation_messages %{http_code}\n" \
  -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "https://rmmkjczuwsuxcnrdtkrh.supabase.co/rest/v1/conversation_messages?select=id&limit=1"
```

Expected: `200` for both.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/202608140001_delegate_conversations.sql
git commit -m "feat(delegate): add conversations and conversation_messages tables"
```

---

### Task 2: Open the two access gates

Both gates must open together — opening only one produces a confusing half-failure (reads 400, or upserts reject an injected column).

**Files:**
- Modify: `backend/admin-api/app/main.py:83` (`DATA_TABLE_WHITELIST`)
- Modify: `apps/admin/src/lib/api.js:146` (`noSemesterFilter` array)
- Modify: `apps/admin/src/lib/api.js:222` (inline no-semester list in `apiUpsertTable`)

**Interfaces:**
- Consumes: table names from Task 1.
- Produces: working `apiFetchTable('conversations')`, `apiFetchTable('conversation_messages')`, and the matching upserts.

- [ ] **Step 1: Add both tables to the server whitelist**

In `backend/admin-api/app/main.py`, inside the `DATA_TABLE_WHITELIST` set, add:

```python
    "conversations",
    "conversation_messages",
```

- [ ] **Step 2: Exclude only `conversation_messages` from semester filtering**

`conversations` HAS a `semester_id` column and must keep normal filtering. `conversation_messages` does NOT — add it to both lists.

In `apps/admin/src/lib/api.js`, append to the `noSemesterFilter` array (line ~146):

```javascript
        'presentation_evaluation_scores',
        'conversation_messages'
```

And in `apiUpsertTable` (line ~222), add `'conversation_messages'` to the inline array:

```javascript
    if (!['semester_config', 'mentors', 'panels', 'notifications', 'problem_statements', 'student_preferences', 'extra_activities', 'presentation_rubrics', 'presentation_evaluation_scores', 'conversation_messages'].includes(tableName)) {
```

- [ ] **Step 3: Restart the admin backend and verify**

```bash
cd /Users/samarthverma/Project_Management_System
./stop_procksi.sh && ./start_procksi.sh
sleep 12
curl -s -o /dev/null -w "docs %{http_code}\n" http://localhost:8000/docs
```

Expected: `200`. A `400 Table 'conversations' is not allowed.` from the app later means Step 1 did not take effect.

- [ ] **Step 4: Commit**

```bash
git add backend/admin-api/app/main.py apps/admin/src/lib/api.js
git commit -m "feat(delegate): allow conversation tables through data API and semester filter"
```

---

### Task 3: Channel definitions and recipient resolution

**Files:**
- Create: `apps/admin/src/lib/delegateChannels.js`
- Test: `apps/admin/tests/delegate-channels.test.mjs`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CHANNELS: Array<{ id: string, label: string, roles: string[] }>`
  - `channelById(id: string) => channel` (falls back to `CHANNELS[0]`)
  - `isValidChannel(id: string) => boolean`
  - `resolveRecipients(channelId: string, sources: { mentors?: [], students?: [], panels?: [], teams?: [] }) => { mentors: [], students: [], panels: [], teams: [], total: number }`
  - `describeRecipients(resolved) => string`

- [ ] **Step 1: Write the failing test**

Create `apps/admin/tests/delegate-channels.test.mjs`:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import {
    CHANNELS,
    channelById,
    isValidChannel,
    resolveRecipients,
    describeRecipients,
} from '../src/lib/delegateChannels.js';

const sources = {
    mentors: [{ id: 'M-1', name: 'Preshit' }, { id: 'M-2', name: 'Asha' }],
    students: [{ id: '2415500148', name: 'Devang' }],
    panels: [{ id: 'P-1', name: 'Anushka' }],
    teams: [{ id: 'T-1', title: 'AuthPulse' }, { id: 'T-2', title: 'Echo' }],
};

test('CHANNELS has exactly the three spec channels in order', () => {
    assert.deepEqual(CHANNELS.map(c => c.id), ['mentor_student', 'panel_team', 'all']);
});

test('isValidChannel accepts known ids and rejects anything else', () => {
    assert.equal(isValidChannel('panel_team'), true);
    assert.equal(isValidChannel('mentor'), false);
    assert.equal(isValidChannel(null), false);
});

test('channelById falls back to the first channel for unknown ids', () => {
    assert.equal(channelById('all').id, 'all');
    assert.equal(channelById('nope').id, 'mentor_student');
    assert.equal(channelById(undefined).id, 'mentor_student');
});

test('mentor_student resolves mentors and students only', () => {
    const r = resolveRecipients('mentor_student', sources);
    assert.equal(r.mentors.length, 2);
    assert.equal(r.students.length, 1);
    assert.equal(r.panels.length, 0);
    assert.equal(r.teams.length, 0);
    assert.equal(r.total, 3);
});

test('panel_team resolves panels and teams only', () => {
    const r = resolveRecipients('panel_team', sources);
    assert.equal(r.panels.length, 1);
    assert.equal(r.teams.length, 2);
    assert.equal(r.mentors.length, 0);
    assert.equal(r.students.length, 0);
    assert.equal(r.total, 3);
});

test('all resolves every source', () => {
    const r = resolveRecipients('all', sources);
    assert.equal(r.total, 6);
});

test('resolveRecipients tolerates missing and empty sources', () => {
    const r = resolveRecipients('all', {});
    assert.deepEqual(r.mentors, []);
    assert.equal(r.total, 0);
});

test('unknown channel resolves as the fallback channel, never throws', () => {
    const r = resolveRecipients('bogus', sources);
    assert.equal(r.total, 3);
});

test('describeRecipients lists non-empty groups only, in a stable order', () => {
    assert.equal(describeRecipients(resolveRecipients('panel_team', sources)), '1 panel, 2 teams');
    assert.equal(describeRecipients(resolveRecipients('mentor_student', sources)), '2 mentors, 1 student');
    assert.equal(describeRecipients(resolveRecipients('all', {})), 'no recipients');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/admin && node --test tests/delegate-channels.test.mjs`
Expected: FAIL — `Cannot find module '../src/lib/delegateChannels.js'`

- [ ] **Step 3: Write the implementation**

Create `apps/admin/src/lib/delegateChannels.js`:

```javascript
/**
 * delegateChannels.js
 *
 * Pure channel/recipient logic for the Delegate conversations dashboard.
 * No React, no network, no imports — so it can be unit-tested directly.
 *
 * A conversation's channel is fixed at creation. Changing audience means
 * starting a new conversation, so a recipient added later can never read
 * messages they were not addressed in.
 */

export const CHANNELS = [
    { id: 'mentor_student', label: 'Mentors & Students', roles: ['mentor', 'student'] },
    { id: 'panel_team', label: 'Panels & Teams', roles: ['panel', 'student'] },
    { id: 'all', label: 'All Portals', roles: ['mentor', 'student', 'panel'] },
];

export function isValidChannel(id) {
    return CHANNELS.some((c) => c.id === id);
}

export function channelById(id) {
    return CHANNELS.find((c) => c.id === id) || CHANNELS[0];
}

const GROUPS_BY_CHANNEL = {
    mentor_student: ['mentors', 'students'],
    panel_team: ['panels', 'teams'],
    all: ['mentors', 'students', 'panels', 'teams'],
};

export function resolveRecipients(channelId, sources = {}) {
    const channel = channelById(channelId);
    const wanted = GROUPS_BY_CHANNEL[channel.id];
    const pick = (key) => (wanted.includes(key) && Array.isArray(sources[key]) ? sources[key] : []);

    const resolved = {
        mentors: pick('mentors'),
        students: pick('students'),
        panels: pick('panels'),
        teams: pick('teams'),
    };
    resolved.total = resolved.mentors.length + resolved.students.length
        + resolved.panels.length + resolved.teams.length;
    return resolved;
}

const LABELS = [
    ['mentors', 'mentor'],
    ['students', 'student'],
    ['panels', 'panel'],
    ['teams', 'team'],
];

export function describeRecipients(resolved) {
    const parts = LABELS
        .filter(([key]) => resolved[key].length > 0)
        .map(([key, noun]) => {
            const n = resolved[key].length;
            return `${n} ${noun}${n === 1 ? '' : 's'}`;
        });
    return parts.length ? parts.join(', ') : 'no recipients';
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/admin && node --test tests/delegate-channels.test.mjs`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/lib/delegateChannels.js apps/admin/tests/delegate-channels.test.mjs
git commit -m "feat(delegate): add pure channel and recipient resolution module"
```

---

### Task 4: Thread summarising and unread counting

**Files:**
- Create: `apps/admin/src/lib/delegateThreads.js`
- Test: `apps/admin/tests/delegate-threads.test.mjs`

**Interfaces:**
- Consumes: nothing (operates on plain row objects shaped like Task 1's tables).
- Produces:
  - `isUnreadFor(message, viewerId) => boolean`
  - `unreadCount(messages, viewerId) => number`
  - `groupMessagesByConversation(messages) => Map<number, message[]>`
  - `summariseThreads(conversations, messages, viewerId) => Array<{ ...conversation, lastMessage, unread, preview }>` sorted by `updated_at` desc

- [ ] **Step 1: Write the failing test**

Create `apps/admin/tests/delegate-threads.test.mjs`:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import {
    isUnreadFor,
    unreadCount,
    groupMessagesByConversation,
    summariseThreads,
} from '../src/lib/delegateThreads.js';

const ADMIN = 'aiml_project_coordinator@example.edu';

const messages = [
    { id: 1, conversation_id: 10, sender_role: 'admin', sender_id: ADMIN, body: 'Kickoff', read_by: [], created_at: '2026-08-01T10:00:00Z' },
    { id: 2, conversation_id: 10, sender_role: 'mentor', sender_id: 'M-1', body: 'Acknowledged', read_by: [], created_at: '2026-08-02T10:00:00Z' },
    { id: 3, conversation_id: 11, sender_role: 'panel', sender_id: 'P-1', body: 'Slot clash', read_by: [ADMIN], created_at: '2026-08-03T10:00:00Z' },
];

const conversations = [
    { id: 10, channel: 'mentor_student', subject: 'Kickoff', updated_at: '2026-08-02T10:00:00Z' },
    { id: 11, channel: 'panel_team', subject: 'Scheduling', updated_at: '2026-08-03T10:00:00Z' },
    { id: 12, channel: 'all', subject: 'Empty thread', updated_at: '2026-08-04T10:00:00Z' },
];

test('a message the viewer sent is never unread to them', () => {
    assert.equal(isUnreadFor(messages[0], ADMIN), false);
});

test('a message from someone else with an empty read_by is unread', () => {
    assert.equal(isUnreadFor(messages[1], ADMIN), true);
});

test('a message already in read_by is not unread', () => {
    assert.equal(isUnreadFor(messages[2], ADMIN), false);
});

test('a missing read_by is treated as empty, not a crash', () => {
    assert.equal(isUnreadFor({ sender_id: 'M-9', body: 'hi' }, ADMIN), true);
});

test('unreadCount counts only other peoples unread messages', () => {
    assert.equal(unreadCount(messages, ADMIN), 1);
    assert.equal(unreadCount([], ADMIN), 0);
});

test('groupMessagesByConversation buckets by conversation_id', () => {
    const grouped = groupMessagesByConversation(messages);
    assert.equal(grouped.get(10).length, 2);
    assert.equal(grouped.get(11).length, 1);
    assert.equal(grouped.has(12), false);
});

test('summariseThreads sorts newest first and attaches preview and unread', () => {
    const threads = summariseThreads(conversations, messages, ADMIN);
    assert.deepEqual(threads.map(t => t.id), [12, 11, 10]);

    const kickoff = threads.find(t => t.id === 10);
    assert.equal(kickoff.unread, 1);
    assert.equal(kickoff.preview, 'Acknowledged');
    assert.equal(kickoff.lastMessage.id, 2);
});

test('a conversation with no messages summarises safely', () => {
    const empty = summariseThreads(conversations, messages, ADMIN).find(t => t.id === 12);
    assert.equal(empty.unread, 0);
    assert.equal(empty.preview, 'No messages yet');
    assert.equal(empty.lastMessage, null);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/admin && node --test tests/delegate-threads.test.mjs`
Expected: FAIL — `Cannot find module '../src/lib/delegateThreads.js'`

- [ ] **Step 3: Write the implementation**

Create `apps/admin/src/lib/delegateThreads.js`:

```javascript
/**
 * delegateThreads.js
 *
 * Pure thread-summarising and unread logic for the Delegate dashboard.
 * Unread state is derived from each message's `read_by` array rather than a
 * join table — see the spec's note on why this does not scale past a few
 * thousand recipients per message.
 */

export function isUnreadFor(message, viewerId) {
    if (!message) return false;
    if (message.sender_id === viewerId) return false;
    const readBy = Array.isArray(message.read_by) ? message.read_by : [];
    return !readBy.includes(viewerId);
}

export function unreadCount(messages, viewerId) {
    if (!Array.isArray(messages)) return 0;
    return messages.reduce((n, m) => n + (isUnreadFor(m, viewerId) ? 1 : 0), 0);
}

export function groupMessagesByConversation(messages) {
    const grouped = new Map();
    if (!Array.isArray(messages)) return grouped;
    for (const message of messages) {
        const key = message.conversation_id;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(message);
    }
    for (const list of grouped.values()) {
        list.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    }
    return grouped;
}

export function summariseThreads(conversations, messages, viewerId) {
    if (!Array.isArray(conversations)) return [];
    const grouped = groupMessagesByConversation(messages);

    return conversations
        .map((conversation) => {
            const thread = grouped.get(conversation.id) || [];
            const lastMessage = thread.length ? thread[thread.length - 1] : null;
            return {
                ...conversation,
                lastMessage,
                unread: unreadCount(thread, viewerId),
                preview: lastMessage ? lastMessage.body : 'No messages yet',
            };
        })
        .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/admin && node --test tests/delegate-threads.test.mjs`
Expected: PASS, 8 tests.

- [ ] **Step 5: Run the whole admin suite for regressions**

Run: `cd apps/admin && node --test tests/`
Expected: PASS — 14 pre-existing + 9 + 8 = 31 tests.

- [ ] **Step 6: Commit**

```bash
git add apps/admin/src/lib/delegateThreads.js apps/admin/tests/delegate-threads.test.mjs
git commit -m "feat(delegate): add pure thread summarising and unread counting"
```

---

### Task 5: Repoint the target dropdown to the three channels

The dropdown currently offers Mentor / Panel / Team on `?target=`. It becomes the channel selector, driven by `CHANNELS` from Task 3.

**Files:**
- Modify: `apps/admin/src/components/DelegateTargetDropdown.jsx` (whole file)

**Interfaces:**
- Consumes: `CHANNELS`, `channelById`, `isValidChannel` from `delegateChannels.js`.
- Produces: `?target=<channel id>` in the URL; default `mentor_student`. Exports `default DelegateTargetDropdown`.

- [ ] **Step 1: Rewrite the component**

Replace the contents of `apps/admin/src/components/DelegateTargetDropdown.jsx`:

```jsx
import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import { UserCircle, ShieldCheck, Globe, ChevronDown } from 'lucide-react';
import { CHANNELS, channelById, isValidChannel } from '../lib/delegateChannels';

// Delegate channel selector. Lives in the top nav (left of the semester filter)
// and syncs the chosen channel to the `?target=` URL param, which the Delegate
// page reads. Channel ids and labels come from delegateChannels.js so the
// dropdown and the recipient resolution can never drift apart.
const ICONS = {
    mentor_student: UserCircle,
    panel_team: ShieldCheck,
    all: Globe,
};

export default function DelegateTargetDropdown() {
    const [params, setParams] = useSearchParams();
    const requested = params.get('target');
    const current = isValidChannel(requested) ? requested : CHANNELS[0].id;
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, []);

    const select = (id) => {
        const next = new URLSearchParams(params);
        next.set('target', id);
        setParams(next, { replace: true });
        setOpen(false);
    };

    const active = channelById(current);
    const ActiveIcon = ICONS[active.id];

    return (
        <div className="relative shrink-0" ref={ref}>
            <button onClick={() => setOpen((o) => !o)}
                className="flex items-center gap-2 px-3 h-9 rounded-full bg-slate-100/60 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/70 shadow-inner text-xs font-bold text-slate-600 dark:text-slate-300 hover:border-indigo-400 transition-colors max-w-[15rem]">
                <ActiveIcon className="w-4 h-4 text-indigo-500 shrink-0" />
                <span className="truncate flex-1 text-left">{active.label}</span>
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
                {open && (
                    <motion.ul
                        initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        className="absolute z-50 mt-2 w-60 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl overflow-hidden p-1.5">
                        {CHANNELS.map((c) => {
                            const Icon = ICONS[c.id];
                            return (
                                <li key={c.id}>
                                    <button
                                        onClick={() => select(c.id)}
                                        className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-bold text-left transition-colors
                                            ${c.id === current ? 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-300'
                                                : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                        <Icon className="w-4 h-4 shrink-0" />
                                        <span className="flex-1 truncate">{c.label}</span>
                                    </button>
                                </li>
                            );
                        })}
                    </motion.ul>
                )}
            </AnimatePresence>
        </div>
    );
}
```

- [ ] **Step 2: Verify it hot-reloads without error**

```bash
cd /Users/samarthverma/Project_Management_System
tail -3 logs/admin-frontend.log
curl -s -o /dev/null -w "delegate %{http_code}\n" http://localhost:3000/admin/delegate
```

Expected: `200`, and no `Pre-transform error` in the log tail.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/src/components/DelegateTargetDropdown.jsx
git commit -m "feat(delegate): repoint target dropdown to the three conversation channels"
```

---

### Task 6: Conversation data access helpers

Isolating the four Supabase calls keeps the page component a renderer and gives the notification fan-out one home.

**Files:**
- Create: `apps/admin/src/services/delegateApi.js`

**Interfaces:**
- Consumes: `apiFetchTable`, `apiUpsertTable`, `apiPatchRow` from `../lib/api`; `channelById` from `../lib/delegateChannels`.
- Produces:
  - `fetchConversations() => Promise<row[]>`
  - `fetchMessages() => Promise<row[]>`
  - `createConversation({ channel, subject, body, createdBy }) => Promise<void>`
  - `sendMessage({ conversationId, body, senderId }) => Promise<void>`
  - `notifyChannel({ channel, subject, body }) => Promise<void>`

- [ ] **Step 1: Write the module**

Create `apps/admin/src/services/delegateApi.js`:

```javascript
/**
 * delegateApi.js
 *
 * Supabase access for the Delegate conversations dashboard.
 *
 * `conversations` carries semester_id and is filtered by the global semester
 * selector automatically. `conversation_messages` has no semester_id and is
 * excluded from that filtering in lib/api.js — do not add one.
 */
import { apiFetchTable, apiUpsertTable, apiPatchRow } from '../lib/api';
import { channelById } from '../lib/delegateChannels';

export async function fetchConversations() {
    return apiFetchTable('conversations', { orderBy: 'updated_at', ascending: false });
}

export async function fetchMessages() {
    return apiFetchTable('conversation_messages', { orderBy: 'created_at', ascending: true });
}

// Fans a new message out to the existing notifications table, one row per
// recipient role, so every portal's existing notification bell surfaces it
// without waiting on the Phase 2 inbox UI.
export async function notifyChannel({ channel, subject, body }) {
    const rows = channelById(channel).roles.map((role) => ({
        recipient_email: null,
        recipient_role: role,
        audience: 'all',
        title: `New message: ${subject}`,
        message: String(body).slice(0, 200),
        type: 'conversation',
        read: false,
    }));
    await apiUpsertTable('notifications', rows);
}

export async function createConversation({ channel, subject, body, createdBy }) {
    const [conversation] = await apiUpsertTable('conversations', [{
        channel,
        subject,
        created_by: createdBy,
        status: 'open',
        updated_at: new Date().toISOString(),
    }]);

    await apiUpsertTable('conversation_messages', [{
        conversation_id: conversation.id,
        sender_role: 'admin',
        sender_id: createdBy,
        body,
        read_by: [createdBy],
    }]);

    await notifyChannel({ channel, subject, body });
    return conversation;
}

export async function sendMessage({ conversationId, channel, subject, body, senderId }) {
    await apiUpsertTable('conversation_messages', [{
        conversation_id: conversationId,
        sender_role: 'admin',
        sender_id: senderId,
        body,
        read_by: [senderId],
    }]);
    await apiPatchRow('conversations', conversationId, { updated_at: new Date().toISOString() });
    await notifyChannel({ channel, subject, body });
}
```

**Known sharp edge:** `apiUpsertTable` must return the inserted row for `createConversation` to read `conversation.id`. Verify this against `api.js:219-268` during implementation. If it returns something else (e.g. a status envelope), fetch the newest conversation for this `created_by` immediately after insert instead, and note the race in the Limitations section.

- [ ] **Step 2: Commit**

```bash
git add apps/admin/src/services/delegateApi.js
git commit -m "feat(delegate): add conversation data access and notification fan-out"
```

---

### Task 7: The Delegate dashboard

**Files:**
- Modify: `apps/admin/src/pages/Delegate.jsx` (replace the hero-only placeholder body)

**Interfaces:**
- Consumes: everything from Tasks 3, 4, and 6; `useSupabaseTableState` from `../hooks/useSupabaseTableState` for `mentors`, `students`, `panels`, `teams_validation`; `getStoredSession` from `../lib/api`.

**Do not use `getCurrentUser()` from `lib/auditLogger`.** It is a stub that returns the literal string `'admin'` (`auditLogger.js:55-59`), so every admin would share one `sender_id` and `read_by` membership would be meaningless. Use the real session email instead, as `AdminLayout.jsx:49` does.
- Produces: the rendered dashboard. Nothing imports from it.

- [ ] **Step 1: Write the page**

Replace `apps/admin/src/pages/Delegate.jsx` with a two-pane layout below the existing hero banner. Keep the hero exactly as it is today (gradient, SVG wave, `<h1>Delegate</h1>`, subtitle) and add beneath it:

```jsx
import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import { Send, Plus, MessageSquare, X } from 'lucide-react';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { getStoredSession } from '../lib/api';
import { channelById, resolveRecipients, describeRecipients } from '../lib/delegateChannels';
import { summariseThreads } from '../lib/delegateThreads';
import { fetchConversations, fetchMessages, createConversation, sendMessage } from '../services/delegateApi';

const Delegate = () => {
    const [params] = useSearchParams();
    const channel = channelById(params.get('target'));
    const viewerId = getStoredSession()?.user?.email || '';

    const { data: mentors } = useSupabaseTableState('mentors', [], { orderBy: 'id' });
    const { data: students } = useSupabaseTableState('students', [], { orderBy: 'id' });
    const { data: panels } = useSupabaseTableState('panels', [], { orderBy: 'id' });
    const { data: teams } = useSupabaseTableState('teams_validation', [], { orderBy: 'id' });

    const [conversations, setConversations] = useState([]);
    const [messages, setMessages] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [composerOpen, setComposerOpen] = useState(false);
    const [subject, setSubject] = useState('');
    const [draft, setDraft] = useState('');
    const [reply, setReply] = useState('');
    const [busy, setBusy] = useState(false);

    const reload = async () => {
        const [c, m] = await Promise.all([fetchConversations(), fetchMessages()]);
        setConversations(c);
        setMessages(m);
    };

    useEffect(() => { reload().catch(err => console.error('Delegate load failed', err)); }, []);

    const recipients = useMemo(
        () => resolveRecipients(channel.id, { mentors, students, panels, teams }),
        [channel.id, mentors, students, panels, teams],
    );

    const threads = useMemo(
        () => summariseThreads(conversations.filter(c => c.channel === channel.id), messages, viewerId),
        [conversations, messages, channel.id, viewerId],
    );

    // Selection is per-channel; clear it when the channel changes so a thread
    // from another channel can never stay open.
    useEffect(() => { setSelectedId(null); }, [channel.id]);

    const selected = threads.find(t => t.id === selectedId) || null;
    const thread = messages
        .filter(m => m.conversation_id === selectedId)
        .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!subject.trim() || !draft.trim() || busy) return;
        setBusy(true);
        try {
            await createConversation({ channel: channel.id, subject: subject.trim(), body: draft.trim(), createdBy: viewerId });
            setSubject(''); setDraft(''); setComposerOpen(false);
            await reload();
        } catch (err) {
            alert(`Could not start conversation: ${err.message}`);
        } finally {
            setBusy(false);
        }
    };

    const handleReply = async (e) => {
        e.preventDefault();
        if (!reply.trim() || !selected || busy) return;
        setBusy(true);
        try {
            await sendMessage({
                conversationId: selected.id, channel: selected.channel,
                subject: selected.subject, body: reply.trim(), senderId: viewerId,
            });
            setReply('');
            await reload();
        } catch (err) {
            alert(`Could not send: ${err.message}`);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="space-y-6">
            {/* Hero — unchanged */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-sky-600 via-sky-700 to-indigo-900 rounded-3xl p-8 text-white shadow-xl shadow-sky-500/20 relative overflow-hidden border border-sky-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10">
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Delegate</h1>
                    <p className="text-sky-100/90 text-sm md:text-base max-w-lg font-medium">
                        {channel.label} — reaching {describeRecipients(recipients)}.
                    </p>
                </div>
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Thread list */}
                <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col">
                    <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <h2 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest">Conversations</h2>
                        <button onClick={() => setComposerOpen(true)}
                            className="flex items-center px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg shadow-sky-500/30">
                            <Plus className="w-4 h-4 mr-1.5" /> New
                        </button>
                    </div>
                    <div className="divide-y divide-slate-100 dark:divide-slate-700/50 overflow-y-auto max-h-[32rem]">
                        {threads.length === 0 && (
                            <p className="p-8 text-center text-sm font-medium text-slate-500">No conversations in this channel yet.</p>
                        )}
                        {threads.map(t => (
                            <button key={t.id} onClick={() => setSelectedId(t.id)}
                                className={`w-full text-left p-4 transition-colors ${t.id === selectedId ? 'bg-sky-50 dark:bg-sky-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                <div className="flex items-center justify-between gap-2">
                                    <span className="font-bold text-sm text-slate-800 dark:text-white truncate">{t.subject}</span>
                                    {t.unread > 0 && (
                                        <span className="shrink-0 px-2 py-0.5 bg-sky-600 text-white rounded-full text-[10px] font-black">{t.unread}</span>
                                    )}
                                </div>
                                <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-1">{t.preview}</p>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Thread view */}
                <div className="lg:col-span-2 bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col min-h-[24rem]">
                    {!selected ? (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-3">
                            <MessageSquare className="w-10 h-10" />
                            <p className="text-sm font-bold">Select a conversation</p>
                        </div>
                    ) : (
                        <>
                            <div className="p-4 border-b border-slate-100 dark:border-slate-700/50">
                                <h2 className="font-black text-slate-800 dark:text-white">{selected.subject}</h2>
                                <p className="text-[10px] font-black uppercase tracking-widest text-sky-600 dark:text-sky-400 mt-0.5">{channelById(selected.channel).label}</p>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[26rem]">
                                {thread.map(m => (
                                    <div key={m.id} className={`flex ${m.sender_role === 'admin' ? 'justify-end' : 'justify-start'}`}>
                                        <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${m.sender_role === 'admin' ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100'}`}>
                                            <p className="text-[10px] font-black uppercase tracking-widest opacity-70 mb-1">{m.sender_role}</p>
                                            <p className="text-sm font-medium whitespace-pre-wrap">{m.body}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <form onSubmit={handleReply} className="p-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2">
                                <input value={reply} onChange={e => setReply(e.target.value)} placeholder="Write a reply..."
                                    className="flex-1 px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-sky-500" />
                                <button type="submit" disabled={busy || !reply.trim()}
                                    className="px-4 py-2.5 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white rounded-xl transition-colors">
                                    <Send className="w-4 h-4" />
                                </button>
                            </form>
                        </>
                    )}
                </div>
            </div>

            {/* Composer */}
            {composerOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" onClick={() => setComposerOpen(false)}>
                    <form onClick={e => e.stopPropagation()} onSubmit={handleCreate}
                        className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden">
                        <div className="p-5 bg-sky-600 text-white flex items-center justify-between">
                            <h2 className="text-lg font-black">New conversation</h2>
                            <button type="button" onClick={() => setComposerOpen(false)} className="p-2 hover:bg-black/20 rounded-full"><X className="w-5 h-5" /></button>
                        </div>
                        <div className="p-5 space-y-4">
                            <p className="text-xs font-bold text-slate-500 dark:text-slate-400">
                                {channel.label} — will reach {describeRecipients(recipients)}.
                            </p>
                            <input value={subject} onChange={e => setSubject(e.target.value)} placeholder="Subject" required
                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold dark:text-white outline-none focus:ring-2 focus:ring-sky-500" />
                            <textarea value={draft} onChange={e => setDraft(e.target.value)} placeholder="Message" rows={5} required
                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-sky-500" />
                            <button type="submit" disabled={busy}
                                className="w-full py-3 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors">
                                {busy ? 'Sending...' : 'Send'}
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
};

export default Delegate;
```

- [ ] **Step 2: Verify against the running app**

```bash
cd /Users/samarthverma/Project_Management_System
tail -4 logs/admin-frontend.log
curl -s -o /dev/null -w "delegate %{http_code}\n" http://localhost:3000/admin/delegate
```

Expected: `200`, no `Pre-transform error`.

Then in the browser at `http://localhost:3000/admin/delegate`: switch channels in the dropdown and confirm the hero subtitle recipient count changes; create a conversation; confirm it appears in the list and its message renders right-aligned.

- [ ] **Step 3: Run the full suite**

Run: `cd apps/admin && node --test tests/`
Expected: PASS, 31 tests.

- [ ] **Step 4: Commit**

```bash
git add apps/admin/src/pages/Delegate.jsx
git commit -m "feat(delegate): add two-pane conversations dashboard"
```

---

## Limitations

These are properties of the delivered Phase 1, not bugs to fix during it.

1. **Broadcast-only in practice.** No recipient has a reply UI until Phase 2, so the `sender_role !== 'admin'` rendering path is exercised only by tests and hand-inserted rows. Do not report "two-way conversations" as working after Phase 1.
2. **`read_by` does not scale.** Unread state is a `text[]` on each message. At `all`-channel scale (496 students today) a fully-read message carries a 496-element array, and every unread count is computed client-side after fetching every message. Fine at current volume; revisit past a few thousand recipients per message.
3. **Every message is fetched on every load.** `fetchMessages()` pulls the entire `conversation_messages` table with no pagination or `conversation_id` filter. This is simple and correct now and will degrade linearly. Pagination is deliberately deferred.
4. **No realtime.** The dashboard reloads only on mount and after the admin sends. A reply arriving from another portal appears on the next manual refresh. Supabase realtime subscriptions are out of scope.
5. **Notification fan-out is role-wide, not per-person.** `notifyChannel` writes one `notifications` row per role with `audience: 'all'`. Every mentor sees "new message" even if the thread is not addressed to them individually — matching how the existing `notifications` rows in this codebase already behave.
6. **`conversation_messages` is not semester-scoped.** Only `conversations` carries `semester_id`. Messages are reachable across semesters if queried directly; the UI never does, because it filters threads by channel from the semester-filtered `conversations` fetch.
7. **No attachments, no edit, no delete.** Per the spec's Out of Scope.
8. **Admin identity depends on a populated session.** `sender_id` and `created_by` come from `getStoredSession()?.user?.email`, falling back to `''`. If the stored session lacks an email, every message is attributed to the empty string and unread tracking silently degrades, because `read_by` membership is an exact string match. The fallback is deliberately `''` rather than a placeholder like `'admin'` so the failure is visibly wrong rather than plausibly wrong.

## Loose Ends and Risks

Things that may bite during implementation, with the response for each.

1. **`apiUpsertTable`'s return shape is unverified.** `createConversation` assumes it resolves to an array of inserted rows so it can read `conversation.id`. If it resolves to a status envelope instead, the follow-up message insert throws on `undefined.id`. **Response:** read `api.js:219-268` first; if the shape differs, re-fetch the newest `conversations` row for this `created_by` and accept the documented race.
2. **`students` may not be in `DATA_TABLE_WHITELIST` in the shape Task 7 needs.** It is listed, but the page loads all 496 rows purely to count recipients. **Response:** if load time suffers, count students with a `select=id` projection rather than `*`.
3. ~~**`useSupabaseTableState` return shape unverified.**~~ **Resolved during plan self-review:** the hook returns `{ data, setData, loading, error }` (`useSupabaseTableState.js:71`), so Task 7's `{ data: mentors }` destructuring is correct as written. No action needed.
4. **The `panel_team` channel's student reach is ambiguous.** The spec resolves it to *teams*, one recipient per validated team, not to individual students. If the intent was "every student on a validated team", the recipient count and the notification fan-out both change. **Response:** confirm with the user before Task 3; this is the one open product question.
5. **Two gates, opened separately, fail confusingly.** Adding tables to `DATA_TABLE_WHITELIST` without restarting the backend yields `400 Table 'conversations' is not allowed.` — which looks like a migration failure, not a stale process. **Response:** Task 2 Step 3 restarts the backend explicitly; do not skip it.
6. **Direct Postgres is unreachable from this machine.** Ports 5432 and 6543 to `aws-1-ap-northeast-1.pooler.supabase.com` time out on the current network, so `supabase db push` will hang. **Response:** apply Task 1 through the Supabase SQL editor, or from a network that permits outbound 5432/6543.
7. ~~**`getCurrentUser()` may have side effects.**~~ **Resolved during plan self-review, and it was worse than expected:** `getCurrentUser()` is a stub that returns the literal string `'admin'` (`auditLogger.js:55-59`, comment reads "For now, returning 'admin' as placeholder"). Had Task 7 used it, every admin would share one `sender_id`, `read_by` would be meaningless, and nothing would visibly fail. The plan now uses `getStoredSession()?.user?.email`, matching `AdminLayout.jsx:49`. **Separate concern worth raising:** every existing audit-log row written through `AuditLogger.logAdminAction(getCurrentUser(), ...)` across the admin portal is attributed to `'admin'`, so the governance audit trail currently identifies nobody. That is a pre-existing bug outside this plan's scope.
8. **Channel repoint is a breaking URL change.** Any bookmark of `?target=mentor` now falls back to `mentor_student` rather than erroring. This is intended, but means old links silently change meaning. **Response:** none needed; documented here so it is not mistaken for a bug.
9. **`updated_at` is set client-side.** `createConversation` and `sendMessage` both write `new Date().toISOString()` from the browser. Clock skew between admin machines can misorder the thread list. **Response:** acceptable at this scale; a DB trigger would be the fix if it matters.
10. **No RLS policies are defined.** The migration creates tables without row-level security. Every portal's service key can read every conversation. **Response:** acceptable for Phase 1 because only the admin portal touches these tables; RLS must be designed in Phase 2 before recipient portals get access.

## Self-Review Notes

- **Spec coverage:** channels → Task 3; data model → Task 1; recipient resolution → Task 3; Delegate page → Task 7; `api.js`/whitelist gates → Task 2; notification fan-out → Task 6; testing → Tasks 3 and 4. The spec's `delegate-unread.test.mjs` is delivered as `delegate-threads.test.mjs`, covering unread counting plus thread summarising in one file.
- **Type consistency:** `channelById`, `resolveRecipients`, `describeRecipients`, `summariseThreads`, `unreadCount` keep identical signatures across Tasks 3, 4, 5, and 7. `notifyChannel` takes `{ channel, subject, body }` in both call sites.
- **Known gap carried deliberately:** Loose End 4 (the `panel_team` student-reach question) is unresolved and should be answered before Task 3 is implemented.
