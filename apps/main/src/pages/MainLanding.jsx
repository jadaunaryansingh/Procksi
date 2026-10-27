import React, { useRef, useState } from 'react';
import { motion, useScroll, useTransform, useMotionValueEvent, AnimatePresence, useInView } from 'framer-motion';
import ScrollStory from '../components/ScrollStory';
import MagicDeck from '../components/MagicDeck';
import LiveMetrics from '../components/LiveMetrics';
import BentoFeatures from '../components/BentoFeatures';
import LifecycleTimeline from '../components/LifecycleTimeline';
import { ArrowRight, UserCheck, Users, Sun, Moon } from 'lucide-react';
import { portalUrl } from '../lib/portalUrls';

export const MainLanding = ({ isDark, toggleTheme }) => {
    const landingRef = useRef(null);
    const scrollStoryRef = useRef(null);
    const magicDeckRef = useRef(null);
    // Requires the top of the element to reach the middle of the screen to trigger
    const isMagicDeckInView = useInView(magicDeckRef, { margin: "-40% 0px -40% 0px" });
    const [isStoryActive, setIsStoryActive] = useState(true);

    const scrollToLanding = () => {
        landingRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    // Track the scroll of the ScrollStory section
    const { scrollYProgress } = useScroll({
        target: scrollStoryRef,
        offset: ["start start", "end end"]
    });

    // Since you are using Lenis (SmoothScroll.jsx) globally, the scroll is ALREADY smoothed!
    // Applying useSpring on top of Lenis creates "double physics" which causes that laggy, stuttering tail 
    // at the end of a scroll. We can just use the naturally smoothed scrollYProgress directly.
    const smoothProgress = scrollYProgress;

    useMotionValueEvent(smoothProgress, "change", (latest) => {
        setIsStoryActive(latest < 0.95);
    });

    // --- DYNAMIC BRANDING (GLOBALLY FIXED) ---
    // Color shift
    const brandColor = useTransform(smoothProgress, [0, 0.3, 0.6, 0.9], ["#22d3ee", "#6366f1", "#a855f7", "#10b981"]);
    const brandGlow = useTransform(smoothProgress, 
        [0, 0.3, 0.6, 0.8, 0.9], 
        [
            "0px 0px 30px rgba(34, 211, 238, 0.4)", 
            "0px 0px 30px rgba(99, 102, 241, 0.4)", 
            "0px 0px 30px rgba(168, 85, 247, 0.4)", 
            "0px 0px 30px rgba(16, 185, 129, 0.4)",
            "0px 0px 0px rgba(0,0,0,0)" // Glow fades out at navbar
        ]
    );

    // X and Y Positioning
    const brandX = useTransform(smoothProgress, [0.75, 0.95], ["8vw", "1.5vw"]); 
    const brandY = useTransform(smoothProgress, [0.75, 0.95], ["15vh", "1.5vh"]); 

    // Scale down the entire container slightly
    const brandScale = useTransform(smoothProgress, [0.75, 0.95], [1, 0.7]);
    
    // Logo image size
    const logoSize = useTransform(smoothProgress, [0.75, 0.95], [64, 40]); // w-16 to w-10

    // Text sizes and margins
    const brandSize = useTransform(smoothProgress, [0.75, 0.95], ["1.5rem", "1.25rem"]); // text-2xl to text-xl
    const brandTracking = useTransform(smoothProgress, [0.75, 0.95], ["0.1em", "-0.025em"]); // tracking-widest to tracking-tight
    
    const procksiSize = useTransform(smoothProgress, [0.75, 0.95], ["2.5rem", "0.625rem"]); // scaled down from 3.2rem
    const procksiTracking = useTransform(smoothProgress, [0.75, 0.95], ["-0.02em", "0.1em"]); // slightly tighter initially
    const procksiTransform = useTransform(smoothProgress, [0.75, 0.95], ["none", "uppercase"]);
    const procksiWidth = useTransform(smoothProgress, [0.75, 0.95], ["12em", "35em"]); // forces wrap initially, then single line

    // Navbar specific adjustments
    const navbarTextOpacity = useTransform(smoothProgress, [0.85, 0.95], [0, 1]); // the "Procksi" native colors
    const heroTextOpacity = useTransform(smoothProgress, [0.85, 0.95], [1, 0]); // the "PROCKSI" big colors

    return (
        <div className="bg-slate-900 text-white min-h-screen relative font-sans selection:bg-indigo-500/30">
            
            {/* Navbar Controls (Theme Toggle) */}
            <div className="fixed top-6 right-6 z-[60] flex items-center gap-4">
                <button 
                    onClick={toggleTheme}
                    className="p-2 rounded-full text-white/50 hover:bg-white/10 transition-colors"
                    aria-label="Toggle Dark Mode"
                >
                    {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                </button>
            </div>

            {/* --- GLOBALLY FIXED BRANDING LAYER --- */}
            <motion.div 
                style={{ 
                    position: 'fixed',
                    left: brandX,
                    top: brandY,
                    scale: brandScale,
                    zIndex: 100, // Above navbar (z-50)
                    transformOrigin: "top left"
                }}
                className="pointer-events-none flex flex-row items-start gap-4"
            >
                <motion.img 
                    src="/procksi-mark.png" 
                    alt="Procksi" 
                    style={{ width: logoSize, height: logoSize }}
                    className="object-contain drop-shadow-md" 
                />
                <div className="flex flex-col">
                    {/* Procksi Text */}
                    <div className="relative">
                        <motion.span 
                            style={{ 
                                fontSize: brandSize, 
                                letterSpacing: brandTracking,
                                opacity: heroTextOpacity 
                            }} 
                            className="font-bold uppercase text-white whitespace-nowrap block"
                        >
                            Procksi
                        </motion.span>
                        <motion.span 
                            style={{ 
                                fontSize: brandSize, 
                                letterSpacing: brandTracking,
                                opacity: navbarTextOpacity,
                                position: 'absolute',
                                top: 0,
                                left: 0
                            }} 
                            className={`font-black leading-none whitespace-nowrap block transition-colors duration-500 ${isMagicDeckInView ? 'text-white' : 'text-slate-900 dark:text-white'}`}
                        >
                            Procksi
                        </motion.span>
                    </div>

                    {/* PROJECT MANAGEMENT PLATFORM Text */}
                    <div className="relative">
                        <motion.span 
                            style={{ 
                                fontSize: procksiSize, 
                                letterSpacing: procksiTracking,
                                color: brandColor,
                                textShadow: brandGlow,
                                opacity: heroTextOpacity,
                                width: procksiWidth
                            }} 
                            className="font-black leading-tight block mt-2"
                        >
                            PROJECT MANAGEMENT PLATFORM
                        </motion.span>
                        <motion.span 
                            style={{ 
                                fontSize: procksiSize, 
                                letterSpacing: procksiTracking,
                                textTransform: procksiTransform,
                                opacity: navbarTextOpacity,
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                width: procksiWidth
                            }} 
                            className={`font-bold mt-1 block transition-colors duration-500 ${isMagicDeckInView ? 'text-indigo-300' : 'text-indigo-600 dark:text-indigo-400'}`}
                        >
                            Project Management Platform
                        </motion.span>
                    </div>
                </div>
            </motion.div>

            {/* Skip button */}
            <AnimatePresence>
                {isStoryActive && (
                    <motion.div 
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0, scale: 0.8, transition: { duration: 0.4 } }}
                        className="fixed bottom-[10vh] right-[4vw] lg:bottom-[12vh] lg:right-[5vw] z-[60] flex justify-end items-center pointer-events-none"
                    >
                        <button 
                            onClick={scrollToLanding}
                            className="pointer-events-auto px-8 py-4 bg-slate-900/80 hover:bg-slate-800 backdrop-blur-xl border border-slate-700/50 rounded-full text-base font-bold transition-all shadow-[0_0_40px_rgba(0,0,0,0.8)] text-white hover:scale-105"
                        >
                            Skip Animation
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Scrollytelling Section */}
            <div ref={scrollStoryRef} className="relative">
                <ScrollStory smoothProgress={smoothProgress} />
            </div>

            {/* Entry Portals Section */}
            <div ref={landingRef} className="relative z-10 bg-slate-50 dark:bg-[#020617] text-slate-900 dark:text-white min-h-screen flex flex-col transition-colors duration-300">
                <div className="flex-1 max-w-7xl mx-auto px-6 w-full py-32 flex flex-col items-center justify-center relative">
                    
                    <motion.div 
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        className="text-center mb-16 relative z-20"
                    >
                        <h2 className="text-4xl md:text-5xl font-black tracking-tight mb-4 text-slate-800 dark:text-white">
                            Select Your Workspace
                        </h2>
                        <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
                            Choose your role to access the dedicated tools and dashboards for Procksi.
                        </p>
                    </motion.div>

                    <div className="grid md:grid-cols-2 gap-8 w-full max-w-4xl relative z-20">
                        {/* Student Portal Card */}
                        <motion.a 
                            href={portalUrl('student')}
                            whileHover={{ y: -8 }}
                            className="group flex flex-col p-10 rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl hover:shadow-indigo-500/10 dark:hover:shadow-indigo-500/10 transition-all cursor-pointer relative overflow-hidden"
                        >
                            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 dark:bg-indigo-500/5 rounded-full blur-3xl group-hover:bg-indigo-500/20 transition-all"></div>
                            <div className="w-16 h-16 bg-indigo-100 dark:bg-indigo-900/50 rounded-2xl flex items-center justify-center mb-8 shadow-sm">
                                <Users className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
                            </div>
                            <h3 className="text-3xl font-extrabold mb-3 text-slate-900 dark:text-white">Student Portal</h3>
                            <p className="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                                Form teams, submit proposals, track milestones, and view your live cohort rankings.
                            </p>
                            <div className="mt-auto flex items-center text-indigo-600 dark:text-indigo-400 font-bold group-hover:gap-3 transition-all gap-2">
                                Enter Workspace <ArrowRight className="w-5 h-5" />
                            </div>
                        </motion.a>

                        {/* Staff Portal Card */}
                        <motion.a 
                            href="/staff"
                            whileHover={{ y: -8 }}
                            className="group flex flex-col p-10 rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl hover:shadow-purple-500/10 dark:hover:shadow-purple-500/10 transition-all cursor-pointer relative overflow-hidden"
                        >
                            <div className="absolute top-0 right-0 w-64 h-64 bg-purple-500/10 dark:bg-purple-500/5 rounded-full blur-3xl group-hover:bg-purple-500/20 transition-all"></div>
                            <div className="w-16 h-16 bg-purple-100 dark:bg-purple-900/50 rounded-2xl flex items-center justify-center mb-8 shadow-sm">
                                <UserCheck className="w-8 h-8 text-purple-600 dark:text-purple-400" />
                            </div>
                            <h3 className="text-3xl font-extrabold mb-3 text-slate-900 dark:text-white">Staff Portal</h3>
                            <p className="text-slate-600 dark:text-slate-400 mb-8 leading-relaxed">
                                Access Admin, Mentor, and Evaluation Panel tools to guide and grade student projects.
                            </p>
                            <div className="mt-auto flex items-center text-purple-600 dark:text-purple-400 font-bold group-hover:gap-3 transition-all gap-2">
                                Staff Login Options <ArrowRight className="w-5 h-5" />
                            </div>
                        </motion.a>
                    </div>

                </div>

                <LiveMetrics />
                <BentoFeatures />
                <LifecycleTimeline />

                {/* Team Details Animation (MagicDeck) */}
                <div ref={magicDeckRef} className="w-full relative z-10 border-t border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/30 backdrop-blur-sm pt-20 pb-32">
                    <div className="max-w-7xl mx-auto px-6 mb-16 text-center">
                        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                            Discover Top Projects
                        </h2>
                        <p className="text-slate-600 dark:text-slate-400 mt-3">
                            Swipe through the highest-ranking teams from previous semesters.
                        </p>
                    </div>
                    <MagicDeck />
                </div>

                {/* Simple Footer */}
                <footer className="relative z-10 bg-white dark:bg-[#020617] border-t border-slate-200 dark:border-slate-800 py-8 text-slate-500 text-xs mt-auto">
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
        </div>
    );
};

export default MainLanding;
