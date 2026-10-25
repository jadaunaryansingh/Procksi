import React, { useState, useEffect } from 'react';
import { Save, Lock, Unlock, AlertCircle, Settings2, Calendar, CheckCircle, Plus, ChevronLeft, CalendarDays, Power, Loader2, Edit2, Trash2, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../services/api';
import { syncEvaluationParameters } from '../services/panelSync';
import { apiFetchTable, apiUpsertTable, apiDeleteRows } from '../lib/api';

function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

export default function SemesterSettings() {
    const [viewMode, setViewMode] = useState('list'); // 'list' | 'create' | 'edit'
    const [semesters, setSemesters] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [editingId, setEditingId] = useState(null);
    const [deletingSem, setDeletingSem] = useState(null);
    const [isDeleting, setIsDeleting] = useState(false);
    const [presentationCycles, setPresentationCycles] = useState([]);
    
    // Creation State
    const [config, setConfig] = useState({
        year: '2026-2027',
        semester_type: 'odd',
        academic_level: 4,
        semester_number: 7,
        branch: 'BTech CSE',
        team_size_min: 1,
        team_size_max: 3,
        number_of_presentations: 3,
        proposal_weight: 20,
        mid_weight: 30,
        final_weight: 50,
        evaluation_parameters: [
            { name: 'Project Overview & Problem Statement', description: 'Clarity of problem definition and project scope', max_marks: 10 },
            { name: 'Solution Design & Feasibility', description: 'Technical approach, architecture, and viability of the solution', max_marks: 15 },
            { name: 'Progress vs Plan', description: 'How well the team is tracking against the original project timeline', max_marks: 15 },
            { name: 'Technical Implementation', description: 'Code quality, design patterns, and system functionality', max_marks: 20 },
            { name: 'Innovation & Impact', description: 'Originality of approach and real-world value of the solution', max_marks: 20 },
            { name: 'Demonstration & Viva', description: 'Quality of live demonstration and responses during Q&A', max_marks: 20 },
        ]
    });

    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);


    const loadSemesters = async () => {
        setIsLoading(true);
        try {
            const [res, cyclesRes, rubricsRes] = await Promise.all([
                api.getSemesterConfig(),
                apiFetchTable('presentation_cycles').catch(() => []),
                apiFetchTable('presentation_rubrics').catch(() => [])
            ]);
            const rows = Array.isArray(res?.data) ? res.data : [];
            const cycles = Array.isArray(cyclesRes) ? cyclesRes : [];
            const rubrics = Array.isArray(rubricsRes) ? rubricsRes : [];

            const enriched = rows.map(s => {
                const semCycles = cycles.filter(c => c.semester_id === s.id).map(c => {
                    const cycleRubrics = rubrics.filter(r => r.cycle_id === c.id);
                    return {
                        ...c,
                        evaluation_parameters: cycleRubrics.map(r => ({
                            id: r.id,
                            criterion: r.criterion,
                            max_marks: r.max_marks,
                            weight: r.weight || 1
                        }))
                    };
                });
                return {
                    ...s,
                    presentation_cycles: semCycles,
                    evaluation_parameters: s.evaluation_parameters || []
                };
            });

            setSemesters(enriched);
        } catch (err) {
            setError('Failed to load semester configurations.');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        loadSemesters();
    }, []);

    const resetConfig = async () => {
        setConfig({
            year: '2026-2027',
            semester_type: 'odd',
            academic_level: 4,
            semester_number: 7,
            branch: 'BTech CSE',
            team_size_min: 1,
            team_size_max: 3,
            number_of_presentations: 3,
            proposal_weight: 20,
            mid_weight: 30,
            final_weight: 50,
            evaluation_parameters: [],
        });
        setPresentationCycles([
            {
                id: `cycle-${Date.now()}-1`,
                title: 'Proposal Evaluation',
                type: 'proposal',
                weightage: 20,
                deadline: '',
                status: 'draft',
                requires_synopsis: true,
                evaluation_parameters: [
                    { id: `rubric-${Date.now()}-1-1`, criterion: 'Literature Survey & Motivation', max_marks: 30 },
                    { id: `rubric-${Date.now()}-1-2`, criterion: 'Problem Statement & Scope', max_marks: 30 },
                    { id: `rubric-${Date.now()}-1-3`, criterion: 'Proposed Methodology', max_marks: 40 }
                ]
            },
            {
                id: `cycle-${Date.now()}-2`,
                title: 'Mid-Term Presentation',
                type: 'mid',
                weightage: 30,
                deadline: '',
                status: 'draft',
                requires_synopsis: true,
                evaluation_parameters: [
                    { id: `rubric-${Date.now()}-2-1`, criterion: 'Design & Architecture', max_marks: 30 },
                    { id: `rubric-${Date.now()}-2-2`, criterion: 'Implementation Progress', max_marks: 40 },
                    { id: `rubric-${Date.now()}-2-3`, criterion: 'Presentation & Q&A', max_marks: 30 }
                ]
            },
            {
                id: `cycle-${Date.now()}-3`,
                title: 'Final Evaluation',
                type: 'final',
                weightage: 50,
                deadline: '',
                status: 'draft',
                requires_synopsis: true,
                evaluation_parameters: [
                    { id: `rubric-${Date.now()}-3-1`, criterion: 'Technical Execution & Depth', max_marks: 40 },
                    { id: `rubric-${Date.now()}-3-2`, criterion: 'Quality of Deliverables', max_marks: 30 },
                    { id: `rubric-${Date.now()}-3-3`, criterion: 'Viva Voce & Response to Q&A', max_marks: 30 }
                ]
            }
        ]);
        setEditingId(null);
    };

    const startEditing = (sem) => {
        if (sem.is_locked) return;

        setConfig({
            year: sem.year,
            semester_type: sem.semester_type,
            academic_level: sem.academic_level,
            semester_number: sem.semester_number,
            branch: sem.branch,
            team_size_min: sem.team_size_min,
            team_size_max: sem.team_size_max,
            number_of_presentations: sem.number_of_presentations,
            proposal_weight: sem.proposal_weight,
            mid_weight: sem.mid_weight,
            final_weight: sem.final_weight,
            evaluation_parameters: [],
        });
        setPresentationCycles(sem.presentation_cycles || []);
        setEditingId(sem.id);
        setViewMode('edit');
    };

    const handleSave = async () => {
        setError('');
        setSuccess('');

        const totalCyclesWeight = presentationCycles.reduce((sum, c) => sum + parseInt(c.weightage || 0), 0);
        if (totalCyclesWeight !== 100) {
            setError(`Total weight of presentation cycles must exactly equal 100%. Current total: ${totalCyclesWeight}%`);
            return;
        }

        if (config.team_size_min > config.team_size_max) {
            setError('Minimum team size cannot be greater than maximum team size.');
            return;
        }

        setIsSubmitting(true);
        try {
            const semId = editingId || uuidv4();
            
            const proposalCycle = presentationCycles.find(c => c.type === 'proposal');
            const midCycle = presentationCycles.find(c => c.type === 'mid');
            const finalCycle = presentationCycles.find(c => c.type === 'final');

            const proposalWeight = proposalCycle ? parseInt(proposalCycle.weightage || 0) : 0;
            const midWeight = midCycle ? parseInt(midCycle.weightage || 0) : 0;
            const finalWeight = finalCycle ? parseInt(finalCycle.weightage || 0) : 0;

            const configToSave = {
                ...config,
                id: semId,
                proposal_weight: proposalWeight,
                mid_weight: midWeight,
                final_weight: finalWeight,
                number_of_presentations: presentationCycles.length
            };

            if (viewMode === 'edit') {
                await api.updateSemesterConfig(semId, configToSave);
            } else {
                await api.createSemesterConfig(configToSave);
            }

            // Sync evaluation rubric to panel portal (non-blocking)
            try {
                await syncEvaluationParameters(config.evaluation_parameters);
            } catch (syncErr) {
                console.warn('Could not sync eval params to panel portal (non-critical):', syncErr.message);
            }

            // Save cycles to DB: upsert all, and delete removed ones
            const cyclesToUpsert = presentationCycles.map(c => ({
                id: c.id && !c.id.startsWith('cycle-') ? c.id : uuidv4(),
                semester_id: semId,
                title: c.title,
                type: c.type,
                weightage: parseInt(c.weightage || 0),
                deadline: c.deadline ? new Date(c.deadline).toISOString() : new Date().toISOString(),
                status: c.status || 'draft',
                requires_synopsis: Boolean(c.requires_synopsis),
                enable_mentor_eval: Boolean(c.enable_mentor_eval),
                mentor_max_marks: parseInt(c.mentor_max_marks || 0)
            }));

            await apiUpsertTable('presentation_cycles', cyclesToUpsert, 'id');

            // Upsert rubric criteria per presentation cycle
            const rubricsToUpsert = [];
            presentationCycles.forEach((c, idx) => {
                const upsertedCycleId = cyclesToUpsert[idx].id;
                const params = c.evaluation_parameters || [];
                params.forEach(p => {
                    rubricsToUpsert.push({
                        id: p.id && !p.id.startsWith('rubric-') ? p.id : uuidv4(),
                        cycle_id: upsertedCycleId,
                        criterion: p.criterion,
                        max_marks: parseInt(p.max_marks || 0),
                        weight: parseInt(p.weight || 1)
                    });
                });
            });

            if (rubricsToUpsert.length > 0) {
                await apiUpsertTable('presentation_rubrics', rubricsToUpsert, 'id');
            }

            // Cleanup deleted rubrics
            const previousRubricIds = [];
            semesters.find(s => s.id === semId)?.presentation_cycles?.forEach(c => {
                c.evaluation_parameters?.forEach(p => {
                    if (p.id) previousRubricIds.push(p.id);
                });
            });
            const currentRubricIds = rubricsToUpsert.map(r => r.id);
            const deletedRubricIds = previousRubricIds.filter(id => !currentRubricIds.includes(id));
            const rubricsToDelete = deletedRubricIds.filter(id => id && !String(id).startsWith('rubric-'));
            if (rubricsToDelete.length > 0) {
                await Promise.all(rubricsToDelete.map(async id => {
                    await apiDeleteRows('presentation_evaluation_scores', { rubric_id: id }).catch(e => console.warn('Ignore cascade delete fail:', e));
                    await apiDeleteRows('presentation_rubrics', { id });
                }));
            }

            if (viewMode === 'edit') {
                const originalCycles = semesters.find(s => s.id === editingId)?.presentation_cycles || [];
                const originalCycleIds = originalCycles.map(c => c.id) || [];
                const currentCycleIds = cyclesToUpsert.map(c => c.id);
                const deletedCycleIds = originalCycleIds.filter(id => !currentCycleIds.includes(id));
                const cyclesToDelete = deletedCycleIds.filter(id => id && !String(id).startsWith('cycle-'));
                if (cyclesToDelete.length > 0) {
                    await Promise.all(cyclesToDelete.map(async id => {
                        const cycleObj = originalCycles.find(c => c.id === id);
                        await apiDeleteRows('presentation_evaluations', { cycle_id: id }).catch(e => console.warn('Ignore cascade:', e));
                        if (cycleObj && cycleObj.evaluation_parameters) {
                            await Promise.all(cycleObj.evaluation_parameters.map(async r => {
                                if (r.id && !String(r.id).startsWith('rubric-')) {
                                    await apiDeleteRows('presentation_evaluation_scores', { rubric_id: r.id }).catch(e => console.warn('Ignore cascade:', e));
                                    await apiDeleteRows('presentation_rubrics', { id: r.id }).catch(e => console.warn('Ignore cascade:', e));
                                }
                            }));
                        }
                        await apiDeleteRows('presentation_cycles', { id });
                    }));
                }
            }

            setSuccess('Semester configuration and presentation cycles saved successfully.');
            await loadSemesters();
            setTimeout(() => {
                setSuccess('');
                setViewMode('list');
            }, 2000);
        } catch (err) {
            setError(err.message || 'Failed to save semester config.');
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleActivate = async (semesterId, isActive) => {
        try {
            await api.activateSemester(semesterId, isActive);
            setSuccess(`Semester ${isActive ? 'activated' : 'deactivated'} successfully.`);
            await loadSemesters();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err) {
            setError(err.message || `Failed to ${isActive ? 'activate' : 'deactivate'} semester.`);
            setTimeout(() => setError(''), 4000);
        }
    };

    const handleLockToggle = async (semesterId, currentLockStatus) => {
        try {
            await api.lockSemester(semesterId, !currentLockStatus);
            setSuccess(`Semester rules ${!currentLockStatus ? 'LOCKED' : 'UNLOCKED'} successfully.`);
            await loadSemesters();
            setTimeout(() => setSuccess(''), 3000);
        } catch (err) {
            setError(err.message || 'Failed to toggle lock.');
            setTimeout(() => setError(''), 4000);
        }
    };

    const handleDeleteSemester = async () => {
        if (!deletingSem) return;
        setIsDeleting(true);
        setError('');
        setSuccess('');
        try {
            await api.deleteSemester(deletingSem.id);
            setSuccess(`Semester configuration and all associated data deleted successfully.`);
            setDeletingSem(null);
            await loadSemesters();
            setTimeout(() => setSuccess(''), 4000);
        } catch (err) {
            setError(err.message || 'Failed to delete semester and associated data.');
            setTimeout(() => setError(''), 5000);
        } finally {
            setIsDeleting(false);
        }
    };

    if (viewMode === 'list') {
        return (
            <div className="space-y-8 relative z-10 w-full min-h-[calc(100vh-8rem)]">
                {/* Header Banner */}
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} 
                    className="bg-gradient-to-r from-violet-600 via-violet-700 to-indigo-800 rounded-3xl p-8 text-white shadow-xl shadow-violet-500/20 relative overflow-hidden flex flex-col md:flex-row items-center justify-between border border-violet-500/30">
                    <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                        <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                            <path d="M0,300 C300,0 700,300 1000,0 L1000,300 Z" fill="currentColor"></path>
                        </svg>
                    </div>
                    <div className="relative z-10 w-full lg:w-2/3">
                        <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20 shadow-sm transition-colors">
                            <Settings2 className="w-4 h-4 mr-2" /> System Configuration
                        </div>
                        <h1 className="text-3xl sm:text-4xl font-black mb-3 flex items-center gap-4">
                            Semester Registry
                        </h1>
                        <p className="text-violet-100/90 leading-relaxed text-sm md:text-base max-w-lg font-medium">Manage and review all historical and active academic semesters in the system.</p>
                    </div>
                    <div className="hidden lg:block relative z-10 opacity-70 drop-shadow-2xl">
                        <svg viewBox="0 0 100 100" className="w-48 h-48 text-violet-200 animate-[spin_30s_linear_infinite]" fill="none" stroke="currentColor">
                            <circle cx="50" cy="50" r="30" strokeWidth="12" strokeDasharray="10 5" />
                            <circle cx="50" cy="50" r="45" strokeWidth="2" strokeDasharray="5 5" opacity="0.5" />
                            <circle cx="50" cy="50" r="15" fill="currentColor" opacity="0.5" />
                        </svg>
                    </div>
                </motion.div>

                {/* Top Toolbar */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="flex justify-end space-x-4 w-full">
                    <button onClick={async () => { await resetConfig(); setViewMode('create'); }} className="flex items-center justify-center px-8 py-3 bg-violet-600 border border-violet-500/50 hover:bg-violet-700 text-white font-black uppercase tracking-widest text-sm rounded-xl transition-all shadow-lg shadow-violet-500/30 active:scale-95">
                        <Plus className="w-5 h-5 mr-3" /> Create New Config
                    </button>
                </motion.div>

                <AnimatePresence>
                    {error && (
                        <motion.div initial={{ opacity: 0, height: 0, y: -20 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -20 }} className="overflow-hidden">
                            <div className="bg-red-50 text-red-700 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 dark:text-red-400 p-5 rounded-2xl flex items-center font-bold shadow-md shadow-red-500/5 mb-2">
                                <AlertCircle className="w-6 h-6 mr-4 shrink-0" /> {error}
                            </div>
                        </motion.div>
                    )}
                    {success && (
                        <motion.div initial={{ opacity: 0, height: 0, y: -20 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -20 }} className="overflow-hidden">
                            <div className="bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 dark:text-emerald-400 p-5 rounded-2xl flex items-center font-bold shadow-md shadow-emerald-500/5 mb-2">
                                <CheckCircle className="w-6 h-6 mr-4 shrink-0 animate-pulse" /> {success}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {isLoading ? (
                    <div className="flex items-center justify-center min-h-[300px]">
                        <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
                    </div>
                ) : semesters.length === 0 ? (
                    <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-12 text-center rounded-3xl border border-slate-200/50 dark:border-slate-700/50">
                        <CalendarDays className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                        <h2 className="text-xl font-bold text-slate-700 dark:text-slate-300">No Semesters Found</h2>
                        <p className="text-sm text-slate-500 mt-2">Initialize your first semester configuration to begin.</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {semesters.map((sem) => (
                            <motion.div key={sem.id} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className={`bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 rounded-3xl shadow-sm border ${sem.is_active ? 'border-violet-400 dark:border-violet-500 shadow-violet-500/10 ring-4 ring-violet-500/10' : 'border-slate-200/50 dark:border-slate-700/50'} relative transition-all group`}>
                                {sem.is_active && (
                                    <div className="absolute top-0 right-6 -translate-y-1/2 bg-violet-500 text-white text-[10px] font-black uppercase tracking-widest px-3 py-1 rounded-full shadow-md">
                                        Active
                                    </div>
                                )}
                                
                                <div className="flex justify-between items-start mb-6">
                                    <div>
                                        <h3 className="text-2xl font-black text-slate-800 dark:text-white flex items-center">
                                            {sem.year}
                                        </h3>
                                        <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mt-1">
                                            {sem.semester_type} sem • {sem.branch}
                                        </p>
                                    </div>
                                    <div className="w-10 h-10 rounded-xl bg-violet-50 dark:bg-violet-500/10 flex items-center justify-center text-violet-600 dark:text-violet-400">
                                        <span className="font-bold">Y{sem.academic_level}</span>
                                    </div>
                                </div>

                                <div className="space-y-4 mb-8">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-slate-500 dark:text-slate-400">Roster Limit</span>
                                        <span className="font-bold text-slate-700 dark:text-slate-200">{sem.team_size_min} - {sem.team_size_max}</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span className="text-slate-500 dark:text-slate-400">Cycles</span>
                                        <span className="font-bold text-slate-700 dark:text-slate-200">{sem.number_of_presentations} presentations</span>
                                    </div>
                                    <div className="border-t border-slate-100 dark:border-slate-700 pt-4 space-y-2">
                                        <span className="block text-xs uppercase tracking-widest font-bold text-slate-400 mb-1">Presentation Cycles & Weights</span>
                                        {Array.isArray(sem.presentation_cycles) && sem.presentation_cycles.length > 0 ? (
                                            <div className="grid grid-cols-1 gap-2">
                                                {sem.presentation_cycles.map((c) => (
                                                    <div key={c.id} className="flex justify-between items-center text-xs bg-slate-50 dark:bg-slate-900/40 px-3 py-1.5 rounded-lg border border-slate-100 dark:border-slate-700/50">
                                                        <span className="font-semibold text-slate-600 dark:text-slate-300 truncate max-w-[160px]" title={c.title}>{c.title || 'Untitled Cycle'}</span>
                                                        <span className="font-black text-violet-600 dark:text-violet-400 shrink-0">{c.weightage}%</span>
                                                    </div>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="text-xs text-slate-400 italic">No presentation cycles defined</div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex items-center justify-between border-t border-slate-100 dark:border-slate-700 pt-5">
                                    <button 
                                        onClick={() => handleLockToggle(sem.id, sem.is_locked)} 
                                        className={`flex items-center px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-widest transition-colors ${sem.is_locked ? 'bg-amber-50 dark:bg-amber-500/10 hover:bg-amber-100 dark:hover:bg-amber-500/20 text-amber-600 dark:text-amber-400' : 'bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'}`}
                                    >
                                        {sem.is_locked ? <><Lock className="w-3.5 h-3.5 mr-1.5" /> Locked</> : <><Unlock className="w-3.5 h-3.5 mr-1.5" /> Mutable</>}
                                    </button>
                                    <div className="flex space-x-2">
                                        {!sem.is_locked && (
                                            <button onClick={() => startEditing(sem)} className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-600 dark:text-slate-300 text-xs font-black uppercase tracking-widest rounded-lg transition-colors flex items-center" title="Edit Configuration">
                                                <Edit2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                        {!sem.is_active ? (
                                            <button onClick={() => handleActivate(sem.id, true)} className="px-4 py-2 bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-xs font-black uppercase tracking-widest rounded-lg transition-colors flex items-center" title="Activate Semester">
                                                <Power className="w-3.5 h-3.5" />
                                            </button>
                                        ) : (
                                            <button onClick={() => handleActivate(sem.id, false)} className="px-4 py-2 bg-rose-50 dark:bg-rose-500/10 hover:bg-rose-100 dark:hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 text-xs font-black uppercase tracking-widest rounded-lg transition-colors flex items-center" title="Deactivate Semester">
                                                <Power className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                        <button onClick={() => setDeletingSem(sem)} className="px-4 py-2 bg-red-50 dark:bg-red-500/10 hover:bg-red-100 dark:hover:bg-red-500/20 text-red-600 dark:text-red-400 text-xs font-black uppercase tracking-widest rounded-lg transition-colors flex items-center" title="Delete Semester Data">
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                )}

                {/* Delete Confirmation Modal */}
                <AnimatePresence>
                    {deletingSem && (
                        <motion.div key="delete-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 shadow-2xl">
                            <motion.div key="delete-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden">
                                <div className="bg-gradient-to-r from-red-600 to-red-800 p-6 flex justify-between items-start">
                                    <div className="text-white">
                                        <h3 className="font-black text-xl">Delete Semester Data?</h3>
                                        <p className="text-xs text-red-100/90 mt-1 font-medium">{deletingSem.year} • {deletingSem.semester_type} sem • {deletingSem.branch}</p>
                                    </div>
                                    <button onClick={() => setDeletingSem(null)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-4 h-4"/></button>
                                </div>
                                <div className="p-6 space-y-4">
                                    <div className="flex items-start bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 p-4 rounded-2xl text-red-700 dark:text-red-400 text-sm font-semibold">
                                        <AlertCircle className="w-6 h-6 mr-3 shrink-0 text-red-500" />
                                        <div>
                                            <p className="font-black mb-1">CRITICAL WARNING:</p>
                                            <p className="leading-relaxed">This action is permanent and cannot be undone. It will completely delete all registered students, proposals, validated teams, panels, schedules, marks, and evaluation logs associated with this semester.</p>
                                        </div>
                                    </div>
                                    {deletingSem.is_active && (
                                        <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 p-4 rounded-2xl text-amber-700 dark:text-amber-400 text-xs font-bold leading-relaxed">
                                            ⚠️ This semester is currently marked as ACTIVE. Deleting it will result in no active academic registry.
                                        </div>
                                    )}
                                </div>
                                <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3">
                                    <button onClick={() => setDeletingSem(null)} disabled={isDeleting} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button onClick={handleDeleteSemester} disabled={isDeleting} className="px-5 py-2.5 text-sm font-bold text-white bg-red-600 border border-red-500/50 hover:bg-red-700 rounded-xl transition-all shadow-lg shadow-red-500/30 active:scale-95 flex items-center">
                                        {isDeleting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Trash2 className="w-4 h-4 mr-2" />} Delete All Data
                                    </button>
                                </div>
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        );
    }

    return (
        <div className="space-y-8 relative z-10 w-full min-h-[calc(100vh-8rem)]">
            
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} 
                className="bg-gradient-to-r from-violet-600 via-violet-700 to-indigo-800 rounded-3xl p-8 text-white shadow-xl shadow-violet-500/20 relative overflow-hidden flex flex-col md:flex-row items-center justify-between border border-violet-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                        <path d="M0,300 C300,0 700,300 1000,0 L1000,300 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 w-full lg:w-2/3">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20 shadow-sm transition-colors">
                        <Settings2 className="w-4 h-4 mr-2" /> Semester {viewMode === 'edit' ? 'Modification' : 'Creation'}
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">
                        {viewMode === 'edit' ? 'Update Configuration' : 'New Configuration'}
                    </h1>
                    <p className="text-violet-100/90 leading-relaxed text-sm md:text-base max-w-lg font-medium">Define systemic rules, parameters, team size limitations, and evaluate core structural weights for the academic timeline.</p>
                </div>
            </motion.div>

            {/* Top Toolbar */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="flex justify-between items-center w-full">
                <button onClick={() => setViewMode('list')} className="flex items-center px-5 py-2.5 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-xl text-sm font-bold transition-all shadow-sm">
                    <ChevronLeft className="w-4 h-4 mr-2" /> Back
                </button>
                <button onClick={handleSave} disabled={isSubmitting} className="flex items-center justify-center px-8 py-3 bg-violet-600 border border-violet-500/50 hover:bg-violet-700 disabled:opacity-70 text-white font-black uppercase tracking-widest text-sm rounded-xl transition-all shadow-lg shadow-violet-500/30 active:scale-95 disabled:active:scale-100">
                    {isSubmitting ? <Loader2 className="w-5 h-5 mr-3 animate-spin"/> : <Save className="w-5 h-5 mr-3" />} 
                    {viewMode === 'edit' ? 'Save Changes' : 'Create Config'}
                </button>
            </motion.div>

            <AnimatePresence>
                {error && (
                    <motion.div initial={{ opacity: 0, height: 0, y: -20 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -20 }} className="overflow-hidden">
                        <div className="bg-red-50 text-red-700 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 dark:text-red-400 p-5 rounded-2xl flex items-center font-bold shadow-md shadow-red-500/5 mb-2">
                            <AlertCircle className="w-6 h-6 mr-4 shrink-0" /> {error}
                        </div>
                    </motion.div>
                )}
                {success && (
                    <motion.div initial={{ opacity: 0, height: 0, y: -20 }} animate={{ opacity: 1, height: 'auto', y: 0 }} exit={{ opacity: 0, height: 0, y: -20 }} className="overflow-hidden">
                        <div className="bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 dark:text-emerald-400 p-5 rounded-2xl flex items-center font-bold shadow-md shadow-emerald-500/5 mb-2">
                            <CheckCircle className="w-6 h-6 mr-4 shrink-0" /> {success}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="grid grid-cols-1 md:grid-cols-2 gap-8 relative">
                
                {/* General Settings */}
                <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 space-y-8 transition-all duration-500">
                    <div className="flex items-center space-x-4 border-b border-slate-100 dark:border-slate-700/50 pb-6 relative">
                        <div className="w-12 h-12 bg-indigo-50 dark:bg-indigo-500/10 rounded-2xl flex items-center justify-center text-indigo-500 border border-indigo-100 dark:border-indigo-500/20 shadow-sm"><Calendar className="w-6 h-6"/></div>
                        <h2 className="text-xl font-black text-slate-800 dark:text-white tracking-tight">Academic Bounds</h2>
                    </div>
                    
                    <div className="space-y-6">
                        <div className="grid grid-cols-2 gap-6">
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Timeline Year</label>
                                <input type="text" value={config.year} onChange={e => setConfig({...config, year: e.target.value})}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow" placeholder="e.g. 2026-2027" />
                            </div>
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Type</label>
                                <select value={['odd', 'even'].includes(config.semester_type) ? config.semester_type : 'custom'} onChange={e => {
                                    const val = e.target.value;
                                    setConfig({...config, semester_type: val === 'custom' ? '' : val});
                                }}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow">
                                    <option value="odd">Odd Semester</option>
                                    <option value="even">Even Semester</option>
                                    <option value="custom">Custom...</option>
                                </select>
                                {!['odd', 'even'].includes(config.semester_type) && (
                                    <div className="mt-3">
                                        <input type="text" value={config.semester_type} onChange={e => setConfig({...config, semester_type: e.target.value})}
                                            className="w-full px-5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-violet-300 dark:border-violet-500 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow" placeholder="Enter custom semester type" />
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-6">
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Academic Level</label>
                                <select value={[1, 2, 3, 4].includes(config.academic_level) ? config.academic_level : 'custom'} onChange={e => {
                                    const val = e.target.value;
                                    setConfig({...config, academic_level: val === 'custom' ? '' : parseInt(val)});
                                }}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center">
                                    <option value="1">Year 1</option>
                                    <option value="2">Year 2</option>
                                    <option value="3">Year 3</option>
                                    <option value="4">Year 4</option>
                                    <option value="custom">Custom...</option>
                                </select>
                                {![1, 2, 3, 4].includes(config.academic_level) && (
                                    <div className="mt-3">
                                        <input type="number" min="1" max="10" value={config.academic_level} onChange={e => setConfig({...config, academic_level: e.target.value === '' ? '' : parseInt(e.target.value)})}
                                            className="w-full px-5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-violet-300 dark:border-violet-500 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center" placeholder="Enter custom level (integer)" />
                                    </div>
                                )}
                            </div>
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Branch</label>
                                <select value={['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(config.branch) ? config.branch : 'custom'} onChange={e => {
                                    const val = e.target.value;
                                    setConfig({...config, branch: val === 'custom' ? '' : val});
                                }}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center cursor-pointer">
                                    <option value="BTech CSE">BTech CSE</option>
                                    <option value="Btech CS-AIML">Btech CS-AIML</option>
                                    <option value="BTech CS(AIML+IOT)">BTech CS(AIML+IOT)</option>
                                    <option value="custom">✏️ Custom (Write manually)...</option>
                                </select>
                                {!['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(config.branch) && (
                                    <div className="mt-3">
                                        <input type="text" value={config.branch} onChange={e => setConfig({...config, branch: e.target.value})}
                                            className="w-full px-5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-violet-300 dark:border-violet-500 rounded-xl text-sm font-bold shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center" placeholder="Write custom branch name" />
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-6">
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Min Students</label>
                                <input type="number" min="1" max="10" value={config.team_size_min} onChange={e => setConfig({...config, team_size_min: parseInt(e.target.value)})}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xl font-black shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center" />
                            </div>
                            <div>
                                <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Max Students</label>
                                <input type="number" min="1" max="10" value={config.team_size_max} onChange={e => setConfig({...config, team_size_max: parseInt(e.target.value)})}
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xl font-black shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center" />
                            </div>
                        </div>

                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-3">Presentation Cycles</label>
                            <input type="number" min="1" max="5" value={config.number_of_presentations} onChange={e => setConfig({...config, number_of_presentations: parseInt(e.target.value)})}
                                className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xl font-black shadow-inner focus:ring-2 focus:ring-violet-500 dark:text-white outline-none transition-shadow text-center" />
                        </div>
                    </div>
                </div>

                {/* Evaluation Weights */}
                {/* Dynamic Presentation Cycles Editor */}
                <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 space-y-8 transition-all duration-500 flex flex-col">
                    <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-700/50 pb-6">
                        <div className="flex items-center space-x-4">
                            <div className="w-12 h-12 bg-amber-50 dark:bg-amber-500/10 rounded-2xl flex items-center justify-center text-amber-500 border border-amber-100 dark:border-amber-500/20 shadow-sm"><Settings2 className="w-6 h-6"/></div>
                            <div>
                                <h2 className="text-xl font-black text-slate-800 dark:text-white tracking-tight">Presentation Cycles</h2>
                                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium mt-0.5">Setup evaluation phases (e.g. Proposal, Mid, Final). Total weight must be 100%.</p>
                            </div>
                        </div>
                        <span className={`text-sm font-black px-4 py-2 rounded-xl border shadow-inner ${
                            presentationCycles.reduce((s, c) => s + parseInt(c.weightage || 0), 0) === 100 
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30' 
                                : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/30 animate-pulse'
                        }`}>
                            Total: {presentationCycles.reduce((s, c) => s + parseInt(c.weightage || 0), 0)}%
                        </span>
                    </div>

                    <div className="flex-1 space-y-4 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                        {presentationCycles.map((cycle, idx) => (
                            <div key={cycle.id || idx} className="p-4 bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700/50 rounded-2xl space-y-4 relative group">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-1">Cycle Title</label>
                                        <input
                                            type="text"
                                            required
                                            value={cycle.title}
                                            onChange={(e) => {
                                                const list = [...presentationCycles];
                                                list[idx].title = e.target.value;
                                                setPresentationCycles(list);
                                            }}
                                            placeholder="e.g. Mid-Term Review"
                                            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-1">Type</label>
                                        <select
                                            value={cycle.type}
                                            onChange={(e) => {
                                                const list = [...presentationCycles];
                                                list[idx].type = e.target.value;
                                                setPresentationCycles(list);
                                            }}
                                            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-500 cursor-pointer"
                                        >
                                            <option value="proposal">Proposal</option>
                                            <option value="mid">Mid-Term</option>
                                            <option value="final">Final/End-Term</option>
                                            <option value="other">Other</option>
                                        </select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 items-center">
                                    <div className="col-span-2">
                                        <label className="block text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-1">Deadline Date & Time</label>
                                        <input
                                            type="datetime-local"
                                            required
                                            value={cycle.deadline ? (cycle.deadline.includes('T') ? cycle.deadline.slice(0, 16) : cycle.deadline) : ''}
                                            onChange={(e) => {
                                                const list = [...presentationCycles];
                                                list[idx].deadline = e.target.value;
                                                setPresentationCycles(list);
                                            }}
                                            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-violet-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-1 text-center">Weight (%)</label>
                                        <input
                                            type="number"
                                            min="0"
                                            max="100"
                                            required
                                            value={cycle.weightage}
                                            onChange={(e) => {
                                                const list = [...presentationCycles];
                                                list[idx].weightage = parseInt(e.target.value) || 0;
                                                setPresentationCycles(list);
                                            }}
                                            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs font-black text-center text-violet-600 dark:text-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-[10px] uppercase tracking-widest font-bold text-slate-400 mb-1 text-center">Status</label>
                                        <select
                                            value={cycle.status || 'draft'}
                                            onChange={(e) => {
                                                const list = [...presentationCycles];
                                                list[idx].status = e.target.value;
                                                setPresentationCycles(list);
                                            }}
                                            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl px-3 py-2 text-xs font-bold text-center text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-violet-500"
                                        >
                                            <option value="draft">Draft</option>
                                            <option value="active">Active</option>
                                        </select>
                                    </div>
                                </div>

                                <div className="border-t border-slate-100 dark:border-slate-800/80 pt-4 mt-2">
                                    <div className="flex justify-between items-center mb-2">
                                        <div className="flex items-center gap-2">
                                            <label className="block text-[10px] uppercase tracking-widest font-black text-slate-500 dark:text-slate-400">Evaluation Rubric (Criteria)</label>
                                            <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30 rounded-md text-[10px] font-black">
                                                Total: {(cycle.evaluation_parameters || []).reduce((sum, p) => sum + (parseInt(p.max_marks) || 0), 0)} Marks
                                            </span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => {
                                                const list = [...presentationCycles];
                                                if (!list[idx].evaluation_parameters) list[idx].evaluation_parameters = [];
                                                list[idx].evaluation_parameters.push({ id: `rubric-${Date.now()}-${Math.floor(Math.random()*1000)}`, criterion: '', max_marks: 10, weight: 1 });
                                                setPresentationCycles(list);
                                            }}
                                            className="inline-flex items-center text-xs font-bold text-violet-600 dark:text-violet-400 hover:underline"
                                        >
                                            <Plus className="w-3 h-3 mr-1" /> Add Criterion
                                        </button>
                                    </div>
                                    <div className="space-y-2">
                                        {(cycle.evaluation_parameters || []).map((param, pIdx) => (
                                            <div key={param.id || pIdx} className="grid grid-cols-[1fr_auto_auto] gap-2 items-center bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-2 rounded-xl">
                                                <input
                                                    type="text"
                                                    required
                                                    value={param.criterion}
                                                    onChange={(e) => {
                                                        const list = [...presentationCycles];
                                                        list[idx].evaluation_parameters[pIdx].criterion = e.target.value;
                                                        setPresentationCycles(list);
                                                    }}
                                                    placeholder="Criterion Name (e.g. Scope)"
                                                    className="w-full bg-transparent text-xs font-bold text-slate-800 dark:text-slate-200 focus:outline-none"
                                                />
                                                <div className="flex items-center gap-1">
                                                    <span className="text-[10px] text-slate-400 font-bold uppercase mr-1">Max Marks</span>
                                                    <input
                                                        type="number"
                                                        min="1"
                                                        required
                                                        value={param.max_marks}
                                                        onChange={(e) => {
                                                            const list = [...presentationCycles];
                                                            list[idx].evaluation_parameters[pIdx].max_marks = parseInt(e.target.value) || 0;
                                                            setPresentationCycles(list);
                                                        }}
                                                        className="w-12 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg py-1 px-1.5 text-xs font-black text-center text-indigo-600 dark:text-indigo-400 focus:outline-none"
                                                    />
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        const list = [...presentationCycles];
                                                        list[idx].evaluation_parameters = list[idx].evaluation_parameters.filter((_, i) => i !== pIdx);
                                                        setPresentationCycles(list);
                                                    }}
                                                    className="p-1 text-slate-300 hover:text-red-500 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700/50"
                                                >
                                                    <X className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        ))}
                                        {(!cycle.evaluation_parameters || cycle.evaluation_parameters.length === 0) && (
                                            <div className="text-[10px] text-amber-500 font-bold italic">No rubric criteria added for this cycle.</div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800/80">
                                    <div className="flex items-center gap-4">
                                        <label className="flex items-center gap-2.5 cursor-pointer select-none">
                                            <button
                                                type="button"
                                                role="switch"
                                                aria-checked={Boolean(cycle.enable_mentor_eval)}
                                                onClick={() => {
                                                    const list = [...presentationCycles];
                                                    list[idx].enable_mentor_eval = !list[idx].enable_mentor_eval;
                                                    setPresentationCycles(list);
                                                }}
                                                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-1 ${
                                                    cycle.enable_mentor_eval ? 'bg-violet-600' : 'bg-slate-300 dark:bg-slate-600'
                                                }`}
                                            >
                                                <span
                                                    className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                                                        cycle.enable_mentor_eval ? 'translate-x-[18px]' : 'translate-x-1'
                                                    }`}
                                                />
                                            </button>
                                            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Enable Mentor Evaluation (Mentor Marks)</span>
                                        </label>
                                        {Boolean(cycle.enable_mentor_eval) && (
                                            <div className="flex items-center gap-1">
                                                <span className="text-[10px] text-slate-400 font-bold uppercase mr-1">Mentor Max Marks</span>
                                                <input
                                                    type="number"
                                                    min="1"
                                                    required
                                                    value={cycle.mentor_max_marks || ''}
                                                    onChange={(e) => {
                                                        const list = [...presentationCycles];
                                                        list[idx].mentor_max_marks = parseInt(e.target.value) || 0;
                                                        setPresentationCycles(list);
                                                    }}
                                                    className="w-14 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg py-1 px-1.5 text-xs font-black text-center text-violet-600 dark:text-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-500"
                                                />
                                            </div>
                                        )}
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const list = presentationCycles.filter((_, i) => i !== idx);
                                            setPresentationCycles(list);
                                        }}
                                        className="p-1.5 text-slate-400 hover:text-red-500 dark:text-slate-500 dark:hover:text-red-400 transition-all rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center gap-1 text-xs font-semibold"
                                    >
                                        <Trash2 className="w-4 h-4" /> Remove Cycle
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    <button
                        type="button"
                        onClick={() => {
                            setPresentationCycles([
                                ...presentationCycles,
                                { id: `cycle-${Date.now()}`, title: '', type: 'mid', weightage: 0, deadline: '', status: 'draft', requires_synopsis: false, evaluation_parameters: [] }
                            ]);
                        }}
                        className="w-full flex items-center justify-center gap-2 px-5 py-3.5 bg-violet-50 dark:bg-violet-500/10 hover:bg-violet-100 dark:hover:bg-violet-500/20 text-violet-600 dark:text-violet-400 text-xs font-black uppercase tracking-wider rounded-2xl transition-colors border border-dashed border-violet-300 dark:border-violet-500/40"
                    >
                        <Plus className="w-4 h-4" /> Add Presentation Cycle
                    </button>
                </div>
            </motion.div>
        </div>
    );
}
