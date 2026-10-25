import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Timer, Send, Lock, Save, CheckCircle2, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { evaluationAPI } from '../../services/api';
import { requirePanelId } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const SCORE_KEYS = ['q1', 'q2', 'q3', 'q4'];

// Build score keys dynamically from the number of sections in the rubric.
// Falls back to the legacy 4-key list if parameters haven't loaded yet.
function buildScoreKeys(count) {
  return Array.from({ length: count }, (_, i) => `q${i + 1}`);
}

// Get max marks for a given section index (from rubric criteria)
function getMaxMarksForSection(section) {
  if (!section) return 10;
  const criteria = section.criteria || [];
  if (criteria.length > 0) {
    return criteria[0].max_marks ?? 10;
  }
  return 10;
}

// Validate score against dynamic max_marks instead of hardcoded 10
const makeValidScore = (value, maxMarks = 10) => {
  if (value === '') return '';
  const num = Number(value);
  if (!Number.isInteger(num) || num < 0 || num > maxMarks) return null;
  return num;
};

// Format a UTC ISO string as local time (HH:MM AM/PM)
function formatLocalTime(isoStr) {
  if (!isoStr) return '';
  try {
    return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoStr;
  }
}

const computeRemainingSeconds = (session) => {
  if (!session?.allow_submission) {
    return 0;
  }

  if (typeof session?.remaining_seconds === 'number') {
    return Math.max(0, session.remaining_seconds);
  }

  const defaultDuration = Number(session?.evaluation_timer_seconds) || 30 * 60;
  const serverNow = Date.parse(session?.server_now || '');
  const windowEnd = Date.parse(session?.window_end || '');

  if (Number.isNaN(serverNow) || Number.isNaN(windowEnd)) {
    return defaultDuration;
  }

  const untilWindowEnd = Math.max(0, Math.floor((windowEnd - serverNow) / 1000));
  return untilWindowEnd;
};

