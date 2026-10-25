import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { BookOpen, Code, Trophy, Users, ArrowRight, Activity, Terminal, Shield, Star, Moon, Sun, Crown, Medal, Search, Bot, FileText, BarChart3, Users2 } from 'lucide-react';

export default function LandingPage({ onGetStarted, isDark, toggleTheme, hideLogo, forceDarkNavbar }) {
    const prefersReducedMotion = useReducedMotion();
    const [isScrolled, setIsScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 10);
        };
        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    const containerVariants = {
        hidden: { opacity: 0 },
        show: {
            opacity: 1,
            transition: { staggerChildren: prefersReducedMotion ? 0 : 0.1 }
        }
    };

    const itemVariants = {
        hidden: { opacity: 0, y: prefersReducedMotion ? 0 : 20 },
        show: { 
            opacity: 1, 
            y: 0, 
            transition: { type: "spring", stiffness: 300, damping: 24 } 
        }
    };

    // When forced dark (e.g. during scroll story), keep the navbar transparent and in dark mode
    const navClasses = forceDarkNavbar 
        ? 'bg-transparent py-6 text-white' 
        : (isScrolled ? 'bg-white/80 dark:bg-slate-950/80 backdrop-blur-md shadow-sm py-4' : 'bg-transparent py-6');

    return (
        <div className="min-h-screen text-slate-900 dark:text-slate-100 overflow-x-hidden relative selection:bg-indigo-500/30 font-sans transition-colors duration-300 bg-gradient-to-br from-slate-50 via-white to-indigo-50/40 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950">
            
            {/* Global Background & Ambient Pattern (Hidden during ScrollStory so it doesn't overlay the space theme) */}
            <div className={`fixed inset-0 pointer-events-none -z-20 transition-opacity duration-700 ${forceDarkNavbar ? 'opacity-0' : 'opacity-100'}`}>
                <div className="absolute inset-0 bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px] opacity-60 dark:opacity-20 mix-blend-multiply dark:mix-blend-lighten"></div>
                {!prefersReducedMotion && (
                    <>
                        <div className="absolute top-0 left-[20%] w-[50%] h-[50%] bg-purple-200/40 dark:bg-purple-600/20 rounded-full blur-[120px] mix-blend-multiply dark:mix-blend-screen"></div>
                        <div className="absolute top-[20%] right-[-10%] w-[40%] h-[40%] bg-indigo-200/40 dark:bg-indigo-600/20 rounded-full blur-[100px] mix-blend-multiply dark:mix-blend-screen"></div>
                        <div className="absolute bottom-[10%] left-[-10%] w-[40%] h-[40%] bg-blue-100/40 dark:bg-cyan-600/20 rounded-full blur-[120px] mix-blend-multiply dark:mix-blend-screen"></div>
                    </>
                )}
            </div>

            {/* Navbar Wrapper for Dark Mode Forcing */}
            <div className={forceDarkNavbar ? "dark" : ""}>
                <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${navClasses}`}>
                    <div className="max-w-7xl mx-auto px-6 flex justify-between items-center gap-4">
                    {/* Brand */}
                    <div className={`flex items-center gap-3 shrink-0 transition-opacity duration-500 ${hideLogo ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
                        <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-10 h-10 object-contain drop-shadow-sm" />
                        <div className="flex flex-col">
                            <span className="text-xl font-black tracking-tight text-slate-900 dark:text-white leading-none">GLA University</span>
                            <span className="text-[10px] text-indigo-600 dark:text-indigo-400 font-bold tracking-widest uppercase mt-1">PMS Portal</span>
                        </div>
                    </div>
                    
                    {/* Nav Links */}
                    <div className="hidden lg:flex items-center gap-8 flex-1 justify-center">
                        <a href="#features" className="text-sm font-semibold text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Features</a>
                        <a href="#workflow" className="text-sm font-semibold text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Workflow</a>
                        <a href="#team" className="text-sm font-semibold text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Team</a>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-4 shrink-0">
                        <button 
                            onClick={toggleTheme}
                            className="p-2 rounded-full text-slate-500 hover:bg-slate-200/50 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
                            aria-label="Toggle Dark Mode"
                        >
                            {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                        </button>
                        <button 
                            onClick={onGetStarted}
                            className="flex items-center gap-2 bg-slate-900 dark:bg-indigo-600 text-white hover:bg-slate-800 dark:hover:bg-indigo-700 px-5 py-2.5 rounded-full text-sm font-bold transition-all shadow-md hover:shadow-lg active:scale-95"
                        >
                            <ArrowRight className="w-4 h-4" />
                            Student Login
                        </button>
                    </div>
                </div>
            </nav>
            </div>

            <main className="relative z-10 pt-32 lg:pt-40 pb-20">
                {/* Hero Section */}
                <section className="max-w-7xl mx-auto px-6 mb-20 lg:mb-32">
                    <div className="flex flex-col lg:flex-row items-center justify-between gap-16 lg:gap-8">
                        
                        {/* Hero Text */}
                        <motion.div 
                            initial="hidden"
                            animate="show"
                            variants={containerVariants}
                            className="flex-1 w-full max-w-2xl text-center lg:text-left z-10"
                        >
                            <motion.div variants={itemVariants} className="mb-4 inline-block">
                                <span className="text-sm font-bold text-slate-600 dark:text-slate-300 tracking-tight">GLA PMS: Elevating College Cohorts</span>
                            </motion.div>
                            
                            <motion.div variants={itemVariants}>
                                <h1 className="text-5xl md:text-6xl lg:text-7xl font-extrabold mb-6 tracking-tighter leading-[1.05] text-slate-800 dark:text-white">
                                    Build, Ship, and Lead Your Semester Project.
                                </h1>
                            </motion.div>

                            <motion.div variants={itemVariants}>
                                <p className="text-lg text-slate-600 dark:text-slate-400 mb-8 max-w-lg mx-auto lg:mx-0 leading-relaxed">
                                    Form teams, submit proposals, and get instantaneous AI code analysis. The all-in-one platform engineered for modern college cohorts.
                                </p>
                            </motion.div>



                            <motion.div variants={itemVariants} className="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-4">
                                <button 
                                    onClick={onGetStarted}
                                    className="w-full sm:w-auto flex items-center justify-center px-8 py-4 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 rounded-xl font-bold text-base transition-all shadow-xl hover:-translate-y-0.5 group"
                                >
                                    Get Started
                                    <ArrowRight className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" />
                                </button>
                                <a 
                                    href="#workflow"
                                    className="w-full sm:w-auto flex items-center justify-center px-8 py-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-xl font-bold text-base transition-all shadow-sm"
                                >
                                    Explore Workflow
                                </a>
                            </motion.div>
                        </motion.div>

                        {/* Hero Visual Mockup */}
                        <motion.div 
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2, duration: 0.8 }}
                            className="flex-1 w-full max-w-lg lg:max-w-[600px] relative z-10"
                        >
                            <div className="relative bg-white/80 dark:bg-slate-900/40 backdrop-blur-xl rounded-2xl shadow-2xl shadow-slate-200/50 dark:shadow-[0_0_50px_-12px_rgba(79,70,229,0.15)] border border-white/40 dark:border-white/10 overflow-hidden aspect-[4/3] flex flex-col transform">
                                {/* Window Header */}
                                <div className="flex items-center justify-between px-4 py-3 bg-slate-50/50 dark:bg-slate-800/30 border-b border-white/20 dark:border-white/5">
                                    <div className="flex gap-2">
                                        <div className="w-3 h-3 rounded-full bg-rose-400"></div>
                                        <div className="w-3 h-3 rounded-full bg-amber-400"></div>
                                        <div className="w-3 h-3 rounded-full bg-emerald-400"></div>
                                    </div>
                                    <div className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full flex items-center gap-1 shadow-sm">
                                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
                                        Status: Panel Evaluation Pending
                                    </div>
                                </div>
                                
                                {/* Mock Dashboard Content */}
                                <div className="flex-1 p-6 relative flex gap-6">
                                    {/* Sidebar Avatars */}
                                    <div className="flex flex-col gap-4">
                                        <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center overflow-hidden border-2 border-white shadow-sm"><img src="https://api.dicebear.com/7.x/micah/svg?seed=Felix" alt="avatar" /></div>
                                        <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center overflow-hidden border-2 border-white shadow-sm"><img src="https://api.dicebear.com/7.x/micah/svg?seed=Aneka" alt="avatar" /></div>
                                        <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center overflow-hidden border-2 border-white shadow-sm"><img src="https://api.dicebear.com/7.x/micah/svg?seed=Liam" alt="avatar" /></div>
                                    </div>

                                    {/* Main Cards */}
                                    <div className="flex-1 flex flex-col gap-5">
                                        <div className="flex gap-4">
                                            {/* Current Rank Card */}
                                            <div className="flex-1 bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-xl p-5 border border-indigo-100/50 dark:border-indigo-500/20 shadow-sm relative overflow-hidden">
                                                <div className="absolute right-0 top-0 w-24 h-24 bg-indigo-400/10 rounded-full blur-xl"></div>
                                                <div className="text-4xl font-mono font-bold text-indigo-700 dark:text-indigo-400 mb-1">2<span className="text-lg text-indigo-400">nd</span></div>
                                                <div className="text-[10px] text-slate-500 dark:text-slate-400 font-bold tracking-widest uppercase">Current Rank</div>
                                            </div>
                                            
                                            {/* Predicted Score Card */}
                                            <div className="flex-1 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl p-5 border border-emerald-100 dark:border-emerald-500/20 shadow-sm relative overflow-hidden">
                                                <div className="absolute right-0 top-0 w-24 h-24 bg-emerald-400/10 rounded-full blur-xl"></div>
                                                <div className="text-4xl font-mono font-bold text-slate-800 dark:text-white mb-1">92</div>
                                                <div className="text-[10px] text-emerald-700/80 dark:text-emerald-400/80 font-bold tracking-widest uppercase">Predicted Score</div>
                                            </div>
                                        </div>

                                        {/* Tech Stack Badges */}
                                        <div className="flex gap-2">
                                            <span className="bg-slate-100 text-slate-600 text-xs px-3 py-1 rounded-full font-bold dark:bg-slate-800 dark:text-slate-300">React</span>
                                            <span className="bg-slate-100 text-slate-600 text-xs px-3 py-1 rounded-full font-bold dark:bg-slate-800 dark:text-slate-300">Tailwind CSS</span>
                                            <span className="bg-slate-100 text-slate-600 text-xs px-3 py-1 rounded-full font-bold dark:bg-slate-800 dark:text-slate-300">FastAPI</span>
                                            <span className="bg-slate-100 text-slate-600 text-xs px-3 py-1 rounded-full font-bold dark:bg-slate-800 dark:text-slate-300">MongoDB</span>
                                        </div>

                                        {/* Mentor Tracking Feed */}
                                        <div className="flex-1 bg-slate-50/50 dark:bg-slate-800/30 rounded-xl border border-slate-100/50 dark:border-slate-700/30 p-4 flex flex-col gap-3 justify-center">
                                            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">✓ Proposal approved by Mentor</p>
                                            <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">✓ Mid-term progress logged</p>
                                            <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">⏳ Awaiting final panel scoring</p>
                                        </div>

                                        {/* Milestone Progress Bar */}
                                        <div>
                                            <div className="h-2 w-full bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                                                <div className="h-full w-3/4 bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Floating Top Right Card */}
                            <motion.div 
                                initial={{ y: -20, opacity: 0 }}
                                animate={{ y: 0, opacity: 1 }}
                                transition={{ delay: 0.6 }}
                                className="absolute -top-6 -right-6 bg-white dark:bg-slate-800 p-3 rounded-2xl shadow-xl border border-slate-100 dark:border-slate-700 flex flex-col items-center gap-2 transform rotate-3"
                            >
                                <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-10 h-10 object-contain" />
                                <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300">GLA Community</span>
                            </motion.div>

                            {/* Floating Bottom Left Team Avatars */}
                            <motion.div 
                                initial={{ x: -20, opacity: 0 }}
                                animate={{ x: 0, opacity: 1 }}
                                transition={{ delay: 0.8 }}
                                className="absolute -bottom-4 left-8 bg-white dark:bg-slate-800 p-2 rounded-full shadow-lg border border-slate-100 dark:border-slate-700 flex items-center"
                            >
                                <div className="flex -space-x-2">
                                    <div className="w-8 h-8 rounded-full bg-pink-100 border-2 border-white overflow-hidden"><img src="https://api.dicebear.com/7.x/micah/svg?seed=1" alt="t1" /></div>
                                    <div className="w-8 h-8 rounded-full bg-blue-100 border-2 border-white overflow-hidden"><img src="https://api.dicebear.com/7.x/micah/svg?seed=2" alt="t2" /></div>
                                    <div className="w-8 h-8 rounded-full bg-yellow-100 border-2 border-white overflow-hidden"><img src="https://api.dicebear.com/7.x/micah/svg?seed=3" alt="t3" /></div>
                                    <div className="w-8 h-8 rounded-full bg-purple-100 border-2 border-white overflow-hidden"><img src="https://api.dicebear.com/7.x/micah/svg?seed=4" alt="t4" /></div>
                                </div>
                            </motion.div>

                            {/* Floating Dark Terminal */}
                            <motion.div 
                                initial={{ y: 20, opacity: 0 }}
                                animate={{ y: 0, opacity: 1 }}
                                transition={{ delay: 1 }}
                                className="absolute -bottom-10 -right-4 w-64 bg-slate-900 rounded-xl shadow-2xl border border-slate-700 overflow-hidden transform -rotate-2"
                            >
                                <div className="flex items-center px-3 py-2 bg-slate-950 border-b border-slate-800">
                                    <div className="flex gap-1.5">
                                        <div className="w-2.5 h-2.5 rounded-full bg-rose-500"></div>
                                        <div className="w-2.5 h-2.5 rounded-full bg-amber-500"></div>
                                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500"></div>
                                    </div>
                                </div>
                                <div className="p-4 font-mono text-[10px] leading-relaxed text-slate-300">
                                    <p><span className="text-pink-400">const</span> <span className="text-yellow-300">engine</span> = <span className="text-pink-400">new</span> <span className="text-yellow-300">Scanner</span>();</p>
                                    <p><span className="text-pink-400">await</span> <span className="text-yellow-300">engine.analyze</span>(repo);</p>
                                    <p className="text-slate-400 mt-2">Running vulnerability scan...</p>
                                    <p className="text-emerald-400 font-bold mt-1">✓ Security checks passed</p>
                                    <p className="mt-2 text-slate-300">Deploying... <span className="animate-pulse text-white">_</span></p>
                                </div>
                            </motion.div>
                        </motion.div>
                    </div>
                </section>

                {/* Stats Banner */}
                <div className="border-y border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm py-6">
                    <div className="max-w-5xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-6">
                        <div className="flex items-center gap-3 text-sm font-bold text-slate-700 dark:text-slate-300">
                            <Users2 className="w-5 h-5 text-indigo-500" /> 500+ Students Collaborating
                        </div>
                        <div className="hidden md:block w-px h-6 bg-slate-200 dark:bg-slate-700"></div>
                        <div className="flex items-center gap-3 text-sm font-bold text-slate-700 dark:text-slate-300">
                            <Code className="w-5 h-5 text-emerald-500" /> 120+ Teams Analysed
                        </div>
                        <div className="hidden md:block w-px h-6 bg-slate-200 dark:bg-slate-700"></div>
                        <div className="flex items-center gap-3 text-sm font-bold text-slate-700 dark:text-slate-300">
                            <Trophy className="w-5 h-5 text-amber-500" /> Live Global Rankings
                        </div>
                    </div>
                </div>

                {/* Everything You Need Grid */}
                <section id="features" className="py-24">
                    <div className="max-w-6xl mx-auto px-6">
                        <div className="text-center md:text-left mb-16">
                            <h2 className="text-3xl md:text-4xl font-extrabold mb-4 tracking-tight">Everything You Need To Ship.</h2>
                        </div>

                        <motion.div 
                            initial="hidden"
                            whileInView="show"
                            viewport={{ once: true, margin: "-50px" }}
                            variants={containerVariants}
                            className="grid grid-cols-1 md:grid-cols-2 gap-6"
                        >
                            <FeatureCard 
                                icon={<Users className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />}
                                title="Formulate & Propose"
                                desc="Lock in your team and submit your abstracts directly to faculty mentors."
                                prefersReducedMotion={prefersReducedMotion}
                            />
                            <FeatureCard 
                                icon={<Users2 className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />}
                                title="Guided Tracking"
                                desc="Receive direct feedback, get unblocked, and log sprint progress with your assigned mentor."
                                prefersReducedMotion={prefersReducedMotion}
                            />
                            <FeatureCard 
                                icon={<BookOpen className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />}
                                title="Formal Evaluation"
                                desc="Present your final build to the academic panel for mid-term and final grading."
                                prefersReducedMotion={prefersReducedMotion}
                            />
                            <FeatureCard 
                                icon={<div className="flex items-end gap-1 text-indigo-600 dark:text-indigo-400"><Trophy className="w-8 h-8" /><Trophy className="w-5 h-5 opacity-70 mb-1" /><Trophy className="w-6 h-6 opacity-80 mb-1" /></div>}
                                title="Cohort Rankings"
                                desc="See where your project stands against the rest of the university cohort in real-time."
                                prefersReducedMotion={prefersReducedMotion}
                            />
                        </motion.div>
                    </div>
                </section>

                {/* How it Works - Horizontal */}
                <section id="workflow" className="py-24 bg-white/40 dark:bg-slate-900/40 border-y border-slate-100 dark:border-slate-800 backdrop-blur-sm">
                    <div className="max-w-7xl mx-auto px-6">
                        <div className="text-center mb-16">
                            <h2 className="text-3xl font-extrabold tracking-tight">How it Works</h2>
                        </div>
                        
                        <div className="relative">
                            {/* Connecting Line (desktop only) */}
                            <div className="hidden md:block absolute top-12 left-[10%] right-[10%] h-0.5 bg-indigo-100 dark:bg-slate-800 -z-10"></div>
                            
                            <div className="flex flex-col md:flex-row justify-between items-start gap-6 relative z-10">
                                {[
                                    { icon: Users, title: 'Login & Assemble', desc: 'Authenticate and form your official team.' },
                                    { icon: FileText, title: 'Propose', desc: 'Submit your project pitch for mentor approval.' },
                                    { icon: Activity, title: 'Build & Track', desc: 'Develop your project while the mentor tracks progress.' },
                                    { icon: Search, title: 'Evaluate', desc: 'Present to the panel for mid and final reviews.' },
                                    { icon: Trophy, title: 'Rank', desc: 'Final scores are tallied and pushed to the live leaderboard.' }
                                ].map((item, idx) => {
                                    const Icon = item.icon;
                                    return (
                                        <motion.div 
                                            key={idx}
                                            initial={{ opacity: 0, y: prefersReducedMotion ? 0 : 20 }}
                                            whileInView={{ opacity: 1, y: 0 }}
                                            viewport={{ once: true, margin: "-50px" }}
                                            transition={{ delay: prefersReducedMotion ? 0 : idx * 0.1 }}
                                            className="flex-1 flex flex-col items-center text-center w-full bg-white md:bg-transparent dark:bg-slate-800 md:dark:bg-transparent rounded-2xl md:rounded-none p-6 md:p-0 shadow-sm md:shadow-none border border-slate-200 md:border-transparent dark:border-slate-700 md:dark:border-transparent"
                                        >
                                            <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-full flex items-center justify-center mb-6 shadow-sm border border-slate-100 dark:border-slate-700">
                                                <span className="text-indigo-700 dark:text-indigo-300 font-bold bg-indigo-100 dark:bg-indigo-900/50 w-8 h-8 flex items-center justify-center rounded-full text-xs">
                                                    <Icon className="w-4 h-4" />
                                                </span>
                                            </div>
                                            <h3 className="font-bold text-lg mb-2">{item.title}</h3>
                                            <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed max-w-[200px]">{item.desc}</p>
                                        </motion.div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </section>

                {/* Performance & Leaderboard */}
                <section className="py-24">
                    <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-16 items-center">
                        <div>
                            <h2 className="text-3xl font-extrabold mb-10 tracking-tight">Built for Performance.</h2>
                            <div className="space-y-8">
                                <div className="flex gap-4">
                                    <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
                                        <Activity className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                                    </div>
                                    <div>
                                        <h4 className="font-bold text-lg mb-1">WebSockets Native</h4>
                                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">Experience zero latency updates. Job statuses and leaderboard ranks stream directly to your client without polling.</p>
                                    </div>
                                </div>
                                <div className="flex gap-4">
                                    <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
                                        <Star className="w-5 h-5 text-slate-600 dark:text-slate-400" />
                                    </div>
                                    <div>
                                        <h4 className="font-bold text-lg mb-1">Mentor Feedback Loop</h4>
                                        <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">Receive structured, actionable feedback from your assigned mentor directly within the portal interface.</p>
                                        <div className="flex -space-x-2 mt-3">
                                            <img className="w-6 h-6 rounded-full border border-white" src="https://api.dicebear.com/7.x/avataaars/svg?seed=M1" alt="m1" />
                                            <img className="w-6 h-6 rounded-full border border-white" src="https://api.dicebear.com/7.x/avataaars/svg?seed=M2" alt="m2" />
                                            <img className="w-6 h-6 rounded-full border border-white" src="https://api.dicebear.com/7.x/avataaars/svg?seed=M3" alt="m3" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Flat Mockup Leaderboard */}
                        <div className="bg-slate-50/80 dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 p-8 shadow-sm">
                            <h3 className="text-center font-bold text-slate-500 text-xs tracking-widest uppercase mb-10">Global Rankings</h3>
                            
                            <div className="flex justify-center items-end h-48 gap-4 w-full max-w-md mx-auto">
                                {/* 2nd Place */}
                                <div className="flex flex-col items-center w-1/3">
                                    <Medal className="w-6 h-6 text-slate-400 mb-2" />
                                    <p className="font-bold text-xs text-center mb-1">Team Alpha</p>
                                    <span className="text-[10px] font-bold text-indigo-500 mb-2">92 pts</span>
                                    <div className="w-full bg-gradient-to-t from-slate-200 to-slate-300 dark:from-slate-700 dark:to-slate-600 h-24 rounded-t-xl flex justify-center items-center shadow-sm">
                                        <span className="font-bold text-slate-500 dark:text-slate-400 text-2xl">2</span>
                                    </div>
                                </div>

                                {/* 1st Place */}
                                <div className="flex flex-col items-center w-1/3">
                                    <Crown className="w-8 h-8 text-yellow-500 mb-2" />
                                    <p className="font-bold text-sm text-center mb-1">Code Ninjas</p>
                                    <span className="text-xs font-bold text-amber-500 bg-amber-50 dark:bg-amber-500/10 px-2 py-0.5 rounded-full mb-2">98 pts</span>
                                    <div className="w-full bg-gradient-to-t from-yellow-400 to-amber-500 h-32 rounded-t-xl flex justify-center items-center shadow-xl shadow-amber-500/20">
                                        <span className="font-bold text-white text-3xl drop-shadow-sm">1</span>
                                    </div>
                                </div>

                                {/* 3rd Place */}
                                <div className="flex flex-col items-center w-1/3">
                                    <Medal className="w-6 h-6 text-orange-400 mb-2" />
                                    <p className="font-bold text-xs text-center mb-1">Byte Me</p>
                                    <span className="text-[10px] font-bold text-indigo-500 mb-2">89 pts</span>
                                    <div className="w-full bg-gradient-to-t from-orange-300 to-orange-400 dark:from-orange-800 dark:to-orange-700 h-20 rounded-t-xl flex justify-center items-center shadow-sm">
                                        <span className="font-bold text-orange-100 text-2xl">3</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>



                {/* Log Testimonials */}
                <section className="py-24 bg-gradient-to-b from-transparent to-indigo-50/30 dark:to-indigo-900/10 border-t border-slate-100 dark:border-slate-800">
                    <div className="max-w-6xl mx-auto px-6">
                        <div className="grid md:grid-cols-2 gap-8">
                            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 shadow-sm">
                                <div className="text-[10px] font-mono text-slate-400 flex items-center gap-2 mb-4">
                                    <ArrowRight className="w-3 h-3" /> student_feedback.log
                                </div>
                                <p className="text-slate-800 dark:text-slate-200 text-sm font-medium leading-relaxed mb-6">
                                    "The AI analysis gave us exactly what we needed to fix our security flaws before the final submission. It feels like having an automated TA."
                                </p>
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-600">AS</div>
                                    <div>
                                        <div className="text-xs font-bold">Alex S.</div>
                                        <div className="text-[10px] text-slate-500">Computer Science, Year 3</div>
                                    </div>
                                </div>
                            </div>
                            
                            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-8 shadow-sm">
                                <div className="text-[10px] font-mono text-slate-400 flex items-center gap-2 mb-4">
                                    <ArrowRight className="w-3 h-3" /> student_feedback.log
                                </div>
                                <p className="text-slate-800 dark:text-slate-200 text-sm font-medium leading-relaxed mb-6">
                                    "Checking the live leaderboard became an obsession for our team. We pushed 3 extra commits just to secure the top podium spot."
                                </p>
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center text-xs font-bold text-emerald-600">MJ</div>
                                    <div>
                                        <div className="text-xs font-bold">Maya J.</div>
                                        <div className="text-[10px] text-slate-500">Software Eng, Year 4</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
            </main>

            {/* Simple Footer */}
            <footer className="relative z-10 bg-white dark:bg-[#020617] border-t border-slate-200 dark:border-slate-800 py-8 text-slate-500 text-xs">
                <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
                    <div className="flex items-center gap-3">
                        <img src="/GLA_University_logo.png" alt="GLA Logo" className="w-6 h-6 grayscale opacity-70" />
                        <div className="flex flex-col">
                            <span className="font-bold text-slate-700 dark:text-slate-300">GLA University</span>
                            <span className="text-[10px] tracking-widest uppercase">PMS Portal</span>
                        </div>
                    </div>
                    
                    <div>© {new Date().getFullYear()} GLA Project Management System. All rights reserved.</div>
                    
                    <div className="flex gap-6">
                        <a href="#" className="hover:text-slate-800 dark:hover:text-white transition-colors">Privacy Policy</a>
                        <a href="#" className="hover:text-slate-800 dark:hover:text-white transition-colors">Terms of Service</a>
                    </div>
                </div>
            </footer>

        </div>
    );
}

function FeatureCard({ icon, title, desc, prefersReducedMotion }) {
    return (
        <motion.div 
            whileHover={prefersReducedMotion ? {} : { y: -4 }}
            className="p-8 rounded-2xl bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-xl hover:shadow-indigo-500/10 dark:hover:shadow-indigo-500/5 transition-all duration-300"
        >
            <div className="mb-6 relative h-16 flex items-center">
                {icon}
            </div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">{title}</h3>
            <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">{desc}</p>
        </motion.div>
    );
}
