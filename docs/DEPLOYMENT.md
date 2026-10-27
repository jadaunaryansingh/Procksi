# Deployment: Vercel (frontends) + Render (backends)

| Frontend (Vercel project) | Root directory | Proxies to (Render service) |
| :--- | :--- | :--- |
| `pms-main` → glapms.in, www.glapms.in | `apps/main` | `pms-student-api` |
| `pms-admin` → admin.glapms.in | `apps/admin` | `pms-admin-api` |
| `pms-panel` → panel.glapms.in | `apps/panel` | `pms-panel-api` |
| `pms-student` → student.glapms.in | `apps/student` | `pms-student-api` |
| `pms-mentor` → mentor.glapms.in | `apps/mentor` | `pms-mentor-api` |

Each app's `vercel.json` forwards `/api/*`, `/auth/*` (and for panel `/panel/*`,
`/mentor/*`, `/evaluation/*`) to its Render service, exactly like the old nginx
config did. The browser only ever talks to its own origin, so **do not set
`VITE_API_BASE_URL`** on Vercel.

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

1. Dashboard → **Environment Groups** → create `pms-secrets` with:
   `DATABASE_URL` (from step 1), `SUPABASE_URL`, `SUPABASE_KEY`,
   `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
   `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
   `MAIL_FROM`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`,
   `OPENAI_API_KEY`, `GOOGLE_CLIENT_SECRET`, `ADMIN_API_KEY`, `PASSWORD_RESET_SECRET`.
   Use the same values as the GitHub Actions secrets used by `deploy-ec2.yml`.
2. **New → Blueprint** → pick this repo. Render reads `render.yaml` and asks for
   each service's `SECRET_KEY` (use `SECRET_KEY` for admin, and
   `PANEL_/STUDENT_/MENTOR_SECRET_KEY` for the others if you had them).
3. Check each service's URL. If Render had to rename one (the name was taken), update
   that URL in `render.yaml` and in the `apps/*/vercel.json` files.
4. Smoke test: `https://pms-<name>-api.onrender.com/health`.
5. Set Render's region to match your Supabase region. `render.yaml` uses Singapore.

## 3. Vercel (frontends)

For each row in the table: **Add New → Project** → this repo → set **Root
Directory** to the app folder (framework is detected as Vite) → env vars:

| Variable | Apps |
| :--- | :--- |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | all |
| `VITE_STUDENT_API_URL=https://student.glapms.in` | admin |
| `VITE_PMS_CHAT` (optional, `true`/`false`) | admin, panel, student, mentor |

Name the projects as in the table. The `*.vercel.app` URLs are already
allowlisted for CORS via `FRONTEND_URL` in `render.yaml`. Update that value if
your project names differ.

## 4. Domains

In each Vercel project → Settings → Domains, add its `*.glapms.in` host and set
the DNS records Vercel shows. If DNS is on Cloudflare, use **DNS only** (grey
cloud) for these records. The Google OAuth redirect
(`https://admin.glapms.in/auth/google/callback`), email links and CORS
allowlists all already use these hostnames, so nothing else changes.

## Render free plan limits

- A service **sleeps after 15 min without requests**. The first request after that
  takes about a minute while it boots.
- **Background schedulers only run while a service is awake.** That covers
  presentation reminders and deadline mails (admin), the panel scheduler,
  GitHub sync (student) and the communication scheduler (mentor). While a
  service is asleep, its jobs don't run.
- Free instance hours are **750/month per workspace, shared by all four
  services**. You can't keep all four awake with a pinger. If the reminders must
  be reliable, move `pms-admin-api` to a paid instance.

## After cutover

Once traffic is on Vercel/Render, these are unused and can be removed:
`docker-compose.yml`, `deploy/cloudflared/`, `apps/*/nginx.conf`,
`apps/*/Dockerfile`, `backend/*/Dockerfile`, `.github/workflows/deploy-main.yml`,
and the deploy job in `.github/workflows/deploy-ec2.yml`. Keep its test job as CI.
