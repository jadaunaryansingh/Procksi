import React from 'react';
import { motion } from 'framer-motion';
import { FileText, CheckCircle, MessageSquare, Calendar, Shield, Zap } from 'lucide-react';

const FeatureCard = ({ title, description, icon: Icon, className, delay }) => (
    <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-50px" }}
        transition={{ duration: 0.5, delay }}
        className={`group relative overflow-hidden rounded-3xl p-8 bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 shadow-xl hover:shadow-2xl transition-all ${className}`}
    >
        <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-10 transition-opacity transform group-hover:scale-110 duration-500">
            <Icon className="w-32 h-32" />
        </div>
        <div className="relative z-10 flex flex-col h-full">
            <div className="w-12 h-12 bg-indigo-50 dark:bg-indigo-900/30 rounded-2xl flex items-center justify-center mb-6 border border-indigo-100 dark:border-indigo-800 shadow-sm">
                <Icon className="w-6 h-6 text-indigo-600 dark:text-indigo-400" />
            </div>
            <h3 className="text-2xl font-bold text-slate-900 dark:text-white mb-3 tracking-tight">{title}</h3>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed max-w-sm">{description}</p>
        </div>
    </motion.div>
);

export default function BentoFeatures() {
    return (
        <div className="py-32 relative z-10 bg-slate-50 dark:bg-[#020617] transition-colors">
            <div className="max-w-7xl mx-auto px-6">
                <div className="text-center mb-20">
                    <h2 className="text-3xl md:text-5xl font-black tracking-tight mb-6 text-slate-900 dark:text-white">
                        Everything you need.<br/>Nothing you don't.
                    </h2>
                    <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
                        A robust toolset carefully curated to remove friction from academic project management.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
                    {/* Top Row */}
                    <FeatureCard
                        title="Zero Paperwork"
                        description="Digitize every aspect of project submission. Proposals, milestones, and final reports are all handled through a secure, traceable portal."
                        icon={FileText}
                        className="md:col-span-2"
                        delay={0.1}
                    />
                    <FeatureCard
                        title="Transparent Grading"
                        description="Evaluation panels grade presentations using predefined, standardized rubrics ensuring 100% fairness."
                        icon={CheckCircle}
                        className="md:col-span-1 bg-gradient-to-br from-white to-slate-50 dark:from-slate-900/80 dark:to-slate-900/30"
                        delay={0.2}
                    />

                    {/* Bottom Row */}
                    <FeatureCard
                        title="Automated Scheduling"
                        description="No more spreadsheet clashes. The system automatically handles presentation slots and panel allocations."
                        icon={Calendar}
                        className="md:col-span-1 bg-gradient-to-br from-white to-slate-50 dark:from-slate-900/80 dark:to-slate-900/30"
                        delay={0.3}
                    />
                    <FeatureCard
                        title="Real-time Mentorship"
                        description="Constant feedback loops between students and mentors. Chat, comment on code, and approve milestones instantly."
                        icon={MessageSquare}
                        className="md:col-span-2"
                        delay={0.4}
                    />
                </div>
            </div>
        </div>
    );
}
