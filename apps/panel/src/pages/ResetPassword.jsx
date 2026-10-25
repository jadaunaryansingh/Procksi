import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, Lock, Shield, CheckCircle2 } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getApiBaseUrl } from '../lib/apiBase';

export default function ResetPassword() {
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    
    const [searchParams] = useSearchParams();
    const token = searchParams.get('token');
    const navigate = useNavigate();

    const onSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setSuccessMessage('');

        if (!password || !confirmPassword) {
            setError('All fields are required.');
            return;
        }

        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        if (password.length < 6) {
            setError('Password must be at least 6 characters long.');
            return;
        }

        if (!token) {
            setError('Reset token is missing from the URL.');
            return;
        }

        setIsSubmitting(true);
        try {
            const apiBase = getApiBaseUrl();
            const response = await fetch(`${apiBase}/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, password }),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.detail || 'Failed to reset password.');
            }
            setSuccessMessage(payload.message || 'Password reset successfully!');
            setTimeout(() => {
                navigate('/login');
            }, 3000);
        } catch (err) {
            setError(err.message || 'An error occurred.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4 sm:p-8 transition-colors relative overflow-hidden z-0">
        
        {/* Absolute SVG Background Waves */}
        <div className="absolute inset-0 z-[-2] opacity-30 dark:opacity-20 pointer-events-none mix-blend-multiply dark:mix-blend-screen text-emerald-500">
            <svg viewBox="0 0 1440 320" preserveAspectRatio="none" className="w-full h-full absolute bottom-0">
                <path fill="currentColor" fillOpacity="1" d="M0,256L48,229.3C96,203,192,149,288,154.7C384,160,480,224,576,218.7C672,213,768,139,864,128C960,117,1056,171,1152,197.3C1248,224,1344,224,1392,224L1440,224L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
            </svg>
            <svg viewBox="0 0 1440 320" preserveAspectRatio="none" className="w-full h-full absolute bottom-0 opacity-50 scale-y-110 translate-x-[5%] text-teal-500">
                <path fill="currentColor" fillOpacity="1" d="M0,64L48,80C96,96,192,128,288,128C384,128,480,96,576,106.7C672,117,768,171,864,176C960,181,1056,139,1152,122.7C1248,107,1344,117,1392,122.7L1440,128L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path>
            </svg>
        </div>

        {/* Ambient Glowing Orbs */}
        <div className="absolute top-[10%] right-[20%] w-96 h-96 bg-emerald-500/20 dark:bg-emerald-500/10 rounded-full blur-[100px] pointer-events-none z-[-2]"></div>
        <div className="absolute bottom-[20%] left-[10%] w-[500px] h-[500px] bg-teal-500/20 dark:bg-teal-500/5 rounded-full blur-[120px] pointer-events-none z-[-2]"></div>

        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.5, type: 'spring' }} className="w-full max-w-4xl bg-white/70 dark:bg-slate-900/80 backdrop-blur-xl rounded-[2.5rem] shadow-2xl border border-white/50 dark:border-slate-700/50 flex flex-col md:flex-row overflow-hidden relative z-10 mx-auto">
            
            {/* Left Graphic Side */}
            <div className="w-full md:w-1/2 p-10 md:p-12 lg:p-16 flex flex-col justify-center relative overflow-hidden bg-gradient-to-br from-emerald-600 to-teal-800 text-white">
                <div className="absolute inset-0 mix-blend-overlay opacity-30" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='1' fill-rule='evenodd'%3E%3Ccircle cx='3' cy='3' r='3'/%3E%3Ccircle cx='13' cy='13' r='3'/%3E%3C/g%3E%3C/svg%3E")`}}></div>
                <div className="relative z-10 flex flex-col items-center text-center">
                    <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-24 h-24 object-contain mb-8 drop-shadow-2xl bg-white p-3 rounded-2xl shadow-xl" onError={(e) => { e.target.style.display = 'none' }} />
                    <h2 className="text-3xl font-black mb-3 tracking-tight">GLA University</h2>
                    <p className="text-emerald-100/90 font-medium">Project Management System</p>
                    
                    <div className="mt-12 bg-white/10 backdrop-blur-md rounded-2xl p-5 border border-white/20 shadow-lg text-left w-full transform -rotate-1 hover:rotate-0 transition-transform">
                        <div className="flex items-center mb-2">
                            <Shield className="w-4 h-4 text-emerald-400 mr-2" />
                            <span className="text-sm font-bold tracking-wider">SECURE RESET</span>
                        </div>
                        <p className="text-xs text-emerald-100 leading-relaxed">Reset your Panel Portal account password securely using the link generated from the recovery service.</p>
                    </div>
                </div>
            </div>

            {/* Right Form Side */}
            <div className="w-full md:w-1/2 p-10 md:p-12 lg:p-16 flex flex-col justify-center bg-white dark:bg-slate-800 shadow-[-20px_0_30px_-15px_rgba(0,0,0,0.1)] z-10">
                <div className="mb-8">
                    <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mb-2">New Password</h1>
                    <p className="text-slate-500 dark:text-slate-400 font-medium">Please enter and confirm your new Panel password.</p>
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

                {!successMessage ? (
                    <form onSubmit={onSubmit} className="space-y-6">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">New Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-11 pr-4 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Confirm New Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-11 pr-4 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        
                        <button type="submit" disabled={isSubmitting} className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-black text-sm uppercase tracking-widest py-4 rounded-xl transition-all shadow-lg shadow-emerald-500/30 hover:shadow-emerald-500/50 active:scale-[0.98] mt-4 border border-emerald-500/50 flex items-center justify-center group">
                            {isSubmitting ? 'Updating...' : 'Update Password'}
                        </button>
                    </form>
                ) : (
                    <div className="text-center py-8">
                        <p className="text-sm font-bold text-slate-500 dark:text-slate-400">Redirecting to login workspace...</p>
                    </div>
                )}
            </div>
            
        </motion.div>
    </div>
    );
}