const TimeBoundEvaluation = () => {
  const { teamId } = useParams();
  const navigate = useNavigate();

  const [panelId, setPanelId] = useState('');

  const [timeLeft, setTimeLeft] = useState(30 * 60);
  const [isActive, setIsActive] = useState(false);
  const [showExtendModal, setShowExtendModal] = useState(false);
  const [extendModalShown, setExtendModalShown] = useState(false);
  const [isExtending, setIsExtending] = useState(false);

  const [scores, setScores] = useState({});
  const [remarks, setRemarks] = useState('');

  const [showSummary, setShowSummary] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedData, setSubmittedData] = useState(null);
  const [draftSavedTime, setDraftSavedTime] = useState(null);

  const [sessionData, setSessionData] = useState(null);
  const [parameters, setParameters] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { semesterMap } = useGlobalFilters();

  const scoreSections = useMemo(() => {
    const sections = parameters?.sections || [];
    return sections;
  }, [parameters]);

  const scoreKeys = useMemo(() => {
    return buildScoreKeys(scoreSections.length || SCORE_KEYS.length);
  }, [scoreSections.length]);

  const isUpcoming = useMemo(() => {
    if (!sessionData) return false;
    const start = Date.parse(sessionData.window_start);
    const serverNow = Date.parse(sessionData.server_now);
    if (!Number.isNaN(start) && !Number.isNaN(serverNow)) {
      return serverNow < start;
    }
    return false;
  }, [sessionData]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const currentPanelId = requirePanelId();
        setPanelId(currentPanelId);

        const [sessionRes, paramsRes, draftRes] = await Promise.all([
          evaluationAPI.getSession(teamId, currentPanelId),
          evaluationAPI.getParameters(teamId, currentPanelId),
          evaluationAPI.getDraft(teamId, currentPanelId)
        ]);

        setSessionData(sessionRes);
        setParameters(paramsRes);
        setScores(draftRes?.scores || {});
        setRemarks(draftRes?.remarks || '');

        const canSubmitNow = Boolean(sessionRes.allow_submission) && !sessionRes.already_submitted;
        setIsActive(canSubmitNow);
        setTimeLeft(computeRemainingSeconds(sessionRes));
      } catch (err) {
        console.error('Failed to fetch evaluation data:', err);
        setError(err.message || 'Unable to load evaluation data');
      } finally {
        setLoading(false);
      }
    };

    if (teamId) {
      fetchData();
    }
  }, [teamId]);

  useEffect(() => {
    if (!isActive || timeLeft <= 0) {
      return;
    }

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          setIsActive(false);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isActive, timeLeft]);

  const WARNING_THRESHOLD = 600; // 10 minutes in seconds

  // Ref-based Set to track which minute-marks have already fired (avoids stale closures)
  const firedAlerts = useRef(new Set());
  const isInitialSync = useRef(true);
  const prevTimeLeft = useRef(timeLeft);

  // Initialize firedAlerts on mount/first load with already passed thresholds
  useEffect(() => {
    if (timeLeft > 0 && isInitialSync.current) {
      const ALERT_POINTS_SEC = [600, 300, 60];
      ALERT_POINTS_SEC.forEach(sec => {
        if (timeLeft < sec) {
          firedAlerts.current.add(sec);
        }
      });
      isInitialSync.current = false;
    }
  }, [timeLeft]);

  // Dynamically clean up firedAlerts when timeLeft increases due to slot extension
  useEffect(() => {
    if (timeLeft > prevTimeLeft.current) {
      const ALERT_POINTS_SEC = [600, 300, 60];
      ALERT_POINTS_SEC.forEach(sec => {
        if (timeLeft >= sec) {
          firedAlerts.current.delete(sec);
        }
      });
    }
    prevTimeLeft.current = timeLeft;
  }, [timeLeft]);

  // Periodically sync evaluation session data with the server to keep timer accurate and handle background throttling / admin extensions
  useEffect(() => {
    if (!teamId || !panelId || submittedData) return;

    const syncSession = async () => {
      try {
        const sessionRes = await evaluationAPI.getSession(teamId, panelId);
        if (sessionRes) {
          setSessionData(sessionRes);
          const canSubmitNow = Boolean(sessionRes.allow_submission) && !sessionRes.already_submitted;
          setIsActive(canSubmitNow);
          
          const serverRemaining = computeRemainingSeconds(sessionRes);
          setTimeLeft((prev) => {
            // Only update if it differs by more than 2 seconds to avoid resetting the tick interval
            if (Math.abs(prev - serverRemaining) > 2) {
              return serverRemaining;
            }
            return prev;
          });
        }
      } catch (err) {
        console.error('Failed to sync evaluation session:', err);
      }
    };

    const interval = setInterval(syncSession, 15000);
    return () => clearInterval(interval);
  }, [teamId, panelId, submittedData]);

  // Sync evaluation session data immediately when the user returns to the tab
  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.visibilityState === 'visible' && teamId && panelId && !submittedData) {
        try {
          const sessionRes = await evaluationAPI.getSession(teamId, panelId);
          if (sessionRes) {
            setSessionData(sessionRes);
            const canSubmitNow = Boolean(sessionRes.allow_submission) && !sessionRes.already_submitted;
            setIsActive(canSubmitNow);
            setTimeLeft(computeRemainingSeconds(sessionRes));
          }
        } catch (err) {
          console.error('Failed to sync session on visibility change:', err);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [teamId, panelId, submittedData]);

  // Request Notification permission on mount
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Listen for postMessages from the Service Worker (action button clicks on notification)
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    const handleSWMessage = (event) => {
      if (event.data?.type === 'EXTEND_SLOT') {
        handleExtendSlot(event.data.minutes);
      }
    };

    navigator.serviceWorker.addEventListener('message', handleSWMessage);
    return () => {
      navigator.serviceWorker.removeEventListener('message', handleSWMessage);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelId, teamId]);

  // Fire one-shot desktop notifications at exactly 10 min, 5 min, and 1 min
  useEffect(() => {
    if (!isActive || timeLeft <= 0) return;

    // If slot was extended back above 10 min, reset fired alerts so they fire again
    if (timeLeft > WARNING_THRESHOLD) {
      firedAlerts.current.clear();
      // Also reset initial sync
      isInitialSync.current = false;
      return;
    }

    const ALERT_POINTS = [
      {
        seconds: 60,
        title: '🚨 1 Minute Left — Evaluation Almost Over',
        body: (label) => `Last minute! Slot for ${label} is about to expire.`,
        tag: 'eval-warn-1',
      },
      {
        seconds: 300,
        title: '⚠️ 5 Minutes Left — Evaluation Ending Very Soon',
        body: (label) => `Only 5 minutes remain for ${label}. Extend now if needed.`,
        tag: 'eval-warn-5',
      },
      {
        seconds: 600,
        title: '⏰ 10 Minutes Left — Evaluation Ending Soon',
        body: (label) => `Slot for ${label} ends in 10 minutes. You can extend the duration.`,
        tag: 'eval-warn-10',
      },
    ];

    for (const point of ALERT_POINTS) {
      if (timeLeft <= point.seconds && !firedAlerts.current.has(point.seconds)) {
        firedAlerts.current.add(point.seconds);
        // Mark all higher/equal thresholds as fired to prevent double/stale warnings
        ALERT_POINTS.forEach(p => {
          if (p.seconds >= point.seconds) firedAlerts.current.add(p.seconds);
        });

        if ("Notification" in window && Notification.permission === "granted") {
          const label = teamDisplayLabel(teamId || sessionData?.team_id, sessionData, semesterMap);
          const title = point.title;
          const body = point.body(label);

          if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            navigator.serviceWorker.ready.then((registration) => {
              registration.showNotification(title, {
                body,
                tag: point.tag,
                requireInteraction: true,
                icon: '/GLA_University_logo.png',
                badge: '/favicon.svg',
                actions: [
                  { action: 'extend-5',  title: '+5 Minutes'  },
                  { action: 'extend-10', title: '+10 Minutes' },
                ],
              });
            }).catch((e) => console.error('SW showNotification failed:', e));
          } else {
            // Fallback: plain Notification when SW is not yet controlling
            try {
              const notif = new Notification(title, {
                body,
                tag: point.tag,
                requireInteraction: true,
              });
              notif.onclick = () => {
                window.focus();
                setShowExtendModal(true);
                notif.close();
              };
            } catch (e) {
              console.error('Failed to show desktop notification:', e);
            }
          }
        }
        break; // only one threshold per tick
      }
    }
  }, [timeLeft, isActive, teamId, sessionData, semesterMap]);

  // Flashing document title in browser tab when ≤ 10 minutes remain
  useEffect(() => {
    let intervalId = null;
    const originalTitle = document.title;
    
    if (isActive && timeLeft > 0 && timeLeft <= WARNING_THRESHOLD) {
      let toggle = false;
      intervalId = setInterval(() => {
        document.title = toggle 
          ? `🚨 TIME RUNNING OUT 🚨`
          : `⚠️ EXTEND EVALUATION? ⚠️`;
        toggle = !toggle;
      }, 1000);
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
      document.title = originalTitle;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, timeLeft <= WARNING_THRESHOLD + 5]);

  useEffect(() => {
    if (isActive && timeLeft > 0 && timeLeft <= WARNING_THRESHOLD && !extendModalShown) {
      setShowExtendModal(true);
      setExtendModalShown(true);
    }
    if (timeLeft > WARNING_THRESHOLD) {
      setExtendModalShown(false);
    }
  }, [timeLeft, isActive, extendModalShown]);

  const handleExtendSlot = async (minutes) => {
    setIsExtending(true);
    try {
      const res = await evaluationAPI.extendSlot(teamId, panelId, minutes);
      if (res) {
        setSessionData(res);
        const newTimeLeft = computeRemainingSeconds(res);
        setTimeLeft(newTimeLeft);
        setIsActive(true);
        setShowExtendModal(false);
        alert(`Slot extended by ${minutes} minutes successfully.`);
      }
    } catch (err) {
      console.error('Failed to extend slot:', err);
      alert(err.message || 'Failed to extend slot. Please try again.');
    } finally {
      setIsExtending(false);
    }
  };

  useEffect(() => {
    if (!isActive || submittedData || !panelId || !teamId) {
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const saved = await evaluationAPI.saveDraft(teamId, panelId, { scores, remarks });
        if (saved?.updated_at) {
          setDraftSavedTime(new Date(saved.updated_at).toLocaleTimeString());
        } else {
          setDraftSavedTime(new Date().toLocaleTimeString());
        }
      } catch (err) {
        console.error('Draft save failed:', err);
      }
    }, 1200);

    return () => clearTimeout(timer);
  }, [scores, remarks, isActive, submittedData, panelId, teamId]);

  const formatTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleScoreChange = (key, value, maxMarks) => {
    if (!isActive || submittedData) {
      return;
    }

    const validated = makeValidScore(value, maxMarks);
    if (validated === null) {
      return;
    }

    setScores((prev) => ({ ...prev, [key]: validated }));
  };

  const calculateTotalScore = () => {
    return scoreKeys.reduce((sum, key) => sum + (Number(scores[key]) || 0), 0);
  };

  const totalMaxMarks = useMemo(() => {
    return parameters?.total_maximum || scoreSections.reduce((sum, s) => sum + getMaxMarksForSection(s), 0) || 40;
  }, [parameters, scoreSections]);

  const handleSubmit = async () => {
    if (!isActive || !panelId || !teamId) {
      return;
    }

    for (let i = 0; i < scoreKeys.length; i++) {
      const key = scoreKeys[i];
      const section = scoreSections[i];
      const maxMarks = getMaxMarksForSection(section);
      const value = makeValidScore(scores[key], maxMarks);
      if (value === '' || value === null) {
        alert(`Please enter valid scores (0 to ${maxMarks}) for all parameters.`);
        return;
      }
    }

    if (!remarks.trim()) {
      alert('Remarks are required before submission.');
      return;
    }

    setIsSubmitting(true);
    try {
      const payloadScores = scoreKeys.reduce((acc, key) => {
        acc[key] = Number(scores[key]);
        return acc;
      }, {});

      const response = await evaluationAPI.submitEvaluation({
        panel_id: panelId,
        team_id: Number(teamId),
        scores: payloadScores,
        remarks: remarks.trim()
      });

      setSubmittedData(response);
      setShowSummary(true);
      setIsActive(false);
    } catch (err) {
      console.error('Submission failed:', err);
      alert(err.message || 'Failed to submit evaluation. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          Failed to load evaluation session: {error}
        </div>
      </div>
    );
  }

  const shouldShowEarlyReturn = (!isActive && !submittedData && (isUpcoming || sessionData?.already_submitted));

  if (shouldShowEarlyReturn) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-600 dark:text-amber-400 px-4 py-3 rounded-xl">
          <div className="flex items-center gap-3">
            <Lock size={20} />
            <div>
              <p className="font-bold">Evaluation Not Available</p>
              {sessionData?.already_submitted ? (
                <p className="text-sm">This team already has a locked submission.</p>
              ) : (
                <div className="text-sm">
                  <p>This evaluation is only accessible during the scheduled time slot.</p>
                  {sessionData?.window_start && sessionData?.window_end && (
                    <p className="mt-1 flex items-center gap-1.5">
                      <Clock size={14} />
                      Scheduled: <strong>{formatLocalTime(sessionData.window_start)}</strong>
                      {' '}&ndash;{' '}
                      <strong>{formatLocalTime(sessionData.window_end)}</strong>
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {sessionData?.already_submitted && (
          <button
            onClick={() => navigate(`/panel/receipt/${teamId}`)}
            className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-3 rounded-xl font-bold transition-all"
          >
            View Secure Receipt
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-1">
            Time-Bound Evaluation
          </h2>
          <p className="text-slate-500 font-medium">
            {teamDisplayLabel(teamId || sessionData?.team_id, sessionData, semesterMap)} • {sessionData?.project_title || 'Project'}
          </p>
          {/* Slot timing display */}
          {sessionData?.window_start && sessionData?.window_end && (
            <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
              <Clock size={13} className="text-emerald-500" />
              Slot: <span className="font-semibold text-slate-600 dark:text-slate-300">
                {formatLocalTime(sessionData.window_start)} – {formatLocalTime(sessionData.window_end)}
              </span>
              {sessionData.slot_label && (
                <span className="ml-1 text-slate-400">({sessionData.slot_label})</span>
              )}
            </p>
          )}
        </div>

        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-3 px-6 py-3 rounded-2xl border ${
            timeLeft <= 300
              ? 'bg-rose-50 border-rose-200 dark:bg-rose-500/10 dark:border-rose-500/20'
              : timeLeft <= WARNING_THRESHOLD
              ? 'bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/20'
              : 'bg-emerald-50 border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/20'
          }`}>
            <Timer className={`${
              timeLeft <= 300 ? 'text-rose-600 dark:text-rose-400'
              : timeLeft <= WARNING_THRESHOLD ? 'text-amber-600 dark:text-amber-400'
              : 'text-emerald-600 dark:text-emerald-400'
            } animate-pulse`} size={24} />
            <div className="flex flex-col">
              <span className="text-xs font-bold uppercase tracking-widest text-slate-500">Time Remaining</span>
              <span className={`text-xl font-mono font-bold ${
                timeLeft <= 300 ? 'text-rose-600 dark:text-rose-400'
                : timeLeft <= WARNING_THRESHOLD ? 'text-amber-600 dark:text-amber-400'
                : 'text-emerald-600 dark:text-emerald-400'
              }`}>
                {formatTime(timeLeft)}
              </span>
            </div>
          </div>

          <button
            onClick={() => setShowExtendModal(true)}
            className="flex items-center justify-center gap-1.5 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-700 dark:text-slate-200 font-bold transition-all active:scale-95 shadow-sm text-sm"
            title="Extend slot duration"
          >
            <Clock size={18} className="text-indigo-500" />
            <span className="hidden sm:inline">Extend Time</span>
          </button>
        </div>
      </div>

      <AnimatePresence>
        {showSummary && submittedData ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-2xl p-8"
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-emerald-100 dark:bg-emerald-500/20 rounded-xl">
                <CheckCircle2 className="text-emerald-600 dark:text-emerald-400" size={24} />
              </div>
              <div>
                <h3 className="text-xl font-black text-emerald-800 dark:text-emerald-200">Evaluation Submitted</h3>
                <p className="text-emerald-600 dark:text-emerald-400 text-sm">Your evaluation has been securely recorded.</p>
              </div>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-xl p-6 border border-emerald-200 dark:border-emerald-500/20">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-slate-500 font-medium">Panel ID:</span>
                  <span className="ml-2 font-bold text-slate-800 dark:text-slate-200">{submittedData.panel_id}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Timestamp:</span>
                  <span className="ml-2 font-bold text-slate-800 dark:text-slate-200">{new Date(submittedData.submitted_at).toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Raw Score:</span>
                  <span className="ml-2 font-bold text-slate-800 dark:text-slate-200">{submittedData.total_raw} / {totalMaxMarks}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Normalized Score:</span>
                  <span className="ml-2 font-bold text-emerald-600 dark:text-emerald-400">{submittedData.final_score_normalized}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-medium">Status:</span>
                  <span className="ml-2 font-bold text-emerald-600 dark:text-emerald-400">Locked</span>
                </div>
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <button
                onClick={() => navigate(`/panel/receipt/${teamId}`)}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-6 py-2 rounded-lg font-bold"
              >
                Open Secure Receipt
              </button>
            </div>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {!isActive && !submittedData && !isUpcoming && (
              <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-600 dark:text-amber-400 p-4 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Clock className="text-amber-500 animate-pulse" size={24} />
                  <div>
                    <p className="font-bold text-sm">Evaluation Time Expired</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      The scheduled slot has ended. Please extend the duration to continue or submit.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowExtendModal(true)}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 flex items-center gap-1.5 shrink-0"
                >
                  <Clock size={14} />
                  Extend Time Now
                </button>
              </div>
            )}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-8 shadow-sm">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Evaluation Parameters</h3>
                <span className="text-sm text-slate-500 bg-slate-100 dark:bg-slate-700 px-3 py-1 rounded-lg font-medium">
                  Total max: <strong className="text-slate-800 dark:text-slate-200">{totalMaxMarks}</strong>
                </span>
              </div>

              <div className="space-y-4">
                {scoreSections.map((section, index) => {
                  const key = scoreKeys[index];
                  const maxMarks = getMaxMarksForSection(section);
                  const currentVal = scores[key] ?? '';
                  const isOverMax = currentVal !== '' && Number(currentVal) > maxMarks;
                  return (
                    <div key={key} className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-900/30 rounded-lg">
                      <div className="flex-1">
                        <label className="font-medium text-slate-700 dark:text-slate-300">
                          {section.category}
                        </label>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                          Score band: 0 to <strong>{maxMarks}</strong>
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <input
                          type="number"
                          min="0"
                          max={maxMarks}
                          value={currentVal}
                          onChange={(e) => handleScoreChange(key, e.target.value, maxMarks)}
                          disabled={!isActive}
                          className={`w-24 px-3 py-2 border rounded-lg text-center font-bold dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 ${
                            isOverMax
                              ? 'border-red-400 ring-1 ring-red-400'
                              : 'border-slate-300 dark:border-slate-600'
                          }`}
                          placeholder="0"
                        />
                        <span className="text-xs text-slate-400">/ {maxMarks}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-8">
                <label className="font-medium text-slate-700 dark:text-slate-300 block mb-2">
                  Additional Remarks
                </label>
                <textarea
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  disabled={!isActive}
                  rows={4}
                  className="w-full px-4 py-3 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 resize-none"
                  placeholder="Enter any additional feedback or observations..."
                />
              </div>

              {draftSavedTime && (
                <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mt-4">
                  <Save size={14} />
                  Draft saved at {draftSavedTime}
                </div>
              )}
            </div>

            <div className="flex justify-between items-center">
              <div className="text-sm font-medium text-slate-500">
                Raw total: <span className="text-slate-800 dark:text-slate-200 font-bold">{calculateTotalScore()}</span>
                <span className="text-slate-400"> / {totalMaxMarks}</span>
              </div>
              <button
                onClick={handleSubmit}
                disabled={!isActive || isSubmitting}
                className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 disabled:cursor-not-allowed text-white px-8 py-3 rounded-xl font-bold transition-all shadow-lg shadow-emerald-600/20 active:scale-95 flex items-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Submitting...
                  </>
                ) : (
                  <>
                    Submit Evaluation <Send size={18} />
                  </>
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showExtendModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/80 shadow-2xl max-w-md w-full overflow-hidden p-6 text-slate-800 dark:text-slate-100"
            >
              <div className="flex items-start gap-4 mb-4">
                <div className="p-3 bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-2xl shrink-0">
                  <Clock size={28} className="animate-pulse" />
                </div>
                <div>
                  <h3 className="text-xl font-black text-slate-900 dark:text-slate-100">
                    {sessionData?.meet_link ? 'Google Meet Evaluation Ending Soon' : 'Evaluation Ending Soon'}
                  </h3>
                  <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
                    {sessionData?.meet_link 
                      ? "The allotted time for this Google Meet evaluation slot is running out. Do you want to extend the slot duration? Subsequent team slots will automatically shift."
                      : "The allotted time for this group's slot is running out. Do you want to extend the slot duration? Downstream slots will automatically shift."
                    }
                  </p>
                </div>
              </div>

              <div className="bg-slate-50 dark:bg-slate-900/30 rounded-2xl p-4 border border-slate-100 dark:border-slate-700/50 mb-6 flex justify-between items-center text-sm font-semibold">
                <span className="text-slate-500">Current Remaining Time:</span>
                <span className={`font-mono text-base ${
                  timeLeft <= 300 ? 'text-rose-600 dark:text-rose-400 font-bold'
                  : 'text-amber-600 dark:text-amber-400'
                }`}>
                  {formatTime(timeLeft)}
                </span>
              </div>

              <div className="space-y-3">
                <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                  Select Extension Duration
                </p>
                <div className="grid grid-cols-3 gap-2.5">
                  <button
                    disabled={isExtending}
                    onClick={() => handleExtendSlot(5)}
                    className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 hover:bg-indigo-50/20 dark:hover:bg-indigo-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                  >
                    <span className="text-lg text-indigo-650 dark:text-indigo-400">+5</span>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                  </button>
                  <button
                    disabled={isExtending}
                    onClick={() => handleExtendSlot(10)}
                    className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 hover:bg-indigo-50/20 dark:hover:bg-indigo-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                  >
                    <span className="text-lg text-indigo-650 dark:text-indigo-400">+10</span>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                  </button>
                  <button
                    disabled={isExtending}
                    onClick={() => handleExtendSlot(15)}
                    className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 hover:bg-indigo-50/20 dark:hover:bg-indigo-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                  >
                    <span className="text-lg text-indigo-650 dark:text-indigo-400">+15</span>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                  </button>
                </div>

                <div className="flex gap-3 mt-6 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                  <button
                    disabled={isExtending}
                    onClick={() => setShowExtendModal(false)}
                    className="flex-1 py-3 px-4 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-bold hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors active:scale-95 text-xs text-center disabled:opacity-50"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default TimeBoundEvaluation;
