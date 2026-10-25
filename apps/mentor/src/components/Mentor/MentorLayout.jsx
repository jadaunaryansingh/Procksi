import React, { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { Home, Users, BarChart2, BrainCircuit, Bell, Presentation, History as HistoryIcon, FileSignature, LogOut, Menu, ChevronLeft, ChevronRight, Filter, RotateCcw, Award, User, MessageSquare, HelpCircle } from 'lucide-react';
import { useChatUnread } from '../../hooks/useChatUnread';
import { motion, AnimatePresence } from 'framer-motion';
import ThemeToggle from '../ThemeToggle';
import { useAuth } from '../../context/useAuth';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { usePmsChatEnabled } from '../../hooks/usePmsChatEnabled';
import { useWalkthrough } from '../../hooks/useWalkthrough';
import WalkthroughOverlay from '../Walkthrough/WalkthroughOverlay';

const MentorLayout = () => {
  const { user, logout: onLogout } = useAuth();
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pmsChatEnabled = usePmsChatEnabled();
  const walkthrough = useWalkthrough();

  const {
    filters,
    semesterOptions,
    updateFilter,
  } = useGlobalFilters();

  // Dropdown States
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  const [alerts, setAlerts] = useState([]);
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    if (user) {
      Promise.all([
          api.get('/alerts').catch(() => ({ data: [] })),
          api.get('/notifications').catch(() => ({ data: [] }))
      ]).then(([alertsRes, notifsRes]) => {
          const unackAlerts = (alertsRes.data || []).filter(a => !a.acknowledged);
          const unreadNotifs = (notifsRes.data || []).filter(n => !n.read);
          setAlerts(unackAlerts);
          setNotifications(unreadNotifs);
      }).catch((err) => {
          console.error('Failed to load alerts/notifications:', err);
      });
    }
  }, [user]);

  const handleMarkAllAsRead = async () => {
    try {
      await Promise.all([
          ...alerts.map(a => api.patch(`/alerts/${a.id}/acknowledge`).catch(() => {})),
          api.post('/notifications/read-all').catch(() => {})
      ]);
      setAlerts([]);
      setNotifications([]);
    } catch (err) {
      // The individual calls above already swallow their own failures, so this
      // only fires on an unexpected error — surface it rather than losing it.
      console.error('Failed to mark alerts/notifications as read:', err);
    }
  };

  const combinedNotifications = [
      ...alerts.map(a => ({ id: `alert-${a.id}`, title: a.title, message: a.description, time: a.time || new Date().toLocaleString(), type: 'alert', original_id: a.id })),
      ...notifications.map(n => ({ id: `notif-${n.id}`, title: n.title, message: n.message, time: new Date(n.created_at).toLocaleString(), type: 'notification', original_id: n.id }))
  ].sort((a, b) => new Date(b.time) - new Date(a.time));

  const chatUnread = useChatUnread();
  const navItems = [
    { name: 'Dashboard', path: '/mentor', icon: Home, end: true },
    { name: 'My Teams', path: '/mentor/teams', icon: Users },
    { name: 'GitHub Analytics Hub', path: '/mentor/analyzer', icon: BrainCircuit },
    { name: 'Synopsis Submissions', path: '/mentor/milestones', icon: Award },
    { name: 'Presentations', path: '/mentor/presentations', icon: Presentation },
    { name: 'PMS-Chat', path: '/mentor/pms-chat', icon: MessageSquare },
    { name: 'Evaluations', path: '/mentor/evaluation', icon: FileSignature },
    { name: 'History', path: '/mentor/history', icon: HistoryIcon },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto overflow-x-hidden relative z-10">
      <div className="p-4 flex items-center justify-between">
        <div className={`flex items-center transition-all duration-300 overflow-hidden ${sidebarCollapsed ? 'w-auto opacity-100 md:w-0 md:opacity-0 md:group-hover/sidebar:w-[150px] md:group-hover/sidebar:opacity-100' : 'w-[150px] opacity-100'}`}>
          <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center shadow-md border border-slate-200 dark:border-slate-700/50 overflow-hidden shrink-0 mr-3">
            <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-full h-full object-contain p-0.5" onError={(e) => { e.target.style.display = 'none' }} />
          </div>
          <div className="flex flex-col">
              <span className="font-bold text-sm text-slate-900 dark:text-white tracking-tight whitespace-nowrap leading-tight">Mentor Portal</span>
              <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold tracking-wider">GLA UNIVERSITY</span>
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
              <p className="text-xs text-slate-500 dark:text-slate-400 uppercase font-bold tracking-wider mb-1">Assigned Profile</p>
              <p className="text-sm font-black text-slate-800 dark:text-slate-100 truncate">{user?.name || '—'}</p>
          </div>
      </div>

      <nav data-tour="sidebar-nav" className="shrink-0 px-3 space-y-1 mt-2 overflow-x-hidden pb-4">
        {navItems.map((item) => {
          // PMS-Chat is disabled: greyed, inert, and no unread badge.
          const isDisabled = item.path === '/mentor/pms-chat' && !pmsChatEnabled;
          return (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            data-tour={`nav-${item.path.split('/').pop()}`}
            aria-disabled={isDisabled}
            tabIndex={isDisabled ? -1 : undefined}
            title={isDisabled ? 'PMS-Chat is currently unavailable' : undefined}
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
                    {item.path.endsWith('/pms-chat') && pmsChatEnabled && chatUnread > 0 && (
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
                    <motion.div layoutId="activeNavMentor" className={`absolute left-0 w-1 h-6 bg-emerald-600 dark:bg-emerald-500 rounded-r-full transition-opacity duration-300 ${sidebarCollapsed ? 'opacity-100 md:opacity-0 md:group-hover/sidebar:opacity-100' : 'opacity-100'}`} />
                )}
              </>
            )}
          </NavLink>
        );
        })}
      </nav>

      <div className="px-3 pt-3 pb-6 shrink-0 border-t border-slate-100 dark:border-slate-800/80">
        <button 
          onClick={onLogout}
          className="w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-bold text-slate-500 hover:bg-rose-50 hover:text-rose-600 dark:text-slate-400 dark:hover:bg-rose-500/10 dark:hover:text-rose-400 transition-colors group/logout"
        >
          <LogOut className="w-5 h-5 shrink-0 text-slate-400 group-hover/logout:text-rose-500 dark:group-hover/logout:text-rose-400" />
          <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs' : 'opacity-100 max-w-xs'}`}>
              Secure Sign Out
          </span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen w-full bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white font-sans transition-colors relative z-0">
      
      {/* Absolute Ambient Background SVG */}
      <div className="absolute inset-0 z-[-1] opacity-[0.03] dark:opacity-[0.05] pointer-events-none" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%2310b981' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`}}></div>

      {/* Sidebar Desktop */}
      <aside className={`hidden md:flex flex-col bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-r border-slate-200 dark:border-slate-800 transition-[width] duration-300 ease-in-out shrink-0 z-50 group/sidebar sticky top-0 h-screen ${sidebarCollapsed ? 'w-20 hover:w-64 shadow-2xl' : 'w-64'}`}>
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
      <div className="flex-1 flex flex-col relative">
        {/* Top Header */}
        <header className="h-16 flex items-center justify-between px-6 bg-white/70 dark:bg-slate-900/70 backdrop-blur-md border-b border-slate-200 dark:border-slate-800/80 sticky top-0 z-30 w-full transition-colors">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileMenuOpen(true)} data-tour="mobile-menu-button" className="md:hidden p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">
              <Menu size={20} />
            </button>
            <h1 className="text-lg font-black text-slate-800 dark:text-slate-100 hidden sm:flex items-center gap-2 tracking-tight">
               <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Workflow Overview
            </h1>
            {/* Replay the first-login tour on demand. */}
            <button
              onClick={walkthrough.restart}
              title="Replay the portal walkthrough"
              aria-label="Replay the portal walkthrough"
              className="p-2 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 rounded-lg hover:bg-emerald-50 dark:hover:bg-slate-800 transition-colors"
            >
              <HelpCircle size={18} />
            </button>
          </div>

          {/* Global filters. The global search input that used to sit here was
              removed; per-page search boxes remain the way to find records. */}
          <div className="flex flex-1 min-w-[260px] items-center justify-end gap-2 sm:gap-3 mr-4">
              <div className="hidden lg:flex items-center gap-2 rounded-full border border-slate-200/70 dark:border-slate-700/70 bg-slate-100/60 dark:bg-slate-800/50 px-3 py-1 shadow-inner">
                  <Filter className="w-4 h-4 text-slate-400 shrink-0" />
                  <select
                      value={filters.semesterId || 'all'}
                      onChange={(event) => updateFilter('semesterId', event.target.value)}
                      className="max-w-[240px] truncate bg-transparent text-xs font-bold text-slate-600 dark:text-slate-300 outline-none cursor-pointer [&>option]:bg-white [&>option]:dark:bg-slate-800 [&>option]:text-slate-700 [&>option]:dark:text-slate-200"
                  >
                      <option value="all" className="bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200">All Active Semesters</option>
                      {semesterOptions.map((semester) => (
                          <option key={semester.id} value={semester.id} className="bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200">{semester.label}</option>
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

          <div className="flex items-center gap-4 text-slate-500 dark:text-slate-400 relative">
            <ThemeToggle />
            
            {/* Notifications Toggle */}
            <div className="relative">
              <button 
                onClick={() => { setIsNotificationsOpen(!isNotificationsOpen); setIsProfileOpen(false); }}
                className="relative p-2 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-all active:scale-95"
              >
                <Bell size={20} />
                {combinedNotifications.length > 0 && (
                  <span className="absolute top-1.5 right-2 w-2 h-2 bg-rose-500 rounded-full border-2 border-white dark:border-slate-900"></span>
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
                        <h3 className="font-bold text-slate-800 dark:text-slate-100">Notifications</h3>
                        {combinedNotifications.length > 0 && (
                          <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 rounded">{combinedNotifications.length} New</span>
                        )}
                      </div>
                      <div className="max-h-[300px] overflow-y-auto p-2">
                        {combinedNotifications.length === 0 ? (
                          <div className="p-8 text-center text-slate-400">
                            <Bell size={24} className="mx-auto mb-2 opacity-30" />
                            <p className="text-xs font-medium">No new notifications</p>
                          </div>
                        ) : (
                          combinedNotifications.map(a => (
                            <div key={a.id} className="p-3 hover:bg-slate-50 dark:hover:bg-slate-700/30 rounded-xl transition-colors cursor-pointer mb-1 border border-transparent hover:border-slate-100 dark:hover:border-slate-700/50 group">
                               <p className="text-sm font-bold text-slate-800 dark:text-slate-200 group-hover:text-emerald-600 dark:group-hover:text-emerald-400">{a.title}</p>
                               <p className="text-xs font-medium text-slate-500 mt-0.5">{a.message}</p>
                               <p className="text-[10px] text-slate-400 font-bold mt-2">{a.time}</p>
                            </div>
                          ))
                        )}
                      </div>
                      {combinedNotifications.length > 0 && (
                        <div className="p-3 border-t border-slate-100 dark:border-slate-700/50 text-center">
                          <button onClick={handleMarkAllAsRead} className="text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300">Mark all as read</button>
                        </div>
                      )}
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>

            {/* Profile Dropdown Toggle */}
            <div className="relative">
              <div 
                onClick={() => { setIsProfileOpen(!isProfileOpen); setIsNotificationsOpen(false); }}
                className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900 border-[1.5px] border-emerald-200 dark:border-emerald-700 flex items-center justify-center shadow-sm cursor-pointer hover:ring-2 ring-emerald-500 ring-offset-2 dark:ring-offset-slate-900 transition-all select-none"
              >
                <User className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
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
                      <div className="p-5 border-b border-slate-100 dark:border-slate-700/50 bg-gradient-to-br from-emerald-50/50 to-white dark:from-emerald-900/10 dark:to-slate-800">
                        <div className="flex gap-3 items-center">
                          <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900 border-2 border-white dark:border-slate-700 flex items-center justify-center shadow-sm">
                            <User className="w-6 h-6 text-emerald-600 dark:text-emerald-400" />
                          </div>
                          <div>
                            <p className="font-bold text-slate-800 dark:text-slate-100">{user?.name || '—'}</p>
                            <p className="text-xs font-medium text-slate-500">{user?.email || '—'}</p>
                          </div>
                        </div>
                      </div>
                      <div className="p-2">
                        <NavLink to="/mentor/profile" className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-300 font-medium text-sm transition-colors" onClick={() => setIsProfileOpen(false)}>
                          <FileSignature size={16} className="text-slate-400" /> Account Settings
                        </NavLink>
                        <div className="h-px bg-slate-100 dark:bg-slate-700/50 my-1 mx-2"></div>
                        <button onClick={onLogout} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10 text-rose-600 dark:text-rose-400 font-bold text-sm transition-colors">
                          <LogOut size={16} /> Sign Out Securely
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
        <main className="flex-1 p-4 md:p-6 w-full relative z-0 min-h-[calc(100vh-4rem)]">
          {/* Ambient Glowing Orbs Background */}
          <div className="fixed top-0 left-0 w-full h-full pointer-events-none overflow-hidden z-[-1]">
            <div className="absolute top-[-10%] left-[-10%] w-[40vw] h-[40vw] bg-emerald-500/10 dark:bg-emerald-500/5 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-lighten animate-pulse" style={{ animationDuration: '8s' }}></div>
            <div className="absolute top-[20%] right-[-10%] w-[35vw] h-[35vw] bg-teal-500/10 dark:bg-teal-500/5 rounded-full blur-[120px] mix-blend-multiply dark:mix-blend-lighten animate-pulse" style={{ animationDuration: '12s', animationDelay: '2s' }}></div>
            <div className="absolute bottom-[-10%] left-[20%] w-[50vw] h-[50vw] bg-emerald-400/10 dark:bg-emerald-400/5 rounded-full blur-[150px] mix-blend-multiply dark:mix-blend-lighten animate-pulse" style={{ animationDuration: '10s', animationDelay: '4s' }}></div>
          </div>
          
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
      </div>

      {/* Renders into document.body via a portal, so the sidebar's stacking
          context cannot trap the spotlight behind it. */}
      <WalkthroughOverlay {...walkthrough} />
    </div>
  );
};

export default MentorLayout;
