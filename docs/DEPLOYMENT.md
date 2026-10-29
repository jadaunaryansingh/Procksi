# Deployment: Vercel (frontends) + Render (backends)

| Frontend (Vercel project) | URL | Root directory | Proxies to (Render service) |
| :--- | :--- | :--- | :--- |
| `procksi-main` | https://www.procksi.in | `apps/main` | student-api |
| `procksi-admin` | https://admin.procksi.in | `apps/admin` | admin-api |
| `procksi-panel` | https://panel.procksi.in | `apps/panel` | panel-api |
| `procksi-student` | https://student.procksi.in | `apps/student` | student-api |
| `procksi-mentor` | https://mentor.procksi.in | `apps/mentor` | mentor-api |

| Render service | URL |
| :--- | :--- |
| admin-api | https://procksi-4d8a.onrender.com |
| student-api | https://procksi-2.onrender.com |
| mentor-api | https://procksi-mentor-portal.onrender.com |
| panel-api | https://procksi-panel-portal.onrender.com |

Each app's `vercel.json` forwards `/api/*`, `/auth/*` (and for panel `/panel/*`,
`/mentor/*`, `/evaluation/*`) to its Render service. The browser only ever talks
to its own origin, so **do not set `VITE_API_BASE_URL`** on Vercel.

No production host, institution or email domain is hardcoded in the code. They
all come from the env vars below, so moving to a custom domain or another
institution is a configuration change only.

## 1. Database URL (Supabase)

Render has no outbound IPv6, and Supabase's direct host (`db.<ref>.supabase.co`)
is IPv6-only. Use the **Session pooler** string instead
(Supabase → Connect → Session pooler). Keep the plain `postgresql://` scheme:
each service rewrites it to its own driver (`+asyncpg` for student/mentor,
`+psycopg` for panel), so a pre-converted `+asyncpg` URL breaks panel-api.

```
postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

## 2. Render (backends)

Every service needs:

| Variable | Notes |
| :--- | :--- |
| `DATABASE_URL` | step 1 |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_PUBLISHABLE_KEY` | project URL and anon key |
| `SUPABASE_SERVICE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | service role key (services read different names) |
| `SECRET_KEY` | per service, random |
| `ADMIN_API_KEY`, `PASSWORD_RESET_SECRET` | random, same value on every service |
| `ALLOWED_EMAIL_DOMAIN` | the only email domain allowed to sign in, e.g. `university.edu`. **Unset rejects everyone.** |
| `MASTER_ADMIN_EMAIL`, `MASTER_ADMIN_PASSWORD` | coordinator account |
| `STUDENT_PORTAL_URL`, `ADMIN_PORTAL_URL`, `MENTOR_PORTAL_URL`, `PANEL_PORTAL_URL` | https://student.procksi.in, https://admin.procksi.in, https://mentor.procksi.in, https://panel.procksi.in (email links) |
| `FRONTEND_URL` | all production frontend origins, comma-separated: `https://www.procksi.in,https://procksi.in,https://admin.procksi.in,https://panel.procksi.in,https://student.procksi.in,https://mentor.procksi.in` (CORS allowlist) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | redirect: `https://admin.procksi.in/auth/google/callback` |
| `MAIL_SERVER`, `MAIL_PORT` | `smtp-relay.brevo.com`, `2525`. Render free web services block outbound SMTP on 25/465/587, so Gmail SMTP cannot connect from Render. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | Brevo SMTP login (`…@smtp-brevo.com`) and SMTP key (`xsmtpsib-…`), from Brevo → SMTP & API → SMTP |
| `MAIL_FROM`, `MAIL_FROM_NAME` | a sender verified in Brevo (e.g. `pmsglau@gmail.com`); `MAIL_FROM_NAME=Procksi` |
| `OPENAI_API_KEY` / `NVIDIA_API_KEY`, `TWILIO_*` | optional |
| `PYTHON_VERSION` | `3.12.7` (also pinned by `backend/*/.python-version`) |

admin-api also needs `PANEL_API_INTERNAL_URL`, `PANEL_PORTAL_API_URL` (panel-api URL)
and `MENTOR_PORTAL_API_URL` (mentor-api URL).

Service settings: Root Directory `backend/<service>`, build
`pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`,
health check `/health`, region Singapore (same as Supabase). `render.yaml` holds
the same settings as a Blueprint.

## 3. Vercel (frontends)

