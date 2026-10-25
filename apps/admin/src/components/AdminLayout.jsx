import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopNav from './TopNav';
import { AnimatePresence, motion } from 'framer-motion';
import { ShieldAlert, X } from 'lucide-react';
import { useGlobalFilters } from '../context/useGlobalFilters';

export const AdminLayout = ({ onLogout, adminUser }) => {
    const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    // Read the stored preference during the first render instead of rendering
    // light and correcting it from the effect below.
    const [isDark, setIsDark] = useState(() => localStorage.getItem('pms-admin-theme') === 'dark');
    const [freezePopupOpen, setFreezePopupOpen] = useState(false);
    useEffect(() => {
        document.documentElement.classList.toggle('dark', isDark);
    }, [isDark]);

    const navigate = useNavigate();
    const { filters } = useGlobalFilters();

    useEffect(() => {
        // Seed the default on a first visit. The class itself is applied by the
        // effect below, which tracks isDark rather than setting it.
        if (!localStorage.getItem('pms-admin-theme')) {
            localStorage.setItem('pms-admin-theme', 'light');
        }

        const handleFreezeError = () => {
            setFreezePopupOpen(true);
        };
        window.addEventListener('system-frozen-error', handleFreezeError);
        
        return () => window.removeEventListener('system-frozen-error', handleFreezeError);
    }, []);

    const toggleTheme = () => {
        setIsDark(!isDark);
        if (!isDark) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('pms-admin-theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('pms-admin-theme', 'light');
        }
    };

    const admin = React.useMemo(() => {
        const email = adminUser?.email || '';
        const profileName = adminUser?.user_metadata?.full_name || adminUser?.user_metadata?.name;
        const fallbackName = email ? email.split('@')[0] : 'System Admin';

        return {
            name: profileName || fallbackName,
            email,
        };
    }, [adminUser]);

    const handleLogout = async () => {
        if (onLogout) {
            await onLogout();
        }
        navigate('/admin/login');
    };

    return (
        <div className="flex h-screen bg-slate-50 dark:bg-slate-900 font-sans overflow-hidden transition-colors selection:bg-indigo-500/30 relative z-0">
            {/* Global Decorative SVG Pattern */}
            <div className="absolute inset-0 z-[-1] opacity-[0.04] dark:opacity-[0.03] pointer-events-none" 
                 style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%236366f1' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")` }}>
            </div>
            {/* Ambient Lighting Orbs */}
            <div className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/10 dark:bg-indigo-500/5 blur-[120px] pointer-events-none z-[-1]"></div>
            <div className="absolute bottom-[-10%] right-[-5%] w-[40%] h-[40%] rounded-full bg-purple-500/10 dark:bg-purple-500/5 blur-[100px] pointer-events-none z-[-1]"></div>

            <Sidebar 
                sidebarCollapsed={sidebarCollapsed} 
                setSidebarCollapsed={setSidebarCollapsed}
                mobileMenuOpen={mobileMenuOpen}
                setMobileMenuOpen={setMobileMenuOpen}
                handleLogout={handleLogout}
                admin={admin}
            />
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                <TopNav 
                    isDark={isDark}
                    toggleTheme={toggleTheme}
                    setMobileMenuOpen={setMobileMenuOpen}
                    handleLogout={handleLogout}
                    adminUser={adminUser}
                />
                <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 scroll-smooth w-full">
                    <div className="max-w-7xl mx-auto pb-20 relative px-2">
                        <Outlet key={filters.semesterId} />
                    </div>
                </main>
            </div>
            
            <AnimatePresence>
                {freezePopupOpen && (
                    <motion.div 
                        initial={{ opacity: 0 }} 
                        animate={{ opacity: 1 }} 
                        exit={{ opacity: 0 }} 
                        className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
                    >
                        <motion.div 
                            initial={{ scale: 0.95, y: 20 }} 
                            animate={{ scale: 1, y: 0 }} 
                            exit={{ scale: 0.95, y: 20 }} 
                            className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl max-w-sm w-full p-6 border border-red-100 dark:border-red-900/50 relative overflow-hidden"
                        >
                            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-red-500 to-rose-600"></div>
                            <button onClick={() => setFreezePopupOpen(false)} className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                            <div className="flex flex-col items-center text-center mt-2">
                                <div className="w-16 h-16 bg-red-50 dark:bg-red-500/10 text-red-500 rounded-full flex items-center justify-center mb-4">
                                    <ShieldAlert className="w-8 h-8" />
                                </div>
                                <h3 className="text-xl font-black text-slate-800 dark:text-white mb-2">Protocol Deactivated</h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                                    The system is currently frozen by an Administrator. All data modifications are strictly prohibited.
                                </p>
                                <button onClick={() => setFreezePopupOpen(false)} className="w-full py-3 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-white rounded-xl font-bold text-sm transition-colors">
                                    Acknowledge
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default AdminLayout;
