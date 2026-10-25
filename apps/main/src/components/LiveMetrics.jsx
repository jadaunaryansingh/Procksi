import React, { useEffect, useState, useRef } from 'react';
import { motion, useInView } from 'framer-motion';
import { Users, FolderGit2, GraduationCap, Clock } from 'lucide-react';
import { supabase } from '../lib/supabase';

const Counter = ({ from = 0, to, duration = 2, suffix = '' }) => {
    const [count, setCount] = useState(from);
    const ref = useRef(null);
    const isInView = useInView(ref, { once: true, margin: "-100px" });

    useEffect(() => {
        if (!isInView) return;
        let startTime;
        let animationFrame;

        const updateCount = (timestamp) => {
            if (!startTime) startTime = timestamp;
            const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
            
            // easeOutExpo
            const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
            
            setCount(Math.floor(easeProgress * (to - from) + from));

            if (progress < 1) {
                animationFrame = requestAnimationFrame(updateCount);
            }
        };

        animationFrame = requestAnimationFrame(updateCount);
        return () => cancelAnimationFrame(animationFrame);
    }, [from, to, duration, isInView]);

    return <span ref={ref}>{count}{suffix}</span>;
};

export default function LiveMetrics() {
    const [stats, setStats] = useState({
        students: { value: 850, suffix: '+' },
        projects: { value: 215, suffix: '' },
        mentors: { value: 45, suffix: '+' },
        submissions: { value: 1200, suffix: '+' }
    });

    useEffect(() => {
        const fetchStats = async () => {
            try {
                // Attempt to fetch real counts from database
                const [
                    { count: studentCount },
                    { count: projectCount },
                    { count: mentorCount },
                    { count: submissionCount }
                ] = await Promise.all([
                    supabase.from('profiles').select('*', { count: 'exact', head: true }).eq('role', 'student'),
                    supabase.from('projects').select('*', { count: 'exact', head: true }),
                    supabase.from('profiles').select('*', { count: 'exact', head: true }).eq('role', 'mentor'),
                    supabase.from('submissions').select('*', { count: 'exact', head: true })
                ]);

                // Update only if data exists and is valid
                setStats(prev => ({
                    students: studentCount > 0 ? { value: studentCount, suffix: '' } : prev.students,
                    projects: projectCount > 0 ? { value: projectCount, suffix: '' } : prev.projects,
                    mentors: mentorCount > 0 ? { value: mentorCount, suffix: '' } : prev.mentors,
                    submissions: submissionCount > 0 ? { value: submissionCount, suffix: '' } : prev.submissions
                }));
            } catch (err) {
                console.error("Could not fetch live metrics, falling back to dummy data:", err);
            }
        };
        fetchStats();
    }, []);

    const metrics = [
        { id: 1, icon: Users, label: "Active Students", ...stats.students, color: "text-blue-500", bg: "bg-blue-500/10" },
        { id: 2, icon: FolderGit2, label: "Live Projects", ...stats.projects, color: "text-indigo-500", bg: "bg-indigo-500/10" },
        { id: 3, icon: GraduationCap, label: "Expert Mentors", ...stats.mentors, color: "text-purple-500", bg: "bg-purple-500/10" },
        { id: 4, icon: Clock, label: "Total Submissions", ...stats.submissions, color: "text-emerald-500", bg: "bg-emerald-500/10" },
    ];

    return (
        <div className="w-full py-16 border-y border-slate-200 dark:border-slate-800 bg-white/30 dark:bg-slate-900/30 backdrop-blur-md relative z-10 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-indigo-500/5 to-transparent pointer-events-none"></div>
            <div className="max-w-7xl mx-auto px-6 relative z-10">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-8 divide-x-0 md:divide-x divide-y md:divide-y-0 divide-slate-200 dark:divide-slate-800">
                    {metrics.map((metric, idx) => {
                        const Icon = metric.icon;
                        return (
                            <motion.div 
                                key={metric.id}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: idx * 0.1 }}
                                className={`flex flex-col items-center justify-center text-center ${idx >= 2 ? 'pt-8 md:pt-0' : ''}`}
                            >
                                <div className={`w-12 h-12 rounded-2xl ${metric.bg} flex items-center justify-center mb-4`}>
                                    <Icon className={`w-6 h-6 ${metric.color}`} />
                                </div>
                                <h4 className="text-4xl md:text-5xl font-black text-slate-900 dark:text-white mb-2 font-mono tracking-tighter">
                                    <Counter to={metric.value} suffix={metric.suffix} />
                                </h4>
                                <p className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">
                                    {metric.label}
                                </p>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
