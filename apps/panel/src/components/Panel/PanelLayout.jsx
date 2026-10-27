import React, { useState, useEffect, useRef } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Home, CalendarClock, BookOpen, LogOut, Menu, ChevronLeft, ChevronRight, Bell, FileX, UserCircle2, Filter, RotateCcw, Clock, Timer, Video, LayoutGrid, MessageSquare, HelpCircle } from 'lucide-react';
import { useChatUnread } from '../../hooks/useChatUnread';
import { motion, AnimatePresence } from 'framer-motion';
import ReminderPopup from './ReminderPopup';
import AlertNotifications from '../AlertNotifications';
import { cleanUUIDsFromText } from '../../lib/globalFilters';
import ThemeToggle from '../ThemeToggle';
import { panelAPI, evaluationAPI } from '../../services/api';
import { getStoredUserInfo, panelInitials, requirePanelId, getMentorName } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { useProcksiChatEnabled } from '../../hooks/useProcksiChatEnabled';
import { useWalkthrough } from '../../hooks/useWalkthrough';
import WalkthroughOverlay from '../Walkthrough/WalkthroughOverlay';
import { TOUR_STEPS, TOUR_LABELS } from '../Walkthrough/steps';

const PanelLayout = ({ onLogout }) => {
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const procksiChatEnabled = useProcksiChatEnabled();
  const walkthrough = useWalkthrough({
    tours: TOUR_STEPS,
    prefix: 'procksi-panel-walkthrough-v1',
    rootPath: '/panel',
  });
  const tourLabel = TOUR_LABELS[location.pathname.replace(/\/+$/, '') || '/panel'];

  const {
    filters,
    semesterOptions,
    updateFilter,
  } = useGlobalFilters();

  // The staged `localFilters` buffer, its sync effect and handleApply lived here
  // only to hold the global search box's text until Enter was pressed. With that
  // input removed the semester dropdown writes straight through via updateFilter,
  // so the whole staging layer is gone.

  const userInfo = getStoredUserInfo();
  const panelId = userInfo.panel_id || 'Unassigned';
  const panelBadgeText = panelInitials(panelId);
  const mentorName = getMentorName();
  const [alerts, setAlerts] = useState([]);

  // Dropdown States
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  // Global Active Session & Timer States
  const [activeSession, setActiveSession] = useState(null);
  const [sessionTimeLeft, setSessionTimeLeft] = useState(0);
  const [globalExtendModalOpen, setGlobalExtendModalOpen] = useState(false);
  const [globalExtendModalShown, setGlobalExtendModalShown] = useState(false);
  const [isExtendingGlobal, setIsExtendingGlobal] = useState(false);

  // Ref to track fired notification points
  const firedGlobalAlerts = useRef(new Set());

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const currentPanelId = requirePanelId();
        const rows = await panelAPI.getAlerts(currentPanelId);
        setAlerts(rows || []);
      } catch (err) {
        console.error('Failed to load alerts:', err);
        setAlerts([]);
      }
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 10000);
    return () => clearInterval(interval);
  }, [location.pathname]);

  const formatGlobalTime = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  // Periodically check dashboard for active slot details
  useEffect(() => {
    let dashboardTimer = null;

    const checkActiveSession = async () => {
      try {
        const currentPanelId = requirePanelId();
        const dbData = await panelAPI.getDashboard(currentPanelId);
        
        // Check if there is an active slot
        if (dbData?.active_slot_detail?.team_id) {
          const teamId = dbData.active_slot_detail.team_id;
          const session = await evaluationAPI.getSession(teamId, currentPanelId);
          if (session && session.allow_submission && !session.already_submitted) {
            setActiveSession(session);
            
            // Calculate remaining seconds
            const serverNow = Date.parse(session.server_now || '');
            const windowEnd = Date.parse(session.window_end || '');
            let remaining = Number(session.evaluation_timer_seconds) || 30 * 60;
            if (!isNaN(serverNow) && !isNaN(windowEnd)) {
              remaining = Math.max(0, Math.floor((windowEnd - serverNow) / 1000));
            }
            setSessionTimeLeft(remaining);
            return;
          }
        }
        setActiveSession(null);
        setSessionTimeLeft(0);
      } catch (err) {
        console.error("Failed global active session check:", err);
      }
    };

    checkActiveSession();
    dashboardTimer = setInterval(checkActiveSession, 15000);

    return () => {
      clearInterval(dashboardTimer);
    };
  }, []);

  // Tick the sessionTimeLeft down every second
  useEffect(() => {
    if (!activeSession || sessionTimeLeft <= 0) {
      return;
    }

    const tickTimer = setInterval(() => {
      setSessionTimeLeft((prev) => {
        if (prev <= 1) {
          setActiveSession(null); // time expired
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(tickTimer);
  }, [activeSession, sessionTimeLeft]);

  // Request Notification permission on mount
  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Reset alert points if slot gets extended above warning threshold
  useEffect(() => {
    if (sessionTimeLeft > 600) {
      firedGlobalAlerts.current.clear();
    }
  }, [sessionTimeLeft]);

  // Trigger global desktop notifications and modal popups for Google Meet evaluations
  useEffect(() => {
    const isEvaluationPage = location.pathname.includes('/panel/evaluation/');
    if (!activeSession || sessionTimeLeft <= 0 || isEvaluationPage) return;

    // Show popup modal inside app if time left <= 10 mins (600s)
    if (sessionTimeLeft <= 600 && !globalExtendModalShown) {
      setGlobalExtendModalOpen(true);
      setGlobalExtendModalShown(true);
    }
    if (sessionTimeLeft > 600) {
      setGlobalExtendModalOpen(false);
      setGlobalExtendModalShown(false);
    }

    // Trigger browser notification at exactly 10 min, 5 min, and 1 min thresholds
    const ALERT_POINTS = [
      { threshold: 60, tag: 'eval-warn-1', title: '🚨 1 Minute Left — Evaluation Almost Over', body: (label) => `Last minute! Slot for ${label} is about to expire.` },
      { threshold: 300, tag: 'eval-warn-5', title: '⚠️ 5 Minutes Left — Evaluation Ending Very Soon', body: (label) => `Only 5 minutes remain for ${label}. Extend now if needed.` },
      { threshold: 600, tag: 'eval-warn-10', title: '⏰ 10 Minutes Left — Evaluation Ending Soon', body: (label) => `Slot for ${label} ends in 10 minutes. You can extend the duration.` }
    ];

    for (const point of ALERT_POINTS) {
      if (sessionTimeLeft <= point.threshold && sessionTimeLeft > 0 && !firedGlobalAlerts.current.has(point.threshold)) {
        // Mark all higher thresholds as fired to prevent double warnings
        ALERT_POINTS.forEach(p => {
          if (p.threshold >= point.threshold) firedGlobalAlerts.current.add(p.threshold);
        });

        if ("Notification" in window && Notification.permission === "granted") {
          const label = activeSession.team_name || `Team ${activeSession.team_id}`;
          const title = activeSession.meet_link ? `📹 Google Meet: ${point.title}` : point.title;
          const body = point.body(label);

          if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
            navigator.serviceWorker.ready.then((registration) => {
              registration.showNotification(title, {
                body,
                tag: point.tag,
                requireInteraction: true,
                icon: '/procksi-mark.png',
                badge: '/procksi-icon-192.png',
                actions: [
                  { action: 'extend-5',  title: '+5 Minutes'  },
                  { action: 'extend-10', title: '+10 Minutes' },
                ],
              });
            }).catch((e) => console.error('SW showNotification failed globally:', e));
          } else {
            try {
              const notif = new Notification(title, {
                body,
                tag: point.tag,
                requireInteraction: true,
              });
              notif.onclick = () => {
                window.focus();
                setGlobalExtendModalOpen(true);
                notif.close();
              };
            } catch (e) {
              console.error('Failed to show global desktop notification:', e);
            }
          }
        }
        break; // only one threshold per tick
      }
    }
  }, [sessionTimeLeft, activeSession, globalExtendModalShown, location.pathname]);

  // Global listener for Service Worker action button messages
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    const handleGlobalSWMessage = async (event) => {
      if (event.data?.type === 'EXTEND_SLOT') {
        // Skip if on evaluation page (the page itself will handle it)
        if (location.pathname.includes('/panel/evaluation/')) {
          return;
        }

        try {
          const currentPanelId = requirePanelId();
          const dbData = await panelAPI.getDashboard(currentPanelId);
          const activeTeamId = dbData?.active_slot_detail?.team_id;
          if (activeTeamId) {
            const res = await evaluationAPI.extendSlot(activeTeamId, currentPanelId, event.data.minutes);
            if (res) {
              alert(`Google Meet Slot extended by ${event.data.minutes} minutes successfully.`);
              window.location.reload();
            }
          }
        } catch (err) {
          console.error("Global SW slot extension failed:", err);
        }
      }
    };

    navigator.serviceWorker.addEventListener('message', handleGlobalSWMessage);
    return () => {
      navigator.serviceWorker.removeEventListener('message', handleGlobalSWMessage);
    };
  }, [location.pathname]);

  // Global extension trigger
  const handleGlobalExtendSlot = async (minutes) => {
    if (!activeSession) return;
    setIsExtendingGlobal(true);
    try {
      const currentPanelId = requirePanelId();
      const res = await evaluationAPI.extendSlot(activeSession.team_id, currentPanelId, minutes);
      if (res) {
        // Refresh session
        const session = await evaluationAPI.getSession(activeSession.team_id, currentPanelId);
        setActiveSession(session);
        // Calculate remaining seconds
        const serverNow = Date.parse(session.server_now || '');
        const windowEnd = Date.parse(session.window_end || '');
        let remaining = Number(session.evaluation_timer_seconds) || 30 * 60;
        if (!isNaN(serverNow) && !isNaN(windowEnd)) {
          remaining = Math.max(0, Math.floor((windowEnd - serverNow) / 1000));
        }
        setSessionTimeLeft(remaining);
        setGlobalExtendModalOpen(false);
        alert(`Google Meet Slot extended by ${minutes} minutes successfully.`);
      }
    } catch (err) {
      console.error('Failed to extend slot globally:', err);
      alert(err.message || 'Failed to extend slot. Please try again.');
    } finally {
      setIsExtendingGlobal(false);
    }
  };

  const chatUnread = useChatUnread();
  const navItems = [
    { name: 'Dashboard', path: '/panel', icon: Home, end: true },
    { name: 'My Teams', path: '/panel/my-teams', icon: UserCircle2 },
    { name: 'My Slots', path: '/panel/slots', icon: CalendarClock },
    { name: 'Parameters', path: '/panel/parameters', icon: BookOpen },
    { name: 'Procksi Chat', path: '/panel/procksi-chat', icon: MessageSquare },
    { name: 'Missed', path: '/panel/missed', icon: FileX },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full overflow-hidden relative z-10">
      <div className="p-4 flex items-center justify-between">
        <div className={`flex items-center transition-all duration-300 overflow-hidden ${sidebarCollapsed ? 'w-auto opacity-100 md:w-0 md:opacity-0 md:group-hover/sidebar:w-[150px] md:group-hover/sidebar:opacity-100' : 'w-[150px] opacity-100'}`}>
          <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center shadow-md border border-slate-200 dark:border-slate-700/50 overflow-hidden shrink-0 mr-3">
            <img src="/procksi-mark.png" alt="Procksi" className="w-full h-full object-contain p-0.5" onError={(e) => { e.target.style.display = 'none' }} />
          </div>
          <div className="flex flex-col">
              <span className="font-bold text-sm text-slate-900 dark:text-white tracking-tight whitespace-nowrap leading-tight">Panel Portal</span>
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold tracking-wider">PROCKSI</span>
          </div>
        </div>
        <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="hidden md:flex p-1.5 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 rounded-lg hover:bg-emerald-50 dark:hover:bg-slate-800 transition-colors shrink-0">
            {sidebarCollapsed ? (
                <>
                    <Menu className="w-5 h-5 block group-hover/sidebar:hidden" />
                    <ChevronRight className="w-5 h-5 hidden group-hover/sidebar:block" />
                </>
            ) : (
                <ChevronLeft className="w-5 h-5" />
            )}
        </button>
      </div>

      <div className={`px-4 transition-all duration-300 overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-h-20 mt-6 mb-4 md:opacity-0 md:max-h-0 md:mt-0 md:mb-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-h-20 md:group-hover/sidebar:mt-6 md:group-hover/sidebar:mb-4' : 'opacity-100 max-h-20 mt-6 mb-4'}`}>
          <div className="bg-slate-100 dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700/50">
              <p className="text-xs text-slate-500 dark:text-slate-400 uppercase font-bold tracking-wider mb-1">Mentor</p>
                <p className="text-sm font-black text-slate-800 dark:text-slate-100 truncate" title={mentorName || `Panel ${panelId}`}>{mentorName || `Panel ${panelId}`}</p>
          </div>
      </div>

      <nav data-tour="sidebar-nav" className="flex-1 px-3 space-y-1 mt-2 overflow-y-auto overflow-x-hidden pb-4">
        {navItems.map((item) => {
          // Procksi Chat is disabled: greyed, inert, and no unread badge.
          const isDisabled = item.path === '/panel/procksi-chat' && !procksiChatEnabled;
          return (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            data-tour={`nav-${item.path.split('/').pop()}`}
            aria-disabled={isDisabled}
            tabIndex={isDisabled ? -1 : undefined}
            title={isDisabled ? 'Procksi Chat is currently unavailable' : undefined}
            onClick={(e) => {
              // NavLink has no disabled attribute, so cancel the navigation here.
              if (isDisabled) { e.preventDefault(); return; }
              setMobileMenuOpen(false);
            }}
            className={({ isActive }) =>
              `w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-bold transition-all group relative ${
                isDisabled
                  ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-600'
                  : isActive
                  ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className="relative shrink-0">
                    <item.icon className={`w-5 h-5 transition-colors ${isActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300'}`} />
                    {item.path.endsWith('/procksi-chat') && procksiChatEnabled && chatUnread > 0 && (
                        // Pinned to the icon rather than the row end, so the count
                        // stays visible when the rail is collapsed to icons only.
                        <span aria-label={`${chatUnread} unread`}
                            className="absolute -top-2 -right-2 min-w-[1.05rem] h-[1.05rem] px-1 rounded-full bg-emerald-600 text-white text-[9px] font-black flex items-center justify-center tabular-nums ring-2 ring-white dark:ring-slate-900">
                            {chatUnread > 99 ? '99+' : chatUnread}
                        </span>
                    )}
                </span>
                <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs' : 'opacity-100 max-w-xs'}`}>
                    {item.name}
                </span>
                {isActive && (
                    <motion.div layoutId="activeNavPanel" className={`absolute left-0 w-1 h-6 bg-emerald-600 dark:bg-emerald-500 rounded-r-full transition-opacity duration-300 ${sidebarCollapsed ? 'opacity-100 md:opacity-0 md:group-hover/sidebar:opacity-100' : 'opacity-100'}`} />
                )}
              </>
            )}
          </NavLink>
        );
        })}
      </nav>

      <div className="p-3 mt-auto shrink-0 border-t border-slate-100 dark:border-slate-800/80">
        <button 
          onClick={onLogout}
          className="w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-bold text-slate-500 hover:bg-rose-50 hover:text-rose-600 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-400 transition-colors group/logout"
        >
          <LogOut className="w-5 h-5 shrink-0 text-slate-400 group-hover/logout:text-rose-500 dark:group-hover/logout:text-rose-400" />
          <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs' : 'opacity-100 max-w-xs'}`}>
              End Session
          </span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen w-full bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-sans overflow-hidden transition-colors relative z-0">
      
      {/* Absolute Ambient Background SVG */}
      <div className="absolute inset-0 z-[-1] opacity-[0.03] dark:opacity-[0.05] pointer-events-none text-emerald-500 mix-blend-multiply dark:mix-blend-screen" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M20 20.5V18H0v-2h20v-2H0v-2h20v-2H0V8h20V6H0V4h20V2H0V0h22v20h2V0h2v20h2V0h2v20h2V0h2v20h2V0h2v20h2v2H20v-1.5zM0 20h2v20H0V20zm4 0h2v20H4V20zm4 0h2v20H8V20zm4 0h2v20h-2V20zm4 0h2v20h-2V20zm4 4h20v2H20v-2zm0 4h20v2H20v-2zm0 4h20v2H20v-2zm0 4h20v2H20v-2z' fill='currentColor' fill-opacity='1' fill-rule='evenodd'/%3E%3C/svg%3E")`}}></div>

      {/* Sidebar Desktop */}
      <aside className={`hidden md:flex flex-col bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-r border-slate-200 dark:border-slate-800 transition-[width] duration-300 ease-in-out shrink-0 z-50 group/sidebar ${sidebarCollapsed ? 'w-20 hover:w-64 shadow-2xl' : 'w-64'}`}>
        {sidebarContent}
      </aside>

      {/* Sidebar Mobile */}
      <AnimatePresence>
          {mobileMenuOpen && (
              <motion.div key="backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileMenuOpen(false)} className="md:hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-40" />
          )}
          {mobileMenuOpen && (
              <motion.aside key="sidebar" initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.3 }} className="md:hidden fixed inset-y-0 left-0 w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shadow-2xl">
                  {sidebarContent}
              </motion.aside>
          )}
      </AnimatePresence>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        {/* Top Header Placeholder */}
        <header className="h-16 flex items-center justify-between px-6 bg-white/70 dark:bg-slate-900/70 backdrop-blur-md border-b border-slate-200 dark:border-slate-800/80 sticky top-0 z-30 w-full transition-colors">
          <div className="flex items-center gap-4">
            <button onClick={() => setMobileMenuOpen(true)} data-tour="mobile-menu-button" className="md:hidden p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">
              <Menu size={20} />
            </button>
            {/* Replays the tour for whichever page is showing. */}
            <button
              onClick={walkthrough.restart}
              title={tourLabel ? `Replay the ${tourLabel} walkthrough` : 'Replay the portal walkthrough'}
              aria-label={tourLabel ? `Replay the ${tourLabel} walkthrough` : 'Replay the portal walkthrough'}
              className="p-2 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 rounded-lg hover:bg-emerald-50 dark:hover:bg-slate-800 transition-colors"
            >
              <HelpCircle size={18} />
            </button>
            <h1 className="text-lg font-black text-slate-800 dark:text-slate-100 hidden sm:block tracking-tight">{mentorName ? `${mentorName}` : `Panel ${panelId}`} — Mid Term Evaluation</h1>
            <span className="px-2.5 py-1 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-xs font-black border border-emerald-200 dark:border-emerald-500/30">
              Active Session
            </span>
          </div>

          {/* Global filters. The global search input that used to sit here was
              removed; per-page search boxes remain the way to find records. */}
          <div className="flex flex-1 min-w-[260px] items-center justify-end gap-2 sm:gap-3 mr-4">
              <div className="flex items-center justify-end">
                  <div className="hidden lg:flex items-center gap-2 rounded-full border border-slate-200/70 dark:border-slate-700/70 bg-slate-100/60 dark:bg-slate-800/50 px-3 py-1 shadow-inner">
                   <Filter className="w-4 h-4 text-slate-400 shrink-0" />
                   <select
                       value={filters.semesterId || 'all'}
                       onChange={(event) => updateFilter('semesterId', event.target.value)}
                       className="max-w-[240px] truncate bg-transparent text-xs font-bold text-slate-600 dark:text-slate-300 outline-none cursor-pointer [&>option]:bg-white [&>option]:dark:bg-slate-800 [&>option]:text-slate-700 [&>option]:dark:text-slate-200"
                   >
                       <option value="all">All Active Semesters</option>
                       {semesterOptions.map((semester) => (
                           <option key={semester.id} value={semester.id}>{semester.label}</option>
                       ))}
                   </select>
                   {filters.semesterId && filters.semesterId !== 'all' && (
                       <button
                           type="button"
                           onClick={() => updateFilter('semesterId', 'all')}
                           title="Reset filter"
                           className="p-1 text-slate-400 hover:text-rose-500 font-bold transition-colors"
                       >
                           <RotateCcw className="w-3.5 h-3.5" />
                       </button>
                   )}
               </div>
              </div>
          </div>

          <div className="flex items-center gap-4 text-slate-500 dark:text-slate-400 relative">
            <ThemeToggle />
            
            {/* Notifications Toggle (Panel) */}
            <div className="relative">
              <button 
                onClick={() => { setIsNotificationsOpen(!isNotificationsOpen); setIsProfileOpen(false); }}
                className="relative p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-all active:scale-95"
              >
                <Bell size={20} />
                {alerts.length > 0 && (
                  <span className="absolute top-1.5 right-2 w-2 h-2 bg-amber-500 rounded-full border-2 border-white dark:border-slate-900"></span>
                )}
              </button>

              <AnimatePresence>
                {isNotificationsOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setIsNotificationsOpen(false)}></div>
                    <motion.div 
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 10, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className="absolute right-0 mt-3 w-80 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 rounded-2xl shadow-xl z-50 overflow-hidden"
                    >
                      <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/20">
                        <h3 className="font-bold text-slate-800 dark:text-slate-100">Live Updates</h3>
                        <span className="text-xs font-bold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-2 py-0.5 rounded">{alerts.length} Alert{alerts.length === 1 ? '' : 's'}</span>
                      </div>
                      <div className="max-h-[300px] overflow-y-auto p-2">
                        {alerts.length === 0 ? (
                          <div className="p-3 text-sm text-slate-500 dark:text-slate-400">No active alerts.</div>
                        ) : (
                          alerts.map((alert) => (
                            <div key={alert.id} className={`p-3 hover:bg-slate-50 dark:hover:bg-slate-700/30 rounded-xl transition-colors cursor-pointer border border-transparent hover:border-slate-100 dark:hover:border-slate-700/50 group ${alert.alert_type === 'reschedule' ? 'bg-emerald-50/50 dark:bg-emerald-500/5' : ''}`}>
                               <p className="text-sm font-bold text-slate-800 dark:text-slate-200 group-hover:text-emerald-600 dark:group-hover:text-emerald-400 flex items-center gap-1">
                                 <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${alert.alert_type === 'reschedule' ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
                                 {cleanUUIDsFromText(alert.title)}
                               </p>
                               {alert.body && <p className="text-xs font-medium text-slate-500 mt-0.5">{cleanUUIDsFromText(alert.body)}</p>}
                               <p className="text-[10px] text-slate-400 font-bold mt-2">{new Date(alert.created_at).toLocaleString()}</p>
                            </div>
                          ))
                        )}
                      </div>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>

            {/* Profile Dropdown Toggle (Panel) */}
            <div className="relative">
              <div 
                onClick={() => { setIsProfileOpen(!isProfileOpen); setIsNotificationsOpen(false); }}
                className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-500/20 border-2 border-emerald-200 dark:border-emerald-500/50 flex items-center justify-center overflow-hidden shadow-sm shadow-emerald-500/20 cursor-pointer hover:ring-2 ring-emerald-500 ring-offset-2 dark:ring-offset-slate-900 transition-all select-none"
              >
                <span className="text-emerald-700 dark:text-emerald-400 font-black text-xs pointer-events-none">{panelBadgeText}</span>
              </div>

              <AnimatePresence>
                {isProfileOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setIsProfileOpen(false)}></div>
                    <motion.div 
                      initial={{ opacity: 0, y: 10, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 10, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className="absolute right-0 mt-3 w-64 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700/80 rounded-2xl shadow-xl z-50 overflow-hidden"
                    >
                      <div className="p-5 border-b border-emerald-100 dark:border-emerald-500/20 bg-gradient-to-br from-emerald-50 to-white dark:from-emerald-900/20 dark:to-slate-800">
                        <div className="flex gap-4 items-center">
                          <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center border-2 border-emerald-300 dark:border-emerald-500/50">
                             <span className="text-emerald-700 dark:text-emerald-400 font-black tracking-widest text-lg">{panelBadgeText}</span>
                          </div>
                        <div>
                            <p className="font-bold text-slate-800 dark:text-slate-100">{mentorName || `Panel ${panelId}`}</p>
                            <p className="text-xs font-medium text-slate-500">{mentorName ? `Panel ID: ${panelId}` : 'Mid-Term Evaluators'}</p>
                          </div>
                        </div>
                      </div>
                      <div className="p-2">
                        <NavLink to="/panel/parameters" className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-300 font-medium text-sm transition-colors" onClick={() => setIsProfileOpen(false)}>
                          <BookOpen size={16} className="text-slate-400" /> Scoring Guidelines
                        </NavLink>
                        <div className="h-px bg-slate-100 dark:bg-slate-700/50 my-1 mx-2"></div>
                        <button onClick={onLogout} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 font-bold text-sm transition-colors">
                          <LogOut size={16} /> End Session Securely
                        </button>
                      </div>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        {/* Scrollable Main Area with Framer Motion Page Transitions */}
        <main className="flex-1 overflow-auto p-4 md:p-8 z-0 w-full relative">
          {/* Subtle glowing orb in background */}
          <div className="absolute top-[10%] left-[20%] w-[500px] h-[500px] bg-emerald-500/10 dark:bg-emerald-500/5 rounded-full blur-[120px] pointer-events-none z-[-1]"></div>

          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="h-full w-full"
            >
              <Outlet key={filters.semesterId} />
            </motion.div>
          </AnimatePresence>
        </main>
        
        <ReminderPopup />
        <AlertNotifications />

        {/* Global Google Meet Slot Extension Modal */}
        <AnimatePresence>
          {globalExtendModalOpen && activeSession && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300">
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
                      {activeSession?.meet_link ? 'Google Meet Evaluation Ending Soon' : 'Evaluation Ending Soon'}
                    </h3>
                    <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
                      {activeSession?.meet_link 
                        ? `The allotted time for ${activeSession.team_name}'s Google Meet evaluation is running out. Do you want to extend the meeting duration? Subsequent slots will automatically shift.`
                        : `The allotted time for ${activeSession.team_name || 'this group'}'s slot is running out. Do you want to extend the slot duration? Subsequent slots will automatically shift.`
                      }
                    </p>
                  </div>
                </div>

                <div className="bg-slate-50 dark:bg-slate-900/30 rounded-2xl p-4 border border-slate-100 dark:border-slate-700/50 mb-6 flex justify-between items-center text-sm font-semibold">
                  <span className="text-slate-500">Remaining Evaluation Time:</span>
                  <span className={`font-mono text-base ${
                    sessionTimeLeft <= 300 ? 'text-rose-600 dark:text-rose-400 font-bold'
                    : 'text-amber-600 dark:text-amber-400'
                  }`}>
                    {formatGlobalTime(sessionTimeLeft)}
                  </span>
                </div>

                <div className="space-y-3">
                  <p className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                    Select Extension Duration
                  </p>
                  <div className="grid grid-cols-3 gap-2.5">
                    <button
                      disabled={isExtendingGlobal}
                      onClick={() => handleGlobalExtendSlot(5)}
                      className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-emerald-500 dark:hover:border-emerald-500 hover:bg-emerald-50/20 dark:hover:bg-emerald-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                    >
                      <span className="text-lg text-emerald-650 dark:text-emerald-400">+5</span>
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                    </button>
                    <button
                      disabled={isExtendingGlobal}
                      onClick={() => handleGlobalExtendSlot(10)}
                      className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-emerald-500 dark:hover:border-emerald-500 hover:bg-emerald-50/20 dark:hover:bg-emerald-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                    >
                      <span className="text-lg text-emerald-650 dark:text-emerald-400">+10</span>
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                    </button>
                    <button
                      disabled={isExtendingGlobal}
                      onClick={() => handleGlobalExtendSlot(15)}
                      className="flex flex-col items-center justify-center p-3 rounded-2xl border border-slate-200 dark:border-slate-700 hover:border-emerald-500 dark:hover:border-emerald-500 hover:bg-emerald-50/20 dark:hover:bg-emerald-500/10 transition-all font-bold active:scale-95 disabled:opacity-50"
                    >
                      <span className="text-lg text-emerald-650 dark:text-emerald-400">+15</span>
                      <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">Mins</span>
                    </button>
                  </div>

                  <div className="flex gap-3 mt-6 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                    <button
                      disabled={isExtendingGlobal}
                      onClick={() => {
                        setGlobalExtendModalOpen(false);
                        setGlobalExtendModalShown(true);
                      }}
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

      {/* Portals into document.body so the sidebar's stacking context cannot
          trap the spotlight behind it. */}
      <WalkthroughOverlay {...walkthrough} />
    </div>
  );
};

export default PanelLayout;
