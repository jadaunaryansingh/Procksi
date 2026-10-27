# Mentor Portal — First-Login Walkthrough Plan

## Decisions

| Question | Choice |
|---|---|
| Scope | First-login orientation only (7 steps) |
| Build | Custom overlay using `framer-motion` (already a dependency) |
| Persistence | `localStorage` |

## Why custom rather than a tour library

`framer-motion@12` is already installed and is what every other animated
surface in this portal uses. A custom overlay is ~250 lines, adds no
dependency, and inherits the existing dark-mode tokens for free. A library
(react-joyride / driver.js) would need theme overrides to stop looking
foreign, which is most of the work a library was meant to save.

Trade-off accepted: we hand-roll scroll-into-view, focus trapping, and
viewport-edge collision. These are the parts libraries genuinely do well,
and they are where bugs will surface. Budgeted below.

## The 7 steps

Each step targets a `data-tour` anchor. Copy is written from the mentor's
side of the screen -- what they can do, not what the component is called.

| # | Anchor | Placement | Purpose |
|---|---|---|---|
| 1 | (none -- centered) | modal | Welcome. Name the portal, state the tour is skippable, one sentence. |
| 2 | `sidebar-nav` | right | The 8 sections live here; the rail collapses. |
| 3 | `stat-total-teams` | bottom | Teams assigned to you. |
| 4 | `stat-pending-proposals` | bottom | Synopses waiting on your review -- the number that means "act". |
| 5 | `nav-teams` | right | Where you open a team and see its members and repo. |
| 6 | `nav-milestones` | right | Where synopsis submissions are approved or returned. |
| 7 | `nav-evaluation` | right | Where marks are submitted, and that submission is final. |

Step 1 is centered because a mentor with zero assigned teams has empty stat
cards; anchoring the opening step to a "0" reads as broken. Steps 3-4 are
skipped automatically when their anchor is absent (see Edge cases).

Deliberately excluded: GitHub Analytics Hub, Presentations, History,
Procksi-Chat. Orientation should name where things live, not teach every
screen. The Analyzer (1279 lines) and Synopsis Submissions (826 lines) are
the two screens that genuinely warrant their own coaching tours -- that is
the "orientation + per-page" scope, and this plan is deliberately not it.
Procksi-Chat is additionally gated off in production by `PROCKSI_CHAT_ENABLED`, so
a step pointing at it would target a disabled, greyed-out nav item.

## Files

**New**
- `src/components/Walkthrough/WalkthroughOverlay.jsx` — spotlight + tooltip + controls
- `src/components/Walkthrough/steps.js` — the step array above (data, no JSX)
- `src/hooks/useWalkthrough.js` — open/close, step index, localStorage flag

**Modified**
- `components/Mentor/MentorLayout.jsx` — mount overlay; `data-tour` on nav items; help button in the header to replay
- `pages/Mentor/MentorHome.jsx` — `data-tour` on two stat cards

Anchors are added as `data-tour="..."` attributes. Nothing else about these
components changes; no restructuring, no class changes.

## How it works

1. On mount inside `MentorLayout`, `useWalkthrough` reads
   `localStorage['procksi-mentor-walkthrough-v1']`.
2. Absent -> open at step 0. Present -> stay closed.
3. Each step resolves its anchor via
   `document.querySelector('[data-tour="..."]')` and reads
   `getBoundingClientRect()` to position the spotlight and tooltip.
4. Finish or Skip writes the flag. Both are terminal -- Skip is not
   "remind me later".
5. A help icon in the layout header clears the flag and reopens, so the
   tour is replayable on demand.

Versioned key (`-v1`): when the nav changes materially, bumping the key
re-runs the tour once for everyone rather than stranding existing mentors
on a stale mental model.

## Edge cases these steps must handle

These are the specific failure modes -- most of them are why a first
version of a hand-rolled tour looks broken.

- **Missing anchor.** A step whose `querySelector` returns null is skipped,
  not rendered against a `null` rect. Real case: a mentor with no assigned
  teams may not render the stat cards at all.
- **Mobile.** The sidebar is a drawer under `md`. Steps 2/5/6/7 target
  elements that are off-screen or unmounted. Below `md` the tour runs a
  4-step variant (1, 3, 4, and a single combined "everything lives in the
  menu" step anchored to the hamburger).
- **Data still loading.** `MentorHome` fetches on mount; the stat cards do
  not exist for the first few hundred ms. The tour waits for its first
  anchor via a short polling window (~2s) before opening, and gives up
  quietly rather than opening against a half-built page.
- **Scroll.** Anchor may be below the fold. Each step issues
  `scrollIntoView({block:'center'})` and recomputes the rect after the
  scroll settles.
- **Resize / sidebar collapse.** Rects go stale. Recompute on `resize` and
  on step change; the collapsed rail is narrower, which moves every
  sidebar anchor.
- **Dark mode.** Overlay and tooltip must read from the same tokens as the
  rest of the portal, in both themes.
- **Keyboard.** Escape closes (and counts as Skip), arrows move between
  steps, focus is trapped in the tooltip, and focus returns to the trigger
  on close.
- **Reduced motion.** Honour `prefers-reduced-motion` -- spotlight moves
  without the transition.

## Build order

1. `steps.js` + `useWalkthrough.js` (pure logic; no UI)
2. `data-tour` anchors into the two components
3. `WalkthroughOverlay` — desktop happy path
4. Edge cases above (this is the bulk of the real work)
5. Help button to replay
6. Verify: fresh localStorage, replay, mobile viewport, dark mode, keyboard-only, reduced motion, and a mentor with zero teams

## Out of scope

Per-page coaching tours, DB-backed persistence, admin-side adoption
metrics, and any tour on the other three portals. The overlay is written
portal-agnostic, so admin/panel/student can reuse it later by supplying
their own `steps.js`.
