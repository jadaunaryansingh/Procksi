import React, { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { Lightbulb, Edit3, GitPullRequest, Award } from 'lucide-react';

// Extracted from the phases.map callback below. useTransform was being called
// inside that callback, so the number of hooks executed depended on the length
// of `phases` — React identifies hooks by call order, and a list whose length
// changes would misalign every hook after it. One component per node keeps the
// hook count fixed at one per render.
function TimelineNode({ phase, idx, scrollYProgress }) {
    const isEven = idx % 2 === 0;
    const Icon = phase.icon;

    const nodeActivationStart = idx * 0.25;
    const isActive = useTransform(
        scrollYProgress,
        [nodeActivationStart, nodeActivationStart + 0.1],
        [0, 1]
    );

    return (
        <div className="relative flex flex-col md:flex-row items-start md:items-center gap-8 md:gap-0">
            {/* Left side text (Even indices) */}
            <div className={`md:w-1/2 ${isEven ? 'md:pr-16 md:text-right flex flex-col md:items-end pl-24 md:pl-0' : 'hidden md:block opacity-0'}`}>
                {isEven && (
                    <>
                        <div className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Phase {idx + 1}</div>
                        <h4 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">{phase.title}</h4>
                        <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-base">{phase.description}</p>
                    </>
                )}
            </div>
            {/* Center Node */}
            <div className="absolute left-8 md:left-1/2 -translate-x-1/2 flex items-center justify-center z-10">
                <motion.div 
                    style={{ opacity: isActive, scale: isActive }}
                    className={`absolute inset-0 ${phase.bg} blur-md opacity-50 rounded-full`} 
                />
                <div className={`w-14 h-14 rounded-full bg-slate-50 dark:bg-slate-900 border-4 border-slate-200 dark:border-slate-800 flex items-center justify-center relative z-10 transition-colors duration-300 group`}>
                    <Icon className={`w-6 h-6 text-slate-400 transition-colors duration-300`} />
                    <motion.div 
                        style={{ opacity: isActive }}
                        className={`absolute inset-0 rounded-full border-4 ${phase.bg} flex items-center justify-center`}
                    >
                        <Icon className="w-6 h-6 text-white" />
                    </motion.div>
                </div>
            </div>
            {/* Right side text (Odd indices) */}
            <div className={`md:w-1/2 ${!isEven ? 'md:pl-16 pl-24 md:pl-16' : 'hidden md:block opacity-0'}`}>
                {!isEven && (
                    <>
                        <div className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Phase {idx + 1}</div>
                        <h4 className="text-2xl font-bold text-slate-900 dark:text-white mb-3">{phase.title}</h4>
                        <p className="text-slate-600 dark:text-slate-400 leading-relaxed text-base">{phase.description}</p>
                    </>
                )}
            </div>
        </div>
    );
}

export default function LifecycleTimeline() {
    const containerRef = useRef(null);
    
    const { scrollYProgress } = useScroll({
        target: containerRef,
        offset: ["start center", "end center"]
    });

    const phases = [
        {
            title: "Ideation & Formation",
            description: "Students group into teams of 3 and brainstorm innovative solutions. They outline their initial abstract and define roles.",
            icon: Lightbulb,
            color: "text-amber-500",
            bg: "bg-amber-500",
            border: "border-amber-500/30"
        },
        {
            title: "Proposal & Approval",
            description: "Teams submit detailed project proposals. Mentors review, suggest modifications, and officially approve the technical scope.",
            icon: Edit3,
            color: "text-blue-500",
            bg: "bg-blue-500",
            border: "border-blue-500/30"
        },
        {
            title: "Iterative Development",
            description: "Projects are broken into 4 continuous milestones. Students build, commit code to GitHub, and receive real-time feedback.",
            icon: GitPullRequest,
            color: "text-indigo-500",
            bg: "bg-indigo-500",
            border: "border-indigo-500/30"
        },
        {
            title: "Final Evaluation",
            description: "Expert panels evaluate the final presentation, prototype, and codebase using standardized grading rubrics.",
            icon: Award,
            color: "text-emerald-500",
            bg: "bg-emerald-500",
            border: "border-emerald-500/30"
        }
    ];

    // Glow line height
    const lineHeight = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

    return (
        <div ref={containerRef} className="py-32 bg-white dark:bg-[#04081c] relative z-10 transition-colors">
            <div className="max-w-7xl mx-auto px-6">
                <div className="text-center mb-24">
                    <h2 className="text-3xl md:text-5xl font-black tracking-tight mb-6 text-slate-900 dark:text-white">
                        The Project Lifecycle
                    </h2>
                    <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
                        A seamless, guided journey from the initial spark of an idea to the final graded prototype.
                    </p>
                </div>

                <div className="relative max-w-3xl mx-auto pb-10">
                    {/* Background faint line */}
                    <div className="absolute left-8 md:left-1/2 top-0 bottom-0 w-1 bg-slate-200 dark:bg-slate-800 -translate-x-1/2 rounded-full"></div>
                    
                    {/* Glowing active line */}
                    <motion.div 
                        style={{ height: lineHeight }}
                        className="absolute left-8 md:left-1/2 top-0 w-1 bg-gradient-to-b from-amber-500 via-indigo-500 to-emerald-500 -translate-x-1/2 rounded-full shadow-[0_0_15px_rgba(99,102,241,0.5)] origin-top"
                    ></motion.div>

                    <div className="space-y-24">
                        {phases.map((phase, idx) => (
                            <TimelineNode key={phase.title || idx} phase={phase} idx={idx} scrollYProgress={scrollYProgress} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
