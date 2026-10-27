import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    LayoutDashboard, Users, Settings, FileText, 
    ShieldCheck, UserCircle, Calendar, Award, 
    Mail, Shield, Activity, FolderSync, Eye, UserMinus, CheckSquare, Target, Github, BarChart3,
    Menu, ChevronLeft, ChevronRight, LogOut, UserPlus
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChatUnread } from '../hooks/useChatUnread';

import { PROCKSI_CHAT_ENABLED } from '../config/features';

const navItems = [
    { id: '/admin/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { id: '/admin/students', icon: Users, label: 'Students' },
    { id: '/admin/semester-settings', icon: Settings, label: 'Semester Settings' },
    { id: '/admin/proposals', icon: FileText, label: 'Proposals' },
    { id: '/admin/teams', icon: ShieldCheck, label: 'Teams' },
    { id: '/admin/mentor-master', icon: UserCircle, label: 'Mentors' },
    { id: '/admin/repo-analysis', icon: Github, label: 'Repo Analysis' },
    { id: '/admin/milestones', icon: CheckSquare, label: 'Synopsis Submissions' },
    { id: '/admin/analysis', icon: BarChart3, label: 'Analysis' },
    { id: '/admin/project-allocations', icon: FolderSync, label: 'Project Allocation' },
    { id: '/admin/mentors', icon: UserCircle, label: 'Mentor Allocation' },
    { id: '/admin/schedule', icon: Calendar, label: 'Presentation Schedule' },
    { id: '/admin/presentation-cycles', icon: Target, label: 'Presentation Cycles' },
    { id: '/admin/procksi-chat', icon: UserPlus, label: 'Procksi Chat' },
    { id: '/admin/evaluations', icon: Activity, label: 'Evaluations' },
    { id: '/admin/results', icon: Award, label: 'Results' },
    { id: '/admin/communication', icon: Mail, label: 'Communication' },
    { id: '/admin/views', icon: Eye, label: 'Views' },
    { id: '/admin/absent-students', icon: UserMinus, label: 'Absent Students' },
    { id: '/admin/extra-activities', icon: Award, label: 'Extra Activities' },
    { id: '/admin/governance', icon: Shield, label: 'Governance' },
];

export const Sidebar = ({ 
    sidebarCollapsed, setSidebarCollapsed, 
    mobileMenuOpen, setMobileMenuOpen, 
    handleLogout, admin = { name: "System Admin" } 
}) => {
    const location = useLocation();
    const navigate = useNavigate();
    const activeTab = location.pathname;
    const chatUnread = useChatUnread();

    const sidebarContent = (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="p-4 flex items-center justify-between">
                <div className={`flex items-center transition-all duration-300 overflow-hidden ${sidebarCollapsed ? 'w-auto opacity-100 md:w-0 md:opacity-0 md:group-hover/sidebar:w-[150px] md:group-hover/sidebar:opacity-100' : 'w-[150px] opacity-100'}`}>
                    <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center shrink-0 mr-3 shadow-md border border-slate-200 dark:border-slate-700/50 overflow-hidden">
                      <img src="/procksi-mark.png" alt="Procksi" className="w-full h-full object-contain p-0.5" onError={(e) => { e.target.style.display = 'none' }} />
                    </div>
                    <div className="flex flex-col">
                        <span className="font-bold text-sm text-slate-900 dark:text-white tracking-tight whitespace-nowrap leading-tight">Admin Portal</span>
                        <span className="text-[10px] text-slate-500 dark:text-slate-400 font-semibold tracking-wider">PROCKSI</span>
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

            <div className={`px-4 transition-all duration-300 overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-h-20 mt-6 mb-4 md:opacity-0 md:max-h-0 md:mt-0 md:mb-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-h-20 md:group-hover/sidebar:mt-6 md:group-hover/sidebar:mb-4' : 'opacity-100 max-h-20 mt-6 mb-4'}`}>
                <div className="bg-slate-100 dark:bg-slate-800 p-3 rounded-xl border border-slate-200 dark:border-slate-700/50">
                    <p className="text-xs text-slate-500 dark:text-slate-400 uppercase font-semibold tracking-wider mb-1">Administrator</p>
                    <p className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{admin.name}</p>
                </div>
            </div>

            <nav className="flex-1 px-3 space-y-1 mt-2 overflow-y-auto overflow-x-hidden pb-4 scrollbar-hide">
                {navItems.map(item => {
                    const Icon = item.icon;
                    const isActive = activeTab === item.id || activeTab.startsWith(item.id + '/');
                    // Procksi Chat is disabled: greyed, inert, and no unread badge.
                    const isDisabled = item.id === '/admin/procksi-chat' && !PROCKSI_CHAT_ENABLED;
                    return (
                        <button key={item.id} disabled={isDisabled} aria-disabled={isDisabled}
                            title={isDisabled ? 'Procksi Chat is currently unavailable' : undefined}
                            onClick={() => { if (isDisabled) return; navigate(item.id); setMobileMenuOpen(false); }}
                            className={`w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-medium transition-all group relative ${isDisabled
                                ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-slate-600'
                                : isActive ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-slate-200'}`}>
                            <span className="relative shrink-0">
                                <Icon className={`w-5 h-5 transition-colors ${isActive ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300'}`} />
                                {item.id === '/admin/procksi-chat' && PROCKSI_CHAT_ENABLED && chatUnread > 0 && (
                                    // Pinned to the icon rather than the row end, so the count
                                    // stays visible when the rail is collapsed to icons only.
                                    <span aria-label={`${chatUnread} unread`}
                                        className="absolute -top-2 -right-2 min-w-[1.05rem] h-[1.05rem] px-1 rounded-full bg-indigo-600 text-white text-[9px] font-black flex items-center justify-center tabular-nums ring-2 ring-white dark:ring-slate-900">
                                        {chatUnread > 99 ? '99+' : chatUnread}
                                    </span>
                                )}
                            </span>
                            <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs' : 'opacity-100 max-w-xs'}`}>
                                {item.label}
                            </span>
                            {isActive && (
                                <motion.div layoutId="activeNav" className={`absolute left-0 w-1 h-6 bg-indigo-600 dark:bg-indigo-500 rounded-r-full transition-opacity duration-300 ${sidebarCollapsed ? 'opacity-100 md:opacity-0 md:group-hover/sidebar:opacity-100' : 'opacity-100'}`} />
                            )}
                        </button>
                    );
                })}
            </nav>

            <div className="p-3 mt-auto shrink-0 border-t border-slate-100 dark:border-slate-800/80">
                <button onClick={handleLogout} className="w-full flex items-center py-2.5 px-3 rounded-xl text-sm font-medium text-slate-500 hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors group/logout">
                    <LogOut className="w-5 h-5 shrink-0 text-slate-400 group-hover/logout:text-red-500 dark:group-hover/logout:text-red-400" />
                    <span className={`ml-3 transition-all duration-300 whitespace-nowrap overflow-hidden ${sidebarCollapsed ? 'opacity-100 max-w-xs md:opacity-0 md:max-w-0 md:group-hover/sidebar:opacity-100 md:group-hover/sidebar:max-w-xs' : 'opacity-100 max-w-xs'}`}>
                        Sign Out
                    </span>
                </button>
            </div>
        </div>
    );

    return (
        <>
            <aside className={`hidden md:flex flex-col bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-[width] duration-300 ease-in-out shrink-0 z-50 group/sidebar ${sidebarCollapsed ? 'w-20 hover:w-64' : 'w-64'}`}>
                {sidebarContent}
            </aside>
            <AnimatePresence>
                {mobileMenuOpen && (
                    <motion.div key="backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileMenuOpen(false)} className="md:hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40" />
                )}
                {mobileMenuOpen && (
                    <motion.aside key="sidebar" initial={{ x: '-100%' }} animate={{ x: 0 }} exit={{ x: '-100%' }} transition={{ type: 'spring', bounce: 0, duration: 0.3 }} className="md:hidden fixed inset-y-0 left-0 w-72 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 z-50 shadow-2xl">
                        {sidebarContent}
                    </motion.aside>
                )}
            </AnimatePresence>
        </>
    );
};

export default Sidebar;
