import React from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, FileText, ClipboardList } from 'lucide-react';
import { useProposals, useEvaluations } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';
import EmptyState from '../components/EmptyState';
import RichText from '../components/RichText';

export const FeedbackView = () => {
    const { data: proposals, loading: proposalsLoading, error: proposalsError, refetch: refetchProposals } = useProposals();
    const { data: evaluations, loading: evaluationsLoading, error: evaluationsError, refetch: refetchEvaluations } = useEvaluations();

    const handleRetry = () => {
        refetchProposals();
        refetchEvaluations();
    };

    if (proposalsLoading || evaluationsLoading) {
        return (
            <div className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                    <LoadingSkeleton lines={5} />
                </div>
            </div>
        );
    }

    if (proposalsError || evaluationsError) {
        const err = proposalsError || evaluationsError;
        // Ignore unassigned errors for empty states
        if (err !== "Student is not assigned to a team") {
            return (
                <ErrorCard message={err} onRetry={handleRetry} />
            );
        }
    }

    // Process timeline items
    const timelineItems = [];

    // 1. From proposals data: extract feedback/remarks from rejected or revision_requested proposals
    if (proposals && Array.isArray(proposals)) {
        proposals.forEach(p => {
            if (p.feedback) {
                timelineItems.push({
                    id: `prop-${p.id}`,
                    type: 'proposal',
                    date: p.submitted_at,
                    title: `Proposal: ${p.title}`,
                    subtitle: `Status: ${p.status === 'revision_requested' ? 'Revision Requested' : p.status === 'rejected' ? 'Rejected' : p.status.toUpperCase()}`,
                    body: p.feedback
                });
            }
        });
    }

    // 2. From evaluations data: extract remarks from each evaluation type where remarks is not null
    if (evaluations) {
        ['proposal', 'mid', 'final'].forEach(evalType => {
            const ev = evaluations[evalType];
            if (ev && ev.remarks) {
                const label = evalType === 'proposal' ? 'Proposal Evaluation' : evalType === 'mid' ? 'Mid-Term Evaluation' : 'Final Evaluation';
                timelineItems.push({
                    id: `eval-${evalType}`,
                    type: 'evaluation',
                    date: ev.schedule_date || new Date().toISOString(),
                    title: label,
                    subtitle: ev.score !== null ? `Score: ${ev.score}/100` : 'Pending Score',
                    body: ev.remarks
                });
            }
        });
    }

    // Sort by date descending
    timelineItems.sort((a, b) => new Date(b.date) - new Date(a.date));

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        try {
            return new Date(dateStr).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
        } catch {
            return dateStr;
        }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="flex justify-between items-end mb-6">
                <div>
                    <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Evaluations & Feedback</h2>
                    <p className="text-slate-500 dark:text-slate-400 mt-1">Unified timeline of remarks and assessments.</p>
                </div>
            </div>

            {timelineItems.length === 0 ? (
                <EmptyState message="No feedback received yet." icon={MessageSquare} />
            ) : (
                <div className="relative border-l border-slate-200 dark:border-slate-700 ml-4 md:ml-6 space-y-8 py-2">
                    {timelineItems.map((item, index) => (
                        <motion.div
                            key={item.id}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: 0.3, delay: index * 0.05 }}
                            className="relative pl-8 md:pl-10"
                        >
                            {/* Marker Icon */}
                            <span className={`absolute -left-[18px] top-1.5 flex h-9 w-9 items-center justify-center rounded-full ring-8 ring-slate-50 dark:ring-slate-900 ${item.type === 'proposal' ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400' : 'bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400'}`}>
                                {item.type === 'proposal' ? (
                                    <FileText className="w-4 h-4" />
                                ) : (
                                    <ClipboardList className="w-4 h-4" />
                                )}
                            </span>

                            {/* Card Content */}
                            <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-all">
                                <div className="flex flex-col sm:flex-row justify-between items-start gap-2 mb-3">
                                    <div>
                                        <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                            {item.title}
                                        </h3>
                                        <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded-md mt-1 ${item.type === 'proposal' ? 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-100 dark:border-amber-500/20' : 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-500/20'}`}>
                                            {item.subtitle}
                                        </span>
                                    </div>
                                    <span className="text-xs font-bold text-slate-400 dark:text-slate-500 whitespace-nowrap bg-slate-100 dark:bg-slate-700/50 px-2 py-1 rounded-md">
                                        {formatDate(item.date)}
                                    </span>
                                </div>
                                <div className="bg-slate-50 dark:bg-slate-900/50 p-4 rounded-xl border border-slate-100 dark:border-slate-700/50 relative shadow-inner">
                                    <div className={`absolute top-0 left-0 w-1 h-full rounded-l-xl ${item.type === 'proposal' ? 'bg-amber-500' : 'bg-blue-500'}`}></div>
                                    <RichText text={item.body} className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed pl-2" />
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}
        </motion.div>
    );
};

export default FeedbackView;

