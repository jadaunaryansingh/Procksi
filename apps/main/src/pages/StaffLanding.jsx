import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
    Shield, BookOpen, Search, ArrowLeft, ArrowRight, 
    Users, Settings, BarChart3, CheckCircle, 
    MessageSquare, Calendar, Award, Lock, FileText, Database, Moon, Sun 
} from 'lucide-react';
import { portalUrl } from '../lib/portalUrls';

export default function StaffLanding() {
    // Read the stored preference during the first render instead of correcting
    // it from an effect, which rendered the light state once before flipping.
    const [isDarkMode, setIsDarkMode] = useState(() =>
        localStorage.theme === 'dark' ||
        (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)
    );

    // Applying the class is a DOM side effect and stays here; it no longer
    // sets state, which is what caused the cascading render.
    useEffect(() => {
        document.documentElement.classList.toggle('dark', isDarkMode);
    }, [isDarkMode]);

    const toggleTheme = () => {
        if (isDarkMode) {
            document.documentElement.classList.remove('dark');
            localStorage.theme = 'light';
            setIsDarkMode(false);
        } else {
            document.documentElement.classList.add('dark');
            localStorage.theme = 'dark';
            setIsDarkMode(true);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-[#020617] text-slate-900 dark:text-white font-sans selection:bg-indigo-500/30 overflow-hidden transition-colors duration-300">
            
            {/* Top Navigation */}
            <div className="absolute top-0 left-0 right-0 p-6 z-50 max-w-7xl mx-auto flex justify-between items-center">
                <div className="flex items-center gap-3">
                    <img src="/procksi-mark.png" alt="Procksi" className="w-10 h-10" />
                    <div className="flex flex-col">
                        <span className="font-bold text-slate-900 dark:text-white text-lg leading-tight">Procksi</span>
                        <span className="text-[10px] tracking-widest text-[#00cba9] font-bold uppercase">Staff & Faculty Portal</span>
                    </div>
                </div>
                
                <div className="hidden md:flex items-center gap-8 text-sm font-semibold text-slate-600 dark:text-slate-300">
                    <a href="#portals" className="hover:text-slate-900 dark:hover:text-white transition-colors">Portals</a>
                    <a href="#capabilities" className="hover:text-slate-900 dark:hover:text-white transition-colors">Capabilities</a>
                    <a href="#workflows" className="hover:text-slate-900 dark:hover:text-white transition-colors">Workflows</a>
                </div>

                <div className="flex items-center gap-4">
                    <button 
                        onClick={toggleTheme} 
                        className="p-2 rounded-full text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors"
                    >
                        {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                    </button>
                </div>
            </div>

            {/* Hero Section */}
            <section className="relative pt-32 pb-20 px-6 max-w-7xl mx-auto flex flex-col md:flex-row items-center gap-12 z-10 min-h-[85vh]">
                {/* Left Side text */}
                <div className="flex-1 space-y-6 text-left">
                    <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400 text-sm font-bold shadow-sm"
                    >
                        <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                        Administrative Access
                    </motion.div>
                    
                    <motion.h1 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="text-5xl md:text-7xl font-black text-slate-900 dark:text-white tracking-tight leading-[1.1]"
                    >
                        Drive Academic <br/>
                        <span className="text-[#00cba9]">Excellence.</span>
                    </motion.h1>
                    
                    <motion.p 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="text-lg text-slate-600 dark:text-slate-400 max-w-lg leading-relaxed"
                    >
                        The central operations hub for university faculty. Configure system parameters, mentor project teams, and conduct formal panel evaluations—all seamlessly integrated.
                    </motion.p>

                    <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.3 }}
                        className="flex items-center gap-4 pt-4"
                    >
                        <a href="#portals" className="px-6 py-3 rounded-full bg-[#00cba9] text-white font-bold hover:bg-[#00b395] transition-colors shadow-lg shadow-[#00cba9]/30 flex items-center gap-2">
                            Access Portals <ArrowRight className="w-4 h-4" />
                        </a>
                        <a href="#workflows" className="px-6 py-3 rounded-full bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 font-bold border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors shadow-sm">
                            View Workflows
                        </a>
                    </motion.div>
                </div>

                {/* Right Side Mockups */}
                <div className="flex-1 relative h-[500px] w-full hidden md:block">
                    {/* Admin Mockup (Bottom Left) */}
                    <motion.div 
                        initial={{ opacity: 0, x: -50, y: 50 }}
                        animate={{ opacity: 1, x: 0, y: 0 }}
                        transition={{ delay: 0.4, duration: 0.8, type: "spring" }}
                        className="absolute bottom-10 left-0 w-80 h-56 bg-[#1a1d27] rounded-xl border border-slate-700/50 shadow-2xl overflow-hidden -rotate-6 scale-90 z-0"
                    >
                        {/* Mac Header */}
                        <div className="px-3 py-2 flex items-center gap-1.5 border-b border-slate-700/50 bg-[#232736]">
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
                        </div>
                        {/* Mockup content */}
                        <div className="flex h-full">
                            <div className="w-16 bg-[#151720] border-r border-slate-700/50 p-2 flex flex-col gap-2">
                                <div className="w-6 h-6 rounded bg-[#00cba9]/20 mx-auto mt-2"></div>
                                <div className="w-8 h-2 bg-slate-700 rounded mx-auto mt-4"></div>
                                <div className="w-8 h-2 bg-slate-700 rounded mx-auto"></div>
                            </div>
                            <div className="flex-1 p-4 flex flex-col gap-3">
                                <div className="w-24 h-3 bg-slate-700 rounded mb-2"></div>
                                <div className="flex gap-2">
                                    <div className="w-14 h-14 rounded bg-[#232736] border border-slate-700/50 flex flex-col items-center justify-center p-1">
                                        <div className="text-[6px] text-slate-400">Users</div>
                                        <div className="text-xs font-bold text-indigo-400">1,204</div>
                                    </div>
                                    <div className="w-14 h-14 rounded bg-[#232736] border border-slate-700/50 flex flex-col items-center justify-center p-1">
                                        <div className="text-[6px] text-slate-400">Projects</div>
                                        <div className="text-xs font-bold text-amber-400">45</div>
                                    </div>
                                </div>
                                <div className="w-full h-16 rounded bg-[#232736] border border-slate-700/50 mt-auto p-2 flex flex-col justify-between">
                                    <div className="text-[8px] text-slate-400">Recent Activity</div>
                                    <div className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 rounded-full bg-[#00cba9]"></div>
                                        <div className="h-1.5 w-16 bg-slate-600 rounded"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Panel Mockup (Top Right) */}
                    <motion.div 
                        initial={{ opacity: 0, x: 50, y: -50 }}
                        animate={{ opacity: 1, x: 0, y: 0 }}
                        transition={{ delay: 0.6, duration: 0.8, type: "spring" }}
                        className="absolute top-10 right-0 w-80 h-56 bg-[#1a1d27] rounded-xl border border-slate-700/50 shadow-2xl overflow-hidden rotate-6 scale-90 z-0"
                    >
                        {/* Mac Header */}
                        <div className="px-3 py-2 flex items-center gap-1.5 border-b border-slate-700/50 bg-[#232736]">
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
                        </div>
                        <div className="p-4">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-8 h-8 rounded bg-emerald-500/20 flex items-center justify-center"><Search className="w-4 h-4 text-emerald-400"/></div>
                                <div>
                                    <div className="text-xs font-bold text-white">Mid Term Evaluation</div>
                                    <div className="text-[9px] text-slate-400">Dr. Anek Patel • Panel 4</div>
                                </div>
                                <div className="ml-auto px-2 py-0.5 rounded border border-emerald-500 text-[8px] text-emerald-400">Active</div>
                            </div>
                            <div className="flex gap-2">
                                <div className="flex-1 h-20 rounded border border-slate-700/50 bg-[#232736] flex flex-col items-center justify-center">
                                    <div className="text-[10px] text-slate-400">Pending</div>
                                    <div className="text-lg font-bold text-white">3</div>
                                </div>
                                <div className="flex-1 h-20 rounded border border-slate-700/50 bg-[#232736] flex flex-col items-center justify-center">
                                    <div className="text-[10px] text-slate-400">Active</div>
                                    <div className="text-lg font-bold text-white">1</div>
                                </div>
                            </div>
                            <div className="mt-3 w-full h-8 rounded bg-[#232736] border border-slate-700/50 flex items-center justify-center text-[10px] font-bold text-slate-300">Join Active Room</div>
                        </div>
                    </motion.div>

                    {/* Mentor Mockup (Center Foreground) */}
                    <motion.div 
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.8, duration: 0.8, type: "spring" }}
                        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-64 bg-[#1a1d27] rounded-xl border border-slate-700/50 shadow-2xl shadow-black/50 overflow-hidden z-10"
                    >
                        {/* Mac Header */}
                        <div className="px-3 py-2 flex items-center gap-1.5 border-b border-slate-700/50 bg-[#232736]">
                            <div className="w-2.5 h-2.5 rounded-full bg-red-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-yellow-500"></div>
                            <div className="w-2.5 h-2.5 rounded-full bg-green-500"></div>
                        </div>
                        <div className="flex h-full">
                            <div className="w-24 bg-[#151720] border-r border-slate-700/50 p-3 flex flex-col gap-3">
                                <div>
                                    <div className="text-[8px] font-bold text-slate-400 uppercase">Faculty</div>
                                    <div className="text-[10px] font-bold text-white">Dr. R. Sharma</div>
                                </div>
                                <div className="w-full py-1.5 rounded bg-indigo-500/20 text-indigo-400 text-[10px] flex items-center px-2 mt-2">Dashboard</div>
                                <div className="w-full py-1.5 rounded text-slate-400 text-[10px] flex items-center px-2">My Teams</div>
                                <div className="w-full py-1.5 rounded text-slate-400 text-[10px] flex items-center px-2">Proposals</div>
                            </div>
                            <div className="flex-1 p-4 flex flex-col gap-3">
                                <div className="flex justify-between items-center">
                                    <div>
                                        <div className="text-sm font-bold text-white">Mentor Dashboard</div>
                                        <div className="text-[8px] text-slate-400">Computer Science Dept.</div>
                                    </div>
                                    <div className="flex gap-1">
                                        <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-[8px] text-white">A</div>
                                        <div className="w-6 h-6 rounded-full bg-indigo-500 flex items-center justify-center text-[8px] text-white">RS</div>
                                    </div>
                                </div>
                                <div className="w-full rounded-lg bg-[#232736] border border-slate-700/50 p-3 flex justify-between items-center">
                                    <div>
                                        <div className="text-[10px] font-bold text-white">Weekly Progress Review</div>
                                        <div className="text-[8px] text-slate-400 mt-1">You have 3 team submissions pending your review.</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-[8px] text-slate-400">Overall Status</div>
                                        <div className="text-[10px] font-bold text-[#00cba9]">On Track</div>
                                    </div>
                                </div>
                                <div className="grid grid-cols-3 gap-2 mt-auto">
                                    <div className="rounded border border-slate-700/50 bg-[#232736] p-2 flex flex-col justify-between">
                                        <div className="text-[8px] text-slate-400">Teams</div>
                                        <div className="text-sm font-bold text-white mt-1">8</div>
                                    </div>
                                    <div className="rounded border border-slate-700/50 bg-[#232736] p-2 border-l-2 border-l-amber-500 flex flex-col justify-between">
                                        <div className="text-[8px] text-slate-400">At Risk</div>
                                        <div className="text-sm font-bold text-amber-500 mt-1">2</div>
                                    </div>
                                    <div className="rounded border border-slate-700/50 bg-[#232736] p-2 flex flex-col justify-between">
                                        <div className="text-[8px] text-slate-400">Pending</div>
                                        <div className="text-sm font-bold text-white mt-1">3</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </section>

            {/* Portal Entry Cards */}
            <div id="portals" className="pt-20">
                <div className="w-full text-center mb-10">
                    <h2 className="text-3xl font-black text-slate-900 dark:text-white">Select Your Gateway</h2>
                </div>
                <div className="grid md:grid-cols-3 gap-6 w-full max-w-6xl mx-auto px-6">
                    {/* Admin Portal */}
                    <motion.a 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.3 }}
                        href={portalUrl('admin')} 
                        className="group relative flex flex-col p-8 rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl hover:-translate-y-2 transition-all overflow-hidden text-left"
                    >
                        <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-bl-full -mr-8 -mt-8 transition-transform group-hover:scale-150"></div>
                        <div className="w-14 h-14 bg-indigo-50 dark:bg-indigo-900/30 rounded-2xl flex items-center justify-center mb-6 relative z-10 border border-indigo-100 dark:border-indigo-800/50">
                            <Settings className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
                        </div>
                        <h3 className="text-2xl font-extrabold mb-3 text-slate-900 dark:text-white relative z-10">Admin Portal</h3>
                        <p className="text-slate-600 dark:text-slate-400 mb-8 flex-grow relative z-10">
                            System-wide control. Manage student rosters, coordinate semester timelines, and oversee all platform activity.
                        </p>
                        <div className="text-indigo-600 dark:text-indigo-400 font-bold flex items-center gap-2 group-hover:gap-3 transition-all relative z-10 mt-auto">
                            Launch Admin Console <ArrowRight className="w-5 h-5" />
                        </div>
                    </motion.a>

                    {/* Mentor Portal */}
                    <motion.a 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.4 }}
                        href={portalUrl('mentor')} 
                        className="group relative flex flex-col p-8 rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl hover:-translate-y-2 transition-all overflow-hidden text-left"
                    >
                        <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-bl-full -mr-8 -mt-8 transition-transform group-hover:scale-150"></div>
                        <div className="w-14 h-14 bg-emerald-50 dark:bg-emerald-900/30 rounded-2xl flex items-center justify-center mb-6 relative z-10 border border-emerald-100 dark:border-emerald-800/50">
                            <BookOpen className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
                        </div>
                        <h3 className="text-2xl font-extrabold mb-3 text-slate-900 dark:text-white relative z-10">Mentor Portal</h3>
                        <p className="text-slate-600 dark:text-slate-400 mb-8 flex-grow relative z-10">
                            Guide your assigned teams. Review proposals, track milestone submissions, and provide direct feedback.
                        </p>
                        <div className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-2 group-hover:gap-3 transition-all relative z-10 mt-auto">
                            Enter Mentor Hub <ArrowRight className="w-5 h-5" />
                        </div>
                    </motion.a>

                    {/* Panel Portal */}
                    <motion.a 
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5 }}
                        href={portalUrl('panel')} 
                        className="group relative flex flex-col p-8 rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl hover:-translate-y-2 transition-all overflow-hidden text-left"
                    >
                        <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-bl-full -mr-8 -mt-8 transition-transform group-hover:scale-150"></div>
                        <div className="w-14 h-14 bg-amber-50 dark:bg-amber-900/30 rounded-2xl flex items-center justify-center mb-6 relative z-10 border border-amber-100 dark:border-amber-800/50">
                            <Search className="w-7 h-7 text-amber-600 dark:text-amber-400" />
                        </div>
                        <h3 className="text-2xl font-extrabold mb-3 text-slate-900 dark:text-white relative z-10">Evaluation Panel</h3>
                        <p className="text-slate-600 dark:text-slate-400 mb-8 flex-grow relative z-10">
                            Conduct structured assessments. Grade mid-term and final project presentations using standardized rubrics.
                        </p>
                        <div className="text-amber-600 dark:text-amber-400 font-bold flex items-center gap-2 group-hover:gap-3 transition-all relative z-10 mt-auto">
                            Open Panel Board <ArrowRight className="w-5 h-5" />
                        </div>
                    </motion.a>
                </div>
            </div>

            {/* Detailed Features Section */}
            <section id="capabilities" className="py-24 bg-white dark:bg-slate-900/50 border-t border-slate-200 dark:border-slate-800 relative z-10 scroll-mt-24">
                <div className="max-w-7xl mx-auto px-6">
                    <div className="text-center mb-20">
                        <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4 text-slate-900 dark:text-white">
                            Comprehensive Capabilities
                        </h2>
                        <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto text-lg">
                            Each portal is specifically designed to provide the exact tools needed for your role in the project lifecycle.
                        </p>
                    </div>

                    <div className="space-y-32">
                        {/* Admin Features */}
                        <div className="flex flex-col md:flex-row items-center gap-12 md:gap-24">
                            <div className="flex-1 space-y-8">
                                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 font-bold border border-indigo-100 dark:border-indigo-800">
                                    <Settings className="w-5 h-5" /> Administrator
                                </div>
                                <h3 className="text-3xl font-bold text-slate-900 dark:text-white leading-tight">
                                    Absolute control over the academic lifecycle.
                                </h3>
                                <ul className="space-y-6">
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <Users className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">User & Roster Management</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Bulk import student lists, manage mentor assignments, and organize panel compositions effortlessly.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <Lock className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Phase Freezing & Locking</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Strictly enforce deadlines by locking team formation or completely freezing system modifications.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <BarChart3 className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Global Analytics</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Monitor system-wide progress, view overall grade distributions, and track milestone completion rates.</p>
                                        </div>
                                    </li>
                                </ul>
                            </div>
                            <div className="flex-1 relative w-full aspect-square md:aspect-[4/3] rounded-3xl bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center shadow-2xl p-8">
                                {/* Detailed Admin UI Mockup */}
                                <div className="w-full h-full border border-slate-200 dark:border-slate-700 rounded-xl bg-white dark:bg-slate-900 shadow-sm flex overflow-hidden">
                                    {/* Sidebar */}
                                    <div className="w-16 border-r border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50 flex flex-col items-center py-4 space-y-4">
                                        <div className="w-8 h-8 rounded bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center"><Settings className="w-4 h-4 text-indigo-600" /></div>
                                        <div className="w-8 h-8 rounded hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center justify-center"><Users className="w-4 h-4 text-slate-400" /></div>
                                        <div className="w-8 h-8 rounded hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center justify-center"><BarChart3 className="w-4 h-4 text-slate-400" /></div>
                                    </div>
                                    {/* Main Content */}
                                    <div className="flex-1 p-4 flex flex-col gap-4">
                                        <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-800 pb-3">
                                            <div>
                                                <h5 className="font-bold text-sm text-slate-800 dark:text-white">Admin Dashboard</h5>
                                                <p className="text-[10px] text-slate-500">Overview of Spring Semester</p>
                                            </div>
                                            <div className="px-3 py-1 bg-indigo-600 text-white text-[10px] font-bold rounded-md">Generate Report</div>
                                        </div>
                                        <div className="grid grid-cols-3 gap-3">
                                            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 p-2">
                                                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Total Students</span>
                                                <div className="text-xl font-black text-slate-800 dark:text-white mt-1">1,248</div>
                                            </div>
                                            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 p-2">
                                                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Active Teams</span>
                                                <div className="text-xl font-black text-slate-800 dark:text-white mt-1">312</div>
                                            </div>
                                            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 p-2">
                                                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Sys Status</span>
                                                <div className="text-sm font-bold text-emerald-600 mt-2 flex items-center gap-1"><CheckCircle className="w-3 h-3"/> Active</div>
                                            </div>
                                        </div>
                                        <div className="flex-1 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 mt-1 flex flex-col overflow-hidden">
                                            <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-800 text-[10px] font-bold text-slate-500 bg-white dark:bg-slate-900/50">Recent System Activity</div>
                                            <div className="p-3 space-y-2">
                                                <div className="flex items-center gap-2 text-[10px]">
                                                    <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                                                    <span className="font-bold text-slate-700 dark:text-slate-300">Phase Unlocked</span>
                                                    <span className="text-slate-400 ml-auto">2 mins ago</span>
                                                </div>
                                                <div className="flex items-center gap-2 text-[10px]">
                                                    <div className="w-2 h-2 rounded-full bg-indigo-500"></div>
                                                    <span className="font-bold text-slate-700 dark:text-slate-300">Roster Imported</span>
                                                    <span className="text-slate-400 ml-auto">1 hr ago</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Mentor Features */}
                        <div className="flex flex-col md:flex-row-reverse items-center gap-12 md:gap-24">
                            <div className="flex-1 space-y-8">
                                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 font-bold border border-emerald-100 dark:border-emerald-800">
                                    <BookOpen className="w-5 h-5" /> Mentor
                                </div>
                                <h3 className="text-3xl font-bold text-slate-900 dark:text-white leading-tight">
                                    Direct guidance and continuous evaluation.
                                </h3>
                                <ul className="space-y-6">
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <FileText className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Proposal Review</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Review incoming project proposals, verify tech stacks, and approve or request revisions from teams.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <CheckCircle className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Milestone Tracking</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Approve iterative deliverables like architecture plans, SRS documents, and sprint completions.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <MessageSquare className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Feedback Loop</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Provide constructive feedback directly on submissions and track improvements over the semester.</p>
                                        </div>
                                    </li>
                                </ul>
                            </div>
                            <div className="flex-1 relative w-full aspect-square md:aspect-[4/3] rounded-3xl bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center shadow-2xl p-8">
                                 {/* Detailed Mentor UI Mockup */}
                                 <div className="w-full h-full border border-slate-200 dark:border-slate-700 rounded-xl bg-white dark:bg-slate-900 shadow-sm flex overflow-hidden">
                                    <div className="w-1/3 bg-slate-50 dark:bg-slate-900/50 border-r border-slate-100 dark:border-slate-800 flex flex-col">
                                        <div className="p-3 border-b border-slate-100 dark:border-slate-800 text-xs font-bold text-slate-800 dark:text-slate-200">My Teams</div>
                                        <div className="p-2 flex flex-col gap-1">
                                            <div className="p-2 bg-white dark:bg-slate-800 rounded border border-emerald-500/30 text-[10px] font-bold flex justify-between items-center shadow-sm">
                                                <span>Team Alpha</span> <span className="w-2 h-2 rounded-full bg-amber-400"></span>
                                            </div>
                                            <div className="p-2 rounded text-[10px] font-bold text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors">Team Beta</div>
                                            <div className="p-2 rounded text-[10px] font-bold text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors">Team Gamma</div>
                                        </div>
                                    </div>
                                    <div className="flex-1 p-4 flex flex-col gap-3">
                                        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                                            <div>
                                                <h5 className="font-bold text-sm text-slate-800 dark:text-white">Team Alpha</h5>
                                                <p className="text-[10px] text-slate-500">Project Proposal Review</p>
                                            </div>
                                            <span className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded text-[9px] font-bold">Pending</span>
                                        </div>
                                        <div className="flex-1 bg-slate-50 dark:bg-slate-800/50 rounded border border-slate-100 dark:border-slate-700 p-3 flex flex-col gap-2 overflow-hidden relative">
                                            <div className="text-xs font-bold text-slate-800 dark:text-slate-200">Smart Healthcare System</div>
                                            <p className="text-[9px] text-slate-500 leading-relaxed">
                                                An AI-based platform to monitor patient vitals remotely using IoT sensors and predict anomalies in real-time...
                                            </p>
                                            <div className="mt-2 flex gap-1">
                                                <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[8px] font-bold">React</span>
                                                <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-[8px] font-bold">Node.js</span>
                                            </div>
                                            <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-slate-50 dark:from-slate-800/90 pt-8 flex gap-2 justify-end">
                                                <button className="px-2 py-1 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded text-[9px] font-bold text-slate-600 dark:text-slate-300">Request Revision</button>
                                                <button className="px-2 py-1 bg-emerald-600 text-white rounded text-[9px] font-bold">Approve</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Panel Features */}
                        <div className="flex flex-col md:flex-row items-center gap-12 md:gap-24">
                            <div className="flex-1 space-y-8">
                                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 font-bold border border-amber-100 dark:border-amber-800">
                                    <Search className="w-5 h-5" /> Evaluation Panel
                                </div>
                                <h3 className="text-3xl font-bold text-slate-900 dark:text-white leading-tight">
                                    Structured, objective project assessment.
                                </h3>
                                <ul className="space-y-6">
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <Calendar className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Presentation Schedules</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">View your assigned presentation dates, times, and team lineups for mid-term and final reviews.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <Database className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Project Context</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Access team repositories, SRS documents, and previous mentor feedback before grading.</p>
                                        </div>
                                    </li>
                                    <li className="flex gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0 border border-slate-200 dark:border-slate-700">
                                            <Award className="w-6 h-6 text-slate-700 dark:text-slate-300" />
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg text-slate-900 dark:text-white mb-1">Rubric Grading</h4>
                                            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">Score teams seamlessly using standardized rubrics ensuring fair and objective evaluations across the board.</p>
                                        </div>
                                    </li>
                                </ul>
                            </div>
                            <div className="flex-1 relative w-full aspect-square md:aspect-[4/3] rounded-3xl bg-slate-100 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 overflow-hidden flex items-center justify-center shadow-2xl p-8">
                                 {/* Detailed Panel UI Mockup */}
                                 <div className="w-full h-full border border-slate-200 dark:border-slate-700 rounded-xl bg-white dark:bg-slate-900 shadow-sm flex flex-col overflow-hidden">
                                    <div className="p-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-slate-50 dark:bg-slate-900/50">
                                        <div className="flex items-center gap-2">
                                            <Search className="w-4 h-4 text-amber-500" />
                                            <span className="font-bold text-xs text-slate-800 dark:text-white">Mid-Term Evaluation</span>
                                        </div>
                                        <span className="text-[10px] font-bold text-slate-500">Room 402</span>
                                    </div>
                                    
                                    <div className="flex-1 p-4 flex gap-4">
                                        <div className="w-1/3 space-y-2 flex flex-col">
                                            <div className="text-[10px] font-bold text-slate-500 uppercase">Schedule</div>
                                            <div className="p-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded shadow-sm">
                                                <div className="text-[9px] font-bold text-amber-600 dark:text-amber-400 mb-1">10:00 AM - Current</div>
                                                <div className="text-[10px] font-bold text-slate-800 dark:text-slate-200">Team Delta</div>
                                            </div>
                                            <div className="p-2 border border-slate-100 dark:border-slate-800 rounded opacity-50">
                                                <div className="text-[9px] font-bold text-slate-400 mb-1">10:30 AM - Up Next</div>
                                                <div className="text-[10px] font-bold text-slate-600 dark:text-slate-400">Team Echo</div>
                                            </div>
                                        </div>

                                        <div className="flex-1 bg-slate-50 dark:bg-slate-800/50 rounded-lg border border-slate-100 dark:border-slate-800 p-3 flex flex-col gap-2">
                                            <div className="text-[11px] font-bold text-slate-800 dark:text-white border-b border-slate-200 dark:border-slate-700 pb-1">Grading Rubric</div>
                                            
                                            <div className="space-y-2 mt-1">
                                                <div>
                                                    <div className="flex justify-between text-[9px] mb-1">
                                                        <span className="font-bold text-slate-600 dark:text-slate-400">Implementation</span>
                                                        <span className="font-bold text-amber-600">35/40</span>
                                                    </div>
                                                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5"><div className="bg-amber-500 h-1.5 rounded-full w-[85%]"></div></div>
                                                </div>
                                                <div>
                                                    <div className="flex justify-between text-[9px] mb-1">
                                                        <span className="font-bold text-slate-600 dark:text-slate-400">Presentation</span>
                                                        <span className="font-bold text-amber-600">28/30</span>
                                                    </div>
                                                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5"><div className="bg-amber-500 h-1.5 rounded-full w-[90%]"></div></div>
                                                </div>
                                                <div>
                                                    <div className="flex justify-between text-[9px] mb-1">
                                                        <span className="font-bold text-slate-600 dark:text-slate-400">Q&A Handling</span>
                                                        <span className="font-bold text-amber-600">20/30</span>
                                                    </div>
                                                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-1.5"><div className="bg-amber-500 h-1.5 rounded-full w-[65%]"></div></div>
                                                </div>
                                            </div>
                                            
                                            <div className="mt-auto flex justify-between items-center pt-2 border-t border-slate-200 dark:border-slate-700">
                                                <div className="text-[9px] font-bold text-slate-500">Total Score</div>
                                                <div className="text-sm font-black text-slate-800 dark:text-white">83 <span className="text-[9px] text-slate-400 font-normal">/ 100</span></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Workflows Section */}
            <section id="workflows" className="py-24 bg-slate-50 dark:bg-[#020617] border-t border-slate-200 dark:border-slate-800 relative z-10 scroll-mt-24">
                <div className="max-w-7xl mx-auto px-6">
                    <div className="text-center mb-20">
                        <h2 className="text-3xl md:text-4xl font-black tracking-tight mb-4 text-slate-900 dark:text-white">
                            Seamless Academic Workflows
                        </h2>
                        <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto text-lg">
                            A connected ecosystem where every role plays a critical part in moving projects from inception to final evaluation.
                        </p>
                    </div>

                    <div className="relative max-w-4xl mx-auto">
                        {/* Connecting Line */}
                        <div className="absolute left-8 md:left-1/2 top-8 bottom-8 w-1 bg-slate-200 dark:bg-slate-800 -translate-x-1/2"></div>
                        
                        <div className="space-y-12">
                            {/* Step 1 */}
                            <div className="relative flex flex-col md:flex-row items-start md:items-center gap-8 md:gap-0">
                                <div className="md:w-1/2 md:pr-16 md:text-right flex flex-col md:items-end pl-24 md:pl-0">
                                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 text-xs font-bold mb-3 border border-indigo-100 dark:border-indigo-800">
                                        Phase 1
                                    </div>
                                    <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Foundation & Planning</h4>
                                    <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-sm md:text-base">Administrators import student rosters, configure the semester timeline, and open the system for team formation and mentor allocations.</p>
                                </div>
                                <div className="absolute left-8 md:left-1/2 w-12 h-12 rounded-full bg-indigo-500 border-4 border-slate-50 dark:border-[#020617] -translate-x-1/2 flex items-center justify-center shadow-lg z-10">
                                    <Settings className="w-5 h-5 text-white" />
                                </div>
                                <div className="md:w-1/2 md:pl-16 hidden md:block opacity-0"></div>
                            </div>

                            {/* Step 2 */}
                            <div className="relative flex flex-col md:flex-row items-start md:items-center gap-8 md:gap-0">
                                <div className="md:w-1/2 md:pr-16 hidden md:block opacity-0"></div>
                                <div className="absolute left-8 md:left-1/2 w-12 h-12 rounded-full bg-emerald-500 border-4 border-slate-50 dark:border-[#020617] -translate-x-1/2 flex items-center justify-center shadow-lg z-10">
                                    <BookOpen className="w-5 h-5 text-white" />
                                </div>
                                <div className="md:w-1/2 md:pl-16 pl-24 md:pl-16">
                                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-xs font-bold mb-3 border border-emerald-100 dark:border-emerald-800">
                                        Phase 2
                                    </div>
                                    <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Iterative Development</h4>
                                    <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-sm md:text-base">Mentors work closely with teams. They review project proposals, track milestone submissions, and provide constant feedback to keep teams on track.</p>
                                </div>
                            </div>

                            {/* Step 3 */}
                            <div className="relative flex flex-col md:flex-row items-start md:items-center gap-8 md:gap-0">
                                <div className="md:w-1/2 md:pr-16 md:text-right flex flex-col md:items-end pl-24 md:pl-0">
                                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 text-xs font-bold mb-3 border border-amber-100 dark:border-amber-800">
                                        Phase 3
                                    </div>
                                    <h4 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Formal Evaluation</h4>
                                    <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-sm md:text-base">Expert panels conduct mid-term and final reviews. They assess the project's quality, presentation, and Q&A handling using standardized rubrics.</p>
                                </div>
                                <div className="absolute left-8 md:left-1/2 w-12 h-12 rounded-full bg-amber-500 border-4 border-slate-50 dark:border-[#020617] -translate-x-1/2 flex items-center justify-center shadow-lg z-10">
                                    <Search className="w-5 h-5 text-white" />
                                </div>
                                <div className="md:w-1/2 md:pl-16 hidden md:block opacity-0"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
            {/* Simple Footer */}
            <footer className="bg-white dark:bg-[#020617] border-t border-slate-200 dark:border-slate-800 py-8 text-slate-500 text-xs relative z-10">
                <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
                    <div className="flex items-center gap-3">
                        <img src="/procksi-mark.png" alt="Procksi" className="w-6 h-6 grayscale opacity-70" />
                        <div className="flex flex-col">
                            <span className="font-bold text-slate-700 dark:text-slate-300">Procksi</span>
                            <span className="text-[10px] tracking-widest uppercase">Project Management Platform</span>
                        </div>
                    </div>
                    <div>© {new Date().getFullYear()} Procksi. All rights reserved.</div>
                </div>
            </footer>
        </div>
    );
}
