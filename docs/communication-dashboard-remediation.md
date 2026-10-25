# Communication Dashboard — Remediation Plan

Five defects, ordered by what they cost you rather than by effort. Each
records what is actually wrong, what to change, and how to prove the change
worked. Cited to file:line so nothing here has to be taken on trust.

## Current shape

One React page (622 lines) drives ten endpoints on `admin-api`
(`communication_agent.py`, 880 lines). Four frontend consumers use them:
`Communication.jsx`, `PerTeamMail.jsx`, `Views.jsx`, and `services/api.js`.

Three further implementations exist and are routable but unused:

| Path | Lines | State |
|---|---|---|
| `backend/admin-api/app/communication_agent.py` | 880 | **live** |
| `backend/mentor-api/app/services/communication_service.py` | 384 | mounted, unused |
| `backend/app/services/communication_service.py` | 384 | byte-identical to the above; not deployed |
| `backend/student-api/app/api/communication.py` | — | mounted, unused |

---

## 1. "Delivered" is not delivery  (highest value)

**Now.** `communication_agent.py:514` writes
`"status": "Delivered" if delivered else "Logged"`. `delivered` is set from
`send_smtp_async`, which starts a **daemon thread and returns immediately**
-- so it means "we began trying", never "the server accepted it". The insert
is wrapped in `except: pass  # logging is best-effort`, so the row can also
vanish silently.

`communication_history` stores one row per *send*, with recipients as a
display string (`"A Specific Team (2)"`). No addresses, no per-recipient
result. 566 rows exist and none can be verified.

This is why the SMTP outage went unnoticed: every failed send still read
"Delivered".

**Change.** Make the sender report outcomes instead of firing and forgetting.

- Give `_send_smtp_chunked` a result: `{sent: [...], failed: [(addr, err)]}`.
  It already tracks `success_count` internally -- it just discards it.
- Add `email_deliveries`: one row per recipient per send, with
  `communication_id`, `email`, `status` (`sent` / `failed` / `skipped`),
  `error`, `attempted_at`.
- Write `status` only after the send resolves. Use `queued` while in flight,
  then `sent` / `partial` / `failed`.
- Stop swallowing the history insert. A failed audit write is worth surfacing.

**Proof.** Send to two addresses, one deliberately invalid. Expect one `sent`
row, one `failed` row carrying the SMTP error, and a parent status of
`partial`. Break `MAIL_PASSWORD` and confirm the history shows `failed`, not
`Delivered`.

---

## 2. The browser orchestrates a distributed transaction

**Now.** `Communication.jsx:91-178` fires four sequential calls to three
backends on one click: `admin-api /send`, a Supabase `notifications` upsert,
`panel-api /admin/sync/broadcast`, `mentor-api /api/admin/broadcast`.

The last three are each wrapped in
`catch { console.warn('... (non-critical)') }`. The UI reports success if the
first succeeded. Closing the tab mid-flight abandons the rest. No retry, no
queue, no record that a step was skipped.

**Change.** Move the fan-out behind the existing `/send` endpoint. The browser
makes one call; the server does the rest and returns per-step results.

- `/send` performs the notification write and both portal broadcasts.
- Response carries a per-step outcome the UI can render, rather than
  discarding it.
- Failed steps are recorded, not printed.

Keep the steps independent -- a panel-portal outage should not block the
email. The difference is that the failure becomes *visible* rather than
inferred from a console the operator never opens.

**Proof.** Stop the panel backend, send, and confirm the response reports the
panel step failed while the email still went. Confirm a row records it.

---

## 3. Three unused implementations, already drifting

**Now.** `mentor-api` and `backend/app` hold **byte-identical** copies of a
384-line service; `student-api` has another. All mounted, none reachable from
any UI.

They have already diverged from the live one: admin-api defines 9 templates,
mentor-api 7 -- `proposal_revision` and `proposal_resubmitted` exist only in
admin-api. Someone fixed the live copy without knowing the others existed.

**Change.** Delete `backend/app/services/communication_service.py`,
`backend/mentor-api/app/services/communication_service.py` and their routers
and schedulers, and the `student-api` router. Unmount them from each `main.py`.

Two things to check first, because deleting a mounted router is not free:
- `mentor-api`'s `communication_scheduler` is started from `main.py:25-27`.
  Confirm nothing depends on that poller before removing it.
- Anything importing `send_mail` from those modules must be repointed.

If a portal genuinely needs to send later, it should call admin-api rather
than carry its own copy.

**Proof.** Grep for imports of each deleted module. Boot all four backends and
confirm no import error. Exercise every consumer -- Communication, PerTeamMail,
Views, deadline mail -- and confirm none regress.

---

## 4. Segments and templates hardcoded in the UI

**Now.** `Communication.jsx:63-71` hardcodes all seven segments. The backend
already serves `GET /segments` and `GET /templates` (`communication_agent.py:535,539`)
and the page never calls either. They agree today by coincidence.

**Change.** Fetch both on mount; keep the hardcoded list as the fallback for a
failed request, so a settings outage degrades rather than empties the form.

**Proof.** Add a segment backend-side and confirm it appears without a
frontend change.

---

## 5. `is_active` means three different things

**Now.**

| Consumer | Behaviour |
|---|---|
| Mentor Allocation (`MentorAllocation.jsx:176`) | excludes `is_active === false` |
| Mentor login (`auth.py:337`) | 403 unless `is_active` |
| Communication `mentors` segment (`communication_agent.py:359`) | ignores it |

All 17 mentors are currently `is_active: false`, so they are simultaneously
too inactive to allocate and active enough to email. The comment at line 357
says "we only want mentors of active semesters" while the query has no filter
at all.

**Change.** Decide the rule and apply it once. The defensible split is:
onboarding templates (`mentor_onboarding`) deliberately target inactive
mentors, everything else targets active ones. Then either split the segment
into `mentors` / `mentors_pending`, or filter by template intent -- and fix
the comment either way.

This is a product decision before a code one. Do not "fix" it by adding a
filter that silently stops 17 people receiving their invitation.

**Proof.** With all 17 inactive, confirm the onboarding template still reaches
all 17 and a general announcement reaches whoever the chosen rule says.

---

## Order

1 and 2 first: together they turn a system that cannot report its own failures
into one that can, and neither needs the others. 3 is nearly free once
verified and stops the drift widening. 4 is small. 5 is blocked on a decision,
not on code.

Nothing here requires the four consumers to change behaviour -- the endpoints
keep their shapes. The work is in what happens behind them and what gets
recorded.
