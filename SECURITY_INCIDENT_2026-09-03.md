# Security incident & full remediation — 2026-09-03

Procksi · Supabase project `rmmkjczuwsuxcnrdtkrh`

This document records the 2026-09-03 compromise, **every** issue found in a full
sweep of the database / auth / API surface, what has been fixed, and what the
team must still do by hand (key rotations and dashboard settings this tooling
cannot change).

Re-verify at any time:

```
python -m scripts.security_audit --dsn "<fresh Postgres URI>" --md audit.md \
  --admin-emails "aiml_project_coordinator@example.edu,admin@example.edu"
```

---

## 1. What happened

An attacker registered ordinary Supabase accounts and used design flaws in the
authorization model to act as an administrator.

| When (UTC) | Event |
|---|---|
| 2026-08-12 → 09-02 | Reconnaissance: `directuser-evil@evil.com`, `idorprobe-student@example.edu`, `__sec_probe_*@evil.com` (13 accounts). |
| 2026-09-03 12:07 | `glaprocksi.nuke.1788437237@emalupe.com` registered. |
| 2026-09-03 12:10 | `attacker@emalupe.com` registered **with `data:{role:"admin"}`** in the signup body → passed the admin portal's auth check. |
| 2026-09-03 12:38 | Attacker signs in as admin. |
| 2026-09-03 ~15:29 | Broadcast email "Procksi — your data is exposed" sent from the coordinator address to students via the admin communication system. |
| 2026-09-03 ~18:09 | Taunt injected as a panel "Deadlines" alert after the team banned some accounts. |
| 2026-09-03 ~16:00 | This remediation applied. |

### Confirmed capability of the attacker
- **Admin API access** to `admin.your-domain.com` (send mail as coordinator, read/modify all admin data).
- **Full read/write on ~35 core tables** as any signed-up user (see 2.1).
- **Read/overwrite/delete of every Storage object** in the `Procksi` bucket (see 2.3).

Treat student PII, mentor password hashes, grades, and uploaded documents as
**breached**. Disclosure is the university's call.

---

## 2. Every issue found — and its status

Legend: **FIXED** = done in this pass · **MANUAL** = you must do it (below) ·
**MONITOR** = acceptable now, keep an eye on it.

### 2.1 `authenticated` role had unscoped read/write on 35 tables — CRITICAL — **FIXED**

Each of these carried a `FOR ALL … USING (true) WITH CHECK (true)` policy for
the `authenticated` role. Because Supabase issues an `authenticated` JWT to
**anyone who completes signup**, this was world read/write:

`students`, `mentors`, `sub_admins`, `panels`, `results`, `evaluations`,
`presentation_evaluations`, `presentation_evaluation_scores`,
`presentation_submissions`, `presentation_cycles`, `presentation_schedule`,
`presentation_rubrics`, `presentation_cycle_audit`, `semester_config`,
`governance_audit`, `communication_history`, `communication_templates`,
`notifications`, `schedule_slots`, `proposals`, `teams_validation`,
`team_memberships`, `mentor_allocations`, `problem_statements` (via
`project_*`), `evaluation_queue`, `evaluation_feed`, `project_locked_ps`,
`project_unallocated_students`, `project_override_logs`, `unassigned_students`,
`absent_students`, `makeup_slots`, `github_agent_analysis`, `chat_events`.

**Fix** — migration `sec_20260903_drop_permissive_authenticated_policies`: every
such policy dropped. `chat_events` (a content-free realtime ping —
`conversation_id` + timestamp only) keeps a `SELECT` policy for `anon` +
`authenticated` because the browser needs it. All other tables now have RLS ON
with **no policy** → `anon`/`authenticated` get nothing; the backends' service
role still bypasses RLS normally.

Verified: `GET /rest/v1/students` as anon → `401 permission denied for table students`.

### 2.2 `anon` / `authenticated` held table privileges on ~67 tables — HIGH — **FIXED**

