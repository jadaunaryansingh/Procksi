# GLA PMS — Full-Stack Security Audit

Supabase project `rmmkjczuwsuxcnrdtkrh` · Repo `Project_Management_System` · Branch `security/incident-2026-09-03-hardening`
Audit date: 2026-09-04 (UTC). Read-only throughout — no data was modified, no auth users were created/banned/deleted, no application code was changed.

This audit is a follow-up to `SECURITY_INCIDENT_2026-09-03.md`. Section 4 below cross-references every item in that document's §2/§3.

---

## 1. Verdict

**The database layer is in good shape (the 2026-09-03 remediation held); the API/secrets layer is not.** The single most damaging item from the original incident — the shared `ADMIN_API_KEY` that lets anyone rewrite panel accounts, passwords, evaluations and rubrics — is **still completely unresolved**: the key was never rotated, it is still the literal value that has sat in git history since commit `db60b69` (2026-08-09), and it is **still compiled into the publicly served admin bundle** (confirmed by a byte-for-byte match against the live file `apps/admin/dist/assets/index-nqnFGzlK.js`). Anyone who opens that JS file today can still do everything the 2026-09-03 attacker did to the panel portal. Two new issues not covered by the original incident were also found: a wildcard CORS policy on all four live backends, and an authenticated-but-unscoped IDOR on the AI-suggestions endpoint that lets any student overwrite other teams' problem-statement data.

### Severity summary

**Database / RLS / JWT**

| Severity | Count |
|---|---:|
| CRITICAL | 0 |
| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 0 |
| INFO | 2 |

**API endpoints**

| Severity | Count |
|---|---:|
| CRITICAL | 1 (cross-referenced with Secrets — counted once in the grand total) |
| HIGH | 1 |
| MEDIUM | 2 |
| LOW | 2 |
| INFO | 1 |

**Secrets / bundles**

| Severity | Count |
|---|---:|
| CRITICAL | 1 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 0 |
| INFO | 0 |

**Grand total (deduplicated): CRITICAL 1 · HIGH 2 · MEDIUM 3 · LOW 2 · INFO 3**

---

## 2. Findings, CRITICAL → INFO

### CRITICAL

#### C-1. `ADMIN_API_KEY` — unrotated, still in git history, still shipping in the public admin bundle, still the only guard on panel-api's admin-sync surface

**Location:**
- Secret value: `backend/panel-api/.env` (`ADMIN_API_KEY=b519b36c09db8dbd172b4649c312b1016b7e…`)
- Same literal value baked into: `apps/admin/dist/assets/index-nqnFGzlK.js` (built from `apps/admin/src/services/panelSync.js:23-28`, via `apps/admin/Dockerfile` which explicitly documents "Vite inlines this into the bundle at build time")
- Guard: `backend/panel-api/app/deps.py:53-62` (`require_admin_key`), applied to every route in `backend/panel-api/app/routers/admin.py` (panel create/rename, panel-user password reset, rubric replace, team/slot bulk upsert, broadcast, alerts — 13 routes, all `dependencies=[Depends(require_admin_key)]`)
- Reachability: `deploy/cloudflared/config.yml` routes `panel.glapms.in` → `panel-frontend`; `apps/panel/nginx.conf:53-59` proxies `location /admin/` straight to `panel-backend:8001/admin/` — i.e. `POST https://panel.glapms.in/admin/sync/panels/{id}` is a real, internet-reachable, unauthenticated-except-for-this-key endpoint today.
- Git history: `git show db60b69` contains the literal key 4 times; the commit has never been purged from history.

**Proof (live-verified, values not printed):**
```
$ grep -c -- "$(grep '^ADMIN_API_KEY=' backend/panel-api/.env | cut -d= -f2-)" apps/admin/dist/assets/index-nqnFGzlK.js
1
```
The value currently active in `backend/panel-api/.env` is byte-identical to the one the incident report already named as compromised.

**Impact:** Identical to incident §2.8: anyone who downloads `apps/admin/dist/assets/index-nqnFGzlK.js` (a public, unauthenticated static asset) can extract `X-Admin-Api-Key` and, without ever touching the admin portal's login, directly call `panel-api`'s `/admin/sync/*` routes to: create/rename panels, **reset any panel account's password** (`PUT /admin/sync/panels/{id}` writes `users.hashed_password`), overwrite the evaluation rubric, bulk-rewrite team/project/GitHub metadata, and post fake panel alerts. This is exactly the mechanism believed to have delivered the attacker's taunt alert and the broadcast phishing email in the original breach — it is still live.

