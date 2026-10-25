import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Activity, Plus, CheckCircle, Clock, Trophy, Target, Award,
    Calendar, Paperclip, X, AlertCircle, ExternalLink
} from 'lucide-react';
import { useExtraActivities, fetchWithAuth } from '../hooks/useStudentData';
import { supabase } from '../lib/supabase';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';

export default function ExtraActivitiesView() {
    const { data: activities = [], loading, error, refetch } = useExtraActivities();

    const [isAdding, setIsAdding] = useState(false);
    const [title, setTitle] = useState('');
    const [desc, setDesc] = useState('');
    const [actDate, setActDate] = useState('');
    const [proofFile, setProofFile] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const [uploadProgress, setUploadProgress] = useState('');
    const fileInputRef = useRef(null);

    const resetForm = () => {
        setTitle('');
        setDesc('');
        setActDate('');
        setProofFile(null);
        setUploadProgress('');
    };

    if (loading) {
        return (
            <div className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                    <LoadingSkeleton lines={5} />
                </div>
            </div>
        );
    }

    if (error) {
        return <ErrorCard message={error} onRetry={refetch} />;
    }

    const verifiedActivities = (activities || []).filter(
        a => (a.status || '').toLowerCase() === 'approved' || (a.status || '').toLowerCase() === 'verified'
    );
    const totalPoints = verifiedActivities.reduce((sum, act) => sum + (act.points || 0), 0);

    const handleFileChange = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 10 * 1024 * 1024) {
            alert('File size must be under 10 MB.');
            return;
        }
        setProofFile(file);
    };

    const handleSubmitActivity = async () => {
        if (!title.trim() || !desc.trim()) {
            alert('Please fill in the title and description.');
            return;
        }
        setSubmitting(true);
        try {
            let proofUrl = null;

            // Upload proof file to Supabase Storage if provided
            if (proofFile) {
                setUploadProgress('Uploading proof…');
                try {
                    const { data: { session } } = await supabase.auth.getSession();
                    const userId = session?.user?.id || 'unknown';
                    const ext = proofFile.name.split('.').pop();
                    const filePath = `extra-activities/${userId}/${Date.now()}.${ext}`;

                    const bucket = 'PMS';
                    const uploadResult = await supabase.storage
                        .from(bucket)
                        .upload(filePath, proofFile, { upsert: false });
                    if (!uploadResult.error) {
                        const { data: urlData } = supabase.storage.from(bucket).getPublicUrl(filePath);
                        proofUrl = urlData?.publicUrl || null;
                    } else {
                        throw uploadResult.error;
                    }
                } catch (_uploadErr) {
                    console.error("Supabase upload error:", _uploadErr);
                    alert("Failed to upload certificate proof: " + (_uploadErr.message || _uploadErr.error_description || JSON.stringify(_uploadErr)));
                    setSubmitting(false);
                    setUploadProgress('');
                    return;
                }
                setUploadProgress('');
            }

            setUploadProgress('Submitting…');
            await fetchWithAuth('/api/student/extra-activities', {
                method: 'POST',
                body: {
                    title: title.trim(),
                    description: desc.trim(),
                    date: actDate || new Date().toISOString().split('T')[0],
                    proof_url: proofUrl
                }
            });

            alert('Activity submitted successfully!');
            resetForm();
            setIsAdding(false);
            refetch();
        } catch (err) {
            alert(err.message || 'Failed to submit activity');
        } finally {
            setSubmitting(false);
            setUploadProgress('');
        }
    };

    const getStatusBadge = (status) => {
        const s = (status || '').toLowerCase();
        if (s === 'approved' || s === 'verified') {
            return (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400">
                    <CheckCircle className="w-3.5 h-3.5 mr-1" /> Approved
                </span>
            );
        }
        if (s === 'rejected') {
            return (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-bold bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400">
                    <AlertCircle className="w-3.5 h-3.5 mr-1" /> Rejected
                </span>
            );
        }
        return (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-bold bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400">
                <Clock className="w-3.5 h-3.5 mr-1" /> Pending Review
            </span>
        );
    };

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                    <Activity className="w-6 h-6 mr-3 text-indigo-500" /> Extra-Curricular Activities
                </h2>
                <button
                    onClick={() => setIsAdding(true)}
                    className="flex items-center px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition-colors shadow-md shadow-indigo-500/20 active:scale-95"
                >
                    <Plus className="w-4 h-4 mr-2" /> Add Activity
                </button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-6 flex items-center space-x-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
                    <Target className="absolute -right-4 -bottom-4 w-24 h-24 text-blue-500/5 dark:text-blue-400/5 group-hover:scale-110 group-hover:-rotate-12 transition-transform" />
                    <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-500/10 text-blue-500 flex items-center justify-center shrink-0">
                        <Target className="w-7 h-7" />
                    </div>
                    <div>
                        <p className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Total Activities</p>
                        <h3 className="text-3xl font-black text-slate-800 dark:text-slate-100">{activities.length}</h3>
                    </div>
                </div>

                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-6 flex items-center space-x-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
                    <CheckCircle className="absolute -right-4 -bottom-4 w-24 h-24 text-emerald-500/5 dark:text-emerald-400/5 group-hover:scale-110 group-hover:rotate-12 transition-transform" />
                    <div className="w-14 h-14 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
                        <CheckCircle className="w-7 h-7" />
                    </div>
                    <div>
                        <p className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Approved</p>
                        <h3 className="text-3xl font-black text-slate-800 dark:text-slate-100">{verifiedActivities.length}</h3>
                    </div>
                </div>

                <div className="bg-gradient-to-br from-indigo-500 to-purple-600 rounded-3xl border border-indigo-400 dark:border-indigo-500/50 p-6 flex items-center space-x-4 shadow-md text-white relative overflow-hidden group">
                    <Trophy className="absolute -right-4 -bottom-4 w-24 h-24 text-white/10 group-hover:scale-110 group-hover:-rotate-12 transition-transform" />
                    <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center shrink-0">
                        <Award className="w-7 h-7 text-white" />
                    </div>
                    <div className="relative z-10">
                        <p className="text-sm font-bold text-indigo-100 uppercase tracking-wider mb-1">Total Points</p>
                        <h3 className="text-3xl font-black">{totalPoints}</h3>
                    </div>
                </div>
            </div>

            {/* Activity History */}
            <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden">
                <div className="p-6 md:p-8 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/80">
                    <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">Activity History</h3>
                </div>
                <div className="divide-y divide-slate-100 dark:divide-slate-700/50">
                    <AnimatePresence>
                        {(activities || []).map((act) => (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                key={act.id}
                                className="p-6 md:p-8 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors flex flex-col md:flex-row gap-6 md:items-center"
                            >
                                <div className="flex-1">
                                    <div className="flex items-center gap-3 mb-2 flex-wrap">
                                        <h4 className="text-lg font-bold text-slate-800 dark:text-slate-100">{act.title}</h4>
                                        {getStatusBadge(act.status)}
                                    </div>
                                    <p className="text-slate-600 dark:text-slate-400 text-sm mb-3">{act.description}</p>
                                    <div className="flex items-center gap-4 flex-wrap">
                                        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider flex items-center">
                                            <Calendar className="w-3.5 h-3.5 mr-1.5" /> {act.date || '—'}
                                        </p>
                                        {act.proof_url && (
                                            <a href={act.proof_url} target="_blank" rel="noopener noreferrer"
                                                className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 flex items-center hover:underline">
                                                <Paperclip className="w-3.5 h-3.5 mr-1" /> View Proof
                                                <ExternalLink className="w-3 h-3 ml-1" />
                                            </a>
                                        )}
                                    </div>
                                </div>
                                <div className="shrink-0 flex items-center md:flex-col md:items-end gap-4 md:gap-2">
                                    <div className="text-center">
                                        <span className="block text-3xl font-black text-indigo-600 dark:text-indigo-400">{act.points || 0}</span>
                                        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Points</span>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </AnimatePresence>
                    {activities.length === 0 && (
                        <div className="p-16 text-center text-slate-500 dark:text-slate-400 flex flex-col items-center justify-center">
                            <Activity className="w-16 h-16 text-indigo-100 dark:text-indigo-900/40 mb-6" />
                            <h3 className="text-xl font-bold text-slate-800 dark:text-slate-200 mb-2">No Activities Yet</h3>
                            <p className="text-sm max-w-sm leading-relaxed">
                                You haven't added any extra-curricular activities. Click <span className="font-semibold text-indigo-600 dark:text-indigo-400">"Add Activity"</span> to get started.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* Add Activity Modal */}
            <AnimatePresence>
                {isAdding && (
                    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => { setIsAdding(false); resetForm(); }} className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm" />
                        <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="relative w-full max-w-lg bg-white dark:bg-slate-800 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden z-10 flex flex-col max-h-[90vh]">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-between shrink-0">
                                <h3 className="text-xl font-bold text-slate-800 dark:text-white">Submit New Activity</h3>
                                <button onClick={() => { setIsAdding(false); resetForm(); }} className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6 space-y-5 overflow-y-auto">
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1.5">Activity Title <span className="text-rose-500">*</span></label>
                                    <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-500 dark:focus:border-indigo-500 transition-colors dark:text-white font-medium" placeholder="Ex: Hackathon Winner, Sports Achievement…" />
                                </div>
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1.5">Description <span className="text-rose-500">*</span></label>
                                    <textarea rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-500 dark:focus:border-indigo-500 transition-colors resize-none dark:text-white font-medium" placeholder="Briefly describe your involvement…"></textarea>
                                </div>
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1.5">Date of Activity</label>
                                    <input type="date" value={actDate} onChange={(e) => setActDate(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm outline-none focus:border-indigo-500 dark:focus:border-indigo-500 transition-colors dark:text-white font-medium" />
                                </div>
                                {/* Proof attachment */}
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
                                        <Paperclip className="w-4 h-4 text-indigo-500" /> Proof / Certificate (optional)
                                    </label>
                                    <input
                                        type="file"
                                        ref={fileInputRef}
                                        accept="image/*,application/pdf"
                                        onChange={handleFileChange}
                                        className="hidden"
                                    />
                                    {proofFile ? (
                                        <div className="flex items-center gap-3 p-3 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 rounded-xl">
                                            <Paperclip className="w-4 h-4 text-indigo-500 shrink-0" />
                                            <span className="text-sm font-medium text-indigo-700 dark:text-indigo-300 truncate flex-1">{proofFile.name}</span>
                                            <button onClick={() => { setProofFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }} className="p-1 text-indigo-400 hover:text-rose-500 transition-colors">
                                                <X className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ) : (
                                        <button onClick={() => fileInputRef.current?.click()} className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-slate-50 dark:bg-slate-900/50 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-xl text-sm font-semibold text-slate-500 dark:text-slate-400 hover:border-indigo-400 hover:text-indigo-600 dark:hover:border-indigo-500 dark:hover:text-indigo-400 transition-colors">
                                            <Paperclip className="w-4 h-4" /> Attach PDF or Image (max 10 MB)
                                        </button>
                                    )}
                                </div>
                            </div>
                            <div className="p-6 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex gap-3 justify-end shrink-0">
                                <button disabled={submitting} onClick={() => { setIsAdding(false); resetForm(); }} className="px-5 py-2.5 rounded-xl text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">Cancel</button>
                                <button disabled={submitting} onClick={handleSubmitActivity} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-xl text-sm font-bold transition-colors shadow-sm active:scale-95 min-w-[120px] flex items-center justify-center gap-2">
                                    {submitting ? (
                                        <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block"></span> {uploadProgress || 'Submitting…'}</>
                                    ) : 'Submit Activity'}
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}
