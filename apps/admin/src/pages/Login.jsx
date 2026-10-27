import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, Lock, Mail, Shield, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { apiLogin } from '../lib/api';
import { getApiBaseUrl } from '../lib/apiBase';
import { ALLOWED_EMAIL_SUFFIX, MASTER_ADMIN_EMAIL, EMAIL_DOMAIN_ERROR, emailPlaceholder } from '../lib/emailPolicy';

export default function Login({ onLogin }) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [isForgotMode, setIsForgotMode] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const navigate = useNavigate();

    const onSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!email.trim() || !password) {
            setError('Both fields are required.');
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address.');
            return;
        }

        const emailClean = email.trim().toLowerCase();
        if (!emailClean.endsWith(ALLOWED_EMAIL_SUFFIX) && emailClean !== MASTER_ADMIN_EMAIL) {
            setError(EMAIL_DOMAIN_ERROR);
            return;
        }

        setIsSubmitting(true);
        try {
            const sessionPayload = await apiLogin(email.trim(), password);
            if (onLogin) onLogin(sessionPayload);
        } catch (loginError) {
            setError(loginError.message || 'Invalid credentials.');
            setIsSubmitting(false);
            return;
        }

        setIsSubmitting(false);
        navigate('/admin/dashboard');
    };

    const onForgotSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!email.trim()) {
            setError('Please enter your email.');
            return;
        }

        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address.');
            return;
        }

        const forgotEmailClean = email.trim().toLowerCase();
        if (!forgotEmailClean.endsWith(ALLOWED_EMAIL_SUFFIX) && forgotEmailClean !== MASTER_ADMIN_EMAIL) {
            setError(EMAIL_DOMAIN_ERROR);
            return;
        }

        setIsSubmitting(true);
        try {
            const apiBase = getApiBaseUrl();
            const response = await fetch(`${apiBase}/api/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email.trim() }),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || 'Failed to send reset link.');
            }
            setSuccessMessage(payload.message || 'Password reset link sent to your email.');
        } catch (err) {
            setError(err.message || 'An error occurred.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4 sm:p-8 transition-colors relative overflow-hidden z-0">
        
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
        <div className="absolute top-[10%] right-[20%] w-96 h-96 bg-indigo-500/20 dark:bg-indigo-500/10 rounded-full blur-[100px] pointer-events-none z-[-2]"></div>
        <div className="absolute bottom-[20%] left-[10%] w-[500px] h-[500px] bg-purple-500/20 dark:bg-purple-500/5 rounded-full blur-[120px] pointer-events-none z-[-2]"></div>

        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.5, type: 'spring' }} className="w-full max-w-4xl bg-white/70 dark:bg-slate-900/80 backdrop-blur-xl rounded-[2.5rem] shadow-2xl border border-white/50 dark:border-slate-700/50 flex flex-col md:flex-row overflow-hidden relative z-10 mx-auto">
            
            {/* Left Graphic Side */}
            <div className="w-full md:w-1/2 p-10 md:p-12 lg:p-16 flex flex-col justify-center relative overflow-hidden bg-gradient-to-br from-indigo-600 to-purple-800 text-white">
                <div className="absolute inset-0 mix-blend-overlay opacity-30" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='1' fill-rule='evenodd'%3E%3Ccircle cx='3' cy='3' r='3'/%3E%3Ccircle cx='13' cy='13' r='3'/%3E%3C/g%3E%3C/svg%3E")`}}></div>
                <div className="relative z-10 flex flex-col items-center text-center">
                    <img src="/procksi-mark.png" alt="Procksi" className="w-24 h-24 object-contain mb-8 drop-shadow-2xl bg-white p-3 rounded-2xl shadow-xl" onError={(e) => { e.target.style.display = 'none' }} />
                    <h2 className="text-3xl font-black mb-3 tracking-tight">Procksi</h2>
                    <p className="text-indigo-100/90 font-medium">Project Management System</p>
                    
                    <div className="mt-12 bg-white/10 backdrop-blur-md rounded-2xl p-5 border border-white/20 shadow-lg text-left w-full transform -rotate-1 hover:rotate-0 transition-transform">
                        <div className="flex items-center mb-2">
                            <Shield className="w-4 h-4 text-emerald-400 mr-2" />
                            <span className="text-sm font-bold tracking-wider">SECURE ACCESS</span>
                        </div>
                        <p className="text-xs text-indigo-100 leading-relaxed">Centralized administrative portal for evaluating projects, tracking student proposals, and assigning faculty mentors seamlessly.</p>
                    </div>
                </div>
            </div>

            {/* Right Form Side */}
            <div className="w-full md:w-1/2 p-10 md:p-12 lg:p-16 flex flex-col justify-center bg-white dark:bg-slate-800 shadow-[-20px_0_30px_-15px_rgba(0,0,0,0.1)] z-10">
                <div className="mb-8">
                    <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mb-2">
                        {isForgotMode ? 'Forgot Password' : 'Admin Signature'}
                    </h1>
                    <p className="text-slate-500 dark:text-slate-400 font-medium">
                        {isForgotMode ? 'Enter your email to receive a recovery link.' : 'Please enter your credentials to continue.'}
                    </p>
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
                                <CheckCircle2 className="w-5 h-5 mr-3 shrink-0" />
                                {successMessage}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {!isForgotMode ? (
                    <form onSubmit={onSubmit} className="space-y-6">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Administrator Email</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder={emailPlaceholder('admin')}
                                    className="w-full pl-11 pr-4 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-2">
                                <label className="block text-sm font-bold text-slate-700 dark:text-slate-300">Secret Password</label>
                                <button type="button" onClick={() => { setIsForgotMode(true); setError(''); setSuccessMessage(''); }}
                                    className="text-xs font-bold text-indigo-600 hover:text-indigo-700 outline-none">
                                    Forgot Password?
                                </button>
                            </div>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-11 pr-4 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        
                        <button type="submit" disabled={isSubmitting} className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-black text-sm uppercase tracking-widest py-4 rounded-xl transition-all shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 active:scale-[0.98] mt-4 border border-indigo-500/50 flex items-center justify-center group">
                            {isSubmitting ? 'Signing in...' : 'Enter Workspace'}
                            <svg className="w-5 h-5 ml-2 transform group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                        </button>
                    </form>
                ) : (
                    <form onSubmit={onForgotSubmit} className="space-y-6">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Registered Email Address</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder={emailPlaceholder('admin')}
                                    className="w-full pl-11 pr-4 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-indigo-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        
                        <button type="submit" disabled={isSubmitting} className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-black text-sm uppercase tracking-widest py-4 rounded-xl transition-all shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 active:scale-[0.98] mt-4 border border-indigo-500/50 flex items-center justify-center group">
                            {isSubmitting ? 'Sending...' : 'Send Reset Link'}
                        </button>

                        <div className="text-center mt-6">
                            <button type="button" onClick={() => { setIsForgotMode(false); setError(''); setSuccessMessage(''); }}
                                className="text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-300 outline-none">
                                Back to Login
                            </button>
                        </div>
                    </form>
                )}
            </div>
            
        </motion.div>
    </div>
    );
}
