// Pure helpers for the student reminder window. No React / no DOM here so this
// can be unit-tested with a plain Node script.

// Map a deadline's internal type key to the label shown to students.
// Unknown keys fall through unchanged. This is the SINGLE source of this map.
const DEADLINE_LABELS = {
  team: 'Team Formation',
  teamFormation: 'Team Formation',
  proposal: 'Proposal Submission',
  proposalUpload: 'Proposal Submission',
  midTerm: 'Mid-Term Evaluation',
  finalEvaluation: 'Final Evaluation',
  problemStatementSelection: 'Problem Statement Selection',
  extraActivities: 'Extra Activities',
  githubRepoSubmission: 'GitHub Repository Submission',
  github: 'GitHub Repository Submission',
};

export function formatDeadlineName(name) {
  return DEADLINE_LABELS[name] || name;
}

// "Due today" / "1 day left" / "N days left".
export function formatDaysLeft(daysRemaining) {
  if (daysRemaining <= 0) return 'Due today';
  if (daysRemaining === 1) return '1 day left';
  return `${daysRemaining} days left`;
}

// Whether the student has already MET each deadline, derived from the same
// data StageIndicator uses. Returns a map keyed by deadline `type` (both the
// canonical and legacy spellings) so buildReminders can look it up directly.
// Any missing input is treated as "not met".
export function deadlineCompletion({ team, proposals, evaluations, profile } = {}) {
  const teamMet = !!(team && team.id && team.id !== 'Unassigned') || !!profile?.team?.id;

  const hasRealTitle = team?.project_title && 
    !/^team\s*\d+$/i.test(String(team.project_title).trim()) && 
    String(team.project_title).trim().toLowerCase() !== 'untitled';

  const proposalMet = (Array.isArray(proposals) && proposals.length > 0) || 
                      !!team?.allocated_ps_id || 
                      hasRealTitle || 
                      (!!team?.proposal_status && team.proposal_status !== 'none' && team.proposal_status !== 'pending_submission');

  const midMet = evaluations?.mid?.score != null || evaluations?.proposal?.score != null || evaluations?.evaluation?.score != null;
  const finalMet = evaluations?.final?.score != null;

  return {
    team: teamMet, teamFormation: teamMet,
    proposal: proposalMet, proposalUpload: proposalMet,
    evaluation: midMet, midTerm: midMet,
    finalEvaluation: finalMet,
  };
}

