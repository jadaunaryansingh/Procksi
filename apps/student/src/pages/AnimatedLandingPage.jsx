import React, { useRef, useState } from 'react';
import { motion, useScroll, useTransform, useSpring, useMotionValueEvent, AnimatePresence } from 'framer-motion';
import LandingPage from './LandingPage';
import ScrollStory from '../components/ScrollStory';

export const AnimatedLandingPage = ({ onGetStarted, isDark, toggleTheme }) => {
    const landingRef = useRef(null);
    const scrollStoryRef = useRef(null);
    const [isStoryActive, setIsStoryActive] = useState(true);

    const scrollToLanding = () => {
        landingRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    // Track the scroll of the ScrollStory section
    const { scrollYProgress } = useScroll({
        target: scrollStoryRef,
        offset: ["start start", "end end"]
    });

    const smoothProgress = useSpring(scrollYProgress, {
        stiffness: 100,
        damping: 30,
        restDelta: 0.001
    });

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

    // X and Y Positioning (Moves from center-left to top-left)
    // We use consistent units (vw/vh) so Framer Motion can interpolate them correctly.
    // 24px is roughly 2vw and 3vh on average screens.
    const brandX = useTransform(smoothProgress, [0.75, 0.95], ["8vw", "1.5vw"]); 
    const brandY = useTransform(smoothProgress, [0.75, 0.95], ["15vh", "1.5vh"]); 

    // Scale down the entire container slightly
    const brandScale = useTransform(smoothProgress, [0.75, 0.95], [1, 0.7]);
    
    // Logo image size
    const logoSize = useTransform(smoothProgress, [0.75, 0.95], [64, 40]); // w-16 to w-10

    // Text sizes and margins
    const glaSize = useTransform(smoothProgress, [0.75, 0.95], ["1.5rem", "1.25rem"]); // text-2xl to text-xl
    const glaTracking = useTransform(smoothProgress, [0.75, 0.95], ["0.1em", "-0.025em"]); // tracking-widest to tracking-tight
    
    const pmsSize = useTransform(smoothProgress, [0.75, 0.95], ["2.5rem", "0.625rem"]); // scaled down from 3.2rem
    const pmsTracking = useTransform(smoothProgress, [0.75, 0.95], ["-0.02em", "0.1em"]); // slightly tighter initially
    const pmsTransform = useTransform(smoothProgress, [0.75, 0.95], ["none", "uppercase"]);
    const pmsWidth = useTransform(smoothProgress, [0.75, 0.95], ["12em", "35em"]); // forces wrap initially, then single line

    
    // Navbar specific adjustments
    const navbarTextOpacity = useTransform(smoothProgress, [0.85, 0.95], [0, 1]); // the "GLA University" native colors
    const heroTextOpacity = useTransform(smoothProgress, [0.85, 0.95], [1, 0]); // the "PMS PORTAL" big colors

    // Z-index needs to be high to go over navbar
    return (
        <div className="bg-slate-900 text-white min-h-screen relative font-sans selection:bg-indigo-500/30">
            
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
                    src="/GLA_University_logo.png" 
                    alt="GLA Logo" 
                    style={{ width: logoSize, height: logoSize }}
                    className="object-contain drop-shadow-md" 
                />
                <div className="flex flex-col">
                    {/* GLA University Text */}
                    <div className="relative">
                        <motion.span 
                            style={{ 
                                fontSize: glaSize, 
                                letterSpacing: glaTracking,
                                opacity: heroTextOpacity 
                            }} 
                            className="font-bold uppercase text-white whitespace-nowrap block"
                        >
                            GLA University
                        </motion.span>
                        {/* The Navbar version of GLA University that fades in */}
                        <motion.span 
                            style={{ 
                                fontSize: glaSize, 
                                letterSpacing: glaTracking,
                                opacity: navbarTextOpacity,
                                position: 'absolute',
                                top: 0,
                                left: 0
                            }} 
                            className="font-black text-slate-900 dark:text-white leading-none whitespace-nowrap block"
                        >
                            GLA University
                        </motion.span>
                    </div>

                    {/* PROJECT MANAGEMENT PORTAL Text */}
                    <div className="relative">
                        <motion.span 
                            style={{ 
                                fontSize: pmsSize, 
                                letterSpacing: pmsTracking,
                                color: brandColor,
                                textShadow: brandGlow,
                                opacity: heroTextOpacity,
                                width: pmsWidth
                            }} 
                            className="font-black leading-tight block mt-2"
                        >
                            PROJECT MANAGEMENT PORTAL
                        </motion.span>
                        {/* The Navbar version that fades in */}
                        <motion.span 
                            style={{ 
                                fontSize: pmsSize, 
                                letterSpacing: pmsTracking,
                                textTransform: pmsTransform,
                                opacity: navbarTextOpacity,
                                position: 'absolute',
                                top: 0,
                                left: 0,
                                width: pmsWidth
                            }} 
                            className="font-bold text-indigo-600 dark:text-indigo-400 mt-1 block"
                        >
                            Project Management Portal
                        </motion.span>
                    </div>
                </div>
            </motion.div>


            {/* Skip button (bottom right - perfectly covers the video watermark) */}
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
            <div ref={scrollStoryRef}>
                <ScrollStory smoothProgress={smoothProgress} />
            </div>

            {/* Original Landing Page Section */}
            <div ref={landingRef} className="relative z-10 bg-slate-900">
                <LandingPage onGetStarted={onGetStarted} isDark={isDark} toggleTheme={toggleTheme} hideLogo={true} forceDarkNavbar={isStoryActive} />
            </div>
        </div>
    );
};

export default AnimatedLandingPage;