Even with RLS on, `anon` and `authenticated` had `SELECT/INSERT/UPDATE/DELETE/
TRUNCATE/REFERENCES/TRIGGER` **grants** on almost every table, including
`admins`, `users`, `refresh_tokens`, `revoked_tokens`, `google_credentials`,
`mentors`. RLS was the *only* thing standing between the internet and this data —
one careless policy away from disaster.

**Fix** — migrations `sec_20260903_revoke_anon_authenticated_privileges` and
`sec_20260903_revoke_all_anon_select`: all write privileges and all read
privileges revoked from both roles on every `public` table (except `SELECT` on
`chat_events`). `ALTER DEFAULT PRIVILEGES` updated so new tables don't inherit
them. Backends are unaffected (service role).

### 2.3 Storage `Procksi` bucket world-writable — CRITICAL — **FIXED**

`storage.objects` had four `public`-role policies (`SELECT/INSERT/UPDATE/DELETE`)
scoped to `bucket_id = 'Procksi'`. Anyone with the publishable key could download,
overwrite or delete every uploaded document. (The bucket itself had already been
switched to private by the team, but the write policies remained live.)

**Fix** — migration `sec_20260903_storage_and_rpc_lockdown`: all four policies
dropped. Backends use the service-role key for storage and are unaffected.

Verified: `GET /storage/v1/object/public/Procksi/x` → `400 Bucket not found`;
anon object list → empty.

### 2.4 Admin portal trusted `user_metadata.role` — CRITICAL — **FIXED (code, needs deploy)**

`backend/admin-api/app/auth_guard.py` and `main.py` granted admin when the
Supabase user's **`user_metadata.role == "admin"`**. `user_metadata` is set by
the client in the `POST /auth/v1/signup` body, so it is attacker-controlled —
this is exactly how `attacker…@emalupe.com` became an admin.

**Fix (two parts):**
- Migration `sec_20260903_admin_role_to_app_metadata`: set
  `app_metadata.role = 'admin'` (server-only, not client-writable) on the two
  genuine admin accounts (`admin@example.edu`, `aiml_project_coordinator@example.edu`),
  then stripped `role` / `is_admin` / `claims` from **every** account's
  `user_metadata`.
- Code (branch `security/incident-2026-09-03-hardening`): `auth_guard.py`,
  `login()`, `get_admins()`, `create_admin()`, `forgot_password()` and the
  master auto-provision now read/write **`app_metadata`**. Added a
  `banned_until` check so disabled accounts are rejected.
- **After you deploy admin-api:** `admin@example.edu` must log in again (its
  current access token still references the old metadata). `aiml_project_coordinator@example.edu`
  is unaffected (matched by the master-email path).

### 2.5 Attacker & probe accounts still active — HIGH — **FIXED**

**Fix** — migration `sec_20260903_ban_attacker_and_probe_accounts`: 14 accounts
set `banned_until = 'infinity'` (not deleted — forensics preserved), their
`auth.sessions` rows deleted. Banned: both `glaprocksi*nuke*@emalupe.com`, and
`__sec_probe_*` / `*@evil.com` / `idorprobe-student@example.edu` /
`directuser-evil@evil.com`.

### 2.6 `emit_chat_event()` callable by anyone — HIGH — **FIXED**

`SECURITY DEFINER` function exposed at `POST /rest/v1/rpc/emit_chat_event`,
executable by `anon`. **Fix** — `REVOKE EXECUTE … FROM anon, authenticated,
public`. It is still fired by the trigger on `conversation_messages` (triggers
run as the table owner regardless). Verified: direct call → `404 PGRST202`.

### 2.7 Unauthenticated FastAPI endpoints — HIGH/MEDIUM — **FIXED (code, needs deploy)**

On branch `security/incident-2026-09-03-hardening`:

