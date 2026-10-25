import React from 'react';
import { motion } from 'framer-motion';
import { ClipboardCheck, TrendingUp, AlertCircle, CheckCircle2, AlertTriangle, MessageSquare } from 'lucide-react';
import { useEvaluations, useProfile } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

export default function EvaluationsView() {
    const { data: evaluations, loading: evalsLoading, error: evalsError, refetch: refetchEvals } = useEvaluations();
    const { data: profile, loading: profileLoading } = useProfile();

    if (evalsLoading || profileLoading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={6} />
            </div>
        );
    }

    if (evalsError && evalsError !== "Student is not assigned to a team") {
        return <ErrorCard message={evalsError} onRetry={refetchEvals} />;
    }

    if (profile?.isSemesterActive === false) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-6 flex items-center">
                    <ClipboardCheck className="w-6 h-6 mr-3 text-indigo-500" /> Evaluations & Scoring
                </h2>
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-12 text-center shadow-sm relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-amber-500 to-orange-500"></div>
                    <div className="w-16 h-16 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-sm">
                        <AlertTriangle className="w-8 h-8 text-amber-500" />
                    </div>
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">Academic Semester Inactive</h3>
                    <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
                        Your academic batch/semester has been deactivated by the administrator. Access to evaluation metrics and results is temporarily restricted.
                    </p>
                </div>
            </motion.div>
        );
    }

    const hasNoEvals = !evaluations || (
        evaluations.cycles ? (evaluations.cycles.length === 0 || evaluations.cycles.every(c => c.score === null)) : (
            (!evaluations.proposal || evaluations.proposal.score === null) &&
            (!evaluations.mid || evaluations.mid.score === null) &&
            (!evaluations.final || evaluations.final.score === null)
        )
    );

    if (hasNoEvals) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-6 flex items-center">
                    <ClipboardCheck className="w-6 h-6 mr-3 text-indigo-500" /> Evaluations & Scoring
                </h2>
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-12 text-center shadow-sm">
                    <ClipboardCheck className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">No Evaluations Yet</h3>
                    <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                        Your project presentations have not been evaluated yet. Once evaluations are completed, your scores and feedback will appear here.
                    </p>
                </div>
            </motion.div>
        );
    }

    const evalTypes = evaluations?.cycles ? evaluations.cycles.map(c => ({
        key: c.cycle_id,
        label: c.presentation,
        maxScore: c.max_score,
        data: c
    })) : [
        { key: 'proposal', label: 'Proposal Review', maxScore: 20, data: evaluations.proposal },
        { key: 'mid', label: 'Mid-Term Presentation', maxScore: 30, data: evaluations.mid },
        { key: 'final', label: 'Final Presentation', maxScore: 50, data: evaluations.final }
    ];

    const getScoreBarColor = (percentage) => {
        if (percentage >= 75) return 'bg-emerald-500';
        if (percentage >= 50) return 'bg-amber-500';
        return 'bg-red-500';
    };

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-6 flex items-center">
                <ClipboardCheck className="w-6 h-6 mr-3 text-indigo-500" /> Evaluations & Scoring
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {evalTypes.map((type, idx) => {
                    const data = type.data;
                    const score = data ? data.score : null;
                    const date = data && data.schedule_date ? new Date(data.schedule_date).toLocaleDateString() : '—';
                    const hasScore = score !== null;
                    const percentage = (hasScore && type.maxScore > 0) ? Math.round((score / type.maxScore) * 100) : 0;

                    return (
                        <motion.div
                            key={type.key}
                            initial={{ opacity: 0, y: 15 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: idx * 0.1 }}
                            className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm p-6 hover:shadow-lg transition-shadow relative overflow-hidden flex flex-col justify-between"
                        >
                            <div>
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <h3 className="font-bold text-slate-800 dark:text-slate-100 text-lg">{type.label}</h3>
                                        <p className="text-xs text-slate-500 mt-1">Evaluated on {date}</p>
                                    </div>
                                    <span className={`px-2.5 py-1 text-xs font-bold rounded-lg ${hasScore ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' : 'bg-slate-100 text-slate-400'}`}>
                                        {hasScore ? 'Graded' : 'Pending'}
                                    </span>
                                </div>

                                {hasScore ? (
                                    <div className="space-y-4">
                                        <div className="flex justify-between items-end">
                                            <span className="text-xs font-bold text-slate-400 uppercase tracking-wide">Score</span>
                                            <div className="text-right">
                                                <span className="text-3xl font-black text-slate-800 dark:text-white">{score}</span>
                                                <span className="text-slate-400 dark:text-slate-500 text-sm font-medium"> / {type.maxScore}</span>
                                            </div>
                                        </div>
                                        {/* Score Bar */}
                                        <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-3 overflow-hidden shadow-inner">
                                            <motion.div
                                                initial={{ width: 0 }}
                                                animate={{ width: `${percentage}%` }}
                                                transition={{ duration: 1, delay: 0.2, ease: "easeOut" }}
                                                className={`h-full rounded-full ${getScoreBarColor(percentage)}`}
                                            />
                                        </div>
                                    </div>
                                ) : (
                                    <div className="py-6 text-center text-sm text-slate-400 dark:text-slate-500 italic">
                                        No score recorded yet
                                    </div>
                                )}
                            </div>

                            {hasScore && data.remarks && (
                                <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700">
                                    <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2 flex items-center">
                                        <MessageSquare className="w-3.5 h-3.5 mr-1" /> Remarks
                                    </h4>
                                    <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed italic">
                                        "{data.remarks}"
                                    </p>
                                </div>
                            )}
                        </motion.div>
                    );
                })}
            </div>
        </motion.div>
    );
}
