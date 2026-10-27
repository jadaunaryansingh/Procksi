import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, Lock, Mail, Shield, User, Check, Loader2, Phone } from 'lucide-react';
import { Link } from 'react-router-dom';
import { authAPI } from '../services/api';
import { emailPlaceholder } from '../lib/emailPolicy';

const MOCK_DOMAINS = [
    'Artificial Intelligence',
    'Machine Learning',
    'IoT',
    'Web Development',
    'Blockchain',
    'Data Science',
    'CyberSecurity',
    'Cloud Computing'
];

export default function Signup() {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [phone, setPhone] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [selectedDomains, setSelectedDomains] = useState([]);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    

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
            setError('Please select at least one area of expertise.');
            return;
        }

        setIsSubmitting(true);
        try {
            const response = await authAPI.signup({ name, email, phone: phone.trim(), password, domains: selectedDomains });
            if (response.success && response.status === 'pending') {
                setSuccessMessage(response.message);
                setName('');
                setEmail('');
                setPhone('');
                setPassword('');
                setConfirmPassword('');
                setSelectedDomains([]);
            } else {
                setError(response.message || 'Signup failed. Please try again.');
            }
        } catch (err) {
            setError(err.message || 'Signup failed. Please try again.');
        } finally {
            setIsSubmitting(false);
        }
    };

    const toggleDomain = (domain) => {
        if (selectedDomains.includes(domain)) {
            setSelectedDomains(selectedDomains.filter(d => d !== domain));
        } else {
            setSelectedDomains([...selectedDomains, domain]);
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
        <div className="absolute top-[10%] left-[20%] w-96 h-96 bg-emerald-500/20 dark:bg-emerald-500/10 rounded-full blur-[100px] pointer-events-none z-[-2]"></div>
        <div className="absolute bottom-[20%] right-[10%] w-[500px] h-[500px] bg-teal-500/20 dark:bg-teal-500/5 rounded-full blur-[120px] pointer-events-none z-[-2]"></div>

        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1, duration: 0.5, type: 'spring' }} className="w-full max-w-5xl bg-white/70 dark:bg-slate-900/80 backdrop-blur-xl rounded-[2.5rem] shadow-2xl border border-white/50 dark:border-slate-700/50 flex flex-col md:flex-row overflow-hidden relative z-10 mx-auto">
            
            {/* Left Graphic Side */}
            <div className="w-full md:w-5/12 p-10 md:p-12 lg:p-16 flex flex-col justify-center relative overflow-hidden bg-gradient-to-br from-emerald-600 to-teal-800 text-white shrink-0">
                <div className="absolute inset-0 mix-blend-overlay opacity-30" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='20' height='20' viewBox='0 0 20 20' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='%23ffffff' fill-opacity='1' fill-rule='evenodd'%3E%3Ccircle cx='3' cy='3' r='3'/%3E%3Ccircle cx='13' cy='13' r='3'/%3E%3C/g%3E%3C/svg%3E")`}}></div>
                <div className="relative z-10 flex flex-col items-center text-center">
                    <img src="/procksi-mark.png" alt="Procksi" className="w-24 h-24 object-contain mb-8 drop-shadow-2xl bg-white p-3 rounded-2xl shadow-xl" onError={(e) => { e.target.style.display = 'none' }} />
                    <h2 className="text-3xl font-black mb-3 tracking-tight">Procksi</h2>
                    <p className="text-emerald-100/90 font-medium mb-8">Project Management System</p>
                    
                    <div className="bg-white/10 backdrop-blur-md rounded-2xl p-5 border border-white/20 shadow-lg text-left w-full transform -rotate-1">
                        <div className="flex items-center mb-2">
                            <Shield className="w-4 h-4 text-emerald-400 mr-2" />
                            <span className="text-sm font-bold tracking-wider">PANEL REGISTRATION</span>
                        </div>
                        <p className="text-xs text-emerald-100 leading-relaxed">Request access to the Panel & Mentor dashboard. Your request will be validated by the system administrator.</p>
                    </div>
                </div>
            </div>

            {/* Right Form Side */}
            <div className="w-full md:w-7/12 p-10 md:p-12 lg:p-16 flex flex-col justify-center bg-white dark:bg-slate-800 shadow-[-20px_0_30px_-15px_rgba(0,0,0,0.1)] z-10">
                <div className="mb-8">
                    <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mb-2">Create Panel Profile</h1>
                    <p className="text-slate-500 dark:text-slate-400 font-medium">Join the evaluation panel and start guiding projects.</p>
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
                            <div className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 px-4 py-4 rounded-xl text-sm font-bold flex items-start shadow-sm">
                                <Check className="w-5 h-5 mr-3 mt-0.5 shrink-0 bg-emerald-500/20 rounded-full p-0.5" />
                                <div>
                                    <h4 className="font-black mb-1">Registration Pending Approval</h4>
                                    <p className="font-medium text-xs opacity-90">{successMessage}</p>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <form onSubmit={onSubmit} className="space-y-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Display Name</label>
                            <div className="relative">
                                <User className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="text" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Dr. Rohan Verma"
                                    className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Panel Email</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder={emailPlaceholder('rohan.verma')}
                                    className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Phone Number</label>
                            <div className="relative">
                                <Phone className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required placeholder="+919876543210"
                                    className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Confirm Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                                <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required placeholder="••••••••"
                                    className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-emerald-500 font-medium dark:text-white outline-none transition-all shadow-sm" />
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Areas of Expertise (Select at least one)</label>
                        <div className="flex flex-wrap gap-2 p-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl max-h-40 overflow-y-auto">
                            {MOCK_DOMAINS.map(domain => {
                                const selected = selectedDomains.includes(domain);
                                return (
                                    <button key={domain} type="button" onClick={() => toggleDomain(domain)}
                                        className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all border ${
                                            selected 
                                                ? 'bg-emerald-600 text-white border-emerald-500 shadow-md shadow-emerald-500/20' 
                                                : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                                        }`}>
                                        {domain}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <button type="submit" disabled={isSubmitting} className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 disabled:cursor-not-allowed text-white font-black text-sm uppercase tracking-widest py-4 rounded-xl transition-all shadow-lg shadow-emerald-500/30 hover:shadow-emerald-500/50 active:scale-[0.98] mt-2 border border-emerald-500/50 flex items-center justify-center gap-2">
                        {isSubmitting ? (
                            <>
                                <Loader2 className="w-5 h-5 animate-spin" />
                                Submitting Request...
                            </>
                        ) : (
                            'Submit Registration'
                        )}
                    </button>

                    <p className="text-center text-sm text-slate-500 dark:text-slate-400 mt-6 font-medium">
                        Already have an account? <Link to="/login" className="text-emerald-600 dark:text-emerald-400 font-bold hover:underline">Log in</Link>
                    </p>
                </form>
            </div>
            
        </motion.div>
    </div>
    );
}
