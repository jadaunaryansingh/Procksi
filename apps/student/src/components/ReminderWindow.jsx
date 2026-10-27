import React, { useState, useEffect, useMemo, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, FileText, AlertTriangle, ChevronDown, ChevronUp, CheckCircle2 } from 'lucide-react';
import { useDeadlines, useAnnouncements, useNotifications, useDeadlineCompletionState, getSessionSafe } from '../hooks/useStudentData';
import { buildReminders, formatDeadlineName, formatDaysLeft, autoOpenDecision, loginSessionKey } from '../lib/reminders';
import RichText from './RichText';

const COUNTDOWN_SECONDS = 10;
const STORAGE_KEY = 'procksi-reminders-shown';
// A cold load can lose the race with Supabase session hydration and fail once.
// Retry a couple of times before giving up, otherwise a single transient error
// means the student never sees their deadlines this session.
const MAX_LOAD_RETRIES = 2;
const RETRY_DELAY_MS = 1500;
// Notifications get more room than announcements — deadline reminders land here
// and a couple of them used to crowd out everything else at the shared cap of 3.
const MAX_NOTIFICATIONS = 5;

// A met deadline stays in the list rather than disappearing — seeing what you
// have already finished is the point. Green card + struck-through name, shared
// by the past-due and upcoming sections so the two never drift apart.
const MET_CARD = 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30';
const MET_TITLE = 'text-emerald-700 dark:text-emerald-300 line-through decoration-emerald-500/60';

// "20 Aug 2026" style date for the expanded detail.
const fmtDate = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
};

// Whole days between an ISO date in the past and now (never negative).
const daysAgo = (iso) => {
  if (!iso) return 0;
  const ms = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(ms / 86400000));
};

// Up/down chevron that flips when a row is expanded.
function Chevron({ isOpen, className = 'text-slate-400' }) {
  const Icon = isOpen ? ChevronUp : ChevronDown;
  return <Icon className={`w-4 h-4 shrink-0 ${className}`} />;
}

// A ring that visualizes how much of the countdown is left.
function CountdownRing({ remaining }) {
  const R = 20;
  const C = 2 * Math.PI * R;
  const offset = C * (1 - remaining / COUNTDOWN_SECONDS);
  return (
    <div className="relative w-14 h-14 shrink-0">
      <svg viewBox="0 0 48 48" className="w-full h-full -rotate-90">
        <circle cx="24" cy="24" r={R} fill="none" stroke="currentColor"
          className="text-slate-200 dark:text-slate-700" strokeWidth="4" />
        <circle cx="24" cy="24" r={R} fill="none" stroke="currentColor"
          className="text-indigo-500" strokeWidth="4" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 1s linear' }} />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-sm font-black text-slate-700 dark:text-slate-200">{remaining}</span>
      </div>
    </div>
  );
}

