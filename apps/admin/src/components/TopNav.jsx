import React, { useEffect, useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Sun, Moon, Bell, Menu, User, Settings, LogOut, ExternalLink, X, Filter, RotateCcw, Shield, Trash2, Plus, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { getStoredSession } from '../lib/api';
import PresentationViewDropdown from './PresentationViewDropdown';
import { getApiBaseUrl } from '../lib/apiBase';
import { MASTER_ADMIN_EMAIL } from '../lib/emailPolicy';

export const TopNav = ({
    isDark,
    toggleTheme,
    setMobileMenuOpen,
    handleLogout,
    adminUser
}) => {
    const location = useLocation();
    const [notificationsOpen, setNotificationsOpen] = useState(false);
    const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [adminProfile, setAdminProfile] = useState({ name: 'System Admin', email: '' });
    const [notifications, setNotifications] = useState([]);
    const notifRef = useRef(null);

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
    }, [notificationsOpen]);

    // Admin IDs Management State
    const [settingsTab, setSettingsTab] = useState('profile'); // 'profile' | 'admins'
    const [admins, setAdmins] = useState([]);
    const [newAdminEmail, setNewAdminEmail] = useState('');
    const [newAdminPassword, setNewAdminPassword] = useState('');
    const [isAdminLoading, setIsAdminLoading] = useState(false);
    const [adminError, setAdminError] = useState('');
    const [adminSuccess, setAdminSuccess] = useState('');
    const {
        filters,
        semesterOptions,
        updateFilter,
    } = useGlobalFilters();
    const panelViewUrl = import.meta.env.VITE_PANEL_VIEW_URL || '';
    const mentorViewUrl = import.meta.env.VITE_MENTOR_VIEW_URL || '';


    useEffect(() => {
        const email = adminUser?.email || '';
        const profileName = adminUser?.user_metadata?.full_name || adminUser?.user_metadata?.name;
        const fallbackName = email ? email.split('@')[0] : 'System Admin';

        setAdminProfile({
            name: profileName || fallbackName,
            email,
        });

        // Fetch notifications
        import('../lib/api.js').then(({ apiFetchTable }) => {
            apiFetchTable('notifications').then(data => {
                const adminNotifs = data.filter(n => n.recipient_role === 'admin' || n.audience === 'admin');
                setNotifications(adminNotifs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)));
            }).catch(console.error);
        });
    }, [adminUser]);

    const markAllAsRead = () => {
        import('../lib/api.js').then(({ apiPatchRow }) => {
            const unread = notifications.filter(n => !n.read);
            if (unread.length > 0) {
                Promise.all(unread.map(n => apiPatchRow('notifications', n.id, { read: true })))
                    .then(() => {
                        setNotifications(notifications.map(n => ({ ...n, read: true })));
                    })
                    .catch(console.error);
            }
        });
    };
    const fetchAdmins = async () => {
        try {
            const token = getStoredSession()?.access_token;
            const apiBase = getApiBaseUrl();
            const response = await fetch(`${apiBase}/api/auth/admins`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const payload = await response.json();
            if (payload.status === 'success') {
                setAdmins(payload.data);
            }
        } catch (err) {
            console.error('Failed to load admins:', err);
        }
    };

    const handleAddAdmin = async (e) => {
        e.preventDefault();
        setAdminError('');
        setAdminSuccess('');
        if (!newAdminEmail.trim() || !newAdminPassword) {
            setAdminError('Please fill out all fields.');
            return;
        }
        setIsAdminLoading(true);
        try {
            const token = getStoredSession()?.access_token;
            const apiBase = getApiBaseUrl();
            const response = await fetch(`${apiBase}/api/auth/admins`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ email: newAdminEmail.trim(), password: newAdminPassword })
            });
            const payload = await response.json();
            if (response.ok && payload.status === 'success') {
                setAdminSuccess(payload.message || 'Account created successfully.');
                setNewAdminEmail('');
                setNewAdminPassword('');
                fetchAdmins();
            } else {
                setAdminError(payload.detail || 'Failed to create account.');
            }
        } catch (err) {
            setAdminError('An error occurred while creating account.');
        } finally {
            setIsAdminLoading(false);
        }
    };

    const handleDeleteAdmin = async (id) => {
        if (!window.confirm('Are you sure you want to delete this administrator account?')) return;
        setAdminError('');
        setAdminSuccess('');
        try {
            const token = getStoredSession()?.access_token;
            const apiBase = getApiBaseUrl();
            const response = await fetch(`${apiBase}/api/auth/admins/${id}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const payload = await response.json();
            if (response.ok && payload.status === 'success') {
                setAdminSuccess(payload.message || 'Account deleted successfully.');
                fetchAdmins();
            } else {
                setAdminError(payload.detail || 'Failed to delete account.');
            }
        } catch (err) {
            setAdminError('An error occurred while deleting account.');
        }
    };

    useEffect(() => {
        if (settingsOpen) {
            setSettingsTab('profile');
            setAdminError('');
            setAdminSuccess('');
            fetchAdmins();
        }
    }, [settingsOpen]);

    // Format path to title
    const getTitle = () => {
        const path = location.pathname.replace('/admin/', '').split('/')[0];
        if (!path || path === 'dashboard') return 'Dashboard';
        return path.split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    };

    return (
        <header className="min-h-16 border-b border-slate-200/80 dark:border-slate-800/80 bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl sticky top-0 z-40 flex flex-wrap items-center justify-between gap-3 px-4 sm:px-6 py-2 transition-colors">
            <div className="absolute inset-0 overflow-hidden pointer-events-none z-[-1]">
                <div className="absolute top-[-50px] left-[10%] w-[200px] h-[200px] bg-indigo-500/10 dark:bg-indigo-500/10 rounded-full blur-3xl"></div>
                <div className="absolute top-[-50px] right-[25%] w-[150px] h-[150px] bg-purple-500/10 dark:bg-purple-500/10 rounded-full blur-3xl"></div>
            </div>

            <div className="flex items-center">
                <button onClick={() => setMobileMenuOpen(true)} className="md:hidden mr-4 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-colors">
                    <Menu className="w-6 h-6" />
                </button>
                <div className="flex flex-col">
                    <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 hidden sm:block drop-shadow-sm">
                        {getTitle()}
                    </h2>
                    <span className="text-xs font-extrabold tracking-wide uppercase bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent hidden sm:block">
                        Procksi Admin Portal
                    </span>
                </div>
            </div>

            <div className="flex flex-1 min-w-[260px] items-center justify-end gap-2 sm:gap-3">
                {/* Analysis view selector — only on the Analysis page, left of the search bar */}
                {location.pathname.replace('/admin/', '').split('/')[0] === 'analysis' && (
                    <PresentationViewDropdown />
                )}

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

                <button onClick={toggleTheme} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-all rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 hover:rotate-12 active:scale-95">
                    {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                </button>

                <div className="relative" ref={notifRef}>
                    <button onClick={() => setNotificationsOpen(!notificationsOpen)} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 transition-all rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 relative hover:rotate-12 active:scale-95">
                        <Bell className="w-5 h-5" />
                        {notifications.filter(n => !n.read).length > 0 && <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-white dark:border-slate-900 animate-pulse"></span>}
                    </button>
                    <AnimatePresence>
                        {notificationsOpen && (
                            <motion.div key="notifications" initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute right-0 mt-2 w-80 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
                                <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
                                    <h3 className="font-semibold text-slate-800 dark:text-slate-100">Notifications</h3>
                                    <button onClick={markAllAsRead} className="text-xs text-indigo-600 dark:text-indigo-400 font-medium hover:underline">Mark all as read</button>
                                </div>
                                <div className="max-h-80 overflow-y-auto">
                                    {notifications.length === 0 ? (
                                        <div className="p-4 text-center text-sm text-slate-500">
                                            No new notifications.
                                        </div>
                                    ) : (
                                        notifications.map(n => (
                                            <div key={n.id} className={`p-4 border-b border-slate-50 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors ${!n.read ? 'bg-indigo-50/50 dark:bg-indigo-900/10' : ''}`}>
                                                <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{n.title}</p>
                                                <p className="text-sm text-slate-600 dark:text-slate-300 mt-1">{n.message}</p>
                                                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{new Date(n.created_at).toLocaleString()}</p>
                                            </div>
                                        ))
                                    )}
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                <div className="relative pl-2 sm:pl-4 border-l border-slate-200 dark:border-slate-800">
                    <div onClick={() => setProfileDropdownOpen(!profileDropdownOpen)} className="relative h-9 w-9 rounded-full border-2 border-slate-200 dark:border-slate-700 flex items-center justify-center bg-indigo-100 dark:bg-indigo-900 overflow-hidden cursor-pointer hover:border-indigo-500 dark:hover:border-indigo-500 hover:shadow-md hover:shadow-indigo-500/20 transition-all group">
                        <User className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                    </div>
                    <AnimatePresence>
                        {profileDropdownOpen && (
                            <div key="backdrop" className="fixed inset-0 z-40" onClick={() => setProfileDropdownOpen(false)}></div>
                        )}
                        {profileDropdownOpen && (
                            <motion.div key="dropdown" initial={{ opacity: 0, y: 10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.95 }}
                                className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50">
                                    <div className="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
                                        <p className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">{adminProfile.name}</p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">{adminProfile.email}</p>
                                    </div>
                                    <div className="p-2 space-y-1">
                                        <button onClick={() => { setSettingsOpen(true); setProfileDropdownOpen(false); }} className="w-full flex items-center px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors">
                                            <Settings className="w-4 h-4 mr-3 text-slate-400" /> Settings
                                        </button>
                                        <div className="border-t border-slate-100 dark:border-slate-700 my-1 pt-1">
                                            <div className="px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-400">Impersonate Role</div>
                                            <button onClick={() => window.open(panelViewUrl, '_blank')} className="w-full flex items-center px-3 py-2 text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 rounded-lg transition-colors">
                                                <ExternalLink className="w-4 h-4 mr-3" /> Panel View
                                            </button>
                                            <button onClick={() => window.open(mentorViewUrl, '_blank')} className="w-full flex items-center px-3 py-2 text-sm font-medium text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10 rounded-lg transition-colors">
                                                <ExternalLink className="w-4 h-4 mr-3" /> Mentor View
                                            </button>
                                        </div>
                                        <button onClick={handleLogout} className="w-full flex items-center px-3 py-2 mt-1 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors border-t border-slate-100 dark:border-slate-700">
                                            <LogOut className="w-4 h-4 mr-3 text-red-400" /> Sign Out
                                        </button>
                                    </div>
                                </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Profile Settings Modal */}
            {/* Profile Settings Modal */}
            {createPortal(
                <AnimatePresence>
                    {settingsOpen && (
                        <motion.div key="settings-modal" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                            <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} 
                                className={`bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full border border-slate-200 dark:border-slate-700 overflow-hidden transition-all duration-300 max-h-[85vh] flex flex-col ${settingsTab === 'admins' ? 'max-w-3xl' : 'max-w-md'}`}>
                                <div className="p-6 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex justify-between items-center shrink-0">
                                    <h3 className="text-xl font-black text-slate-800 dark:text-white flex items-center">
                                        <Settings className="w-5 h-5 mr-2 text-indigo-500" /> Settings
                                    </h3>
                                    <button onClick={() => setSettingsOpen(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors">
                                        <X className="w-5 h-5" />
                                    </button>
                                </div>

                                {/* Tab Switcher */}
                                <div className="flex border-b border-slate-100 dark:border-slate-700 px-6 bg-slate-50/50 dark:bg-slate-800/30 shrink-0">
                                    <button onClick={() => setSettingsTab('profile')} className={`flex items-center py-3 px-4 border-b-2 text-xs font-black uppercase tracking-widest transition-all ${settingsTab === 'profile' ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}>
                                        <User className="w-4 h-4 mr-2" /> My Profile
                                    </button>
                                    <button onClick={() => setSettingsTab('admins')} className={`flex items-center py-3 px-4 border-b-2 text-xs font-black uppercase tracking-widest transition-all ${settingsTab === 'admins' ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400'}`}>
                                        <Shield className="w-4 h-4 mr-2" /> Manage Admins
                                    </button>
                                </div>

                                {settingsTab === 'profile' ? (
                                    <>
                                        <div className="p-6 space-y-4 overflow-y-auto flex-1">
                                            <div>
                                                <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Display Name</label>
                                                <input 
                                                    type="text" 
                                                    value={adminProfile.name} 
                                                    onChange={(e) => setAdminProfile({...adminProfile, name: e.target.value})}
                                                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner transition-shadow" 
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Email Address</label>
                                                <input 
                                                    type="email" 
                                                    value={adminProfile.email} 
                                                    onChange={(e) => setAdminProfile({...adminProfile, email: e.target.value})}
                                                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner transition-shadow" 
                                                />
                                            </div>
                                        </div>
                                        <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 shrink-0">
                                            <button onClick={() => setSettingsOpen(false)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-200/50 dark:hover:bg-slate-700 rounded-xl transition-colors">
                                                Cancel
                                            </button>
                                            <button onClick={() => setSettingsOpen(false)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/30">
                                                Save Changes
                                            </button>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div className="p-6 grid grid-cols-1 md:grid-cols-5 gap-6 overflow-y-auto flex-1">
                                            {/* Left: Accounts List */}
                                            <div className="md:col-span-3 space-y-3">
                                                <h4 className="text-xs font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest">Registered Admins</h4>
                                                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                                                    {admins.length === 0 ? (
                                                        <div className="flex justify-center py-8">
                                                            <Loader2 className="w-6 h-6 text-indigo-500 animate-spin" />
                                                        </div>
                                                    ) : (
                                                        admins.map(admin => (
                                                            <div key={admin.id} className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 rounded-xl">
                                                                <div className="flex items-center space-x-3 overflow-hidden">
                                                                    <div className="w-7 h-7 rounded-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-bold text-xs shrink-0 border border-indigo-100/50 dark:border-indigo-500/10">
                                                                        AD
                                                                    </div>
                                                                    <div className="truncate">
                                                                        <p className="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">{admin.email}</p>
                                                                        <p className="text-[9px] text-slate-450 dark:text-slate-500 font-semibold">Added: {new Date(admin.created_at).toLocaleDateString()}</p>
                                                                    </div>
                                                                </div>
                                                                <div className="flex items-center space-x-2 shrink-0">
                                                                    {admin.email === MASTER_ADMIN_EMAIL ? (
                                                                        <span className="px-2 py-0.5 bg-amber-50 dark:bg-amber-500/10 border border-amber-250 dark:border-amber-500/20 text-amber-600 dark:text-amber-450 rounded-md text-[9px] font-black uppercase tracking-wider scale-90">
                                                                            Master
                                                                        </span>
                                                                    ) : (
                                                                        <button onClick={() => handleDeleteAdmin(admin.id)}
                                                                            className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-all active:scale-95"
                                                                            title="Delete Admin Account">
                                                                            <Trash2 className="w-3.5 h-3.5"/>
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ))
                                                    )}
                                                </div>
                                            </div>

                                            {/* Right: Add New Admin Form */}
                                            <div className="md:col-span-2 bg-slate-50 dark:bg-slate-900/30 p-4 rounded-2xl border border-slate-150 dark:border-slate-800 space-y-3 h-fit shrink-0">
                                                <h4 className="text-xs font-black text-slate-650 dark:text-slate-350 uppercase tracking-widest">Create Account</h4>
                                                <p className="text-[10px] text-slate-555 dark:text-slate-400 leading-relaxed font-semibold">New administrator IDs will receive identical login rights and data access permissions as the master account.</p>

                                                <AnimatePresence>
                                                    {adminError && (
                                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                                                            className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 p-2.5 rounded-lg text-[10px] font-bold flex items-start">
                                                            <AlertCircle className="w-3.5 h-3.5 mr-2.5 shrink-0 mt-0.5" />
                                                            <span>{adminError}</span>
                                                        </motion.div>
                                                    )}
                                                    {adminSuccess && (
                                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                                                            className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 p-2.5 rounded-lg text-[10px] font-bold flex items-start">
                                                            <CheckCircle className="w-3.5 h-3.5 mr-2.5 shrink-0 mt-0.5" />
                                                            <span>{adminSuccess}</span>
                                                        </motion.div>
                                                    )}
                                                </AnimatePresence>

                                                <form onSubmit={handleAddAdmin} className="space-y-3 pt-1">
                                                    <div>
                                                        <label className="block text-[9px] uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400 mb-1">Email</label>
                                                        <input type="email" value={newAdminEmail} onChange={e => setNewAdminEmail(e.target.value)} required placeholder="admin@domain.com"
                                                            className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 transition-all shadow-sm" />
                                                    </div>
                                                    <div>
                                                        <label className="block text-[9px] uppercase tracking-wider font-bold text-slate-500 dark:text-slate-400 mb-1">Password</label>
                                                        <input type="password" value={newAdminPassword} onChange={e => setNewAdminPassword(e.target.value)} required placeholder="••••••••"
                                                            className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 transition-all shadow-sm" />
                                                    </div>
                                                    <button type="submit" disabled={isAdminLoading}
                                                        className="w-full mt-2 flex items-center justify-center py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-70 text-white font-black uppercase tracking-widest text-[9px] rounded-xl transition-all shadow-md active:scale-95">
                                                        {isAdminLoading ? <Loader2 className="w-3 h-3 mr-2 animate-spin"/> : <Plus className="w-3 h-3 mr-2" />} Create Admin
                                                    </button>
                                                </form>
                                            </div>
                                        </div>
                                        <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end shrink-0">
                                            <button onClick={() => setSettingsOpen(false)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/30">
                                                Close Settings
                                            </button>
                                        </div>
                                    </>
                                )}
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>,
                document.body
            )}
        </header>
    );
};

export default TopNav;
