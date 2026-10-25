# Delegate Conversations Design

## Goal

Give the admin portal a single place — the **Delegate** page — to hold two-way conversations with the other three portals, replacing the current fire-and-forget email blast as the mechanism for anything that needs a reply. Three audiences are addressable: mentors + students, panels + teams, and everyone.

## Current Behavior

Admin → portal communication today is one-directional and has no reply path:

1. `apps/admin/src/pages/Communication.jsx` (614 lines) composes an email, picks a segment (`all_students`, `team_leaders`, `unassigned_students`, `incomplete_teams`, `teams_without_mentors`, `mentors`, `specific_team`), and sends via `backend/admin-api/app/email_notifier.py`. It also writes a row to `notifications` (`Communication.jsx:137`).
2. `apps/admin/src/pages/PerTeamMail.jsx` (321 lines) does the same per-team, with the same segment vocabulary.
3. `apps/admin/src/services/panelSync.js` pushes schedule slots and alerts to the panel backend over `/admin/sync/*`, authenticated with the shared `X-Admin-Api-Key`. One-way, admin → panel only.
4. `notifications` is the only cross-portal message store. It is read by `apps/admin/src/components/TopNav.jsx:94`, and the student and main portals render a notifications view. It carries no thread identity, no sender role, and no reply affordance.

There is no table representing a conversation, no concept of a message thread, and no way for a mentor, student, or panel member to respond to anything the admin sends.

## Behavior Change

Introduce conversations as a first-class entity, scoped by semester, addressed to one of three fixed channels, and rendered as a two-pane dashboard in the Delegate page.

### Channels

The `?target=` URL param already driving `DelegateTargetDropdown` is repointed from `mentor` / `panel` / `team` to three channels:

| `channel` value | Label | Recipient roles | Portals reached |
|---|---|---|---|
| `mentor_student` | Mentors & Students | mentor, student | mentor, student |
| `panel_team` | Panels & Teams | panel, student | panel, student |
| `all` | All Portals | mentor, student, panel | all four |

The channel is a property of the conversation, fixed at creation. Changing audience means starting a new conversation — this keeps the recipient set of an existing thread immutable, so a late-added recipient can never see earlier messages they were not addressed in.

### Data model

Two new tables, one migration file (`supabase/migrations/202608140001_delegate_conversations.sql`), following the existing migration's naming and structure.

**`conversations`**

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | |
| `channel` | `text NOT NULL` | one of `mentor_student`, `panel_team`, `all`; CHECK-constrained |
| `subject` | `text NOT NULL` | |
| `created_by` | `text NOT NULL` | admin email |
| `semester_id` | `text` | matches the scoping used by `teams_validation` |
| `status` | `text NOT NULL DEFAULT 'open'` | `open` or `closed` |
| `created_at` / `updated_at` | `timestamptz DEFAULT now()` | `updated_at` bumped on each new message |

**`conversation_messages`**

| Column | Type | Notes |
|---|---|---|
| `id` | `bigint` identity PK | |
| `conversation_id` | `bigint NOT NULL REFERENCES conversations(id) ON DELETE CASCADE` | |
| `sender_role` | `text NOT NULL` | `admin`, `mentor`, `student`, `panel`; CHECK-constrained |
| `sender_id` | `text NOT NULL` | email or roll number, whichever the sending portal authenticates with |
| `body` | `text NOT NULL` | |
| `created_at` | `timestamptz DEFAULT now()` | |
| `read_by` | `text[] DEFAULT '{}'` | sender ids that have read this message |

Indexes: `conversation_messages(conversation_id, created_at)` for thread rendering, `conversations(channel, semester_id)` for the filtered list.

`read_by` as an array is deliberate: unread counts are computed client-side from a single fetch, avoiding a per-recipient join table for what is a low-volume, admin-facing count. This does not scale past a few thousand recipients per message and should be revisited if it ever needs to.

### Recipient resolution

A pure module, `apps/admin/src/lib/delegateChannels.js`, maps a channel to concrete recipients from already-loaded table state:

- `mentor_student` → all rows of `mentors` + all enrolled students
- `panel_team` → all rows of `panels` + one entry per validated team in `teams_validation`
- `all` → the union of both

Kept pure and dependency-free so it is directly unit-testable, in the same spirit as `apps/admin/src/lib/psAllocation.js`.

### Delegate page

`apps/admin/src/pages/Delegate.jsx` grows from the current hero-only placeholder into a two-pane layout beneath the existing banner:

- **Left** — conversation list for the active channel: subject, last-message preview, relative timestamp, unread badge. Sorted by `updated_at` desc. A "New conversation" button opens the composer.
- **Right** — the selected thread: messages oldest-first, sender role and name per message, admin's own messages right-aligned, and a reply box pinned to the bottom.
- **Composer** — subject + body, with the channel taken from the active dropdown selection and its resolved recipient count shown before sending ("This will reach 172 teams and 2 mentors").

