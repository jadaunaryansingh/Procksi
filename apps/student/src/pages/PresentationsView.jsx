import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Presentation, Calendar, Clock, MapPin, Video, Users, CheckCircle, CircleDashed, CalendarClock, Upload, ExternalLink, Loader2 } from 'lucide-react';
import { useSchedule, useEvaluations, usePresentationCycles, fetchWithAuth, useResultSemesters } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

export default function PresentationsView() {
    const { data: semestersList, loading: semsLoading } = useResultSemesters();
    const [selectedSemId, setSelectedSemId] = useState('');

    if (semestersList && semestersList.length > 0 && !selectedSemId) {
        const activeSem = semestersList.find(s => s.is_active) || semestersList[0];
        setSelectedSemId(activeSem.id);
    }

    const { data: schedule, loading: scheduleLoading, error: scheduleError, refetch: refetchSchedule } = useSchedule();
    const { data: evaluations, loading: evalsLoading } = useEvaluations();
    const { data: cycles, loading: cyclesLoading, refetch: refetchCycles } = usePresentationCycles(selectedSemId);
    
    const [submitting, setSubmitting] = useState(false);
    const [submitForm, setSubmitForm] = useState({ cycleId: null, github_url: '', file_url: '', notes: '' });

    if (scheduleLoading || evalsLoading || cyclesLoading || semsLoading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={6} />
            </div>
        );
    }

    if (scheduleError) {
        return <ErrorCard message={scheduleError} onRetry={refetchSchedule} />;
    }

    const presentations = schedule || [];
    const activeCycles = cycles || [];

    const getStatusIcon = (status) => {
        const lowerStatus = String(status).toLowerCase();
        if (lowerStatus === 'completed') return <CheckCircle className="w-5 h-5 text-emerald-500" />;
        if (lowerStatus === 'scheduled') return <CalendarClock className="w-5 h-5 text-indigo-500" />;
        return <CircleDashed className="w-5 h-5 text-slate-400" />;
    };

    const getStatusColor = (status) => {
        const lowerStatus = String(status).toLowerCase();
        if (lowerStatus === 'completed') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30';
        if (lowerStatus === 'scheduled') return 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/30';
        return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-200 dark:border-slate-700';
    };

    const getWeightage = (type) => {
        const t = String(type).toLowerCase();
        if (t === 'proposal') return '20%';
        if (t === 'mid') return '30%';
        if (t === 'final') return '50%';
        return '—';
    };

    const getTitle = (type) => {
        const t = String(type).toLowerCase();
        if (t === 'proposal') return 'Proposal Review';
        if (t === 'mid') return 'Mid-Term Presentation';
        if (t === 'final') return 'Final Presentation';
        return 'Presentation';
    };

    const handleSubmit = async (e, cycleId) => {
        e.preventDefault();
        setSubmitting(true);
        try {
            await fetchWithAuth(`/api/student/presentation-cycles/${cycleId}/submit`, {
                method: 'POST',
                body: { ...submitForm }
            });
            alert('Presentation submitted successfully!');
            setSubmitForm({ cycleId: null, github_url: '', file_url: '', notes: '' });
            refetchCycles();
        } catch (err) {
            alert(err.message);
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                    <Presentation className="w-6 h-6 mr-3 text-indigo-500" /> My Presentations & Evaluations
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
            
            {activeCycles.length > 0 && (
                <div className="space-y-6">
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center border-b border-slate-200 dark:border-slate-700 pb-2">
                        Active Presentation Cycles
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {activeCycles.map((cycle) => (
                            <motion.div key={cycle.id} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-md p-6 flex flex-col relative overflow-hidden">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <div className="flex gap-2 items-center mb-1">
                                            <span className={`px-2 py-0.5 text-[10px] font-black uppercase rounded-md ${
                                                cycle.status === 'draft' ? 'bg-slate-100 text-slate-600' :
                                                cycle.status === 'active' ? 'bg-indigo-100 text-indigo-600' :
                                                cycle.status === 'closed' ? 'bg-amber-100 text-amber-600' :
                                                'bg-blue-100 text-blue-600'
                                            }`}>
                                                {cycle.status}
                                            </span>
                                            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] font-black uppercase rounded-md">{cycle.type}</span>
                                        </div>
                                        <h3 className="font-black text-slate-800 dark:text-white text-lg">{cycle.title}</h3>
                                    </div>
                                    <div className="text-2xl font-black text-indigo-600 dark:text-indigo-400">
                                        {cycle.weightage}%
                                    </div>
                                </div>

                                <div className="space-y-3 mb-6">
                                    <div className="flex items-center text-sm text-slate-600 dark:text-slate-400 font-medium">
                                        <Calendar className="w-4 h-4 mr-2 text-slate-400"/>
                                        Deadline: {new Date(cycle.deadline).toLocaleString()}
                                    </div>
                                </div>

                                {cycle.evaluation ? (
                                    <div className="mt-auto p-4 bg-emerald-50 dark:bg-emerald-500/10 rounded-xl border border-emerald-100 dark:border-emerald-500/20">
                                        <div className="flex justify-between items-center mb-2">
                                            <span className="font-bold text-emerald-700 dark:text-emerald-400 text-sm">Evaluation Completed</span>
                                            <span className="font-black text-emerald-700 dark:text-emerald-400 text-xl">{cycle.evaluation.total_score} / 100</span>
                                        </div>
                                        <p className="text-xs text-emerald-600 dark:text-emerald-500">{cycle.evaluation.remarks}</p>
                                    </div>
                                ) : cycle.submission ? (
                                    <div className="mt-auto p-4 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
                                        <div className="flex items-center text-sm font-bold text-indigo-600 dark:text-indigo-400 mb-2">
                                            <CheckCircle className="w-4 h-4 mr-2" />
                                            Submitted Successfully
                                        </div>
                                        {cycle.submission.github_url && <a href={cycle.submission.github_url} target="_blank" rel="noreferrer" className="flex items-center text-xs text-slate-500 hover:text-indigo-500 mb-1"><ExternalLink className="w-3 h-3 mr-1"/> GitHub Link</a>}
                                        {cycle.submission.file_url && <a href={cycle.submission.file_url} target="_blank" rel="noreferrer" className="flex items-center text-xs text-slate-500 hover:text-indigo-500"><ExternalLink className="w-3 h-3 mr-1"/> File Document</a>}
                                    </div>
                                ) : cycle.status === 'active' ? (
                                    <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700">
                                        {submitForm.cycleId === cycle.id ? (
                                            <form onSubmit={(e) => handleSubmit(e, cycle.id)} className="space-y-3">
                                                <input type="url" placeholder="GitHub Repository URL" value={submitForm.github_url} onChange={e => setSubmitForm({...submitForm, github_url: e.target.value})} className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg" />
                                                <input type="url" placeholder={cycle.requires_synopsis ? "Google Drive / File URL (Required)" : "Google Drive / File URL (Optional)"} required={cycle.requires_synopsis} value={submitForm.file_url} onChange={e => setSubmitForm({...submitForm, file_url: e.target.value})} className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg" />
                                                <textarea placeholder="Additional Notes..." value={submitForm.notes} onChange={e => setSubmitForm({...submitForm, notes: e.target.value})} className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg" />
                                                <div className="flex gap-2">
                                                    <button type="button" onClick={() => setSubmitForm({ cycleId: null, github_url: '', file_url: '', notes: '' })} className="flex-1 py-2 bg-slate-100 text-slate-600 rounded-lg text-xs font-bold">Cancel</button>
                                                    <button type="submit" disabled={submitting} className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold flex items-center justify-center">
                                                        {submitting ? <Loader2 className="w-4 h-4 animate-spin"/> : 'Submit Presentation'}
                                                    </button>
                                                </div>
                                            </form>
                                        ) : (
                                            <button onClick={() => setSubmitForm({ cycleId: cycle.id, github_url: '', file_url: '', notes: '' })} className="w-full py-2.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 dark:text-indigo-400 rounded-xl font-bold text-sm flex items-center justify-center transition-colors">
                                                <Upload className="w-4 h-4 mr-2" /> Submit Presentation Work
                                            </button>
                                        )}
                                    </div>
                                ) : (
                                    <div className="mt-auto p-3 text-center bg-slate-50 dark:bg-slate-900 text-slate-500 text-sm font-bold rounded-xl border border-slate-200 dark:border-slate-700">
                                        Cycle is {cycle.status}
                                    </div>
                                )}
                            </motion.div>
                        ))}
                    </div>
                </div>
            )}

            {presentations.length > 0 && (
                <div className="space-y-6">
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center border-b border-slate-200 dark:border-slate-700 pb-2">
                        Legacy Scheduled Slots
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {presentations.map((pres, idx) => {
                            const statusText = String(pres.status).charAt(0).toUpperCase() + String(pres.status).slice(1);
                            const isOnline = String(pres.mode).toLowerCase() === 'online';
                            const scoreData = evaluations?.[pres.evaluation_type];
                            const hasScore = scoreData && scoreData.score !== null;

                            return (
                                <motion.div
                                    key={pres.id || idx}
                                    className={`bg-white dark:bg-slate-800 rounded-3xl border ${statusText === 'Scheduled' ? 'border-indigo-200 dark:border-indigo-500/50 shadow-lg shadow-indigo-500/10' : 'border-slate-200 dark:border-slate-700/50 shadow-md'} overflow-hidden transition-all flex flex-col h-full relative group`}
                                >
                                    <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/80 relative overflow-hidden">
                                        <div className="relative z-10 flex justify-between items-start mb-4">
                                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">
                                                {getTitle(pres.evaluation_type)}
                                            </h3>
                                            <div className={`flex items-center px-3 py-1 rounded-full text-xs font-bold border ${getStatusColor(pres.status)}`}>
                                                {getStatusIcon(pres.status)}
                                                <span className="ml-1.5">{statusText}</span>
                                            </div>
                                        </div>
                                        <div className="relative z-10 flex items-center mt-2 group-hover:scale-[1.02] origin-left transition-transform">
                                            <div className="text-3xl font-black text-indigo-600 dark:text-indigo-400">
                                                {getWeightage(pres.evaluation_type)}
                                            </div>
                                            <span className="ml-2 text-sm font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-widest mt-2">Weightage</span>
                                        </div>
                                    </div>

                                    <div className="p-6 space-y-4 flex-1">
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="flex items-start">
                                                <Calendar className="w-5 h-5 mr-3 text-slate-400 shrink-0" />
                                                <div>
                                                    <p className="text-xs font-semibold text-slate-500 uppercase">Date</p>
                                                    <p className="font-semibold text-slate-700 dark:text-slate-200">{new Date(pres.date).toLocaleDateString()}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-start">
                                                <Clock className="w-5 h-5 mr-3 text-slate-400 shrink-0" />
                                                <div>
                                                    <p className="text-xs font-semibold text-slate-500 uppercase">Time Slot</p>
                                                    <p className="font-semibold text-slate-700 dark:text-slate-200">{pres.time_slot}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="p-6 pt-0 mt-auto">
                                        {statusText === 'Completed' && hasScore ? (
                                            <div className="w-full flex items-center justify-between py-2.5 px-4 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded-xl font-bold border border-emerald-100 dark:border-emerald-500/20">
                                                <span>Score Obtained</span>
                                                <span className="text-lg">{scoreData.score}</span>
                                            </div>
                                        ) : statusText === 'Completed' ? (
                                            <div className="w-full text-center py-2.5 bg-slate-100 dark:bg-slate-800 text-slate-500 rounded-xl font-semibold border border-slate-200 dark:border-slate-700">
                                                Pending Evaluation Score
                                            </div>
                                        ) : isOnline ? (
                                            <a
                                                href={pres.meet_link || '#'}
                                                target={pres.meet_link ? '_blank' : '_self'}
                                                rel="noreferrer"
                                                className="w-full flex items-center justify-center py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold shadow-sm transition-colors"
                                            >
                                                <Video className="w-4 h-4 mr-2" />
                                                {pres.meet_link ? 'Join Online Meeting' : 'Link Not Ready'}
                                            </a>
                                        ) : (
                                            <button disabled className="w-full flex items-center justify-center py-2.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-xl font-semibold cursor-default border border-slate-200 dark:border-slate-600">
                                                In-Person Presentation
                                            </button>
                                        )}
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            )}
            
            {activeCycles.length === 0 && presentations.length === 0 && (
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-12 text-center shadow-sm">
                    <Presentation className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">No Presentations Scheduled</h3>
                    <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                        There are no presentations scheduled for your team yet.
                    </p>
                </div>
            )}
        </motion.div>
    );
}
