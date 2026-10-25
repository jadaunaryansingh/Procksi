import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon, Bell, Menu, User, Settings, LogOut, AlertTriangle, HelpCircle } from 'lucide-react';
import { useProfile, useNotifications, useDeadlines, useAnnouncements, useDeadlineCompletionState, fetchWithAuth } from '../hooks/useStudentData';
import { buildReminders } from '../lib/reminders';
import RichText from './RichText';

// Deliberately faster than the other views (DASHBOARD_POLL_MS /
// NOTIFICATIONS_POLL_MS are both 30s): the alert button is the one thing a
// student is meant to notice within seconds of it going red.
//
// Cost: four endpoints per tick, so ~48 requests/minute per visible tab. The
// visibility check below means a backgrounded tab costs nothing, which is what
// keeps this affordable.
const ALERT_POLL_MS = 5000;

export const TopNav = ({
    isDark,
    toggleTheme,
    setMobileMenuOpen,
    notificationsOpen,
    setNotificationsOpen,
    profileDropdownOpen,
    setProfileDropdownOpen,
    handleLogout
, onReplayWalkthrough}) => {
    const location = useLocation();
    const navigate = useNavigate();
    const { data: profile } = useProfile();
    const { data: notificationsData, refetch: refetchNotifications } = useNotifications();

    // Whether there's anything to alert about: an UNMET deadline, an
    // announcement, or an unread notification. Once every deadline is met (or
    // nothing remains), the alert button goes quiet (stays visible).
    //
    // `notificationsData` MUST be passed through. Deadline reminders are written
    // to the notifications table by the backend scheduler, so omitting them left
    // this button grey while the reminder window was popping for that very alert
    // — the two must agree, they both read hasAlert.
    const { data: deadlines, refetch: refetchDeadlines } = useDeadlines();
    const { data: announcements, refetch: refetchAnnouncements } = useAnnouncements();
    const { completion, refetch: refetchCompletion } = useDeadlineCompletionState();
    // maxNotifications is raised past the render cap because this result also
    // decides whether the bell dot lights: a capped list would be a fine basis
    // for "is there anything?" today, but only by accident.
    const reminders = useMemo(
        () => buildReminders(deadlines || [], announcements || [], 3, completion, notificationsData || [], Number.MAX_SAFE_INTEGER),
        [deadlines, announcements, completion, notificationsData]
    );
    const hasReminders = reminders.hasAlert;
    const [joinRequests, setJoinRequests] = useState([]);
    const notifRef = useRef(null);

    // Keep the alert button live without a page reload.
    //
    // Everything it reads (deadlines, announcements, notifications, completion)
    // was fetched once on mount, so a reminder written by the backend scheduler
    // left the button grey until the student happened to reload. Refresh on a
    // timer, and again the moment the tab regains focus — a student coming back
    // to a long-open tab is exactly when a stale button misleads.
    //
    // All refreshes are silent: they never flip the UI back to a loading state.
    // Every refetch below is a stable useCallback, so this identity is stable and
    // the effects that depend on it do not re-subscribe each render.
    const refreshAlerts = useCallback(() => {
        refetchDeadlines(true);
        refetchAnnouncements(true);
        refetchNotifications(true);
        refetchCompletion(true);
    }, [refetchDeadlines, refetchAnnouncements, refetchNotifications, refetchCompletion]);

    useEffect(() => {
        // Don't poll a tab nobody is looking at — the same handler catches it up
        // on return, so a backgrounded tab costs nothing and is never stale.
        const tick = () => {
            if (document.visibilityState === 'visible') refreshAlerts();
        };
        const interval = setInterval(tick, ALERT_POLL_MS);
        document.addEventListener('visibilitychange', tick);
        return () => {
            clearInterval(interval);
            document.removeEventListener('visibilitychange', tick);
        };
    }, [refreshAlerts]);

    // The reminder window marks notifications read and the student may act on a
    // deadline while it is open, so re-check as soon as it closes.
    useEffect(() => {
        window.addEventListener('student:reminders-closed', refreshAlerts);
        return () => window.removeEventListener('student:reminders-closed', refreshAlerts);
    }, [refreshAlerts]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (notifRef.current && !notifRef.current.contains(event.target)) {
                setNotificationsOpen(false);
            }
        };
        if (notificationsOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, [notificationsOpen, setNotificationsOpen]);

    // Periodically fetch join requests
    useEffect(() => {
        let active = true;
        const fetchReqs = async () => {
            try {
                const data = await fetchWithAuth('/api/student/join-requests');
                if (active) {
                    setJoinRequests(Array.isArray(data) ? data : []);
                }
            } catch {
                // Silently ignore
            }
        };
        fetchReqs();
        const interval = setInterval(fetchReqs, 30000);
        return () => {
            active = false;
            clearInterval(interval);
        };
    }, []);

    const getTitle = () => {
        const path = location.pathname;
        if (path.includes('dashboard')) return 'Dashboard';
        if (path.includes('team')) return 'Team & Proposal';
        if (path.includes('preferences')) return 'Project Preferences';
        if (path.includes('mentor')) return 'Mentor';
        if (path.includes('presentations')) return 'Presentation Schedule';
        if (path.includes('evaluations')) return 'Evaluation';
        if (path.includes('results')) return 'Results';
        if (path.includes('feedback')) return 'Feedback Timeline';
        if (path.includes('profile')) return 'My Profile';
        if (path.includes('notifications')) return 'Notifications';
        if (path.includes('activities')) return 'Extra Activities';
        if (path.includes('milestones')) return 'Milestones';
        return 'Dashboard';
    };

    const studentName = profile?.name || 'Loading Student...';
    const studentEmail = profile?.email || '';
    const avatarUrl = profile?.avatar_url || `https://ui-avatars.com/api/?name=${encodeURIComponent(studentName)}&background=random`;

    const notifications = (notificationsData || []).map(a => ({
        id: a.id,
        title: a.title,
        text: a.message,
        time: new Date(a.created_at).toLocaleDateString(),
        unread: !a.read
    }));

    // The bell dot follows the same rule as the alert button: a deadline
    // reminder whose deadline has closed is no longer something to act on, so
    // it must not keep the dot lit. buildReminders has already dropped those;
    // anything it kept, plus non-deadline unread rows, still counts.
    const alertingIds = new Set((reminders.alertingNotifications || []).map(n => n.id));
    const unreadNotifications = notifications.filter(n => alertingIds.has(n.id));

    return (
        <header className="h-16 border-b border-slate-200/80 dark:border-slate-800/80 bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl sticky top-0 z-40 flex items-center justify-between px-4 sm:px-6 transition-colors">
            {/* Aesthetic background glows */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none z-[-1]">
                <div className="absolute top-[-50px] left-[10%] w-[200px] h-[200px] bg-indigo-500/10 dark:bg-indigo-500/10 rounded-full blur-3xl"></div>
                <div className="absolute top-[-50px] right-[25%] w-[150px] h-[150px] bg-purple-500/10 dark:bg-purple-500/10 rounded-full blur-3xl"></div>
            </div>

            <div className="flex items-center">
                <button onClick={() => setMobileMenuOpen(true)} data-tour="mobile-menu-button" className="md:hidden mr-4 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-colors">
                    <Menu className="w-6 h-6" />
                </button>
                {/* Replays the tour for whichever page is showing. */}
                <button
                  onClick={onReplayWalkthrough}
                  title="Replay the walkthrough for this page"
                  aria-label="Replay the walkthrough for this page"
                  className="p-2 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 rounded-lg hover:bg-indigo-50 dark:hover:bg-slate-800 transition-colors"
                >
                  <HelpCircle size={18} />
                </button>
                <div className="flex flex-col">
                    <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 hidden sm:block drop-shadow-sm">
                        {getTitle()}
                    </h2>
                    <span className="text-xs font-extrabold tracking-wide uppercase bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent hidden sm:block">
                        GLA University – Project Management System
                    </span>
                </div>
            </div>

            <div className="flex items-center space-x-3 sm:space-x-5">
                <button
                    type="button"
                    onClick={() => window.dispatchEvent(new CustomEvent('student:open-reminders'))}
                    title={hasReminders ? 'You have active alerts' : 'No active alerts'}
                    aria-label="Alerts"
                    className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-bold transition-colors active:scale-95 ${
                        hasReminders
                            ? 'alert-blink bg-red-500 hover:bg-red-600 text-white shadow-md shadow-red-500/40'
                            : 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500 hover:bg-slate-300 dark:hover:bg-slate-600 hover:text-slate-600 dark:hover:text-slate-300 cursor-pointer'
                    }`}>
                    <AlertTriangle className="w-4 h-4" />
                    <span className="hidden sm:inline">Alert</span>
                </button>

                <button onClick={toggleTheme} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-all rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 hover:rotate-12 active:scale-95">
                    {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                </button>

                <div className="relative" ref={notifRef}>
                    <button onClick={() => setNotificationsOpen(!notificationsOpen)} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-all rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 relative hover:rotate-12 active:scale-95">
                        <Bell className="w-5 h-5" />
                        {(unreadNotifications.length > 0 || joinRequests.length > 0) && <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-white dark:border-slate-900 animate-pulse"></span>}
                    </button>
                    <AnimatePresence>
                        {notificationsOpen && (
                            <motion.div initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute right-0 mt-2 w-80 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
                                <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
                                    <h3 className="font-semibold text-slate-800 dark:text-slate-100">Notifications</h3>
                                    <button className="text-xs text-indigo-600 dark:text-indigo-400 font-medium hover:underline" onClick={() => setNotificationsOpen(false)}>Close</button>
                                </div>
                                <div className="max-h-80 overflow-y-auto">
                                    {joinRequests.filter(req => req.is_recipient !== false).map(req => {
                                        let titleText = "Team Join Request";
                                        let subtext = req.student_name ? `${req.student_name} has requested to join your team` : 'New team join request';
                                        if (req.initiated_by === 'leader') {
                                            titleText = "Team Invitation";
                                            subtext = `You have been invited to join team ${req.team_name || ''}`;
                                        } else if (req.initiated_by === 'admin') {
                                            titleText = "Team Assignment";
                                            subtext = `Admin requested to add you to team ${req.team_name || ''}`;
                                        }
                                        return (
                                            <div key={`jr-${req.id}`} className="p-4 border-b border-purple-50 dark:border-purple-900/30 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors cursor-pointer bg-purple-50/50 dark:bg-purple-900/10" onClick={() => { navigate('/student/notifications'); setNotificationsOpen(false); }}>
                                                <div className="flex items-center gap-2 mb-0.5">
                                                    <span className="w-2 h-2 rounded-full bg-purple-500 shrink-0 animate-pulse" />
                                                    <p className="text-sm font-bold text-slate-800 dark:text-slate-100">{titleText}</p>
                                                </div>
                                                <p className="text-xs text-slate-500 dark:text-slate-400 ml-4">{subtext} <span className="font-semibold text-purple-600 dark:text-purple-400">{req.initiated_by === 'student' ? (req.team_name || '') : ''}</span></p>
                                            </div>
                                        );
                                    })}
                                    {notifications.length === 0 && joinRequests.filter(req => req.is_recipient !== false).length === 0 && (
                                        <div className="p-6 text-center text-sm text-slate-500">
                                            No new notifications
                                        </div>
                                    )}
                                    {notifications.map(n => (
                                        <div key={n.id} className={`p-4 border-b border-slate-50 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors cursor-pointer bg-indigo-50/50 dark:bg-indigo-900/10`} onClick={() => { navigate('/student/notifications'); setNotificationsOpen(false); }}>
                                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{n.title}</p>
                                            <RichText text={n.text} className="text-sm text-slate-600 dark:text-slate-300 mt-1 line-clamp-3" />
                                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{n.time}</p>
                                        </div>
                                    ))}
                                </div>
                                <div className="p-3 border-t border-slate-100 dark:border-slate-700">
                                    <button className="w-full text-center text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:underline" onClick={() => { navigate('/student/notifications'); setNotificationsOpen(false); }}>View All Notifications</button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* Profile Dropdown */}
                <div className="relative pl-2 sm:pl-4 border-l border-slate-200 dark:border-slate-800">
                    <div onClick={() => setProfileDropdownOpen(!profileDropdownOpen)} className="relative h-9 w-9 rounded-full border-2 border-slate-200 dark:border-slate-700 overflow-hidden cursor-pointer hover:border-indigo-500 dark:hover:border-indigo-500 hover:shadow-md hover:shadow-indigo-500/20 transition-all group">
                        <div className="absolute inset-0 bg-indigo-500/10 group-hover:bg-indigo-500/0 transition-colors z-10"></div>
                        <img src={avatarUrl} alt="Profile" className="w-full h-full object-cover relative z-0" />
                    </div>
                    <AnimatePresence>
                        {profileDropdownOpen && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setProfileDropdownOpen(false)}></div>
                                <motion.div initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                    className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
                                    <div className="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                                        <p className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{studentName}</p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">{studentEmail}</p>
                                    </div>
                                    <div className="p-2 space-y-1">
                                        <button onClick={() => { navigate('/student/profile'); setProfileDropdownOpen(false); }} className="w-full flex items-center px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors">
                                            <User className="w-4 h-4 mr-3 text-slate-400" /> Profile View
                                        </button>
                                        <button onClick={() => { navigate('/student/profile'); setProfileDropdownOpen(false); }} className="w-full flex items-center px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors">
                                            <Settings className="w-4 h-4 mr-3 text-slate-400" /> Settings
                                        </button>
                                        <button onClick={handleLogout} className="w-full flex items-center px-3 py-2 mt-1 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors border-t border-slate-100 dark:border-slate-700">
                                            <LogOut className="w-4 h-4 mr-3 text-red-400" /> Sign Out
                                        </button>
                                    </div>
                                </motion.div>
                            </>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </header>
    );
};

export default TopNav;