| Endpoint | Was | Now |
|---|---|---|
| `POST /api/student/admin/publish-results` (student-api) | no auth; ignored its own `admin_key` field | requires `X-Admin-Api-Key` header (hmac compare) |
| `GET /api/student/join-requests/debug` (student-api) | no auth; IDOR dump of `team_join_requests` for any student id | **route removed** |
| `POST /api/student/problem-statements/generate-ai-suggestions` (student-api, ×2 registrations) | no auth; unmetered OpenAI spend | requires `get_current_student` |
| `GET /api/mentor/semesters` (mentor-api) | no auth; full `semester_config` dump | requires `get_current_mentor` |
| `GET /panel/semesters` (panel-api) | no auth; full `semester_config` dump | requires `get_current_user` |

`/api/*/procksi-chat-enabled` endpoints are intentionally public (a single boolean,
no data) and were left as-is.

### 2.8 `ADMIN_API_KEY` compiled into the public admin bundle — CRITICAL — **MANUAL**

`apps/admin/dist/assets/index-*.js` contains the literal
`X-Admin-Api-Key` value (`b519b36c…`, from `VITE_ADMIN_API_KEY`). It is the
**only** credential `panel-api`'s `/admin/sync/*` routes check, so anyone who
opens that JS file can create/rename panel accounts and reset their passwords
(`PUT /admin/sync/panels/{id}` writes `users.hashed_password`), rewrite
evaluations / rubrics / schedule, and post panel alerts. This is almost
certainly how the taunt alert and the broadcast were planted.

**Not fixable by rotation alone** (the new key would be baked into the new
bundle). Required:
1. Rotate `ADMIN_API_KEY` (panel-api `.env` + wherever admin references it).
2. Move the `panelSync.js` calls **server-side**: admin frontend → admin-api
   (which holds the key as a server env var) → panel-api. Remove
   `VITE_ADMIN_API_KEY` from the admin build entirely.
3. Until (2) ships, take `panel-api` `/admin/sync/*` off the public internet
   (network ACL / disable the router).
4. The key value is also in git history (commit `db60b69`); rotation is
   mandatory regardless.

### 2.9 Open public signup + auto-confirm — HIGH — **MANUAL (dashboard)**

Anyone can create an `authenticated` session with the publishable key, and
(with 2.1/2.2 fixed) that no longer grants data access — but it is still the
entry point for anonymous abuse and was step 1 of this incident.

- **Supabase → Authentication → Sign In / Providers:** disable email signups, or
  restrict to an allowed domain / invite-only. Review the Google provider the
  same way.
- **Authentication → enable email confirmation** (turn off auto-confirm).
- **Authentication → enable "Leaked password protection"** (advisor `auth_leaked_password_protection`).
- Consider a CAPTCHA on auth endpoints.

### 2.10 `pre_request_guard()` executable by anon — LOW — **MONITOR**

`SECURITY DEFINER`, anon/authenticated-executable (advisor
`0028_anon_security_definer_function_executable`). This is the team's own
IP-block hook (migration `ip_block_pre_request`, with `blocked_ips`). It is
meant to run on every PostgREST request. **Either** wire it as the
`db-pre-request` hook (Settings → API → "DB pre-request function") **or**
`REVOKE EXECUTE … FROM anon, authenticated` if it is not in use. It does not
mutate data, so the risk is low.

### 2.11 `rls_enabled_no_policy` on ~70 tables — INFO — **expected / not a bug**

The security advisor now lists every table as "RLS enabled, no policy". After
this remediation that is the **intended** state: RLS on + no policy = deny-all
for `anon`/`authenticated`; the backends' service-role key bypasses RLS and is
unaffected. No action needed. If you later want any table readable directly by
the browser, add a *scoped* policy (`USING (… = auth.uid())`) — never
`USING (true)`.

---

## 3. Manual actions still required (in priority order)

