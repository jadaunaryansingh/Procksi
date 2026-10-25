import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, Megaphone, Clock, CheckCircle, Calendar, CheckCheck, Users, Check, X, UserPlus, Building2, Hourglass, ShieldCheck, ChevronDown } from 'lucide-react';
import { useNotifications, useJoinRequests, fetchWithAuth } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';
import EmptyState from '../components/EmptyState';
import RichText from '../components/RichText';

// Same reasoning as DASHBOARD_POLL_MS: a 3s poll of two endpoints was ~40
// requests/minute per open tab, for data that changes a few times a day.
const NOTIFICATIONS_POLL_MS = 30000;

export default function NotificationsView() {
    const [activeTab, setActiveTab] = useState('All');
    const [processingId, setProcessingId] = useState(null);
    // Which notification bodies are expanded, keyed by id so the set survives the
    // 30s poll re-render without collapsing what the student just opened.
    const [expanded, setExpanded] = useState(() => new Set());

    const toggleExpand = (id) => {
        setExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const { data: notifications = [], loading: notifLoading, error: notifError, refetch: refetchNotif } = useNotifications();
    const { data: joinRequests = [], loading: jrLoading, error: jrError, refetch: refetchJr } = useJoinRequests();

    const handleRetry = () => {
        refetchNotif();
        refetchJr();
    };

    const _notifRefetchRef = React.useRef({});
    useEffect(() => {
        _notifRefetchRef.current = { refetchNotif, refetchJr };
    });

    useEffect(() => {
        const interval = setInterval(() => {
            _notifRefetchRef.current.refetchNotif(true);
            _notifRefetchRef.current.refetchJr(true);
        }, NOTIFICATIONS_POLL_MS);
        return () => clearInterval(interval);
    }, []);

    // Latches true the first time both queries settle; see the skeleton guard.
    const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
    if (!hasLoadedOnce && !notifLoading && !jrLoading) {
        setHasLoadedOnce(true);
    }

    const activeJoinRequests = (jrError && jrError.includes("not assigned to a team")) ? [] : (joinRequests || []);
    const pendingJoinCount = activeJoinRequests.length;

    const getCategory = (type) => {
        switch (type) {
            case 'announcement': return 'Announcements';
            case 'workflow': return 'Deadlines';
            case 'approval': return 'Decisions';
            case 'allocation': return 'Schedules';
            default: return 'Announcements';
        }
    };

    const mappedNotifications = (notifications || []).map(a => ({
        id: a.id,
        title: a.title,
        text: a.message,
        type: a.type,
        category: getCategory(a.type),
        time: a.created_at,
        unread: !a.read
    }));

    const filteredNotifications = mappedNotifications.filter(n =>
        activeTab === 'All' ? true : n.category === activeTab
    );

    const unreadCount = mappedNotifications.filter(n => n.unread).length;
    const totalUnread = unreadCount + pendingJoinCount;

    // Every post-mutation refetch below passes silent=true. A plain refetch()
    // flips `loading` back to true, and the guard above returns a full-page
    // skeleton while it is — so simply opening a notification blanked the whole
    // list and read like a page reload.
    const markAllAsRead = async () => {
        try {
            await fetchWithAuth('/api/student/notifications/read-all', { method: 'POST' });
            refetchNotif(true);
        } catch (e) {
            console.error(e);
        }
    };

    const toggleRead = async (id) => {
        try {
            await fetchWithAuth(`/api/student/notifications/${id}/read`, { method: 'POST' });
            refetchNotif(true);
        } catch (e) {
            console.error(e);
        }
    };

    const getIcon = (category) => {
        switch (category) {
            case 'Announcements': return <Megaphone className="w-5 h-5 text-blue-500" />;
            case 'Deadlines': return <Clock className="w-5 h-5 text-rose-500" />;
            case 'Decisions': return <CheckCircle className="w-5 h-5 text-emerald-500" />;
            case 'Schedules': return <Calendar className="w-5 h-5 text-indigo-500" />;
            case 'Team Requests': return <Users className="w-5 h-5 text-purple-500" />;
            default: return <Bell className="w-5 h-5 text-slate-500" />;
        }
    };

    const handleAccept = async (requestId, studentName) => {
        if (processingId) return;
        if (!window.confirm(`Accept request and add ${studentName || 'this student'} to your team?`)) return;
        setProcessingId(requestId);
        try {
            await fetchWithAuth(`/api/student/join-requests/${requestId}/accept`, { method: 'POST' });
            alert("Request accepted successfully");
            refetchJr(true);
        } catch (err) {
            alert(err.message || "Failed to accept request");
        } finally {
            setProcessingId(null);
        }
    };

    const handleDecline = async (requestId, studentName) => {
        if (processingId) return;
        if (!window.confirm(`Decline the request to add ${studentName || 'this student'} to your team?`)) return;
        setProcessingId(requestId);
        try {
            await fetchWithAuth(`/api/student/join-requests/${requestId}/decline`, { method: 'POST' });
            alert("Request declined successfully");
            refetchJr(true);
        } catch (err) {
            alert(err.message || "Failed to decline request");
        } finally {
            setProcessingId(null);
        }
    };

    const formatDate = (isoStr) => {
        if (!isoStr) return '';
        try {
            return new Date(isoStr).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
        } catch {
            return isoStr;
        }
    };

    // Full timestamp for the expanded panel. The collapsed header shows a short
    // "05 Aug, 11:31 pm"; this spells out weekday, year and seconds.
    const formatFullDate = (isoStr) => {
        if (!isoStr) return 'Unknown';
        const d = new Date(isoStr);
        if (Number.isNaN(d.getTime())) return isoStr;
        return d.toLocaleString('en-IN', {
            weekday: 'short', day: '2-digit', month: 'long', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
    };

    const showJoinRequests = activeTab === 'All' || activeTab === 'Team Requests';
    const tabs = ['All', 'Announcements', 'Deadlines', 'Decisions', 'Schedules', 'Team Requests'];

    // Skeleton only on the FIRST load. Once the list has rendered, a later
    // loading state (an explicit retry, or any future non-silent refetch) must
    // not tear the page down and rebuild it — that reads as a page reload.
    if ((notifLoading || jrLoading) && !hasLoadedOnce) {
        return (
            <div className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                    <LoadingSkeleton lines={5} />
                </div>
            </div>
        );
    }

    if (notifError || (jrError && !jrError.includes("not assigned to a team"))) {
        return (
            <ErrorCard message={notifError || jrError} onRetry={handleRetry} />
        );
    }

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                        Notifications {totalUnread > 0 && <span className="ml-3 bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 text-xs px-2.5 py-1 rounded-full font-bold">{totalUnread} new</span>}
                    </h2>
                    <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">Stay updated with important project activities.</p>
                </div>
                <button
                    onClick={markAllAsRead}
                    disabled={unreadCount === 0}
                    className="flex items-center px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300 rounded-xl text-sm font-semibold transition-colors"
                >
                    <CheckCheck className="w-4 h-4 mr-2" /> Mark all as read
                </button>
            </div>

            {/* Tabs */}
            <div className="flex overflow-x-auto hide-scrollbar pb-2">
                <div className="flex space-x-2 bg-slate-100/50 dark:bg-slate-800/50 p-1 rounded-xl">
                    {tabs.map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all whitespace-nowrap relative ${activeTab === tab
                                ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800'
                                }`}
                        >
                            {tab}
                            {tab === 'Team Requests' && pendingJoinCount > 0 && (
                                <span className="absolute -top-1 -right-1 w-4 h-4 bg-purple-500 text-white text-[9px] font-black rounded-full flex items-center justify-center animate-pulse">
                                    {pendingJoinCount}
                                </span>
                            )}
                        </button>
                    ))}
                </div>
            </div>

            {/* List */}
            <div className="space-y-4">
                <AnimatePresence mode="popLayout">

                    {/* ── Admin / Team Join Requests (incoming only) ── */}
                    {showJoinRequests && activeJoinRequests.filter(req => req.is_recipient !== false).map((req, idx) => {
                        let headerTitle = "Team Join Request";
                        let detailText = `${req.student_name || 'A student'} has requested to join your team. Review and confirm or decline.`;
                        if (req.initiated_by === 'leader') {
                            headerTitle = "Team Invitation";
                            detailText = `You have been invited to join team ${req.team_name || ''}. Review and confirm or decline.`;
                        } else if (req.initiated_by === 'admin') {
                            headerTitle = "Team Assignment";
                            detailText = `The admin has requested to add you to team ${req.team_name || ''}. Review and confirm or decline.`;
                        }

                        return (
                            <motion.div
                                // No `layout` here either — see the notification cards below. These
                                // sit in the same list, so a stale projection on one shifts the rest.
                                key={`jr-${req.id}`}
                                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.95, y: -20 }}
                                transition={{ duration: 0.3, delay: idx * 0.05 }}
                                className="p-5 rounded-3xl border bg-white dark:bg-slate-800 border-purple-200 dark:border-purple-500/40 shadow-lg shadow-purple-500/10 flex flex-col sm:flex-row gap-5"
                            >
                                {/* Icon */}
                                <div className="shrink-0 pt-1">
                                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center bg-gradient-to-br from-purple-100 to-indigo-100 dark:from-purple-500/20 dark:to-indigo-500/20 shadow-inner">
                                        <UserPlus className="w-5 h-5 text-purple-500" />
                                    </div>
                                </div>

                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 mb-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <h4 className="text-base font-bold text-slate-900 dark:text-white">
                                                {headerTitle}
                                            </h4>
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-400 text-[10px] font-black uppercase tracking-widest rounded-full border border-purple-200 dark:border-purple-500/30">
                                                <Hourglass className="w-2.5 h-2.5" /> Pending
                                            </span>
                                        </div>
                                        <span className="text-xs font-bold text-slate-400 dark:text-slate-500 whitespace-nowrap sm:mt-1 bg-slate-100 dark:bg-slate-700/50 px-2 py-1 rounded-md">
                                            {formatDate(req.requested_at)}
                                        </span>
                                    </div>

                                    <div className="mb-3 p-3.5 rounded-2xl bg-purple-50/70 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-500/20">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Building2 className="w-4 h-4 text-purple-500 shrink-0" />
                                            <span className="text-sm font-bold text-slate-800 dark:text-white truncate">
                                                {req.team_name || `Team ${(req.team_id || '').toString().slice(0, 8).toUpperCase()}`}
                                            </span>
                                        </div>
                                        {req.student_name && (
                                            <div className="flex items-center gap-2 mb-1.5">
                                                <ShieldCheck className="w-4 h-4 text-indigo-400 shrink-0" />
                                                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                                                    {req.student_name}
                                                    <span className="ml-1 text-slate-500 dark:text-slate-400 font-normal text-xs">({req.student_roll || req.student_id})</span>
                                                </span>
                                            </div>
                                        )}
                                        <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                                            {detailText}
                                        </p>
                                    </div>

                                    {/* Action buttons */}
                                    <div className="flex flex-wrap gap-3">
                                        <button
                                            onClick={() => handleAccept(req.id, req.student_name)}
                                            disabled={processingId === req.id}
                                            className="flex items-center px-5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-xl text-sm font-bold transition-all active:scale-95 shadow-md shadow-emerald-500/20"
                                        >
                                            {processingId === req.id ? (
                                                <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />Processing...</>
                                            ) : (
                                                <><Check className="w-4 h-4 mr-2" />Accept & Join Team</>
                                            )}
                                        </button>
                                        <button
                                            onClick={() => handleDecline(req.id, req.student_name)}
                                            disabled={processingId === req.id}
                                            className="flex items-center px-5 py-2 bg-slate-100 hover:bg-red-50 dark:bg-slate-700 dark:hover:bg-red-500/20 disabled:opacity-60 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 rounded-xl text-sm font-bold transition-all active:scale-95 border border-slate-200 dark:border-slate-600"
                                        >
                                            <X className="w-4 h-4 mr-2" />Decline
                                        </button>
                                    </div>
                                </div>
                                <div className="shrink-0 flex items-start sm:items-center">
                                    <div className="w-3 h-3 rounded-full bg-purple-500 shadow-[0_0_10px_rgba(168,85,247,0.6)] mt-2 sm:mt-0 animate-pulse" />
                                </div>
                            </motion.div>
                        );
                    })}

                    {/* ── Regular Notifications ── */}
                    {(activeTab !== 'Team Requests' ? filteredNotifications : []).map((notification, idx) => {
                      const isExpanded = expanded.has(notification.id);
                      // Only clamp bodies long enough to need it — clamping a
                      // one-line reminder just clips it for no reason.
                      const isLong = (notification.text || '').length > 140;
                      return (
                        <motion.div
                            // No `layout` prop on purpose. These cards change height when expanded,
                            // and motion's layout projection handled that badly twice over: a bare
                            // `layout` scaled the box and (because whileHover puts a scale on the
                            // element) skipped the inverse-scale correction for children, stretching
                            // the text; `layout="position"` then left ~400px of stale gap under a
                            // collapsed card because the projected position was measured while it
                            // was still expanded.
                            //
                            // Nothing is lost: the expand/collapse itself is animated by the
                            // AnimatePresence height transition inside the card, and entry/exit by
                            // the initial/animate/exit props below. Only the sibling-reflow tween is
                            // gone, and siblings now simply reflow instantly, which is correct.
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: -20 }}
                            transition={{ duration: 0.3, delay: (showJoinRequests ? activeJoinRequests.length : 0) * 0.05 + idx * 0.05 }}
                            whileHover={{ scale: 1.015, transition: { duration: 0.2 } }}
                            key={notification.id}
                            onClick={() => { toggleExpand(notification.id); toggleRead(notification.id); }}
                            className={`p-5 rounded-3xl border transition-all flex flex-col sm:flex-row gap-5 cursor-pointer ${notification.unread
                                ? 'bg-white dark:bg-slate-800 border-indigo-100 dark:border-indigo-500/30 shadow-lg shadow-indigo-500/10'
                                : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/50 opacity-80 hover:opacity-100 shadow-sm'
                                }`}
                        >
                            <div className="shrink-0 pt-1">
                                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-inner ${notification.unread ? 'bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-500/20 dark:to-purple-500/20' : 'bg-slate-200/50 dark:bg-slate-700'}`}>
                                    {getIcon(notification.category)}
                                </div>
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 mb-1.5">
                                    <h4 className={`text-base font-bold ${notification.unread ? 'text-slate-900 dark:text-white' : 'text-slate-700 dark:text-slate-300'}`}>
                                        {notification.title}
                                    </h4>
                                    <div className="flex items-center gap-2 shrink-0 sm:mt-1">
                                        <span className="text-xs font-bold text-slate-400 dark:text-slate-500 whitespace-nowrap bg-slate-100 dark:bg-slate-700/50 px-2 py-1 rounded-md">
                                            {formatDate(notification.time)}
                                        </span>
                                        {/* Expand/collapse. The whole card does this too; the
                                            chevron just makes it discoverable. stopPropagation is
                                            required — without it the card's handler would fire as
                                            well and the second toggle would cancel the first. */}
                                        <button
                                            type="button"
                                            onClick={(e) => { e.stopPropagation(); toggleExpand(notification.id); toggleRead(notification.id); }}
                                            aria-expanded={isExpanded}
                                            aria-label={isExpanded ? 'Hide details' : 'Show details'}
                                            title={isExpanded ? 'Hide details' : 'Show details'}
                                            className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors active:scale-90"
                                        >
                                            <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                                        </button>
                                    </div>
                                </div>
                                {/* RichText renders block children (<p>/<ul>), which
                                    line-clamp handles badly, so collapse with a
                                    max-height instead. */}
                                <div className={!isExpanded && isLong ? 'max-h-12 overflow-hidden' : ''}>
                                    <RichText
                                        text={notification.text}
                                        className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed font-medium"
                                    />
                                </div>
                                {!isExpanded && isLong && (
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); toggleExpand(notification.id); toggleRead(notification.id); }}
                                        className="mt-1 text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:underline"
                                    >
                                        Show more
                                    </button>
                                )}

                                <AnimatePresence initial={false}>
                                    {isExpanded && (
                                        <motion.div
                                            key="details"
                                            initial={{ height: 0, opacity: 0 }}
                                            animate={{ height: 'auto', opacity: 1 }}
                                            exit={{ height: 0, opacity: 0 }}
                                            transition={{ duration: 0.2 }}
                                            className="overflow-hidden"
                                        >
                                            <dl className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/60 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                                                <div>
                                                    <dt className="font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Category</dt>
                                                    <dd className="mt-0.5 font-semibold text-slate-700 dark:text-slate-300">{notification.category}</dd>
                                                </div>
                                                <div>
                                                    <dt className="font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Status</dt>
                                                    <dd className={`mt-0.5 font-semibold ${notification.unread ? 'text-indigo-600 dark:text-indigo-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                                                        {notification.unread ? 'Unread' : 'Read'}
                                                    </dd>
                                                </div>
                                                <div>
                                                    <dt className="font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">Received</dt>
                                                    <dd className="mt-0.5 font-semibold text-slate-700 dark:text-slate-300">{formatFullDate(notification.time)}</dd>
                                                </div>
                                            </dl>
                                            <p className="mt-3 text-[11px] font-medium text-slate-400 dark:text-slate-500">
                                                Tap anywhere on this card to collapse it.
                                            </p>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                            {notification.unread && (
                                <div className="shrink-0 flex items-center">
                                    <div className="w-3 h-3 rounded-full bg-indigo-500 shadow-[0_0_10px_rgba(99,102,241,0.6)] mt-2 sm:mt-0"></div>
                                </div>
                            )}
                        </motion.div>
                      );
                    })}

                    {/* ── Empty State ── */}
                    {(showJoinRequests ? activeJoinRequests.length === 0 : true) &&
                        (activeTab === 'Team Requests' ? true : filteredNotifications.length === 0) && (
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                            className="text-center py-16 bg-white dark:bg-slate-800/80 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm flex flex-col items-center justify-center w-full"
                        >
                            <svg className="w-32 h-32 text-indigo-100 dark:text-indigo-900/40 mb-6" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <circle cx="50" cy="50" r="50" fill="currentColor" />
                                <path d="M40 35C40 29.4772 44.4772 25 50 25C55.5228 25 60 29.4772 60 35V45H75C76.1046 45 77 45.8954 77 47C77 48.1046 76.1046 49 75 49H25C23.8954 49 23 48.1046 23 47C23 45.8954 23.8954 45 25 45H40V35Z" fill="#818cf8" />
                                <path d="M43 53C43 56.866 46.134 60 50 60C53.866 60 57 56.866 57 53H43Z" fill="#818cf8" />
                                <circle cx="70" cy="25" r="4" fill="#a5b4fc" />
                                <circle cx="80" cy="40" r="3" fill="#a5b4fc" />
                                <circle cx="25" cy="20" r="5" fill="#a5b4fc" />
                                <circle cx="20" cy="35" r="3" fill="#a5b4fc" />
                            </svg>
                            <h3 className="text-xl font-bold text-slate-800 dark:text-slate-200 mb-2">All Caught Up!</h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xs leading-relaxed">
                                You have no new notifications in the <span className="font-bold text-slate-700 dark:text-slate-300">{activeTab}</span> category. Take a break!
                            </p>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </motion.div>
    );
}