**Fix (unchanged from incident §2.8, none of it has been done):**
1. Rotate `ADMIN_API_KEY` in `backend/panel-api/.env` (and anywhere else it's read from) to a fresh, never-committed value.
2. Move `panelSync.js`'s calls server-side: admin frontend → `admin-api` (which holds the key as a server-only env var, never shipped to a browser) → `panel-api`. Remove `VITE_ADMIN_API_KEY` from `apps/admin/Dockerfile`, `docker-compose.yml`, and `apps/admin/.env*` entirely, and rebuild the admin bundle so the old key is no longer served.
3. Until (2) ships, take `panel-api`'s `/admin/sync/*` off the public internet (drop the `location /admin/` proxy in `apps/panel/nginx.conf`, or add a network ACL) — this is a one-line mitigation available today.
4. Because the key is also in git history (`db60b69`), rotation is mandatory regardless of whether/when the architecture fix lands.

---

### HIGH

#### H-1. `pre_request_guard()` — SECURITY DEFINER, still executable by `anon`/`authenticated`, live-probe confirmed callable

**Location:** `public.pre_request_guard()` (owner `postgres`, `SECURITY DEFINER`)
**Status:** Confirmed still open — this is incident §2.10, previously logged as MONITOR/LOW. Re-verified live this session:
```
POST /rest/v1/rpc/pre_request_guard  →  HTTP 204 (anon key, no auth)
```
Also flagged by `mcp__supabase__get_advisors(security)`: `anon_security_definer_function_executable` and `authenticated_security_definer_function_executable`, both WARN.

**Impact:** This is the team's own IP-block hook (`blocked_ips` table). It runs with the definer's (postgres) privileges and is directly callable by anyone with the anon key. It does not currently mutate data (low practical risk, matching the incident's original MONITOR rating), but it is not doing its job either — if it is meant to run as the `db-pre-request` hook to block IPs, it has evidently **not been wired up**, since a normal anon RPC call to it succeeds instead of being intercepted beforehand. Raising this to HIGH per the audit's own severity guide ("SECURITY DEFINER function anon can execute"), because an unused SECURITY DEFINER RPC reachable by anon is a standing latent-privilege-escalation surface even when today's implementation happens to be inert — any future edit to this function's body (e.g. adding a write) would immediately become anon-exploitable with no additional review trigger.

**Fix:** Either wire it as the Supabase `db-pre-request` hook (Settings → API → "DB pre-request function") so it actually blocks the IPs it's meant to, **or** `REVOKE EXECUTE ON FUNCTION public.pre_request_guard() FROM anon, authenticated;` if it's not in active use. This has been sitting open since 2026-09-03.

---

### MEDIUM

#### M-1. CORS: `allow_origin_regex=r"https?://.*"` + `allow_credentials=True` on all four live backends

**Location:**
- `backend/admin-api/app/main.py:427-428`
- `backend/mentor-api/app/main.py:157-158`
- `backend/panel-api/app/main.py:105-106`
- `backend/student-api/app/main.py:55-56`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,        # a real, curated whitelist...
    allow_origin_regex=r"https?://.*",    # ...defeated by this: matches ANY http(s) origin
    allow_credentials=True,
    ...
)
```
Each service also has a hand-rolled `Access-Control-Allow-Origin: <reflected request Origin>` + `Access-Control-Allow-Credentials: true` fallback in its manual `OPTIONS`/exception-handling code (e.g. `backend/student-api/app/main.py:61-70`, `112-115`), which independently reproduces the same "reflect any origin with credentials" behavior even if the middleware regex were tightened.

**Note on production exposure:** in the current Cloudflare/Nginx topology, each frontend's Nginx same-origin-proxies `/api/` and `/auth/` to its own backend (`apps/*/nginx.conf`), so ordinary browser traffic never actually needs cross-origin CORS in production. The backends are still directly reachable, however, by any script that talks HTTP straight to the backend (not through a browser's same-origin model) — e.g. panel-api's `/admin/sync/*` is directly internet-routable (see C-1), and any of the four backend ports could become directly exposed by a future infra change without anyone noticing the CORS policy was already wide open. `backend/app` (dead code, see §3) shows the *intended* pattern — `allow_origin_regex=r"https?://(.*\.)?glapms\.in(:[0-9]+)?"` — the live services regressed from that to a wildcard at some point.

**Impact:** Any website can issue a credentialed cross-origin request to any of these four APIs and have the browser honor cookies/credentials on it. Actual exploitability depends on whether any of these services rely on cookie-based auth for a browser session (most auth here is header-based Bearer tokens, which a third-party page cannot forge without already having the token) — so this is defense-in-depth-severity rather than an immediately demonstrated account-takeover, hence MEDIUM rather than CRITICAL. It should still be fixed: it is one infra change away from being directly exploitable, and it defeats the purpose of maintaining a curated origin allowlist at all.

**Fix:** Drop `allow_origin_regex` (or restrict it to `r"https?://(.*\.)?glapms\.in(:[0-9]+)?"` as `backend/app`'s dead copy already does) on all four live services, and replace the manual `Access-Control-Allow-Origin: <reflected>` fallbacks with a lookup against the same curated `allowed_origins` list instead of blindly reflecting the request's `Origin` header.

#### M-2. `generate-ai-suggestions` — authenticated-but-unscoped bulk `UPDATE` on `problem_statements` / `teams_validation` (IDOR / mass data-integrity risk)

**Location:** `backend/student-api/app/api/student_portal.py:2856-2986` (route `POST /api/student/problem-statements/generate-ai-suggestions`, the live copy — a byte-identical duplicate route is also registered at `:5097-5268` but is dead code since FastAPI keeps only the first registration for a given path+method).

```python
# student_portal.py:2968-2982
if payload.title:
    try:
        clean_title = payload.title.strip()
        # 1. Update problem_statements
        await supabase_client.client.table("problem_statements").update({...})\
            .ilike("title", f"%{clean_title}%").execute()
        # 2. Update teams_validation
        await supabase_client.client.table("teams_validation").update({...})\
            .ilike("title", f"%{clean_title}%").execute()
```

**Impact:** The endpoint requires `get_current_student` (correctly matches incident §2.7's fix — it is no longer unauthenticated), but the write it performs afterwards is scoped only by an `ILIKE` pattern built directly from the caller-supplied `payload.title`, with **no check that the matched `problem_statements`/`teams_validation` rows belong to the caller's own team**. Any authenticated student can:
- send a broad/generic `title` (e.g. a single common word, or `"%"`-style wildcard content) to match and overwrite the `description`/`domain`/`difficulty` of problem statements and team records belonging to *other* teams, with AI-generated filler content;
- repeat this at will (see M-3, no rate limiting) to degrade or vandalize the shared problem-statement catalog used by every team.

This is the same class of bug the incident's §2.7 IDOR fixes targeted (`join-requests/debug`), just in a route that already got an auth-dependency fix but not an ownership-scoping fix.

**Fix:** Scope both updates to the caller's own team (join through the student's `team_membership`/`team_uid`, matching the ownership pattern already used correctly elsewhere in this same file, e.g. `get_student_proposal_detail` at line ~673-698), and use an exact-match key (row id / team_uid) instead of an unscoped `ILIKE %title%` for the `UPDATE ... WHERE` clause. Also remove the dead duplicate route at line 5097 to reduce future-maintenance risk of the fix landing on only one copy.

---

### LOW

#### L-1. Shared JWT `SECRET_KEY` across mentor-api, panel-api, and student-api, with no audience/issuer separation

**Location:** `backend/mentor-api/.env`, `backend/panel-api/.env`, `backend/student-api/.env` — all three `SECRET_KEY` values are identical (verified by SHA-256 comparison without exposing the value); `jwt.encode()`/`jwt.decode()` calls in `backend/{mentor,panel,student}-api/app/core/auth.py` and `backend/panel-api/app/security.py` set no `aud`/`iss` claim.

**Impact:** A token minted by any one of these three services passes signature verification on the other two (same secret, same `HS256` algorithm). In practice this is not currently exploitable because each service's `sub` claim addresses a different ID-space that must resolve against that service's own table (student-api: `admins.id`, mentor-api: `mentors.id`, panel-api: `users.email`) — a token minted for one service's identity space will simply 404/401 when looked up under another service's semantics, absent an accidental primary-key collision across tables. This is nonetheless a defense-in-depth gap: a single leaked `SECRET_KEY` compromises three independently-deployed services at once, and there is no cryptographic boundary (`aud`) stopping a token from even being *attempted* against the wrong service.

**Fix:** Give each service its own `SECRET_KEY`, and add an `aud` (or a service-name) claim that each service's decode step verifies, so a token minted for one service is rejected outright by the others regardless of ID-space collisions.

#### L-2. No rate limiting on costly/abusable authenticated endpoints

**Location:** repo-wide — no rate-limiting library (`slowapi`, or equivalent) or per-user throttle found in any of the four services. Concretely costly examples: `POST /api/student/problem-statements/generate-ai-suggestions` (OpenAI call, see M-2), `POST /api/mentor/teams/{team_id}/github/analyze` (`backend/mentor-api/app/api/mentor_portal.py:1884`), `POST /api/admin/communication/broadcast` and `POST /api/mentor/communication/send` (bulk email).

**Impact:** Any authenticated-but-untrusted user can call these repeatedly to run up third-party API costs (OpenAI, GitHub analysis) or spam the mailbox used for outbound communication. Matches the audit brief's explicit severity guide ("missing rate limit on a costly operation" = MEDIUM in general; rated LOW here specifically because every such endpoint already requires real authentication post-incident, so the blast radius is "an abusive legitimate account", not "the open internet").

**Fix:** Add per-user/per-IP rate limiting (e.g. `slowapi`) to AI-backed and bulk-communication endpoints.

---

### INFO

#### I-1. `backend/app` is dead legacy code — not deployed, not referenced anywhere

**Evidence:** No `Dockerfile` in `backend/app/`; not a service in `docker-compose.yml` (only `admin-api`, `panel-api`, `student-api`, `mentor-api` are built); not started by `start_pms.sh`/`start_pms.bat` (they invoke `backend/admin-api`, `backend/panel-api`, `backend/student-api`, `backend/mentor-api` only); no reference in `.github/workflows/deploy-ec2.yml` or `deploy-main.yml`; `git log --oneline -- backend/app` shows no recent commits. It appears to be an old, pre-split copy of what is now `student-api` (it even has its own copies of `student_portal.py`, `mentor_portal.py`, etc.) and still shows the **more restrictive** CORS regex (`r"https?://(.*\.)?glapms\.in(:[0-9]+)?"`) that the live services have since regressed away from (see M-1) — additional evidence it predates the current wildcard CORS and was never updated because it isn't running. **Not audited as a live surface; flagged here for cleanup** (a stale, unmaintained copy of sensitive backend logic sitting in the repo is itself a minor risk if anyone ever wires it up by accident).

**Recommendation:** Delete `backend/app` (and the sibling top-level `backend/alembic`, which appears to belong to it) once confirmed unused, or clearly mark it archived.

#### I-2. Duplicate route registration for `generate-ai-suggestions`

See M-2 — `backend/student-api/app/api/student_portal.py` registers `POST /api/student/problem-statements/generate-ai-suggestions` twice (lines 2856 and 5097). FastAPI silently keeps only the first; the second is dead code that will bit-rot and mislead future maintainers into thinking there are two independent code paths to patch.

#### I-3. `chat_events` anon/authenticated `SELECT` — reconfirmed intentional, unchanged

See §3 "already fixed" below.

---

## 3. Already fixed / matches incident report — reverified this session

- **35-table world read/write (incident §2.1)** — reverified: the `sec_20260903_drop_permissive_authenticated_policies` migration is still in effect. Live auditor run (`scripts.security_audit`, static + anon-probe both `on`) shows only one remaining permissive anon/authenticated policy: `chat_events_readable` (`SELECT`, content-free ping table — no `conversation_id`/timestamp is sensitive). This matches the incident's documented, deliberate exception. **No other permissive policy exists on any of the 71 scanned `public` tables.**
- **`anon`/`authenticated` table grants (§2.2)** — reverified via `information_schema.role_table_grants`: zero write grants remain on any `public` table for `anon`/`authenticated`; the only read grant left is `SELECT` on `chat_events`. All other `public` tables show `rls_enabled_no_policy` (RLS on, deny-all) — the intended post-remediation state.
- **Storage `PMS` bucket (§2.3)** — reverified: `storage.buckets.public = false`; `pg_policies` on `storage.objects`/`storage.buckets` is **empty** (no policies at all, i.e. deny-all beyond the service-role key). No public read/write path.
- **`emit_chat_event()` RPC (§2.6)** — not independently re-probed this session (would require a write-probe, which was out of scope), but the `pg_proc`/grants scan shows no `EXECUTE` grant to `anon`/`authenticated` remains on it, consistent with the incident's fix.
- **`user_metadata.role` trust (§2.4, root cause of the original breach)** — reverified in code: `backend/admin-api/app/auth_guard.py:125-130` and every admin-role-granting code path in `backend/admin-api/app/main.py` now read `app_metadata.role`, never `user_metadata`. Repo-wide grep for `user_metadata` across all four live services turns up exactly one remaining use, in `backend/student-api/app/api/student_deps.py:136`, and it's cosmetic only (`full_name`/`name` for display), not an authorization decision. **No regression.**
- **Attacker/probe accounts (§2.5)** — reverified in `auth.users`: all 14 originally-named accounts are still `banned_until = infinity`, plus one additional account (`pms-admin-ops@gla.ac.in`) also banned. No unbanning occurred.
- **Unauthenticated FastAPI endpoints (§2.7)** — reverified in code: `POST /api/student/admin/publish-results` requires an `X-Admin-Api-Key` header; `GET /api/student/join-requests/debug` no longer exists (removed); both registrations of `generate-ai-suggestions` require `get_current_student` (see M-2 for the residual ownership gap); `GET /api/mentor/semesters` requires `get_current_mentor`; `GET /panel/semesters` requires `get_current_user`. A full route-by-route scan of every `@router.get/post/put/patch/delete` in all four services (`admin-api`, `mentor-api`, `panel-api`, `student-api` — see the methodology note below) found **no other unauthenticated write endpoint**; the only unauthenticated routes remaining anywhere are login/signup/refresh/forgot-password/reset-password (must be public to bootstrap auth) and the two documented `pms-chat-enabled` boolean probes.
- **RLS-bypassing views / `security_invoker`** — no views were found granted to `anon`/`authenticated` in `public` at all (grants scan returned only the two `chat_events` rows and standard `storage.*` schema-level grants that Supabase ships by default and that RLS on `storage.objects` — empty policy set — already blocks).
- **`anon`/`authenticated` role posture** — `rolbypassrls = false` and `rolsuper = false` for both; no membership in `service_role` or `postgres` (`pg_auth_members` empty for both roles). `service_role` correctly shows `rolbypassrls = true`.
- **JWT key style** — both the publishable and service-role keys are the new-style opaque, individually-revocable Supabase API keys (`sb_...`), not the legacy shared JWT secret — good baseline per the auditor's own check.
- **Admin API auth architecture (§2.4 code fix)** — `backend/admin-api/app/main.py:220-224` registers `require_admin` as an **application-level** dependency (not per-route), so a future forgotten `Depends()` cannot silently reopen an endpoint — this is a materially better pattern than the per-route dependency style used elsewhere, and worth calling out as good practice.
- **Panel-api ownership checks** — every panel-api route under `evaluation.py`/`panel.py`/`mentor.py` consistently pairs `Depends(get_current_user)` with `require_panel_access(panel_id, user)`, correctly scoping panel-role users to their own `panel_id` (admin role bypasses, as intended). No IDOR found in this service.
- **student-api team ownership checks** — `remove-member`/`add-member`/proposal-detail routes in `student_portal.py` all explicitly verify the target resource belongs to the caller's own team before acting, including an in-code comment documenting a previously-fixed cross-team leak in the removal fallback path. Good.
- **SQL injection sweep** — no string-formatted SQL statement text was found anywhere that interpolates *request-supplied values*; the only `f"...{var}..."` raw-SQL patterns found (in `mentor_portal.py` and `github_sync_scheduler.py`) interpolate a column-name selector (`gh_field`) that is hardcoded to one of exactly two literal strings (`"team_uid"` / `"team_ref"`) chosen server-side — not attacker-controlled — with all actual values passed as bound parameters (`:gh_val`). Clean.
- **`.gitignore` / secrets hygiene** — `backend/*/.env`, `apps/*/.env*`, `apps/*/dist/`, `backups/`, and `docs/ENVIRONMENT_SETUP.md` are all correctly excluded, and `git ls-files` confirms none of them (nor any `.env` file anywhere in the repo) has ever been tracked. `docs/ENVIRONMENT_SETUP.md` (called out in `.gitignore` as containing real credentials) has never been committed. No hardcoded `sk-…`/`sb_secret_…`/AWS-style/private-key material was found anywhere in tracked source.

**Methodology note (route walk):** every `@router.get/post/put/patch/delete` decorator in `backend/admin-api/app/**/*.py`, `backend/mentor-api/app/api/**/*.py`, `backend/panel-api/app/routers/**/*.py`, and `backend/student-api/app/api/**/*.py` (and each service's `main.py`) was extracted programmatically and checked for an auth dependency (`Depends(get_current_*)`, `require_admin*`, `require_panel_access`, or an `X-Admin-Api-Key`/`admin_key` check) in its signature; `admin-api` additionally relies on its application-level `require_admin` dependency (confirmed separately, since it doesn't show up per-route). Every route not carrying one of these was individually read; all of them turned out to be intentionally public (auth bootstrap endpoints, or the two `pms-chat-enabled` booleans).

---

## 4. Cross-reference against `SECURITY_INCIDENT_2026-09-03.md` §2/§3

| Incident item | Status per this audit |
|---|---|
| §2.1 35-table world r/w | **FIXED, reverified** |
| §2.2 anon/authenticated table grants | **FIXED, reverified** |
| §2.3 Storage `PMS` bucket world-writable | **FIXED, reverified** |
| §2.4 Admin portal trusted `user_metadata.role` | **FIXED (code), reverified, no regression** — confirm §3 item 2 below on deploy status |
| §2.5 Attacker/probe accounts | **FIXED, reverified (15 banned now, was 14)** |
| §2.6 `emit_chat_event()` anon-executable | **FIXED per grants scan** (not re-probed live this session) |
| §2.7 Unauthenticated FastAPI endpoints | **FIXED in code, reverified** — residual ownership gap on `generate-ai-suggestions` newly found, see M-2 |
| §2.8 `ADMIN_API_KEY` in public admin bundle | **STILL FULLY OPEN — confirmed live and unrotated (C-1).** This is the highest-priority item in this entire audit. |
| §2.9 Open public signup + auto-confirm / leaked-password protection | **STILL OPEN.** `get_advisors(security)` still returns `auth_leaked_password_protection: WARN` live. Signup/auto-confirm dashboard settings were **not independently re-verified this session** (no Supabase Management API access token was available to the auditor, and `--signup-probe` was intentionally not run per this task's constraints) — 97 signups in the last 7 days (13 unconfirmed) is *consistent with* signup still being open but is not conclusive either way. Treat as still-MANUAL until the team confirms the dashboard setting directly. |
| §2.10 `pre_request_guard()` anon-executable | **STILL OPEN — live-probe reconfirmed (H-1).** Escalated from the incident's original LOW/MONITOR rating for the reasons given in H-1. |
| §2.11 `rls_enabled_no_policy` on ~70 tables | **Confirmed still the expected/intended state**, not a bug. |
| §3.1 Rotate exposed secrets (keys, DB password, `ADMIN_API_KEY`, `SECRET_KEY`, SMTP, Google OAuth, OpenAI) | DB password: confirmed rotated (static pass connected this session, previously failed). `ADMIN_API_KEY`: **confirmed NOT rotated** (C-1). Other secrets (SMTP, Google OAuth, OpenAI, FastAPI `SECRET_KEY`) were not independently testable from this audit's vantage point; their `.env` values were not compared against the historical git-leaked ones beyond `ADMIN_API_KEY`, which is the one this audit could conclusively check end-to-end (git history value = live `.env` value = value shipped in the current bundle). |
| §3.2 Deploy the hardening branch | The code fixes for §2.4/§2.7 are present in the checked-out branch (`security/incident-2026-09-03-hardening`) and were reviewed as source; whether they are running on production admin-api/mentor-api/student-api/panel-api right now was not independently verified (would require hitting the live public endpoints, which was out of scope for a read-only DB/code audit). Recommend the team confirm deploy status directly. |
| §3.3 Apply §2.8 and §2.9 | **Not done** — see above. |
| §3.4 Reset panel-user / `admins` seed credentials (`admin@pms.com`, `student@pms.com`) | Both seed rows still exist in `admins` (`admin@pms.com`, `student@pms.com`, both `role=ADMIN`). **Mitigating factor found this session:** `backend/student-api/app/api/auth.py:27-38`'s `/api/admin/login` now hard-rejects any email that isn't `@gla.ac.in` or the master coordinator address before even checking the password — so these two non-`@gla.ac.in` seed accounts are currently unreachable through that login route regardless of their password hash. The rows themselves were not deleted/reset, so this is a code-level mitigation, not a completed remediation; still recommend the credential reset per the incident doc as defense-in-depth (a future code path or a different auth surface could reintroduce reachability). |
| §3.5 Forensics / diff for tampering | Out of scope for this audit (would require historical diffing, not a live security scan). |
| §3.6 Notify affected recipients / breach disclosure | Organizational action, out of scope. |
| §3.7 Rebuild frontends so no secret ships in `dist/` | **Not done** — `apps/admin/dist/assets/index-nqnFGzlK.js` still contains the key today (C-1). |

---

## 5. Notes on scope and what was not re-verified live

- Layer 1 ran with the bundled `scripts.security_audit` tool in `static:on, probe:on (anon), write-probe:off, signup-probe:off` mode, per this task's constraints (`DATABASE_URL` connected successfully this session — no fallback to manual queries was needed, though several manual `execute_sql` checks were run anyway for completeness/cross-verification: storage policies, `pg_roles`, `pg_auth_members`, `auth.users` metadata scan, `admins` table contents).
- No write-probe or signup-probe was run (per instructions), so §2.9's dashboard-level signup/auto-confirm settings could not be conclusively confirmed either way this session — flagged as still-open/unverified rather than re-closed.
- Layer 2's route-auth walk was exhaustive (every route in all four live services, programmatically extracted and manually spot-checked); deeper business-logic review (every service/repository file behind each route) was not exhaustive given the codebase size (~150+ Python files across the four services) — the review prioritized auth-dependency presence, ownership/ID0R patterns on routes handling another user's ID, SQL construction, `user_metadata` trust, and cross-service JWT consistency, per the task brief.
- Layer 3's git-history check focused on `.env`-style files and the specific `ADMIN_API_KEY` commit named in the incident doc; a full history scan of every file that has ever been deleted from the tree was not performed (would require a much longer-running `git log --all --full-history` sweep across the entire repo, not just targeted paths).

---

## 6. File/location index for the findings above

- `backend/panel-api/.env`, `backend/panel-api/app/deps.py:53-62`, `backend/panel-api/app/routers/admin.py`, `apps/admin/src/services/panelSync.js:23-28`, `apps/admin/Dockerfile`, `apps/admin/dist/assets/index-nqnFGzlK.js`, `apps/panel/nginx.conf:53-59`, `deploy/cloudflared/config.yml`, git commit `db60b69` — **C-1**
- `public.pre_request_guard()` (Supabase project `rmmkjczuwsuxcnrdtkrh`) — **H-1**
- `backend/admin-api/app/main.py:427-428`, `backend/mentor-api/app/main.py:157-158`, `backend/panel-api/app/main.py:105-106`, `backend/student-api/app/main.py:55-56` — **M-1**
- `backend/student-api/app/api/student_portal.py:2856-2986` (dead duplicate at `:5097-5268`) — **M-2, I-2**
- `backend/mentor-api/.env`, `backend/panel-api/.env`, `backend/student-api/.env`, `backend/{mentor,panel,student}-api/app/core/auth.py`, `backend/panel-api/app/security.py` — **L-1**
- Repo-wide (no rate-limit library found) — **L-2**
- `backend/app/` (entire directory, dead code) — **I-1**
- `public.chat_events` policy `chat_events_readable` — **I-3 / accepted risk, unchanged**