| Variable | Apps |
| :--- | :--- |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | all |
| `VITE_ALLOWED_EMAIL_DOMAIN` | all (same value as `ALLOWED_EMAIL_DOMAIN`) |
| `VITE_MASTER_ADMIN_EMAIL` | admin |
| `VITE_STUDENT_API_URL`, `VITE_STUDENT_PORTAL_URL`, `VITE_PANEL_VIEW_URL`, `VITE_MENTOR_VIEW_URL` | admin |
| `VITE_STUDENT_PORTAL_URL`, `VITE_SCROLL_FRAMES_BASE` (main URL) | student |
| `VITE_STUDENT_PORTAL_URL`, `VITE_ADMIN_PORTAL_URL`, `VITE_PANEL_PORTAL_URL`, `VITE_MENTOR_PORTAL_URL` | main |
| `VITE_PROCKSI_CHAT` (optional, `true`/`false`) | admin, panel, student, mentor |

`VITE_*` values are baked in at build time: redeploy after changing one.

## 4. Supabase Auth

Authentication → URL Configuration: Site URL = `https://student.procksi.in`; Redirect URLs = all
six portal URLs with `/**` (`https://www.procksi.in/**`, `https://procksi.in/**`, `https://student.procksi.in/**`, `https://admin.procksi.in/**`, `https://mentor.procksi.in/**`, `https://panel.procksi.in/**`). Providers → Google: same client ID/secret as above.
Google Cloud Console: add `https://<ref>.supabase.co/auth/v1/callback` and
`https://admin.procksi.in/auth/google/callback` as authorized redirect URIs.

## 5. Custom domain (optional)

Add the host in each Vercel project → Settings → Domains, then update the URL
env vars above (Vercel and Render), Supabase redirect URLs and Google redirect
URIs. No code change is needed.

## Render free plan limits

- A service **sleeps after 15 min without requests**. The first request after that
  takes about a minute while it boots.
- **Background schedulers only run while a service is awake.** That covers
  presentation reminders and deadline mails (admin), the panel scheduler,
  GitHub sync (student) and the communication scheduler (mentor).
- Free instance hours are **750/month per workspace, shared by all four
  services**. If the reminders must be reliable, move admin-api to a paid instance.

## 6. CI/CD (GitHub Actions)

`.github/workflows/ci-cd.yml` is the only path to production. Render auto-deploy
(`autoDeployTrigger: "off"` in `render.yaml`) and Vercel Git deployments
(`"git": { "deploymentEnabled": false }` in each `vercel.json`) are switched off,
so nothing ships without passing the tests.

| Event | Tests | Render (backends) | Vercel (frontends) |
| :--- | :--- | :--- | :--- |
| Pull request to `main` | full suite | not deployed | **preview** for changed apps |
| Push / merge to `main` | full suite | changed services | **production** for changed apps |
| Manual run (Actions → CI/CD → Run workflow) | full suite | all four | all five, production |

Order: detect changes → tests (backend pytest per service, compile check,
lint + `node --test` + build per frontend) → deploy. If any test job fails, no
deploy job runs. Only services whose folder changed are deployed; editing the
workflow (or `render.yaml` for backends) redeploys all of them. PRs from forks
are tested but never deployed, because GitHub does not give them secrets.

### Repository secrets (Settings → Secrets and variables → Actions)

| Secret | Where to get it |
| :--- | :--- |
| `RENDER_DEPLOY_HOOK_ADMIN_API`, `RENDER_DEPLOY_HOOK_PANEL_API`, `RENDER_DEPLOY_HOOK_STUDENT_API`, `RENDER_DEPLOY_HOOK_MENTOR_API` | Render → service → Settings → Deploy Hook (the full URL) |
| `VERCEL_TOKEN` | Vercel → Account Settings → Tokens |
| `VERCEL_ORG_ID` | `orgId` in `.vercel/project.json` after `vercel link`, or Team Settings → General |
| `VERCEL_PROJECT_ID_MAIN`, `_ADMIN`, `_PANEL`, `_STUDENT`, `_MENTOR` | each project → Settings → General → Project ID |

The Vercel projects keep their **Root Directory = `apps/<app>`** setting; the
pipeline runs the CLI from the repository root and Vercel applies it. Build-time
`VITE_*` variables still live in each Vercel project (§3) and are pulled by
`vercel pull` for the matching environment (Preview or Production), so set
them for both.

### Blocking merges on red tests

Settings → Branches → add a rule for `main` → *Require status checks to pass*
and select the test jobs (`Backend tests (…)`, `Backend compile check`,
`Frontend checks (…)`). Without the rule a PR can still be merged while its
checks fail; the merge commit would then fail the tests again and not deploy.

## Unused since the move off EC2

`docker-compose.yml`, `deploy/cloudflared/`, `apps/*/nginx.conf`,
`apps/*/Dockerfile` and `backend/*/Dockerfile`.
