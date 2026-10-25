# Mentor Allocation Agent

Self-contained agent that assigns **one mentor per team** automatically, on an
**admin one-click run**, by matching each team's project domain against the
**preference-ordered domain list every mentor sets at signup** — capped by a
per-mentor capacity — with the admin retaining manual override + lock.

## Allocation model (current)
- **Mentor input = signup.** A mentor signs up, sees the **live project domains**
  (the ones students/problem-statements actually use, from `/auth/domains`) and
  **picks them in rank order** (1st choice, 2nd, …). No primary/secondary split,
  **no years of experience**. The ordered list is stored in `mentors.domains`
  (array index 0 = strongest choice).
- **Matching = domain rank.** A team is scored against a mentor by the *best
  (lowest-index) rank* at which the mentor's domain overlaps the team's domain
  (exact beats same-cluster; rank #1 beats rank #2), then ties break on
  availability. `score = 0.8·domain_rank + 0.2·availability`. See
  `get_domain_rank_score` / `rank_mentors_by_domain` in `engine.py`.
- **No student step.** Students do **not** pick or rank mentors and get no
  suggestion list — the agent decides; the student just sees the assigned mentor.
- **Trigger = admin one-click.** `POST /allocation/run` assigns every eligible
  team. By default it only fills teams with **no mentor yet**; `reassign_all=true`
  re-runs across all unlocked teams. Admin-locked teams are never touched.
- **Cardinality: 1 mentor per team; ≤ `max_teams` teams per mentor** (default 2).

## Why it lives here (and on `teams_validation`)
The live **`teams`** table (SQLAlchemy world used by mentor-api/student-api) is a
21-row stub (`id, name` only). The real **295 teams** — with `domain`, the problem
statement (`title`/`description`), `members`, `mentor`, and `keywords` — live in
**`teams_validation`** (the Supabase/admin world). So the agent runs in **admin-api**
on the Supabase `service_client`, against `teams_validation` + `mentors`. Mentor
*load* is derived from `teams_validation.mentor` (the JSON name array the admin UI
already writes), so capacity is always consistent with reality.

## Files
| File | Purpose |
|------|---------|
| `engine.py` | Pure, no-API scoring: domain taxonomy, rule score (domain 40 / keywords 30 / experience 10 / availability 20), keyword extraction (RAKE-lite), and `infer_domains` (recovers a real domain from the title/keywords when `domain` is "General"/blank). |
| `agent.py` | FastAPI router (`build_allocation_router`) — all endpoints. |
| `migration.py` | Idempotent schema setup (`mentor_preferences` + `teams_validation` columns). Already applied to the live DB. |
| `__init__.py` | Exposes `build_allocation_router`. |

Mounted in `admin-api/app/main.py`:
```python
from app.mentor_allocation_agent import build_allocation_router
app.include_router(build_allocation_router(service_client))
```

## Endpoints (all `/api/admin/...`, port 8000)
| Method | Path | Milestone |
|--------|------|-----------|
| GET  | `/allocation/suggestions/{team_id}` | Inspect: top-5 mentors for a team by domain rank + reasons |
| POST | `/allocation/run` | **Admin one-click** — assign by domain rank; `reassign_all` to re-run all unlocked |
| GET  | `/allocation/overview` | Every team + mentor + source + each mentor's load |
| POST | `/allocation/assign` | Manual single assign |
| POST | `/allocation/lock` | Freeze a team's assignment (agent never touches it) |
| PATCH| `/mentors/{id}/capacity` | Bump a mentor's `max_teams` |
| POST | `/mentors/import` · `/mentors/import/save` | Optional admin bulk-load (CSV/Excel/PDF) — fallback to signup |
| GET/POST | `/allocation/preferences[/{team_id}]` | **Legacy / dormant** — the team-preference step is no longer part of the flow |

Scoring is **domain-rank only** (no experience, no embeddings — the deployment has no
NVIDIA/OpenAI key). Capacity default = **2 teams** (a signup mentor gets `max_teams=3`).

## Status
- **Built + verified live:** signup ranked-domain capture, `engine.rank_mentors_by_domain`,
  rank-based `suggestions` (read-only smoke test passed), `overview`.
- **Built, not yet fired live:** `/allocation/run` (it writes the `mentor` field — it's
  meant to be triggered by the admin's **Run Allocation** button in `apps/admin`).
- **Frontends:** mentor signup ranked-domain UI (`apps/mentor/.../Signup.jsx`) and the
  admin **Run Allocation / Reassign All** button (`apps/admin/.../MentorAllocation.jsx`)
  are wired. Students intentionally have **no** mentor-picker.
- **Not built:** **M7** mentor-side privacy serializer (strip the PS summary/scores from
  the mentor's team view, in `mentor-api`); **M8** MS Teams link.