export default function ReminderWindow() {
  const { data: deadlines, loading: dLoading, error: dError, refetch: refetchDeadlines } = useDeadlines();
  const { data: announcements, loading: aLoading, error: aError, refetch: refetchAnnouncements } = useAnnouncements();
  const { data: notifications, loading: nLoading } = useNotifications();
  const { completion, loading: cLoading } = useDeadlineCompletionState();

  const [open, setOpen] = useState(false);
  // Visibility is decided once per login. This is a latch, never rendered --
  // only read as a guard -- so a ref keeps the decision out of render state.
  const decidedRef = useRef(false);
  const [remaining, setRemaining] = useState(COUNTDOWN_SECONDS);
  const [manual, setManual] = useState(false); // opened via the alert button (no timer)
  const [expanded, setExpanded] = useState(() => new Set()); // keys of expanded rows
  const [retries, setRetries] = useState(0);
  // Identifies the current login. null until resolved, so we never decide early.
  const [sessionKey, setSessionKey] = useState(undefined);

  useEffect(() => {
    let alive = true;
    getSessionSafe()
      .then((session) => { if (alive) setSessionKey(loginSessionKey(session)); })
      .catch(() => { if (alive) setSessionKey(null); });
    return () => { alive = false; };
  }, []);

  const reminders = useMemo(
    () => buildReminders(deadlines || [], announcements || [], 3, completion, notifications || [], MAX_NOTIFICATIONS),
    [deadlines, announcements, completion, notifications]
  );

  // Wait for the completion sources too — not just deadlines/announcements.
  // While they're in flight the completion map reads "nothing met", which would
  // render already-finished deadlines as Past Due.
  const loaded = !dLoading && !aLoading && !cLoading && !nLoading && sessionKey !== undefined;
  const failed = Boolean(dError || aError);

  // Decide visibility ONCE per login, after the initial loads succeed. A failed
  // load stays undecided so the retry below can still fire — it must never burn
  // the flag, or the window is suppressed until the next login.
  //
  // The flag stores the login's session key rather than a bare '1', so a new
  // sign-in re-arms the window automatically while a reload, tab focus or token
  // refresh inside the same login does not.
  useEffect(() => {
    if (decidedRef.current) return;
    const { decided: isDecided, markShown, open: shouldOpen } = autoOpenDecision({
      loaded,
      failed,
      alreadyShown: Boolean(sessionKey) && sessionStorage.getItem(STORAGE_KEY) === sessionKey,
      hasAlert: reminders.hasAlert,
    });
    if (!isDecided) return;
    decidedRef.current = true;
    if (markShown && sessionKey) sessionStorage.setItem(STORAGE_KEY, sessionKey);
    // Deliberate setState-in-effect. `open` is also driven by the alert button
    // and by dismiss, so it cannot be derived during render, and the decision
    // depends on async loads that have not settled on the first render. The
    // decidedRef latch above guarantees this runs at most once per login.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (shouldOpen) setOpen(true);
  }, [loaded, failed, reminders.hasAlert, sessionKey]);

  // Retry a failed initial load a bounded number of times.
  useEffect(() => {
    if (!loaded || !failed || retries >= MAX_LOAD_RETRIES) return;
    const id = setTimeout(() => {
      setRetries((n) => n + 1);
      if (dError) refetchDeadlines();
      if (aError) refetchAnnouncements();
    }, RETRY_DELAY_MS);
    return () => clearTimeout(id);
  }, [loaded, failed, retries, dError, aError, refetchDeadlines, refetchAnnouncements]);

  // The top-nav alert button re-opens this window on demand, WITHOUT a countdown
  // (immediately closable). Always allowed — it ignores the once-per-session gate.
  useEffect(() => {
    const openManual = () => { setManual(true); setOpen(true); };
    window.addEventListener('student:open-reminders', openManual);
    return () => window.removeEventListener('student:open-reminders', openManual);
  }, []);

  // Tick the countdown while the window is open (auto mode only). It stops at 0,
  // after which the window becomes dismissible. Manual opens skip the timer.
  useEffect(() => {
    if (!open || manual) return;
    const id = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) { clearInterval(id); return 0; }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [open, manual]);

  // Manual opens are dismissible right away; auto opens only once the timer ends.
  const canDismiss = manual || remaining === 0;

  const close = () => {
    if (!canDismiss) return;
    setOpen(false);
    setManual(false);
    // Let the alert button re-check: the student may have read a notification
    // or acted on a deadline while this was open.
    window.dispatchEvent(new CustomEvent('student:reminders-closed'));
  };

  // Expand/collapse a single reminder row.
  const toggleExpand = (key) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const buttonLabel = canDismiss ? 'Got it' : `Continue in ${remaining}s`;

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop — closes only after the countdown finishes. */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={close}
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[80]" />

          {/* Card */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[92%] max-w-3xl bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 z-[90] overflow-hidden flex flex-col max-h-[90vh] min-h-[80vh]">

            {/* Header */}
            <div className="p-5 border-b border-slate-100 dark:border-slate-700 flex items-center gap-4 bg-slate-50 dark:bg-slate-800/50">
              {manual ? (
                <div className="w-14 h-14 shrink-0 flex items-center justify-center rounded-full bg-rose-50 dark:bg-rose-500/10">
                  <AlertTriangle className="w-6 h-6 text-rose-500" />
                </div>
              ) : (
                <CountdownRing remaining={remaining} />
              )}
              <div>
                <h2 className="text-lg font-bold text-slate-800 dark:text-white flex items-center">
                  <Clock className="w-5 h-5 mr-2 text-indigo-500" /> Your Reminders
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Tap a reminder for details
                </p>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 p-6 overflow-y-auto space-y-5">
              {/* Past-due warnings */}
              {reminders.pastDue.length > 0 && (
                <div className="space-y-2">
                  {reminders.pastDue.map((d) => {
                    const key = `d:${d.id}`;
                    const isOpen = expanded.has(key);
                    const ago = daysAgo(d.deadline_date);
                    return (
                      <div key={key} onClick={(e) => { e.stopPropagation(); toggleExpand(key); }}
                        className={`rounded-xl border overflow-hidden cursor-pointer ${d.met ? MET_CARD : 'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/30'}`}>
                        <div className="flex items-center gap-3 p-3">
                          {d.met
                            ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                            : <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />}
                          <div className="min-w-0 flex-1">
                            <p className={`font-bold text-sm truncate ${d.met ? MET_TITLE : 'text-rose-700 dark:text-rose-400'}`}>{formatDeadlineName(d.name)}</p>
                            <p className={`text-xs ${d.met ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500'}`}>{d.met ? 'Done' : 'Past Due'}</p>
                          </div>
                          <Chevron isOpen={isOpen} className={d.met ? 'text-emerald-400' : 'text-rose-400'} />
                        </div>
                        {isOpen && (
                          <div className={`px-3 pb-3 text-xs border-t ${d.met ? 'text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-500/20' : 'text-rose-600 dark:text-rose-300 border-rose-200/60 dark:border-rose-500/20'}`}>
                            <p className="mt-2">
                              {d.met ? 'Completed. ' : ''}Was due on <span className="font-semibold">{fmtDate(d.deadline_date)}</span>
                              {!d.met && ago > 0 ? ` · ${ago} day${ago === 1 ? '' : 's'} ago` : ''}.
                            </p>
                            {!d.met && <p className="mt-1 text-rose-500/90">Contact your coordinator if you still need to submit.</p>}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Upcoming deadlines */}
              {reminders.upcoming.length > 0 && (
                <div className="space-y-2">
                  {reminders.upcoming.map((d) => {
                    const key = `d:${d.id}`;
                    const isOpen = expanded.has(key);
                    return (
                      <div key={key} onClick={(e) => { e.stopPropagation(); toggleExpand(key); }}
                        className={`rounded-xl border overflow-hidden cursor-pointer ${d.met ? MET_CARD : 'bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-700'}`}>
                        <div className="flex justify-between items-center p-3">
                          <div className="flex items-center gap-2 min-w-0">
                            {d.met && <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />}
                            <p className={`font-bold text-sm truncate ${d.met ? MET_TITLE : 'text-slate-800 dark:text-slate-200'}`}>{formatDeadlineName(d.name)}</p>
                          </div>
                          <div className="flex items-center gap-2 shrink-0 ml-3">
                            {d.met ? (
                              <span className="flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 rounded-full">
                                <CheckCircle2 className="w-3 h-3" /> Done
                              </span>
                            ) : (
                              <span className="text-xs font-bold text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2.5 py-1 rounded-full">
                                {formatDaysLeft(d.days_remaining)}
                              </span>
                            )}
                            <Chevron isOpen={isOpen} />
                          </div>
                        </div>
                        {isOpen && (
                          <div className={`px-3 pb-3 text-xs border-t ${d.met ? 'text-emerald-700 dark:text-emerald-300 border-emerald-200/60 dark:border-emerald-500/20' : 'text-slate-600 dark:text-slate-300 border-slate-100 dark:border-slate-700'}`}>
                            <p className="mt-2">{d.met ? 'Completed · was due ' : 'Due on '}<span className="font-semibold">{fmtDate(d.deadline_date)}</span>.</p>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Announcements */}
              {reminders.announcements.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-700">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center">
                    <FileText className="w-3.5 h-3.5 mr-1.5" /> Announcements
                  </p>
                  {reminders.announcements.map((a) => {
                    const key = `a:${a.id}`;
                    const isOpen = expanded.has(key);
                    return (
                      <div key={key} onClick={(e) => { e.stopPropagation(); toggleExpand(key); }}
                        className="p-3 rounded-xl bg-indigo-50/50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 cursor-pointer">
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-sm text-indigo-900 dark:text-indigo-100 truncate">{a.title}</p>
                            {a.body && <RichText text={a.body} className={`text-xs text-indigo-700 dark:text-indigo-300 mt-0.5 ${isOpen ? '' : 'line-clamp-2'}`} />}
                          </div>
                          <Chevron isOpen={isOpen} className="text-indigo-400 mt-0.5" />
                        </div>
                        {isOpen && a.created_at && (
                          <p className="mt-2 text-[11px] font-semibold text-indigo-500">Posted {fmtDate(a.created_at)}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Unread notifications — deadline reminders written by the backend
                  scheduler land here, not in `deadlines`, so without this section
                  they open the window onto an empty state. */}
              {reminders.alertingNotifications.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-700">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center">
                    <AlertTriangle className="w-3.5 h-3.5 mr-1.5" /> New for you
                  </p>
                  {reminders.alertingNotifications.map((n) => {
                    const key = `n:${n.id}`;
                    const isOpen = expanded.has(key);
                    return (
                      <div key={key} onClick={(e) => { e.stopPropagation(); toggleExpand(key); }}
                        className="p-3 rounded-xl bg-amber-50/60 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 cursor-pointer">
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="font-bold text-sm text-amber-900 dark:text-amber-100 truncate">{n.title}</p>
                            {n.message && <RichText text={n.message} className={`text-xs text-amber-700 dark:text-amber-300 mt-0.5 ${isOpen ? '' : 'line-clamp-2'}`} />}
                          </div>
                          <Chevron isOpen={isOpen} className="text-amber-400 mt-0.5" />
                        </div>
                        {isOpen && n.created_at && (
                          <p className="mt-2 text-[11px] font-semibold text-amber-600">Sent {fmtDate(n.created_at)}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Empty state — only reachable via a manual (alert-button) open,
                  since the auto-open never fires when there's nothing to show. */}
              {!reminders.hasContent && (
                <div className="flex flex-col items-center justify-center text-center py-12 text-slate-500 dark:text-slate-400">
                  <CheckCircle2 className="w-10 h-10 text-emerald-400 mb-3" />
                  <p className="text-sm font-semibold">You're all caught up</p>
                  <p className="text-xs mt-1">No deadlines or announcements right now.</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-5 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex justify-end">
              <button
                onClick={(e) => { e.stopPropagation(); close(); }}
                disabled={!canDismiss}
                className={`px-6 py-2 rounded-lg text-sm font-semibold transition-colors shadow-md ${
                  canDismiss
                    ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                    : 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
                }`}>
                {buttonLabel}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