Data access goes through the existing `apiFetchTable` / `apiUpsertTable` helpers in `apps/admin/src/lib/api.js`. **Three** separate gates are involved, and they are commonly confused:

1. **Server-side access gate** — `DATA_TABLE_WHITELIST` in `backend/admin-api/app/main.py:83`. Any table not listed is rejected with `400 Table '<name>' is not allowed.` on all four data endpoints (`GET /api/data/{table}`, `.../upsert`, `.../delete`, `PATCH /api/data/{table}/{row_id}`). Both `conversations` and `conversation_messages` must be added here or every request fails.
2. **Client-side semester-filter exclusions** — the `noSemesterFilter` array at `api.js:146` and the inline list at `api.js:222`. These are *not* access control; they mark tables that have no `semester_id` column. `conversations` has `semester_id` and must stay out of both lists so it is filtered normally. `conversation_messages` has no `semester_id` and must be added to both, otherwise fetches send a `semester_id` filter against a non-existent column and upserts inject a `semester_id` field that the insert will reject.

3. **Server-side semester gate** — `TABLES_WITH_SEMESTER_ID` in `backend/admin-api/app/main.py:125`. Without `conversations` here, `main.py:1061-1063` silently discards the `semester_id` param the client correctly sends, and conversations are returned across every semester.

### ⚠️ Do not open gate 3 before the migration is applied

`TABLES_WITH_SEMESTER_ID` is **not only a filter gate**. `main.py:2489` iterates it inside `DELETE /api/semester/{semester_id}` to delete each table's rows for that semester. If a table listed there does not exist in the database, that delete raises, the error is appended to `errors` (`main.py:2496`), and the endpoint returns 500 at `main.py:2517` — **after** steps 5, 6 and 7 have already deleted the students, teams, evaluations, and the `semester_config` row. The admin sees "Failed to delete some semester tables or data", the semester list never refreshes (the client throws before `clearSemesterCache()`), and the natural response is to retry the most destructive operation in the app against a half-torn-down state.

This was hit for real during implementation: `conversations` was added to `TABLES_WITH_SEMESTER_ID` while the migration was deliberately unapplied, and the change had to be reverted.

**Correct ordering:** apply `202608140001_delegate_conversations.sql` FIRST, then add `"conversations"` to `TABLES_WITH_SEMESTER_ID` in the same change. Never the reverse. Hardening that deletion loop to skip missing tables would remove the hazard generally, and is worth doing independently of this feature.

Sending a message also writes a `notifications` row per recipient portal.

**Correction — this does not work as shipped.** The rows are written with `recipient_email: null`, but every consumer queries `notifications` by `recipient_email`: student portal (`student_portal.py:2469`, `:2558`), mentor portal (`mentor_portal.py:2371`), and the admin bell (`TopNav.jsx:95`). The panel portal reads an entirely different table (`alerts`, via `panel.py:269`). A row with a null `recipient_email` is therefore returned to nobody, and combined with `notifyChannel` failures being console-only, the admin gets no signal either way. Since Phase 2 is out of scope, this means **Phase 1 has no working recipient-visible delivery at all**. Fixing it requires expanding the fan-out to one row per recipient email (as `notification_agent.py` does) and pushing panels through `panelSync`'s broadcast endpoint (as `Communication.jsx:150` already does).

## Phasing

**Phase 1 (this spec).** Migration, `delegateChannels.js`, the Delegate dashboard, the `api.js` allowlist entries, and tests. Admin can create conversations, send messages, and read replies. Recipients are notified through `notifications`.

Phase 1 is broadcast-only in practice: until Phase 2 ships, no recipient has a UI to reply with, so the reply-rendering half of the thread view will be exercised only by tests and manually inserted rows. This is a known and accepted interim state.

**Phase 2 (separate spec).** Inbox and reply UI in the mentor, student, and panel portals. Each is a separate React app with its own auth model, and the panel portal reaches its backend through `panelSync`-style authenticated endpoints rather than direct Supabase access — so it is a materially different integration per portal, not one component reused three times.

## Testing

Following the existing `node --test` convention (`apps/admin/tests/*.test.mjs`, per `ps-allocation.test.mjs`):

- `delegate-channels.test.mjs` — recipient resolution for each of the three channels, including empty mentor and empty team lists.
- `delegate-unread.test.mjs` — unread counting from `read_by` arrays: all-read, none-read, partially-read, and the admin's own messages never counting as unread to the admin.

Both target pure functions. The React rendering is left to manual verification against the running dev server, matching how the other admin pages in this repo are covered.

## Out of Scope

- File attachments on messages. The existing mail flow handles attachments; conversations are text-only in Phase 1.
- Editing or deleting sent messages.
- Recipient-initiated conversations. All threads start with admin in both phases.
- Replacing or migrating `Communication.jsx` / `PerTeamMail.jsx`. Email blasts remain as they are; conversations are additive.
