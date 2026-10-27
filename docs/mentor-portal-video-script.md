# Mentor Portal — Avatar Narration Script

For an AI avatar / video generation model (Runway or similar).
Total runtime: about 4 minutes 27 seconds across 9 scenes.

## How to use this document

- **NARRATION** is the only text the avatar speaks. Word counts are tuned to
  roughly 145 words per minute.
- **ON SCREEN** tells the editor which capture to show and when to cut.
- **AVATAR** is the delivery note for that scene.

Spoken numbers are written the way they should be said ("thirty", not "30").
No emoji anywhere, by project convention.

## Voice and tone

Warm, competent, unhurried — a colleague showing you around, not a product
advert. Second person throughout ("you", "your teams"). Short sentences.
No superlatives, no "seamless", no "empower", no "revolutionary".

Because the demo account has a single team and mostly empty screens, the
narration deliberately describes what each screen *does* rather than
reading numbers off it. This keeps the script true to the recording.

---

## Scene 1 — Opening (0:00–0:17)

**ON SCREEN:** Dashboard, full page. Slow push in on the green profile card.
**AVATAR:** Direct to camera, welcoming. Slight smile.

> **NARRATION**
> This is the Mentor Portal — the place where you supervise your project
> teams from first proposal to final marks. Everything is organised around
> one question: what needs your attention today? Let me show you around.

---

## Scene 2 — Dashboard (0:17–0:55)

**ON SCREEN:** Dashboard. Cut to the three stat cards as they are named,
then to the Assigned Teams and Pending Proposals panels.
**AVATAR:** Explanatory, relaxed pace.

> **NARRATION**
> Your dashboard opens on a summary. The green card confirms who you are
> signed in as and how many teams you are carrying this semester.
> Underneath, three numbers: total teams, pending proposals, and
> evaluations. Pending proposals is the one to watch — when that number is
> above zero, a team is waiting on your decision.
>
> Below that, your assigned teams sit on the left with their current status,
> and anything awaiting review sits on the right. When it says you are all
> caught up, you genuinely are.

---

## Scene 3 — My Teams (0:55–1:26)

**ON SCREEN:** My Teams page. Highlight the search field, then the team
card, then the three actions along its base.
**AVATAR:** Practical.

> **NARRATION**
> My Teams is your roster. Each card carries the team name, its
> identifier, its project, and the students on it — so you can see the shape
> of a team before opening it.
>
> Search across teams or projects if your list is long, and filter by
> status. Every card gives you three actions: view the full details, leave
> feedback for the team, or flag it for the coordinator's attention.

---

## Scene 4 — GitHub Analytics Hub (1:26–2:15)

**ON SCREEN:** Analyzer page. Cut across the five tabs, then the overall
score ring, then the eight-dimension grid.
**AVATAR:** More engaged — this is the standout feature.

> **NARRATION**
> The GitHub Analytics Hub reads a team's repository and turns it into
> something you can actually assess.
>
> Pick a team, and you get an overall score out of one hundred, a health
> reading, and a maturity checklist — whether the project has tests,
> continuous integration, Docker, and a readme.
>
> The AI breakdown scores eight separate dimensions: quality, security,
> originality, architecture, documentation, implementation, engineering,
> and effort. So instead of one vague impression, you can see exactly where
> a project is strong and where it is thin.
>
> Five tabs go deeper — code and security, the commit history, the full AI
> analysis, and per-student grading. Refresh re-runs the analysis whenever
> the team has pushed new work.

---

## Scene 5 — Synopsis Submissions (2:15–2:54)

**ON SCREEN:** Synopsis page. Show the creator form top to bottom, pausing
on the question-type buttons, then the Active Requirements panel.
**AVATAR:** Instructional, steady.

> **NARRATION**
> Synopsis Submissions is where you ask teams for work and collect it back.
>
> Build a request on the left: give it a title, describe what you expect,
> set a deadline, and choose whether it goes to all your teams or only
> specific ones.
>
> Then compose the form itself. Short answers, long answers, multiple
> choice, checkboxes, a GitHub link, or a file upload — assembled the same
> way you would build a Google Form. Publish it, and it appears for your
> teams. Everything currently open is listed on the right.

---

## Scene 6 — Presentations (2:54–3:11)

**ON SCREEN:** Presentations page. Show the upcoming and completed counters,
then the two tabs.
**AVATAR:** Brisk — this is a short scene.

> **NARRATION**
> Presentations shows your scheduled sessions — what is coming up, and what
> is already done. Slots appear here once the coordinator schedules them,
> so this page is your calendar rather than something you fill in yourself.

---

## Scene 7 — Procksi-Chat (3:11–3:34)

**ON SCREEN:** Procksi-Chat page. Show the channel filters, then the
conversation list with My Teams, Announcements, and Groups.
**AVATAR:** Warmer, conversational.

> **NARRATION**
> Procksi-Chat keeps every conversation in one place. Filter to your
> coordinator, to your teams, or to announcements.
>
> Message a team directly, reach the coordinator when something needs
> escalating, or use the all-mentors group. Announcements are read-only —
> they come from the coordinator, so nothing gets lost in a busy thread.

---

## Scene 8 — Evaluations (3:34–4:05)

**ON SCREEN:** Mentor Assessment page. Show the team dropdown, then the
per-student scoring rows.
**AVATAR:** Noticeably more serious. Slow down.

> **NARRATION**
> Evaluations is where your assessment is recorded. Choose a team, and you
> score each student individually against the criteria — out of thirty for
> the final student score.
>
> Two things worth knowing. Your marks are submitted before the panel
> presentation, so they stand on their own. And once you confirm, the form
> locks — you will be asked to confirm for exactly that reason. Review
> carefully before you submit.

---

## Scene 9 — History and close (4:05–4:27)

**ON SCREEN:** Evaluation History page, then a slow pull back to the
dashboard.
**AVATAR:** Return to the warm opening tone.

> **NARRATION**
> Finally, History is your record — every evaluation you have submitted,
> with its scores and feedback, searchable whenever you need to look
> something up.
>
> That is the Mentor Portal. Start at the dashboard, work through whatever
> is waiting, and everything else is one click away in the sidebar.

---

## Production notes

**Casting.** A single presenter throughout. If the avatar is composited
beside the screen capture, keep it lower-right at roughly twenty percent of
frame width and let the UI hold the centre.

**Pacing.** Scenes 4, 5 and 8 carry the most information — hold each
supporting shot for at least three seconds so a viewer can read the labels.
Scenes 6 and 9 are short by design and give the viewer a breath.

**Captions.** Burn in subtitles. Much of this vocabulary is
domain-specific ("synopsis", "panel presentation") and easily misheard.

**Accuracy caveats worth respecting.** The recording is from a demo account,
so almost every screen shows zeros and empty states. The narration never
reads a live number aloud for this reason. If you later re-record against a
populated account, this script still fits — but if you want the avatar to
cite real figures, that copy has to be rewritten against the new capture.

**One screen to re-record.** Procksi-Chat is enabled in local development only.
It is greyed out in the deployed portals, so this scene must be captured
locally, and viewers on the live site will not see that menu item until the
feature is turned on in production.