// Shape the raw deadline + announcement lists into what the window renders:
//   pastDue   — deadlines already overdue (order preserved)
//   upcoming  — future deadlines, soonest first
//   announcements — newest first, capped at maxAnnouncements
//   alertingNotifications — still-relevant rows, newest first, capped at
//                maxNotifications
//   hasContent — whether there is anything at all to render
//   hasAlert   — whether anything still needs attention (an UNMET deadline, any
//                announcement, or a still-alerting notification). Drives the
//                alert button + auto-open.
// Each deadline gains `met` from the `completion` map (see deadlineCompletion),
// so met deadlines can be rendered greyed instead of being removed.
//
// `notifications` exists because deadline reminders are written to the
// notifications table by the backend scheduler, which this function otherwise
// never sees: a student who had met every deadline got a reminder row and still
// saw nothing pop. They must feed hasContent as well as hasAlert — driving only
// the alert opens the window onto an "all caught up" empty state.
export function buildReminders(
  deadlines,
  announcements,
  maxAnnouncements = 3,
  completion = {},
  notifications = [],
  // Notifications get their own cap: they and announcements used to share one,
  // so a couple of duplicate "Deadline Updated" notices could crowd out
  // everything else. Defaults to the announcement cap for older callers.
  maxNotifications = maxAnnouncements,
) {
  const dl = Array.isArray(deadlines) ? deadlines : [];
  const anns = Array.isArray(announcements) ? announcements : [];

  const withMet = (d) => {
    const rawId = String(d.id || '').replace(/^deadline-/, '');
    const isMet = completion[d.name] === true || 
                  completion[d.type] === true || 
                  completion[d.id] === true || 
                  completion[rawId] === true;
    return { ...d, met: isMet };
  };

  const pastDue = dl.filter((d) => d.is_past === true).map(withMet);
  const upcoming = dl
    .filter((d) => d.is_past !== true)
    .slice()
    .sort((a, b) => (a.days_remaining ?? 0) - (b.days_remaining ?? 0))
    .map(withMet);

  const sortedAnns = anns
    .slice()
    .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    .slice(0, maxAnnouncements);

  // Met/unmet indexed by every key a notification might reference: the raw type
  // keys (metadata.deadline_type) and the display label (title fallback). If two
  // rows share a key, unmet wins — a stale met row must not silence a live one.
  const metByKey = new Map();
  const metByLabel = new Map();
  const mark = (map, key, met) => {
    if (!key) return;
    map.set(key, (map.get(key) ?? true) && met);
  };
  [...pastDue, ...upcoming].forEach((d) => {
    const rawId = String(d.id || '').replace(/^deadline-/, '');
    mark(metByKey, d.name, d.met);
    mark(metByKey, d.type, d.met);
    mark(metByKey, rawId, d.met);
    mark(metByLabel, formatDeadlineName(d.name || d.type || rawId || ''), d.met);
  });

  // Which notifications still demand attention.
  //
  // Deadline reminders are deliberately NOT silenced by being read: the student
  // having seen the message says nothing about whether the work is done. They go
  // quiet only when the deadline they name is met. Everything else (invitations,
  // results, schedules) follows the ordinary unread rule.
  //
  // A deadline reminder naming a deadline that is NOT in the current list is
  // dropped. The API only returns deadlines inside their open window, so an
  // absent one has closed (or never applied to this student) -- there is
  // nothing left to act on, and keeping it alerting is what left "Problem
  // Statement Selection" in the window days after it closed.
  const sortedAlerting = (Array.isArray(notifications) ? notifications : [])
    .filter((n) => {
      if (!n) return false;
      if (n.read) return false;
      // A notification that names its own deadline expires with it, whatever
      // its title looks like ("New Evaluation Cycle" never matched the
      // deadline-reminder prefix, so these alerted indefinitely).
      if (notificationDeadlinePassed(n)) return false;
      const ref = deadlineNotificationRef(n);
      if (ref !== null) {
        const met = metByKey.get(ref.type) ?? metByLabel.get(ref.label);
        if (met === undefined) return false;
        return met !== true;
      }
      return n.read !== true;
    })
    .slice()
    .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  // Deduplicate deadline notifications so students only see the most recent update per deadline
  const seenDeadlineTargets = new Set();
  const alertingNotifications = sortedAlerting
    .filter((n) => {
      const ref = deadlineNotificationRef(n);
      if (ref !== null) {
        const key = (ref.type || ref.label || '').trim().toLowerCase();
        if (key) {
          if (seenDeadlineTargets.has(key)) return false;
          seenDeadlineTargets.add(key);
        }
      }
      return true;
    })
    .slice(0, maxNotifications);

  const hasContent =
    pastDue.length + upcoming.length + sortedAnns.length + alertingNotifications.length > 0;
  const hasUnmetUpcomingDeadline = upcoming.some((d) => !d.met);
  const hasAlert = sortedAnns.length > 0 || hasUnmetUpcomingDeadline || alertingNotifications.length > 0;

  return { pastDue, upcoming, announcements: sortedAnns, alertingNotifications, hasContent, hasAlert };
}

// Deadline reminders are written by the backend scheduler as
// "Upcoming Deadline: <name>" and by the admin deadline editor as
// "Deadline Updated: <name>". Returns <name> for those, null for anything else,
// which is how buildReminders tells a deadline reminder from a general
// notification without needing a foreign key the notifications table lacks.
const DEADLINE_TITLE_PREFIX = /^(?:upcoming deadline|deadline updated|deadline reminder)\s*:\s*/i;

export function deadlineNotificationTarget(title) {
  const raw = String(title ?? '').trim();
  const match = raw.match(DEADLINE_TITLE_PREFIX);
  if (!match) return null;
  return raw.slice(match[0].length).trim() || null;
}

