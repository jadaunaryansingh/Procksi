import React from 'react';
import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Users, LayoutDashboard, MessageSquare, LogOut,
    Calendar, Menu, ChevronLeft, ChevronRight,
    Bell, UserCircle, Presentation, ClipboardCheck, Award, Activity, ClipboardList
} from 'lucide-react';

export const Sidebar = ({
    user,
    sidebarCollapsed,
    setSidebarCollapsed,
    mobileMenuOpen,
    setMobileMenuOpen,
    handleLogout
}) => {
    const navItems = [
        { id: 'overview', icon: LayoutDashboard, label: 'Dashboard', path: '/student/dashboard' },
        { id: 'team', icon: Users, label: 'Team', path: '/student/team' },
        { id: 'preferences', icon: ClipboardList, label: 'Project Preferences', path: '/student/preferences' },
        { id: 'milestones', icon: Award, label: 'Milestones', path: '/student/milestones' },
        { id: 'mentor', icon: UserCircle, label: 'Mentor', path: '/student/mentor' },
        { id: 'presentations', icon: Presentation, label: 'Presentation Schedule', path: '/student/presentations' },
        { id: 'evaluations', icon: ClipboardCheck, label: 'Evaluation', path: '/student/evaluations' },
        { id: 'results', icon: ClipboardCheck, label: 'Results', path: '/student/results' },
        { id: 'feedback', icon: MessageSquare, label: 'Feedback Timeline', path: '/student/feedback' },
        { id: 'activities', icon: Activity, label: 'Extra Activities', path: '/student/activities' },
    ];

    const sidebarContent = (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="p-4 flex items-center justify-between">
                <div className={`flex items-center transition-all duration-300 overflow-hidden ${sidebarCollapsed
                    ? 'w-auto opacity-100 md:w-0 md:opacity-0 md:group-hover/sidebar:w-[150px] md:group-hover/sidebar:opacity-100'
                    : 'w-[150px] opacity-100'
                    }`}>
                    <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-8 h-8 object-contain shrink-0 mr-3 drop-shadow-sm" />
                    <div className="flex flex-col">
                        <span className="font-bold text-sm text-slate-900 dark:text-white tracking-tight whitespace-nowrap leading-tight">GLA University</span>
                        <span className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold tracking-wider">PMS PORTAL</span>
                    </div>
                </div>
                <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className="hidden md:flex p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors shrink-0">
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

            <div className={`px-4 transition-all duration-300 overflow-hidden ${sidebarCollapsed
                ? 'opacity-100 max-h-20 mt-6 mb-4 md:opacity-0 md:max-h-0 md:mt-0 md:mb-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-h-20 md:group-hover/sidebar:mt-6 md:group-hover/sidebar:mb-4'
                : 'opacity-100 max-h-20 mt-6 mb-4'
                }`}>
                <div className="bg-slate-100 dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700/50">
                    <p className="text-xs text-slate-500 dark:text-slate-400 uppercase font-semibold tracking-wider mb-1">Student</p>
                    <p className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{user?.name}</p>
                </div>
            </div>

            <nav className="flex-1 px-3 space-y-1 mt-2 overflow-y-auto">
                {navItems.map(item => {
                    const Icon = item.icon;
                    return (
                        <NavLink
                            key={item.id}
                            to={item.path}
                            onClick={() => setMobileMenuOpen(false)}
                            className={({ isActive }) => `w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-medium transition-all group relative
                                ${isActive ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'}`}
                        >
                            {({ isActive }) => (
                                <>
                                    <Icon className={`w-5 h-5 shrink-0 transition-colors ${isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300'}`} />
                                    <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed
                                        ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs'
                                        : 'opacity-100 max-w-xs'
                                        }`}>
                                        {item.label}
                                    </span>
                                    {isActive && (
                                        <motion.div layoutId="activeNav" className={`absolute left-0 w-1 h-6 bg-indigo-600 dark:bg-indigo-500 rounded-r-full transition-opacity duration-300 ${sidebarCollapsed ? 'opacity-100 md:opacity-0 md:group-hover/sidebar:opacity-100' : 'opacity-100'}`} />
                                    )}
                                </>
                            )}
                        </NavLink>
                    );
                })}
            </nav>

            <div className="p-3 mt-auto">
                <button onClick={handleLogout} className="w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-medium text-slate-500 hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors group/logout">
                    <LogOut className="w-5 h-5 shrink-0 text-slate-400 group-hover/logout:text-red-500 dark:group-hover/logout:text-red-400" />
                    <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed
                        ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs'
                        : 'opacity-100 max-w-xs'
                        }`}>
                        Sign Out
                    </span>
                </button>
            </div>
        </div>
    );

    return (
        <>
            {/* Desktop Sidebar (CSS Hover-Expandable) */}
            <aside className={`hidden md:flex flex-col bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-[width] duration-300 ease-in-out shrink-0 z-50 group/sidebar ${sidebarCollapsed ? 'w-20 hover:w-64' : 'w-64'}`}>
                {sidebarContent}
            </aside>

            {/* Mobile Sidebar */}
            <AnimatePresence>
                {mobileMenuOpen && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileMenuOpen(false)}
                            className="md:hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40" />
                        <motion.aside initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.3 }}
                            className="md:hidden fixed inset-y-0 left-0 w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shadow-2xl">
                            {sidebarContent}
                        </motion.aside>
                    </>
                )}
            </AnimatePresence>
        </>
    );
};

export default Sidebar;
