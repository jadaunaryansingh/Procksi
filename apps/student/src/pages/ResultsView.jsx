import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Award, CheckCircle2, AlertCircle, FileSpreadsheet, Trophy, AlertTriangle, Calendar } from 'lucide-react';
import { useResults, useProfile, usePresentationCycles, useResultSemesters } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

export default function ResultsView() {
    const { data: semestersList, loading: semsLoading } = useResultSemesters();
    // Only an explicit choice is stored. The default is derived during render
    // from whatever the semester list currently holds, so the first paint
    // already has a value — the effect this replaces set state on arrival,
    // costing an extra render and a fetch with an empty id before it.
    const [chosenSemId, setChosenSemId] = useState('');
    const defaultSemId = semestersList?.length
        ? (semestersList.find(s => s.is_active) || semestersList[0]).id
        : '';
    const selectedSemId = chosenSemId || defaultSemId;
    const setSelectedSemId = setChosenSemId;

    const { data: results, loading: resultsLoading, error: resultsError } = useResults(selectedSemId);
    const { data: profile, loading: profileLoading } = useProfile();
    const { data: cycles, loading: cyclesLoading } = usePresentationCycles(selectedSemId);

    if (resultsLoading || profileLoading || cyclesLoading || semsLoading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={6} />
            </div>
        );
    }

    if (profile?.isSemesterActive === false) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-6 flex items-center">
                    <Award className="w-6 h-6 mr-3 text-indigo-500" /> Final Results
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

    if (resultsError || !results) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-6 flex items-center">
                    <Award className="w-6 h-6 mr-3 text-indigo-500" /> Final Results
                </h2>
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-12 text-center shadow-sm">
                    <Award className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">Results Not Released Yet</h3>
                    <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                        Final semester grades and evaluation results have not been finalized yet. They will be published here as soon as the review committee releases them.
                    </p>
                </div>
            </motion.div>
        );
    }

    const maxTotalScore = 100;
    const totalScore = results.total_score ?? 0;
    const percentage = Math.round((Math.min(totalScore, maxTotalScore) / maxTotalScore) * 100);

    // Build breakdown: prefer cycle_scores from the API (cycle-aware),
    // then fall back to cycle hook data, then fall back to legacy columns.
    let breakdown = [];

    if (results.cycle_scores && results.cycle_scores.length > 0) {
        // New: cycle-based scores with exact weightage applied
        breakdown = results.cycle_scores.map(cs => ({
            presentation: cs.presentation,
            weightage: `${cs.weightage}%`,
            rawScore: cs.raw_score != null ? `${cs.raw_score} / ${cs.max_score}` : '--',
            weightedScore: cs.weighted_score != null ? cs.weighted_score : '--'
        }));
    } else if (cycles && cycles.length > 0) {
        // Cycle hook data with evaluation embedded
        breakdown = cycles.map(c => {
            const raw = c.evaluation ? c.evaluation.total_score : null;
            const maxScore = c.evaluation ? (c.evaluation.max_score || 100) : 100;
            const weighted = raw != null ? Math.round((raw / maxScore) * c.weightage * 10) / 10 : null;
            return {
                presentation: c.title,
                weightage: `${c.weightage}%`,
                rawScore: raw != null ? `${raw} / ${maxScore}` : '--',
                weightedScore: weighted != null ? weighted : '--'
            };
        });
    } else {
        // Legacy fallback
        breakdown = [
            { presentation: 'Proposal Review', weightage: '20%', rawScore: results.proposal_score != null ? Math.round((results.proposal_score / 0.2) * 10) / 10 : '--', weightedScore: results.proposal_score ?? '--' },
            { presentation: 'Mid-Term Presentation', weightage: '30%', rawScore: results.mid_score != null ? Math.round((results.mid_score / 0.3) * 10) / 10 : '--', weightedScore: results.mid_score ?? '--' },
            { presentation: 'Final Presentation', weightage: '50%', rawScore: results.final_score != null ? Math.round((results.final_score / 0.5) * 10) / 10 : '--', weightedScore: results.final_score ?? '--' }
        ];
    }

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 mb-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                    <Award className="w-6 h-6 mr-3 text-indigo-500" /> Final Results
                </h2>
                {semestersList && semestersList.length > 0 && (
                    <div className="flex items-center gap-3 bg-white dark:bg-slate-800 px-4 py-2 border border-slate-200 dark:border-slate-700/50 rounded-2xl shadow-sm">
                        <span className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest flex items-center gap-1.5"><Calendar className="w-4 h-4 text-indigo-500" /> Year / Term:</span>
                        <select
                            value={selectedSemId}
                            onChange={e => setSelectedSemId(e.target.value)}
                            className="bg-transparent text-sm font-bold text-slate-800 dark:text-white outline-none cursor-pointer focus:ring-0 border-0 p-0"
                        >
                            {semestersList.map(sem => (
                                <option key={sem.id} value={sem.id} className="dark:bg-slate-800">
                                    {sem.year} — {sem.semester_type} {sem.branch ? `— ${sem.branch}` : ''} {sem.is_active ? '[Current]' : ''}
                                </option>
                            ))}
                        </select>
                    </div>
                )}
            </div>

            {/* Top Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-2 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl p-8 text-white shadow-md relative overflow-hidden flex flex-col justify-center">
                    <motion.div animate={{ rotate: 360 }} transition={{ duration: 40, repeat: Infinity, ease: "linear" }} className="absolute -left-16 -top-16 text-white/5 w-64 h-64 pointer-events-none">
                        <svg viewBox="0 0 100 100" fill="currentColor"><polygon points="50,0 61,35 98,35 68,57 79,91 50,70 21,91 32,57 2,35 39,35" /></svg>
                    </motion.div>
                    <Trophy className="absolute -right-6 top-1/2 -translate-y-1/2 w-48 h-48 text-white/10 rotate-12 pointer-events-none" />
                    <div className="relative z-10 flex flex-col md:flex-row items-center md:items-start gap-8">
                        <div className="shrink-0">
                            <div className="relative w-32 h-32 flex items-center justify-center bg-white/10 rounded-full backdrop-blur-sm border-4 border-white/20 shadow-inner">
                                <svg className="absolute inset-0 w-full h-full -rotate-90 origin-center scale-[1.05]" viewBox="0 0 100 100">
                                    <circle cx="50" cy="50" r="46" fill="transparent" stroke="currentColor" strokeWidth="6" className="text-black/10" />
                                    <motion.circle
                                        cx="50" cy="50" r="46" fill="transparent" stroke="currentColor" strokeWidth="6"
                                        strokeDasharray="289.026"
                                        initial={{ strokeDashoffset: 289.026 }}
                                        animate={{ strokeDashoffset: 289.026 - (289.026 * percentage) / 100 }}
                                        transition={{ duration: 1.5, ease: "easeOut" }}
                                        className="text-white drop-shadow-sm"
                                        strokeLinecap="round"
                                    />
                                </svg>
                                <div className="text-center">
                                    <span className="text-3xl font-black">{percentage}%</span>
                                </div>
                            </div>
                        </div>
                        <div data-tour="student-results-score" className="text-center md:text-left pt-2">
                            <h3 className="text-3xl md:text-4xl font-bold mb-2 text-white tracking-tight">Overall Score</h3>
                            <p className="text-indigo-100 text-lg mb-5 font-medium">
                                You achieved <span className="font-bold text-white text-xl">{totalScore}</span> out of {maxTotalScore} possible marks.
                            </p>
                            <div className="inline-flex items-center px-4 py-2 bg-white/20 backdrop-blur-md border border-white/30 rounded-xl text-sm font-bold shadow-sm">
                                <CheckCircle2 className="w-5 h-5 mr-2 text-emerald-300" />
                                Status: Released
                            </div>
                        </div>
                    </div>
                </div>

                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-8 shadow-sm flex flex-col items-center justify-center text-center">
                    <h3 className="text-lg font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-4">Final Grade</h3>
                    <div className="w-32 h-32 rounded-3xl bg-amber-50 dark:bg-amber-500/10 border-2 border-amber-200 dark:border-amber-500/20 flex items-center justify-center shadow-inner shadow-amber-500/5 rotate-3 hover:rotate-0 transition-transform">
                        <span className="text-7xl font-black text-amber-500 dark:text-amber-400 drop-shadow-sm">{results.grade}</span>
                    </div>
                </div>
            </div>

            {results.override_reason && (
                <div className="p-4 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-2xl text-amber-800 dark:text-amber-300 text-sm font-semibold flex items-center">
                    <AlertCircle className="w-5 h-5 mr-3" />
                    Score adjusted by coordinator: {results.override_reason}
                </div>
            )}

            {/* Breakdown Table */}
            <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden">
                <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/80 flex items-center justify-between">
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                        <FileSpreadsheet className="w-5 h-5 mr-3 text-indigo-500" /> Component Breakdown
                    </h3>
                    <span className="text-xs text-slate-400 dark:text-slate-500 font-medium">
                        Weighted score = (raw / max) × weightage
                    </span>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-50/50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 text-sm uppercase tracking-widest border-b border-slate-100 dark:border-slate-700/50">
                                <th className="px-6 py-4 font-semibold w-1/3">Presentation</th>
                                <th className="px-6 py-4 font-semibold text-center w-1/5">Weightage</th>
                                <th className="px-6 py-4 font-semibold text-center w-1/4">Raw Score</th>
                                <th className="px-6 py-4 font-semibold text-right">Weighted Score</th>
                            </tr>
                        </thead>
                        <motion.tbody initial="hidden" animate="show" variants={{ hidden: {}, show: { transition: { staggerChildren: 0.1 } } }} className="divide-y divide-slate-100 dark:divide-slate-700/50 text-slate-700 dark:text-slate-300">
                            {breakdown.map((item, idx) => (
                                <motion.tr variants={{ hidden: { opacity: 0, x: -15 }, show: { opacity: 1, x: 0 } }} key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group">
                                    <td className="px-6 py-5 font-bold text-slate-800 dark:text-slate-200 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                                        {item.presentation}
                                    </td>
                                    <td className="px-6 py-5 text-center font-medium">
                                        <span className="px-3 py-1 bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-600 dark:text-slate-300 text-sm font-semibold inline-block">
                                            {item.weightage}
                                        </span>
                                    </td>
                                    <td className="px-6 py-5 text-center font-semibold text-slate-600 dark:text-slate-400">
                                        {item.rawScore}
                                    </td>
                                    <td className="px-6 py-5 text-right font-black text-lg text-indigo-600 dark:text-indigo-400">
                                        {item.weightedScore}
                                    </td>
                                </motion.tr>
                            ))}
                        </motion.tbody>
                        <tfoot className="bg-slate-50/50 dark:bg-slate-900/50 border-t-2 border-slate-200 dark:border-slate-700">
                            <tr>
                                <td colSpan="3" className="px-6 py-5 text-right font-bold text-slate-600 dark:text-slate-400 uppercase tracking-widest">
                                    Total Score
                                </td>
                                <td className="px-6 py-5 text-right font-black text-2xl text-slate-900 dark:text-white">
                                    {totalScore}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        </motion.div>
    );
}