1. **Rotate every secret that was exposed or may have been used:**
   - Supabase **anon (publishable)** + **service_role (secret)** keys — Settings →
     API. Rotating the legacy JWT secret invalidates all sessions; update every
     backend `.env` and rebuild all 4 frontends.
   - Supabase **database password** — the one in `backend/*/.env` `DATABASE_URL`
     already fails auth (stale); set a known one so the auditor's static pass and
     any direct-Postgres tooling work.
   - **`ADMIN_API_KEY`** (see 2.8).
   - FastAPI **`SECRET_KEY`** for mentor-api / student-api / panel-api (JWT
     signing; values appear in git history — commit `db60b69`).
   - **SMTP** credentials for the coordinator mailbox (mail was sent as it) — and
     check that mailbox for forwarding rules / filters the attacker may have added.
   - **Google OAuth** client secret; **OpenAI** API key.
2. **Deploy** branch `security/incident-2026-09-03-hardening` to admin-api,
   student-api, mentor-api, panel-api.
3. **Apply 2.8 and 2.9.**
4. **Reset credentials** for the 6 `users` rows with `role = 'panel'` and both
   `admins` rows (`admin@procksi.com`, `student@procksi.com` — likely seed defaults).
   Force a password reset on `aiml_project_coordinator@example.edu`.
5. **Forensics / scope:** snapshot the DB now; pull Supabase Postgres + Auth +
   Storage logs for 2026-08-12 → now; diff `results`, `governance_audit`,
   `communication_history`, `panels`, `users`, `evaluations` for tampering; keep
   the 14 banned accounts for investigation.
6. **Notify** the recipients of the "your data is exposed" email that it was not
   an official message; handle breach-disclosure obligations for student PII +
   mentor password hashes.
7. **Rebuild** the frontends so no built bundle under `apps/*/dist/` carries a
   secret; add `apps/*/dist/` to `.gitignore` if it isn't already ignored on the
   server.

---

## 4. Changes applied in this pass

### Database (migrations, live on `rmmkjczuwsuxcnrdtkrh`)
| Version | Name |
|---|---|
| 20260903161344 | `sec_20260903_drop_permissive_authenticated_policies` |
| 20260903161353 | `sec_20260903_revoke_anon_authenticated_privileges` |
| 20260903161401 | `sec_20260903_storage_and_rpc_lockdown` |
| 20260903161411 | `sec_20260903_admin_role_to_app_metadata` |
| 20260903161432 | `sec_20260903_ban_attacker_and_probe_accounts` |
| 20260903161834 | `sec_20260903_revoke_all_anon_select` |

### Code (branch `security/incident-2026-09-03-hardening`, not deployed)
- `backend/admin-api/app/auth_guard.py` — trust `app_metadata.role`, not
  `user_metadata`; reject `banned_until` accounts.
- `backend/admin-api/app/main.py` — `login`, `get_admins`, `create_admin`,
  `forgot_password`, master auto-provision → `app_metadata`.
- `backend/student-api/app/api/student_portal.py` — auth on `publish-results`
  (admin-key header) and the AI-suggestions routes; `join-requests/debug`
  removed; drop the unused `admin_key` field.
- `backend/mentor-api/app/api/mentor_portal.py` — auth on `GET /api/mentor/semesters`.
- `backend/panel-api/app/routers/panel.py` — auth on `GET /panel/semesters`.

### Tooling added
- `scripts/security_audit/` — reusable auditor (RLS, grants, policies,
  functions, views, storage, JWT/auth, live anon probe). `README.md` inside.
- `.claude/agents/db-security-audit.md` — subagent wrapper.

---

## 5. Post-fix verification (2026-09-03, anon publishable key)

| Check | Result |
|---|---|
| `GET /rest/v1/students?limit=1` | `401 permission denied for table students` |
| `POST /rest/v1/rpc/emit_chat_event` | `404 PGRST202` (not exposed) |
| `GET /storage/v1/object/public/Procksi/x` | `400 Bucket not found` |
| `GET /storage/v1/bucket` | `200 []` (no buckets disclosed) |
| Permissive `anon`/`authenticated` policies remaining | `chat_events` SELECT only (by design) |
| `anon`/`authenticated` write grants remaining | 0 |
| Security advisor | only `rls_enabled_no_policy` (expected) + `pre_request_guard` WARN (2.10) + leaked-password WARN (2.9) |
