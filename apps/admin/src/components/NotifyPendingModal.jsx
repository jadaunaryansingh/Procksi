import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mail, X, Send, AlertTriangle, CheckCircle2, Loader2, Github, BookOpen, Layers, Users, ShieldCheck } from 'lucide-react';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { apiFetchTable } from '../lib/api';

export default function NotifyPendingModal({ isOpen, onClose }) {
    const { filters, semesters: globalSemesters, semesterMap } = useGlobalFilters();
    const [fetchedSemesters, setFetchedSemesters] = useState([]);
    const [selectedSemester, setSelectedSemester] = useState('active');
    const [category, setCategory] = useState('all'); // 'all', 'pending_ps', 'pending_github'
    const [customSubject, setCustomSubject] = useState('');
    const [customMessage, setCustomMessage] = useState('');
    const [previewStats, setPreviewStats] = useState(null);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');

    // Load semesters from API as fallback/supplement
    useEffect(() => {
        if (!isOpen) return;
        let isMounted = true;
        const loadSemesters = async () => {
            try {
                const res = await apiFetchTable('semester_config');
                const rows = Array.isArray(res) ? res : (res?.data || []);
                if (isMounted && rows.length > 0) {
                    setFetchedSemesters(rows);
                }
            } catch (err) {
                console.warn('Could not fetch semester_config table:', err);
            }
        };
        loadSemesters();
        setSelectedSemester('active');
        return () => { isMounted = false; };
    }, [isOpen]);

    // Merge globalSemesters and fetchedSemesters
    const allSemesters = (globalSemesters && globalSemesters.length > 0) ? globalSemesters : fetchedSemesters;

    const formatSemObj = (s) => {
        if (!s) return '';
        const levelNum = s.academic_level || s.year_number || s.year;
        const levelStr = levelNum ? `${levelNum}${levelNum == 2 ? 'nd' : levelNum == 3 ? 'rd' : 'th'} Year` : '';
        const semType = s.semester_type ? `${String(s.semester_type).toUpperCase()}` : '';
        const branch = s.branch || '';
        const sessionYear = s.year && String(s.year).includes('-') ? s.year : '';
        const parts = [branch, levelStr, semType, sessionYear].filter(Boolean);
        return parts.length > 0 ? parts.join(' - ') : (s.id || 'Semester');
    };

    const getActiveSemLabel = () => {
        if (!filters.semesterId || filters.semesterId === 'all') return 'All Active Semesters';
        const found = allSemesters.find(s => String(s.id) === String(filters.semesterId));
        if (found) return formatSemObj(found);
        if (semesterMap && semesterMap[filters.semesterId]) {
            const semObj = semesterMap[filters.semesterId];
            return semObj.label || semObj.name || semObj.title || filters.semesterId;
        }
        return filters.semesterId;
    };

    // Live preview fetch whenever semester or category changes
    useEffect(() => {
        if (!isOpen) return;
        let isMounted = true;

        const fetchPreview = async () => {
            setPreviewLoading(true);
            try {
                const targetSemId = selectedSemester === 'active' ? (filters.semesterId || 'active') : selectedSemester;
                const stats = await api.notifyPendingTeams({
                    category,
                    semester_id: targetSemId,
                    year: filters.year !== 'all' ? filters.year : null,
                    preview: true
                });
                if (isMounted) {
                    setPreviewStats(stats);
                }
            } catch (err) {
                console.warn('Failed to load pending teams preview:', err);
            } finally {
                if (isMounted) setPreviewLoading(false);
            }
        };

        fetchPreview();

        return () => { isMounted = false; };
    }, [isOpen, selectedSemester, category, filters.semesterId, filters.year]);

    if (!isOpen) return null;

    const handleSend = async () => {
        if (previewStats && previewStats.target_teams_count === 0) {
            alert('There are no pending teams to email in the selected semester.');
            return;
        }

        const targetSemId = selectedSemester === 'active' ? (filters.semesterId || 'active') : selectedSemester;
        const semName = selectedSemester === 'active' ? getActiveSemLabel() : (selectedSemester === 'all' ? 'All Semesters & Cohorts' : getActiveSemLabel());
        
        const confirmMsg = `Send email reminders to ${previewStats?.target_teams_count || 'pending'} pending teams (${previewStats?.recipients_count || ''} students) in "${semName}"?`;
        if (!window.confirm(confirmMsg)) return;

        setSending(true);
        setError('');
        setResult(null);
        try {
            const res = await api.notifyPendingTeams({
                category,
                semester_id: targetSemId,
                year: filters.year !== 'all' ? filters.year : null,
                custom_subject: customSubject.trim() || undefined,
                custom_message: customMessage.trim() || undefined,
                preview: false
            });
            setResult(res);
        } catch (err) {
            setError(err.message || 'Failed to dispatch email notifications.');
        } finally {
            setSending(false);
        }
    };

    return (
        <AnimatePresence>
            <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-900/70 backdrop-blur-md overflow-y-auto">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                    className="relative w-full max-w-xl max-h-[90vh] bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 flex flex-col my-auto overflow-hidden"
                >
                    {/* Fixed Header */}
                    <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center bg-gradient-to-r from-indigo-500/10 via-purple-500/5 to-transparent shrink-0">
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 bg-indigo-600 text-white rounded-2xl shadow-lg shadow-indigo-500/20">
                                <Mail className="w-5 h-5" />
                            </div>
                            <div>
                                <h3 className="text-lg font-black text-slate-800 dark:text-white leading-snug">Email Pending Teams</h3>
                                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Send reminder emails strictly to pending teams in a selected batch</p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Scrollable Content Body */}
                    <div className="p-5 sm:p-6 space-y-5 overflow-y-auto flex-1 custom-scrollbar">
                        {/* 1. Target Semester Selector */}
                        <div>
                            <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2 flex items-center gap-1.5">
                                <Layers className="w-4 h-4 text-indigo-500" /> Select Target Batch / Semester
                            </label>
                            <select
                                value={selectedSemester}
                                onChange={(e) => { setSelectedSemester(e.target.value); setResult(null); setError(''); }}
                                className="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-xs font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:outline-none cursor-pointer"
                            >
                                <option value="active">Active Selected Semester ({getActiveSemLabel()})</option>
                                <option value="all">All Semesters & Cohorts (Platform Wide)</option>
                                {allSemesters.map(s => (
                                    <option key={s.id} value={s.id}>
                                        {formatSemObj(s)} {s.is_active ? '— [ACTIVE]' : ''}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* 2. Target Recipients Group */}
                        <div>
                            <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2 flex items-center gap-1.5">
                                <Users className="w-4 h-4 text-indigo-500" /> Select Target Category
                            </label>
                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                {[
                                    { id: 'all', label: 'All Pending Teams', desc: 'PS & GitHub Pending', icon: Mail },
                                    { id: 'pending_ps', label: 'PS Selection Pending', desc: 'No PS selected', icon: BookOpen },
                                    { id: 'pending_github', label: 'GitHub Submission Pending', desc: 'Repo URL missing', icon: Github }
                                ].map(t => (
                                    <button
                                        key={t.id}
                                        type="button"
                                        onClick={() => { setCategory(t.id); setResult(null); setError(''); }}
                                        className={`p-3 rounded-2xl text-left border transition-all ${category === t.id ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-900/20 ring-2 ring-indigo-500/20' : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40'}`}
                                    >
                                        <div className="flex items-center justify-between mb-1">
                                            <t.icon className={`w-4 h-4 ${category === t.id ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`} />
                                            <span className={`w-2 h-2 rounded-full ${category === t.id ? 'bg-indigo-600' : 'bg-transparent'}`} />
                                        </div>
                                        <div className="text-xs font-black text-slate-800 dark:text-white">{t.label}</div>
                                        <div className="text-[10px] text-slate-400 font-medium leading-tight mt-0.5">{t.desc}</div>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* 3. Live Preview Breakdown Card */}
                        <div className="p-4 rounded-2xl bg-indigo-50/60 dark:bg-indigo-950/20 border border-indigo-200/60 dark:border-indigo-900/40 space-y-3">
                            <div className="flex items-center justify-between">
                                <div className="text-xs font-black uppercase tracking-wider text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">
                                    <ShieldCheck className="w-4 h-4 text-indigo-600" /> Pending Verification Breakdown
                                </div>
                                {previewLoading && <Loader2 className="w-4 h-4 text-indigo-600 animate-spin" />}
                            </div>

                            {previewStats && (
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
                                    <div className="p-2.5 bg-white dark:bg-slate-800 rounded-xl border border-indigo-100 dark:border-slate-700">
                                        <div className="text-lg font-black text-slate-800 dark:text-white">{previewStats.total_teams_in_semester}</div>
                                        <div className="text-[10px] font-bold text-slate-400">Cohort Teams</div>
                                    </div>
                                    <div className="p-2.5 bg-amber-50 dark:bg-amber-950/30 rounded-xl border border-amber-200/50 dark:border-amber-900/40">
                                        <div className="text-lg font-black text-amber-600 dark:text-amber-400">{previewStats.pending_ps_teams_count}</div>
                                        <div className="text-[10px] font-bold text-amber-700 dark:text-amber-400">PS Pending</div>
                                    </div>
                                    <div className="p-2.5 bg-sky-50 dark:bg-sky-950/30 rounded-xl border border-sky-200/50 dark:border-sky-900/40">
                                        <div className="text-lg font-black text-sky-600 dark:text-sky-400">{previewStats.pending_github_teams_count}</div>
                                        <div className="text-[10px] font-bold text-sky-700 dark:text-sky-400">GitHub Pending</div>
                                    </div>
                                    <div className="p-2.5 bg-emerald-50 dark:bg-emerald-950/30 rounded-xl border border-emerald-200/50 dark:border-emerald-900/40">
                                        <div className="text-lg font-black text-emerald-600 dark:text-emerald-400">{previewStats.fully_completed_teams_count}</div>
                                        <div className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400">Completed (Excluded)</div>
                                    </div>
                                </div>
                            )}

                            {previewStats && (
                                <div className="text-[11px] text-slate-600 dark:text-slate-300 font-semibold bg-white/80 dark:bg-slate-800/80 p-2.5 rounded-xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between">
                                    <span>Target Pending Teams to Email: <strong className="text-indigo-600 dark:text-indigo-400">{previewStats.target_teams_count} Teams</strong></span>
                                    <span>Total Student Recipients: <strong className="text-indigo-600 dark:text-indigo-400">{previewStats.recipients_count} Emails</strong></span>
                                </div>
                            )}
                        </div>

                        {/* Notice Banner */}
                        <div className="p-4 rounded-2xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/40 flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                            <div className="text-xs text-amber-800 dark:text-amber-300 space-y-1">
                                <p className="font-bold">Automated Email Notification Rules:</p>
                                {category === 'pending_ps' && (
                                    <p>Emails will warn students to select a PS (or be assigned one by administration).</p>
                                )}
                                {category === 'pending_github' && (
                                    <p>Emails will remind teams with allocated Problem Statements to submit their GitHub repository URL.</p>
                                )}
                                {category === 'all' && (
                                    <p>Teams missing PS selection will be warned to select a PS (or be assigned one by administration), and teams missing GitHub repository URLs will be notified to submit their repo link.</p>
                                )}
                            </div>
                        </div>

                        {/* Optional Custom Message Overrides */}
                        <div className="space-y-3">
                            <div>
                                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                                    Custom Subject (Optional)
                                </label>
                                <input
                                    type="text"
                                    placeholder="Leave blank to use system default subject..."
                                    value={customSubject}
                                    onChange={(e) => setCustomSubject(e.target.value)}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                                    Additional Message Note (Optional)
                                </label>
                                <textarea
                                    rows={3}
                                    placeholder="Add an optional custom instruction or deadline note to include inside the email..."
                                    value={customMessage}
                                    onChange={(e) => setCustomMessage(e.target.value)}
                                    className="w-full px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                />
                            </div>
                        </div>

                        {/* Error Feedback */}
                        {error && (
                            <div className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/20 border border-rose-200 text-xs text-rose-700 dark:text-rose-400 font-medium">
                                {error}
                            </div>
                        )}

                        {/* Success Result */}
                        {result && (
                            <div className="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200/60 dark:border-emerald-900/40 text-xs text-emerald-800 dark:text-emerald-300 space-y-1">
                                <div className="flex items-center gap-2 font-black text-emerald-700 dark:text-emerald-400">
                                    <CheckCircle2 className="w-4 h-4" /> Emails Dispatched Successfully!
                                </div>
                                <p>{result.message}</p>
                                <div className="pt-2 flex flex-wrap gap-3 font-semibold text-[11px] text-emerald-700 dark:text-emerald-400 border-t border-emerald-200/40">
                                    <span>Teams Notified: <strong>{result.total_teams_notified}</strong></span>
                                    <span>Recipients: <strong>{result.recipients_count}</strong></span>
                                    <span>PS Pending: <strong>{result.pending_ps_teams_count}</strong></span>
                                    <span>GitHub Pending: <strong>{result.pending_github_teams_count}</strong></span>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Fixed Footer */}
                    <div className="p-4 sm:p-5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 flex items-center justify-between shrink-0">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2.5 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                        >
                            {result ? 'Close' : 'Cancel'}
                        </button>

                        <button
                            type="button"
                            disabled={sending || (previewStats && previewStats.target_teams_count === 0)}
                            onClick={handleSend}
                            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-bold tracking-wide shadow-lg shadow-indigo-500/20 transition-all active:scale-95 cursor-pointer"
                        >
                            {sending ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" /> Dispatching Emails...
                                </>
                            ) : (
                                <>
                                    <Send className="w-4 h-4" /> Send Email Reminders ({previewStats?.target_teams_count ?? 0} Teams)
                                </>
                            )}
                        </button>
                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
}
