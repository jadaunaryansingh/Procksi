import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Github, Clock, FileText, CheckCircle, Save, Award } from 'lucide-react';
import { useMilestones, fetchWithAuth } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

function MilestoneCard({ milestone, onUpdateSuccess }) {
    const [githubUrl, setGithubUrl] = useState(milestone.github_url || '');
    const [fileUrl, setFileUrl] = useState(milestone.file_url || '');
    const [saving, setSaving] = useState(false);

    const isApproved = String(milestone.status).toLowerCase() === 'approved';

    const schema = React.useMemo(() => {
        if (!milestone.form_schema) return null;
        try {
            return typeof milestone.form_schema === 'string'
                ? JSON.parse(milestone.form_schema)
                : milestone.form_schema;
        } catch (e) {
            return null;
        }
    }, [milestone.form_schema]);

    const [responses, setResponses] = useState(() => {
        if (milestone.submission_data) {
            try {
                return typeof milestone.submission_data === 'string'
                    ? JSON.parse(milestone.submission_data)
                    : milestone.submission_data;
            } catch (e) {
                return {};
            }
        }
        return {};
    });

    const handleSave = async () => {
        if (schema && schema.length > 0) {
            for (const q of schema) {
                if (q.required) {
                    const ans = responses[q.id];
                    if (!ans || (Array.isArray(ans) && ans.length === 0) || (typeof ans === 'string' && ans.trim() === '')) {
                        alert(`Please answer the required question: "${q.label}"`);
                        return;
                    }
                }
            }
        }

        setSaving(true);
        try {
            const body = schema 
                ? { submission_data: responses }
                : {
                    github_url: githubUrl.trim() || null,
                    file_url: fileUrl.trim() || null
                  };

            await fetchWithAuth(`/api/student/milestones/${milestone.id}`, {
                method: 'PATCH',
                body: body
            });
            alert('Milestone submission updated successfully!');
            onUpdateSuccess();
        } catch (err) {
            alert('Failed to update milestone: ' + err.message);
        } finally {
            setSaving(false);
        }
    };

    const statusColors = {
        not_started: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
        in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
        submitted: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400',
        completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400',
        approved: 'bg-emerald-500 text-white font-black'
    };

    const displayStatus = String(milestone.status).replace('_', ' ').toUpperCase();

    return (
        <div className={`bg-white dark:bg-slate-800 rounded-2xl border ${isApproved ? 'border-emerald-200 dark:border-emerald-500/30' : 'border-slate-200 dark:border-slate-700/50'} p-6 shadow-sm hover:shadow-md transition-all`}>
            <div className="flex flex-col lg:flex-row justify-between gap-6">
                <div className="flex-1 space-y-4">
                    <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{milestone.title}</h3>
                        <span className={`text-xs px-2.5 py-1 rounded-full font-bold uppercase tracking-wide ${statusColors[milestone.status] || 'bg-slate-100'}`}>
                            {displayStatus}
                        </span>
                    </div>

                    <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{milestone.description}</p>

                    <div className="flex items-center text-sm text-slate-500 dark:text-slate-400 mb-4 bg-slate-50 dark:bg-slate-900 w-fit px-3 py-1.5 rounded-lg border border-slate-100 dark:border-slate-700">
                        <Clock className="w-4 h-4 mr-2 text-indigo-500" />
                        <span className="font-semibold">Deadline: {new Date(milestone.deadline).toLocaleDateString()}</span>
                    </div>

                    {/* Conditional submission forms: Dynamic Form vs Legacy Inputs */}
                    <div className="space-y-4 pt-2">
                        {schema ? (
                            schema.map((q) => (
                                <div key={q.id} className="space-y-2 border-b border-slate-100 dark:border-slate-700/50 pb-4 last:border-0 last:pb-0">
                                    <label className="flex items-center text-xs font-bold text-slate-600 dark:text-slate-300 uppercase tracking-wider">
                                        {q.label}
                                        {q.required && <span className="text-red-500 ml-1">*</span>}
                                    </label>
                                    
                                    {q.type === 'text' && (
                                        <input
                                            type="text"
                                            placeholder="Your answer..."
                                            value={responses[q.id] || ''}
                                            onChange={e => setResponses(prev => ({ ...prev, [q.id]: e.target.value }))}
                                            disabled={isApproved || saving}
                                            className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all"
                                        />
                                    )}

                                    {q.type === 'paragraph' && (
                                        <textarea
                                            rows="3"
                                            placeholder="Your answer..."
                                            value={responses[q.id] || ''}
                                            onChange={e => setResponses(prev => ({ ...prev, [q.id]: e.target.value }))}
                                            disabled={isApproved || saving}
                                            className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all resize-none"
                                        />
                                    )}

                                    {q.type === 'mcq' && (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            {(q.options || []).map(option => {
                                                const isSelected = responses[q.id] === option;
                                                return (
                                                    <label 
                                                        key={option} 
                                                        className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm font-semibold cursor-pointer transition-all ${
                                                            isSelected 
                                                                ? 'bg-indigo-50/50 dark:bg-indigo-500/10 border-indigo-500 text-indigo-700 dark:text-indigo-400' 
                                                                : 'bg-slate-50/30 dark:bg-slate-900/30 border-slate-200 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-900/50 text-slate-600 dark:text-slate-300'
                                                        }`}
                                                    >
                                                        <input 
                                                            type="radio" 
                                                            name={q.id} 
                                                            value={option}
                                                            checked={isSelected}
                                                            onChange={() => setResponses(prev => ({ ...prev, [q.id]: option }))}
                                                            disabled={isApproved || saving}
                                                            className="w-4 h-4 text-indigo-600 focus:ring-indigo-500 border-slate-300 dark:border-slate-700"
                                                        />
                                                        <span>{option}</span>
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {q.type === 'checkbox' && (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            {(q.options || []).map(option => {
                                                const currentSelected = responses[q.id] || [];
                                                const isSelected = currentSelected.includes(option);
                                                const handleToggle = () => {
                                                    let next;
                                                    if (isSelected) {
                                                        next = currentSelected.filter(o => o !== option);
                                                    } else {
                                                        next = [...currentSelected, option];
                                                    }
                                                    setResponses(prev => ({ ...prev, [q.id]: next }));
                                                };
                                                return (
                                                    <label 
                                                        key={option} 
                                                        className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm font-semibold cursor-pointer transition-all ${
                                                            isSelected 
                                                                ? 'bg-indigo-50/50 dark:bg-indigo-500/10 border-indigo-500 text-indigo-700 dark:text-indigo-400' 
                                                                : 'bg-slate-50/30 dark:bg-slate-900/30 border-slate-200 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-900/50 text-slate-600 dark:text-slate-300'
                                                        }`}
                                                    >
                                                        <input 
                                                            type="checkbox" 
                                                            checked={isSelected}
                                                            onChange={handleToggle}
                                                            disabled={isApproved || saving}
                                                            className="w-4 h-4 text-indigo-600 focus:ring-indigo-500 border-slate-300 dark:border-slate-700 rounded"
                                                        />
                                                        <span>{option}</span>
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {q.type === 'github' && (
                                        <div className="relative">
                                            <Github className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                                            <input 
                                                type="url" 
                                                placeholder="https://github.com/username/repo-name"
                                                value={responses[q.id] || ''}
                                                onChange={e => setResponses(prev => ({ ...prev, [q.id]: e.target.value }))}
                                                disabled={isApproved || saving}
                                                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all font-mono"
                                            />
                                        </div>
                                    )}

                                    {q.type === 'file' && (
                                        <div className="relative">
                                            <FileText className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                                            <input 
                                                type="url" 
                                                placeholder="https://drive.google.com/your-document-link"
                                                value={responses[q.id] || ''}
                                                onChange={e => setResponses(prev => ({ ...prev, [q.id]: e.target.value }))}
                                                disabled={isApproved || saving}
                                                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all font-mono"
                                            />
                                        </div>
                                    )}
                                </div>
                            ))
                        ) : (
                            <>
                                <div>
                                    <label className="flex items-center text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                                        <Github className="w-4 h-4 mr-1 text-slate-400" /> GitHub URL
                                    </label>
                                    <input
                                        type="url"
                                        placeholder="https://github.com/username/repo-name"
                                        value={githubUrl}
                                        onChange={(e) => setGithubUrl(e.target.value)}
                                        disabled={isApproved || saving}
                                        className="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all font-mono"
                                    />
                                </div>
                                <div>
                                    <label className="flex items-center text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                                        <FileText className="w-4 h-4 mr-1 text-slate-400" /> Deliverable File URL (PDF/DOCX)
                                    </label>
                                    <input
                                        type="url"
                                        placeholder="https://drive.google.com/your-document-link"
                                        value={fileUrl}
                                        onChange={(e) => setFileUrl(e.target.value)}
                                        disabled={isApproved || saving}
                                        className="w-full px-3.5 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50 text-slate-700 dark:text-slate-200 transition-all font-mono"
                                    />
                                </div>
                            </>
                        )}
                    </div>
                </div>

                {!isApproved && (
                    <div className="shrink-0 flex items-end justify-end lg:justify-start">
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition-colors shadow-sm active:scale-95 w-full lg:w-auto"
                        >
                            <Save className="w-4 h-4 mr-2" />
                            {saving ? 'Saving...' : 'Save Submission'}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

export const MilestonesView = () => {
    const { data: milestones, loading, error, refetch } = useMilestones();

    if (loading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={8} />
            </div>
        );
    }

    if (error && error !== "Student is not assigned to a team") {
        return <ErrorCard message={error} onRetry={refetch} />;
    }

    const mList = milestones || [];

    if (mList.length === 0) {
        return (
            <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-12 text-center shadow-sm">
                <Award className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">No Synopsis Requests Assigned</h3>
                <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                    There are no synopsis submission requests assigned to your team yet. Once your mentor assigns a synopsis request, it will be listed here.
                </p>
            </div>
        );
    }

    const completed = mList.filter(m => String(m.status).toLowerCase() === 'completed' || String(m.status).toLowerCase() === 'approved').length;
    const progress = Math.round((completed / mList.length) * 100);

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-6 shadow-sm hover:shadow-md transition-shadow flex flex-col md:flex-row items-center justify-between gap-6">
                <div data-tour="student-milestone-progress" className="flex-1 w-full">
                    <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-2">Synopsis Submission Progress</h3>
                    <div className="flex justify-between items-end mb-2">
                        <span className="text-sm text-slate-500 dark:text-slate-400 font-medium">{completed} of {mList.length} synopsis submissions approved</span>
                        <span className="text-2xl font-black text-indigo-600 dark:text-indigo-400">{progress}%</span>
                    </div>
                    <div className="w-full bg-slate-100 dark:bg-slate-700 rounded-full h-3 overflow-hidden shadow-inner">
                        <motion.div initial={{ width: 0 }} animate={{ width: `${progress}%` }} transition={{ duration: 1, ease: "easeOut" }} className="bg-indigo-600 dark:bg-indigo-500 h-full rounded-full" />
                    </div>
                </div>
            </div>

            {/* Timeline List of Milestones */}
            <div data-tour="student-milestone-list" className="relative border-l-2 border-slate-200 dark:border-slate-700 ml-4 md:ml-6 space-y-10 py-4">
                {mList.map((milestone, idx) => {
                    const isCompleted = String(milestone.status).toLowerCase() === 'completed' || String(milestone.status).toLowerCase() === 'approved';
                    const isNext = !isCompleted && (idx === 0 || String(mList[idx - 1]?.status).toLowerCase() === 'completed' || String(mList[idx - 1]?.status).toLowerCase() === 'approved');

                    return (
                        <div key={milestone.id} className="relative pl-8 md:pl-12">
                            {/* Timeline Dot */}
                            <div className={`absolute w-5 h-5 rounded-full -left-[11px] top-1 border-4 border-white dark:border-slate-900 shadow-sm transition-colors duration-300
                                ${isCompleted ? 'bg-emerald-500' : isNext ? 'bg-indigo-500 animate-pulse' : 'bg-slate-300 dark:bg-slate-600'}`}>
                            </div>

                            <MilestoneCard milestone={milestone} onUpdateSuccess={refetch} />
                        </div>
                    );
                })}
            </div>
        </motion.div>
    );
};

export default MilestonesView;
