import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, Lock, Mail, Shield, User, Briefcase, Check, Loader2, ChevronUp, ChevronDown, X, RefreshCw, Phone, Maximize2, Search } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import { api } from '../services/api';

export default function Signup() {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [phone, setPhone] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [domains, setDomains] = useState([]);
    const [selectedDomains, setSelectedDomains] = useState([]);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    // Ranking guidance, shown as an overlay once — on the first domain picked,
    // from either the inline strip or the picker window.
    const [domainNotice, setDomainNotice] = useState(false);
    const [domainNoticeSeen, setDomainNoticeSeen] = useState(false);
    const [isLoadingDomains, setIsLoadingDomains] = useState(true);
    // The catalogue now runs to ~64 database-sourced domains, too many to browse
    // in the inline strip, so the full list opens in its own window.
    const [domainPickerOpen, setDomainPickerOpen] = useState(false);
    const [domainSearch, setDomainSearch] = useState('');

    const navigate = useNavigate();
    const { signup } = useAuth();

    const loadDomains = async (fresh = false) => {
        setIsLoadingDomains(true);
        try {
            const response = await api.get(`/auth/domains${fresh ? '?fresh=1' : ''}`);
            if (Array.isArray(response)) {
                setDomains(response);
            } else if (response && Array.isArray(response.data)) {
                setDomains(response.data);
            }
        } catch (err) {
            console.error("Failed to load student domain choices", err);
        } finally {
            setIsLoadingDomains(false);
        }
    };

    useEffect(() => {
        loadDomains();
    }, []);

    const onSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!name.trim() || !email.trim() || !phone.trim() || !password || !confirmPassword) {
            setError('All fields including phone number are required.');
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address.');
            return;
        }

        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        if (selectedDomains.length === 0) {
            setError('Please select at least one domain for mentoring.');
            return;
        }

        setIsSubmitting(true);
        const result = await signup({ name, email, phone: phone.trim(), password, domains: selectedDomains });
        setIsSubmitting(false);

        if (result.success) {
            navigate('/mentor');
        } else if (result.pending) {
            setSuccessMessage(result.message);
            setName('');
            setEmail('');
            setPhone('');
            setPassword('');
            setConfirmPassword('');
            setSelectedDomains([]);
        } else {
            setError(result.error || 'Signup failed. Please try again.');
        }
    };

    const toggleDomain = (domain) => {
        if (selectedDomains.includes(domain)) {
            setSelectedDomains(selectedDomains.filter(d => d !== domain));
        } else {
            // Append: pick order == preference rank (1st picked = rank 1).
            setSelectedDomains([...selectedDomains, domain]);
            // Explain the ranking once, on the first pick, wherever it happens.
            // The overlay layers above the picker window, so this fires the same
            // way in both views.
            if (!domainNoticeSeen) {
                setDomainNotice(true);
                setDomainNoticeSeen(true);
            }
        }
    };

    // Reorder a chosen domain within the ranked list (dir: -1 up, +1 down).
    const moveDomain = (index, dir) => {
        setSelectedDomains(prev => {
            const arr = [...prev];
            const j = index + dir;
            if (j < 0 || j >= arr.length) return prev;
            [arr[index], arr[j]] = [arr[j], arr[index]];
            return arr;
        });
    };

    // Escape dismisses the topmost overlay only. The guidance notice can sit on
    // top of the picker, so it is checked first — otherwise one press would
    // close the picker out from under a notice that stayed on screen.
    useEffect(() => {
        if (!domainPickerOpen && !domainNotice) return;
        const onKeyDown = (e) => {
            if (e.key !== 'Escape') return;
            if (domainNotice) setDomainNotice(false);
            else setDomainPickerOpen(false);
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [domainPickerOpen, domainNotice]);

    useEffect(() => {
        if (!domainPickerOpen) setDomainSearch('');
    }, [domainPickerOpen]);

    // One chip renderer for both the inline strip and the picker window, so the
    // selected state and rank badge cannot drift apart between the two.
    const renderDomainChip = (domain, roomy = false) => {
        const isSelected = selectedDomains.includes(domain);
        const rank = selectedDomains.indexOf(domain);
        return (
            <button
                type="button"
                key={domain}
                onClick={() => toggleDomain(domain)}
                aria-pressed={isSelected}
                className={`${roomy ? 'px-3.5 py-2 text-sm' : 'px-3 py-1.5 text-xs'} rounded-lg font-bold border transition-all flex items-center text-left ${isSelected ? 'bg-indigo-50 dark:bg-indigo-500/20 border-indigo-200 dark:border-indigo-500/30 text-indigo-700 dark:text-indigo-400 shadow-sm' : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'}`}
            >
                {isSelected && (
                    <span className={`${roomy ? 'w-5 h-5 text-[10px]' : 'w-4 h-4 text-[9px]'} mr-1.5 shrink-0 rounded-full bg-indigo-600 text-white font-black flex items-center justify-center`}>{rank + 1}</span>
                )}
                {domain}
            </button>
        );
    };

    const domainQuery = domainSearch.trim().toLowerCase();
    const visibleDomains = domainQuery
        ? domains.filter(d => d.toLowerCase().includes(domainQuery))
        : domains;

    return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4 sm:p-8 transition-colors relative overflow-hidden z-0">

        {/* Both overlays are portalled to document.body.
            The page root sets `relative ... z-0`, which opens a stacking
            context and caps everything inside it — and the card below adds more
            via backdrop-blur. Nested in there, this notice could not reliably
            paint above the picker window no matter what z-index it carried,
            which is why it never showed when a domain was picked from the
            expanded view. At body level the two compare directly: 60 over 50. */}
        {createPortal(
        <AnimatePresence>
            {domainNotice && (
                <motion.div
                    key="domain-notice-backdrop"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setDomainNotice(false)}
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
                >
                    <motion.div
                        key="domain-notice-window"
                        initial={{ opacity: 0, scale: 0.9, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9, y: 10 }}
                        transition={{ type: 'spring', duration: 0.4 }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden"
                    >
                        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-700">
                            <div className="flex items-center gap-2">
                                <AlertCircle className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                <h3 className="text-sm font-black text-slate-900 dark:text-white">Domains for Mentoring</h3>
                            </div>
                            <button type="button" onClick={() => setDomainNotice(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Close">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <div className="px-5 py-4">
                            <p className="text-sm font-medium text-slate-600 dark:text-slate-300 leading-relaxed">
                                These are the domains students are actually working in. Pick the ones you can mentor. The order you pick them is your preference rank (1 = strongest).
                            </p>
                        </div>
                        <div className="px-5 py-3 bg-slate-50 dark:bg-slate-900/50 flex justify-end">
                            <button type="button" onClick={() => setDomainNotice(false)} className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-black uppercase tracking-widest transition-colors">
                                Got it
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>,
        document.body
        )}

        {/* Full domain catalogue, opened by "Browse all" */}
        {createPortal(
        <AnimatePresence>
            {domainPickerOpen && (
                <motion.div
                    key="domain-picker-backdrop"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => setDomainPickerOpen(false)}
                    className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4"
                >
                    <motion.div
                        key="domain-picker-window"
                        initial={{ opacity: 0, scale: 0.9, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9, y: 10 }}
                        transition={{ type: 'spring', duration: 0.4, bounce: 0.18 }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full max-w-3xl max-h-[85vh] flex flex-col bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden"
                    >
                        <div className="shrink-0 flex items-start justify-between gap-4 px-5 py-4 border-b border-slate-100 dark:border-slate-700">
                            <div className="flex items-center gap-2">
                                <Briefcase className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                <div>
                                    <h3 className="text-sm font-black text-slate-900 dark:text-white">Domains for Mentoring</h3>
                                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400">Pick every domain you can mentor — the order you pick them is your preference rank.</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                <button type="button" onClick={() => loadDomains(true)} disabled={isLoadingDomains} title="Refresh domains"
                                    className="text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                                    <RefreshCw className={`w-4 h-4 ${isLoadingDomains ? 'animate-spin' : ''}`} />
                                </button>
                                <button type="button" onClick={() => setDomainPickerOpen(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors" title="Close">
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        </div>

                        <div className="shrink-0 px-5 py-3 border-b border-slate-100 dark:border-slate-700">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    type="text"
                                    value={domainSearch}
                                    onChange={(e) => setDomainSearch(e.target.value)}
                                    placeholder="Search domains…"
                                    className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 transition-all"
                                />
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto px-5 py-4">
                            {isLoadingDomains ? (
                                <p className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 font-medium py-2">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading domains…
                                </p>
                            ) : visibleDomains.length === 0 ? (
                                <p className="text-xs text-slate-400 dark:text-slate-500 font-medium py-2">
                                    {domains.length === 0 ? 'No student choices available yet.' : `No domain matches “${domainSearch}”.`}
                                </p>
                            ) : (
                                <div className="flex flex-wrap gap-2">
                                    {visibleDomains.map(domain => renderDomainChip(domain, true))}
                                </div>
                            )}
                        </div>

                        <div className="shrink-0 px-5 py-3 bg-slate-50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between gap-4">
                            <p className="text-xs font-bold text-slate-500 dark:text-slate-400">
                                {selectedDomains.length === 0
                                    ? 'Nothing selected yet'
                                    : `${selectedDomains.length} selected · ranked in pick order`}
                            </p>
                            <button type="button" onClick={() => setDomainPickerOpen(false)}
                                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-black uppercase tracking-widest transition-colors">
                                Done
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>,
        document.body
        )}

        {/* Absolute SVG Background Waves */}
        <div className="absolute inset-0 z-[-2] opacity-30 dark:opacity-20 pointer-events-none mix-blend-multiply dark:mix-blend-screen text-indigo-500">
            <svg viewBox="0 0 1440 320" preserveAspectRatio="none" className="w-full h-full absolute bottom-0">
                <path fill="currentColor" fillOpacity="1" d="M0,256L48,229.3C96,203,192,149,288,154.7C384,160,480,224,576,218.7C672,213,768,139,864,128C960,117,1056,171,1152,197.3C1248,224,1344,224,1392,224L1440,224L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
            </svg>
            <svg viewBox="0 0 1440 320" preserveAspectRatio="none" className="w-full h-full absolute bottom-0 opacity-50 scale-y-110 translate-x-[5%] text-purple-500">
                <path fill="currentColor" fillOpacity="1" d="M0,64L48,80C96,96,192,128,288,128C384,128,480,96,576,106.7C672,117,768,171,864,176C960,181,1056,139,1152,122.7C1248,107,1344,117,1392,122.7L1440,128L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
            </svg>
        </div>

        {/* Ambient Glowing Orbs */}
        <div className="absolute top-[10%] left-[20%] w-96 h-96 bg-purple-500/20 dark:bg-purple-500/10 rounded-full blur-[100px] pointer-events-none z-[-2]"></div>
        <div className="absolute bottom-[20%] right-[10%] w-[500px] h-[500px] bg-indigo-500/20 dark:bg-indigo-500/5 rounded-full blur-[120px] pointer-events-none z-[-2]"></div>

        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.5, type: 'spring' }} className="w-full max-w-5xl bg-white/70 dark:bg-slate-900/80 backdrop-blur-xl rounded-[2.5rem] shadow-2xl border border-white/50 dark:border-slate-700/50 flex flex-col md:flex-row overflow-hidden relative z-10 mx-auto">
            
            {/* Left Graphic Side */}
            <div className="w-full md:w-5/12 p-10 md:p-12 lg:p-16 flex flex-col justify-center relative overflow-hidden bg-gradient-to-br from-indigo-600 to-purple-800 text-white">
                <div className="absolute inset-0 mix-blend-overlay opacity-30" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='1' fill-rule='evenodd'%3E%3Ccircle cx='3' cy='3' r='3'/%3E%3Ccircle cx='13' cy='13' r='3'/%3E%3C/g%3E%3C/svg%3E")`}}></div>
                <div className="relative z-10 flex flex-col items-center text-center">
                    <div className="mb-8 drop-shadow-2xl bg-white/10 backdrop-blur-md p-4 rounded-2xl shadow-xl border border-white/20">
                        <Briefcase className="w-16 h-16 text-white" />
                    </div>
                    <h2 className="text-3xl font-black mb-3 tracking-tight">Join as Mentor</h2>
                    <p className="text-indigo-100/90 font-medium">Project Management System</p>
                    
                    <div className="mt-12 bg-white/10 backdrop-blur-md rounded-2xl p-5 border border-white/20 shadow-lg text-left w-full transform -rotate-1 hover:rotate-0 transition-transform">
                        <div className="flex items-center mb-2">
                            <Shield className="w-4 h-4 text-emerald-400 mr-2" />
                            <span className="text-sm font-bold tracking-wider">ONBOARDING PROFILE</span>
                        </div>
                        <p className="text-xs text-indigo-100 leading-relaxed">Rank the project domains you can mentor in order of preference. Our allocation agent matches teams to your top domains automatically.</p>
                    </div>
                </div>
            </div>

            {/* Right Form Side */}
            <div className="w-full md:w-7/12 p-8 md:p-12 flex flex-col justify-center bg-white dark:bg-slate-800 shadow-[-20px_0_30px_-15px_rgba(0,0,0,0.1)] z-10">
                <div className="mb-6">
                    <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mb-2">Create Profile</h1>
                    <p className="text-slate-500 dark:text-slate-400 font-medium">Setup your faculty account and define your expertise.</p>
                </div>

                <AnimatePresence>
                    {error && (
                        <motion.div key="error" initial={{ opacity: 0, height: 0, y: -10 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -10 }} className="mb-6 overflow-hidden">
                            <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm">
                                <AlertCircle className="w-5 h-5 mr-3 shrink-0" />
                                {error}
                            </div>
                        </motion.div>
                    )}
                    {successMessage && (
                        <motion.div key="success" initial={{ opacity: 0, height: 0, y: -10 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -10 }} className="mb-6 overflow-hidden">
                            <div className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm">
                                <Check className="w-5 h-5 mr-3 shrink-0" />
                                {successMessage}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <form onSubmit={onSubmit} className="space-y-5">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Full Name</label>
                            <div className="relative">
                                <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input type="text" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Dr. John Doe"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm text-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Work Email</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="name@gla.ac.in"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm text-sm" />
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Phone Number</label>
                            <div className="relative">
                                <Phone className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required placeholder="+919876543210"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm text-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm text-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Confirm Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-10 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm text-sm" />
                            </div>
                        </div>
                    </div>
                    
                    <div>
                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2 flex justify-between items-end">
                            Domains for Mentoring
                            {/* Replaces the old "⟳ Select multiple" caption. Refresh
                                moved inside the window, where it sits next to the list
                                it actually reloads. */}
                            <button
                                type="button"
                                onClick={() => setDomainPickerOpen(true)}
                                aria-haspopup="dialog"
                                aria-expanded={domainPickerOpen}
                                className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
                            >
                                <Maximize2 className="w-3 h-3" />
                                Browse all{domains.length > 0 ? ` (${domains.length})` : ''}
                            </button>
                        </label>
                        <div className="flex flex-wrap gap-2 max-h-[140px] overflow-y-auto custom-scrollbar p-1">
                            {isLoadingDomains ? (
                                <p className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 font-medium py-2">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading domains…
                                </p>
                            ) : domains.length === 0 ? (
                                <p className="text-xs text-slate-400 dark:text-slate-500 font-medium py-2">
                                    No student choices available yet.
                                </p>
                            ) : domains.map(domain => renderDomainChip(domain))}
                        </div>

                        {/* Ranked preference list (reorderable) */}
                        {selectedDomains.length > 0 && (
                            <div className="mt-3 space-y-1.5">
                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Your preference order</p>
                                {selectedDomains.map((domain, i) => (
                                    <div key={domain} className="flex items-center gap-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5">
                                        <span className="w-5 h-5 shrink-0 rounded-full bg-indigo-600 text-white text-[10px] font-black flex items-center justify-center">{i + 1}</span>
                                        <span className="flex-1 text-xs font-bold text-slate-700 dark:text-slate-300 truncate">{domain}</span>
                                        <div className="flex items-center gap-0.5">
                                            <button type="button" onClick={() => moveDomain(i, -1)} disabled={i === 0}
                                                className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors" title="Move up">
                                                <ChevronUp className="w-3.5 h-3.5" />
                                            </button>
                                            <button type="button" onClick={() => moveDomain(i, 1)} disabled={i === selectedDomains.length - 1}
                                                className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors" title="Move down">
                                                <ChevronDown className="w-3.5 h-3.5" />
                                            </button>
                                            <button type="button" onClick={() => toggleDomain(domain)}
                                                className="p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors" title="Remove">
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <button type="submit" disabled={isSubmitting} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-black text-sm uppercase tracking-widest py-3.5 rounded-xl transition-all shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 active:scale-[0.98] mt-2 border border-indigo-500/50 flex items-center justify-center group disabled:opacity-70 disabled:cursor-not-allowed">
                        {isSubmitting ? (
                            <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Processing...</>
                        ) : (
                            <>Complete Registration</>
                        )}
                    </button>
                    
                    <p className="text-center text-xs text-slate-500 mt-5 font-medium">
                        Already registered? <Link to="/login" className="text-indigo-600 dark:text-indigo-400 hover:underline font-bold">Sign in here</Link>.
                    </p>
                </form>
            </div>
            
        </motion.div>
    </div>
    );
}