// Some notifications carry their own expiry in their body rather than pointing
// at a row in the deadlines table — the scheduler writes
// "A new evaluation cycle 'X' has been scheduled. Deadline: <ISO timestamp>"
// for every student, and nothing ever clears them. Once that timestamp passes
// there is nothing left to act on, so the row stops alerting.
//
// Returns true only when a date is found AND it is in the past; an absent or
// unparseable date means "cannot tell", which leaves the row alerting.
const EMBEDDED_DEADLINE = /\bdeadline\s*:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9:.]+Z?(?:[+-][0-9:]+)?|[0-9]{4}-[0-9]{2}-[0-9]{2})/i;

export function notificationDeadlinePassed(notification, now = new Date()) {
  const text = String(notification?.message ?? '');
  const match = text.match(EMBEDDED_DEADLINE);
  if (!match) return false;
  const when = new Date(match[1].trim());
  if (Number.isNaN(when.getTime())) return false;
  return when.getTime() < now.getTime();
}

// PostgREST returns jsonb as an object, but tolerate a string in case a caller
// hands us a raw row. Never throws — a malformed blob just means "no metadata".
function readMetadata(value) {
  if (!value) return null;
  if (typeof value === 'object') return value;
  if (typeof value !== 'string') return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

// Identify which deadline a notification is about, as { type, label }.
//
// The scheduler writes `metadata.deadline_type` — a stable key that survives
// any rewording of the title — so that is preferred. Rows written before that
// existed carry the deadline name only in their title, so parsing it remains
// the fallback. Returns null when the notification is not about a deadline.
export function deadlineNotificationRef(notification) {
  if (!notification) return null;

  const meta = readMetadata(notification.metadata);
  const type = meta?.deadline_type ? String(meta.deadline_type) : null;
  const metaLabel = meta?.deadline_label ? String(meta.deadline_label) : null;
  if (type || metaLabel) return { type, label: metaLabel };

  const parsed = deadlineNotificationTarget(notification.title);
  return parsed === null ? null : { type: null, label: parsed };
}

// How many notification rows still need the student's eyes. A row counts as
// unread unless `read` is explicitly true — a missing flag means the backend
// never marked it, which is still unread.
export function countUnread(notifications) {
  if (!Array.isArray(notifications)) return 0;
  return notifications.filter((n) => n && n.read !== true).length;
}

// Decode a JWT payload without verifying it. Safe by construction: any malformed
// input returns null rather than throwing, and the result is only ever used as an
// opaque cache key — never as proof of identity.
function decodeJwtPayload(token) {
  if (typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return null;
  }
}

// A stable identifier for ONE login, used to arm the popup once per sign-in.
//
// Neither the access token nor its expiry works here: Supabase reissues the
// token on refresh and re-fires SIGNED_IN on tab focus, so keying on either
// would re-open the window mid-session on every focus. The `session_id` claim is
// minted at sign-in and survives token refresh, which is exactly the granularity
// we want. Falls back to the user id when the claim is absent, and returns null
// when signed out.
export function loginSessionKey(session) {
  if (!session) return null;
  const claims = decodeJwtPayload(session.access_token);
  return claims?.session_id || session.user?.id || null;
}

// Should the reminder window auto-open? Pure so the gate can be unit-tested —
// getting it wrong silently hides every deadline alert for the whole session.
//
//   loaded       — every query the decision depends on has settled
//   failed       — any of those queries errored
//   alreadyShown — the once-per-session flag is already set
//   hasAlert     — buildReminders(...).hasAlert
//
// Returns { decided, markShown, open }. `decided` false means "ask again later":
// the caller must NOT set the once-per-session flag, so a retry can still fire.
// A failed load is explicitly undecided — previously it marked the session as
// shown and suppressed the window until the next login.
export function autoOpenDecision({ loaded, failed, alreadyShown, hasAlert } = {}) {
  const undecided = { decided: false, markShown: false, open: false };
  if (!loaded || failed) return undecided;
  if (alreadyShown) return { decided: true, markShown: false, open: false };
  return { decided: true, markShown: true, open: !!hasAlert };
}
