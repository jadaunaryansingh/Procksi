import React, { useState, useEffect } from 'react';
import { 
    AlertCircle, CheckCircle, Calendar, Plus, Loader2, Save, 
    Trash2, ExternalLink, AlertTriangle, Award, 
    FileText, Check, Search, RefreshCw, Settings, Target, Eye, X, Edit2
} from 'lucide-react';
import { motion } from 'framer-motion';
import { apiFetchTable, apiUpsertTable, apiDeleteRows } from '../lib/api';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { useGlobalFilters } from '../context/useGlobalFilters';

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

export default function PresentationCycles() {
    const { filters, semesters, semesterOptions } = useGlobalFilters();
    const [activeSemesterId, setActiveSemesterId] = useState(null);
    const [loading, setLoading] = useState(true);
    
    // Core state
    const [cycles, setCycles] = useState([]);
    const [showForm, setShowForm] = useState(false);
    const [editingCycle, setEditingCycle] = useState(null);
    
    // Form state
    const [newCycle, setNewCycle] = useState({
        title: '',
        type: 'mid',
        deadline: '',
        weightage: 30,
        requires_synopsis: false,
        enable_mentor_eval: false,
        mentor_max_marks: 0,
        status: 'draft',
        evaluation_parameters: []
    });

    const formState = editingCycle || newCycle;

    const setFormState = (updatedFields) => {
        if (editingCycle) {
            setEditingCycle(prev => ({ ...prev, ...updatedFields }));
        } else {
            setNewCycle(prev => ({ ...prev, ...updatedFields }));
        }
    };
    
    const loadData = async (targetSemId = null) => {
        setLoading(true);
        try {
            let semId = targetSemId || activeSemesterId;
            if (!semId || semId === 'NONE') {
                if (filters?.semesterId && filters.semesterId !== 'all') {
                    semId = filters.semesterId;
                } else {
                    const activeSems = semesters.filter(s => s.is_active);
                    semId = activeSems.length > 0 ? activeSems[0].id : (semesters.length > 0 ? semesters[0].id : 'NONE');
                }
            }
            setActiveSemesterId(semId);
            
            if (semId !== 'NONE') {
                const [cyclesData, rubricsData] = await Promise.all([
                    apiFetchTable('presentation_cycles'),
                    apiFetchTable('presentation_rubrics').catch(() => [])
                ]);
                
                const filteredCycles = (cyclesData || []).filter(c => c.semester_id === semId);

                // Group rubrics by cycle_id
                const enriched = filteredCycles.map(c => {
                    const cycleRubrics = (rubricsData || []).filter(r => r.cycle_id === c.id);
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

                setCycles(enriched.sort((a, b) => new Date(a.created_at) - new Date(b.created_at)));
            } else {
                setCycles([]);
            }
        } catch (err) {
            console.error("Failed to load cycles:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (filters?.semesterId && filters.semesterId !== 'all') {
            setActiveSemesterId(filters.semesterId);
            loadData(filters.semesterId);
        } else {
            loadData(activeSemesterId || null);
        }
    }, [filters?.semesterId, semesters]);

    const handleCreateCycle = async (e) => {
        e.preventDefault();
        if (!newCycle.title.trim() || !newCycle.deadline) {
            alert("Please fill in required fields.");
            return;
        }

        try {
            const rowToInsert = {
                semester_id: activeSemesterId,
                title: newCycle.title.trim(),
                type: newCycle.type,
                deadline: new Date(newCycle.deadline).toISOString(),
                weightage: parseInt(newCycle.weightage, 10),
                requires_synopsis: newCycle.requires_synopsis,
                enable_mentor_eval: Boolean(newCycle.enable_mentor_eval),
                mentor_max_marks: parseInt(newCycle.mentor_max_marks || 0),
                status: newCycle.status
            };

            const response = await apiUpsertTable('presentation_cycles', [rowToInsert]);
            const createdCycle = response.data && response.data[0];

            if (createdCycle && newCycle.evaluation_parameters?.length > 0) {
                const rubricsToInsert = newCycle.evaluation_parameters.map(p => ({
                    id: uuidv4(),
                    cycle_id: createdCycle.id,
                    criterion: p.criterion.trim(),
                    max_marks: parseInt(p.max_marks || 0),
                    weight: 1
                }));
                await apiUpsertTable('presentation_rubrics', rubricsToInsert, 'id');
            }

            AuditLogger.logAdminAction(getCurrentUser(), `Created presentation cycle "${newCycle.title}"`);
            alert(`Cycle "${newCycle.title}" successfully created!`);
            
            // Reset form and reload
            setNewCycle({ title: '', type: 'mid', deadline: '', weightage: 30, requires_synopsis: false, enable_mentor_eval: false, mentor_max_marks: 0, status: 'draft', evaluation_parameters: [] });
            setShowForm(false);
            loadData();
        } catch (err) {
            alert("Failed to create cycle: " + err.message);
        }
    };

    const handleUpdateCycle = async (e) => {
        e.preventDefault();
        if (!editingCycle.title.trim() || !editingCycle.deadline) {
            alert("Please fill in required fields.");
            return;
        }

        try {
            const rowToUpdate = {
                id: editingCycle.id,
                semester_id: activeSemesterId,
                title: editingCycle.title.trim(),
                type: editingCycle.type,
                deadline: new Date(editingCycle.deadline).toISOString(),
                weightage: parseInt(editingCycle.weightage, 10),
                requires_synopsis: editingCycle.requires_synopsis,
                enable_mentor_eval: Boolean(editingCycle.enable_mentor_eval),
                mentor_max_marks: parseInt(editingCycle.mentor_max_marks || 0),
                status: editingCycle.status
            };

            await apiUpsertTable('presentation_cycles', [rowToUpdate], 'id');

            // Save rubrics
            const rubricsToUpsert = (editingCycle.evaluation_parameters || []).map(p => ({
                id: p.id && !p.id.startsWith('rubric-') ? p.id : uuidv4(),
                cycle_id: editingCycle.id,
                criterion: p.criterion.trim(),
                max_marks: parseInt(p.max_marks || 0),
                weight: 1
            }));

            if (rubricsToUpsert.length > 0) {
                await apiUpsertTable('presentation_rubrics', rubricsToUpsert, 'id');
            }

            // Cleanup deleted rubrics
            const originalRubricIds = cycles.find(c => c.id === editingCycle.id)?.evaluation_parameters?.map(p => p.id) || [];
            const currentRubricIds = rubricsToUpsert.map(r => r.id);
            const deletedRubricIds = originalRubricIds.filter(id => !currentRubricIds.includes(id));
            const rubricsToDelete = deletedRubricIds.filter(id => id && !String(id).startsWith('rubric-'));
            if (rubricsToDelete.length > 0) {
                await Promise.all(rubricsToDelete.map(async id => {
                    await apiDeleteRows('presentation_evaluation_scores', { rubric_id: id }).catch(e => console.warn('Ignore cascade delete fail:', e));
                    await apiDeleteRows('presentation_rubrics', { id });
                }));
            }

            AuditLogger.logAdminAction(getCurrentUser(), `Updated presentation cycle "${editingCycle.title}"`);
            alert(`Cycle "${editingCycle.title}" successfully updated!`);
            
            // Reset form and reload
            setEditingCycle(null);
            setShowForm(false);
            loadData();
        } catch (err) {
            alert("Failed to update cycle: " + err.message);
        }
    };

    const handleUpdateStatus = async (cycle, newStatus) => {
        if (!window.confirm(`Change status of "${cycle.title}" to ${newStatus.toUpperCase()}?`)) return;
        
        try {
            await apiUpsertTable('presentation_cycles', [{ ...cycle, status: newStatus }], 'id');
            AuditLogger.logAdminAction(getCurrentUser(), `Changed status of cycle "${cycle.title}" to ${newStatus}`);
            loadData();
        } catch (err) {
            alert("Failed to update status: " + err.message);
        }
    };

    const handleDelete = async (cycle) => {
        if (!window.confirm(`Are you sure you want to delete cycle "${cycle.title}"?`)) return;
        
        try {
            if (cycle.id && !String(cycle.id).startsWith('cycle-')) {
                await apiDeleteRows('presentation_evaluations', { cycle_id: cycle.id }).catch(e => console.warn('Ignore cascade:', e));
                if (cycle.evaluation_parameters) {
                    await Promise.all(cycle.evaluation_parameters.map(async r => {
                        if (r.id && !String(r.id).startsWith('rubric-')) {
                            await apiDeleteRows('presentation_evaluation_scores', { rubric_id: r.id }).catch(e => console.warn('Ignore cascade:', e));
                            await apiDeleteRows('presentation_rubrics', { id: r.id }).catch(e => console.warn('Ignore cascade:', e));
                        }
                    }));
                }
                await apiDeleteRows('presentation_cycles', { id: cycle.id });
            }
            AuditLogger.logAdminAction(getCurrentUser(), `Deleted cycle "${cycle.title}"`);
            loadData();
        } catch (err) {
            alert("Failed to delete cycle: " + err.message);
        }
    };

    const handleAddCriterion = () => {
        const currentParams = formState.evaluation_parameters || [];
        setFormState({
            evaluation_parameters: [
                ...currentParams,
                { id: `rubric-${Date.now()}-${Math.floor(Math.random() * 1000)}`, criterion: '', max_marks: 10 }
            ]
        });
    };

    const handleCriterionChange = (pIdx, field, value) => {
        const params = [...(formState.evaluation_parameters || [])];
        params[pIdx] = { ...params[pIdx], [field]: value };
        setFormState({ evaluation_parameters: params });
    };

    const handleRemoveCriterion = (pIdx) => {
        const params = (formState.evaluation_parameters || []).filter((_, i) => i !== pIdx);
        setFormState({ evaluation_parameters: params });
    };

    if (loading) {
        return (
            <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            </div>
        );
    }

    return (
        <div className="space-y-8 relative z-10 min-h-[calc(100vh-8rem)]">
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} 
                className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50">
                <div>
                    <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Presentation Cycles</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Manage dynamic evaluation cycles (Proposal, Mid, Final) instead of hardcoded evaluations.</p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    {semesters && semesters.length > 0 && (
                        <div className="flex items-center gap-2 bg-white dark:bg-slate-800 px-4 py-2.5 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm">
                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Term:</span>
                            <select
                                value={activeSemesterId || ''}
                                onChange={(e) => {
                                    const selectedId = e.target.value;
                                    setActiveSemesterId(selectedId);
                                    loadData(selectedId);
                                }}
                                className="bg-transparent text-xs font-bold text-slate-700 dark:text-white border-0 p-0 focus:ring-0 outline-none cursor-pointer"
                            >
                                <option value="NONE">-- Select Semester --</option>
                                {semesterOptions.map(opt => (
                                    <option key={opt.id} value={opt.id}>
                                        {opt.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}
                    <button onClick={() => loadData(activeSemesterId)} className="flex items-center justify-center px-4 py-2.5 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm">
                        <RefreshCw className="w-4 h-4 mr-2" /> Sync Records
                    </button>
                    <button 
                        disabled={activeSemesterId === 'NONE'}
                        onClick={() => { setEditingCycle(null); setShowForm(!showForm); }} 
                        className="flex items-center justify-center px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-400 text-white rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-lg shadow-indigo-500/20 active:scale-95 disabled:opacity-50"
                    >
                        <Plus className="w-4 h-4 mr-2" /> New Cycle
                    </button>
                </div>
            </motion.div>

            {activeSemesterId === 'NONE' && (
                <div className="py-12 text-center bg-slate-50 dark:bg-slate-800/50 rounded-3xl border border-dashed border-slate-200 dark:border-slate-700">
                    <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3"/>
                    <h3 className="text-lg font-bold text-slate-500">No Semester Selected</h3>
                    <p className="text-sm text-slate-400">Select a semester from the dropdown to view or configure its presentation cycles.</p>
                </div>
            )}

            {showForm && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700 p-6">
                    <h2 className="text-lg font-black text-slate-800 dark:text-white mb-4">
                        {editingCycle ? `Edit Presentation Cycle: ${editingCycle.title}` : 'Create New Presentation Cycle'}
                    </h2>
                    <form onSubmit={editingCycle ? handleUpdateCycle : handleCreateCycle} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        <div>
                            <label className="block text-xs uppercase font-bold text-slate-500 mb-2">Title</label>
                            <input required type="text" value={formState.title} onChange={e => setFormState({ title: e.target.value })} className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white" placeholder="e.g. Mid-Term Review 2026" />
                        </div>
                        <div>
                            <label className="block text-xs uppercase font-bold text-slate-500 mb-2">Type</label>
                            <select value={formState.type} onChange={e => setFormState({ type: e.target.value })} className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white">
                                <option value="proposal">Proposal</option>
                                <option value="mid">Mid-Term</option>
                                <option value="final">Final/End-Term</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs uppercase font-bold text-slate-500 mb-2">Deadline</label>
                            <input required type="datetime-local" value={formState.deadline ? formState.deadline.slice(0, 16) : ''} onChange={e => setFormState({ deadline: e.target.value })} className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white" />
                        </div>
                        <div>
                            <label className="block text-xs uppercase font-bold text-slate-500 mb-2">Weightage (%)</label>
                            <input type="number" value={formState.weightage} onChange={e => setFormState({ weightage: parseInt(e.target.value, 10) || 0 })} className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white" />
                        </div>
                        <div>
                            <label className="block text-xs uppercase font-bold text-slate-500 mb-2">Initial Status</label>
                            <select value={formState.status} onChange={e => setFormState({ status: e.target.value })} className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white">
                                <option value="draft">Draft (Hidden from students)</option>
                                <option value="active">Active (Open for submissions)</option>
                                <option value="closed">Closed</option>
                                <option value="frozen">Frozen</option>
                            </select>
                        </div>
                        <div className="flex items-center gap-4 mt-6">
                            <label className="flex items-center gap-2.5 cursor-pointer select-none">
                                <button
                                    type="button"
                                    role="switch"
                                    aria-checked={Boolean(formState.enable_mentor_eval)}
                                    onClick={() => setFormState({ enable_mentor_eval: !formState.enable_mentor_eval })}
                                    className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 ${
                                        formState.enable_mentor_eval ? 'bg-indigo-600' : 'bg-slate-300 dark:bg-slate-600'
                                    }`}
                                >
                                    <span
                                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                                            formState.enable_mentor_eval ? 'translate-x-[18px]' : 'translate-x-1'
                                        }`}
                                    />
                                </button>
                                <span className="text-sm font-bold text-slate-700 dark:text-slate-300">Enable Mentor Evaluation (Mentor Marks)</span>
                            </label>
                            {Boolean(formState.enable_mentor_eval) && (
                                <div className="flex items-center gap-2">
                                    <span className="text-xs uppercase font-bold text-slate-500">Mentor Max Marks</span>
                                    <input
                                        type="number"
                                        min="1"
                                        required
                                        value={formState.mentor_max_marks || ''}
                                        onChange={e => setFormState({ mentor_max_marks: parseInt(e.target.value, 10) || 0 })}
                                        className="w-20 px-3 py-1.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-center text-indigo-600 dark:text-indigo-400"
                                    />
                                </div>
                            )}
                        </div>

                        {/* Rubrics Criteria Editor */}
                        <div className="border-t border-slate-100 dark:border-slate-700/50 pt-4 md:col-span-2 lg:col-span-3">
                            <div className="flex justify-between items-center mb-2">
                                <div className="flex items-center gap-2">
                                    <label className="block text-xs uppercase font-bold text-slate-500">Evaluation Rubric (Criteria)</label>
                                    <span className="px-2.5 py-0.5 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30 rounded-full text-[11px] font-black">
                                        Total: {(formState.evaluation_parameters || []).reduce((sum, p) => sum + (parseInt(p.max_marks) || 0), 0)} Marks
                                    </span>
                                </div>
                                <button
                                    type="button"
                                    onClick={handleAddCriterion}
                                    className="inline-flex items-center text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:underline"
                                >
                                    <Plus className="w-3 h-3 mr-1" /> Add Criterion
                                </button>
                            </div>
                            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                                {(formState.evaluation_parameters || []).map((param, pIdx) => (
                                    <div key={param.id || pIdx} className="grid grid-cols-[1fr_auto_auto] gap-4 items-center bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-2 rounded-xl">
                                        <input
                                            type="text"
                                            required
                                            value={param.criterion}
                                            onChange={(e) => handleCriterionChange(pIdx, 'criterion', e.target.value)}
                                            placeholder="Criterion Name (e.g. Code Quality)"
                                            className="w-full bg-transparent text-xs font-bold text-slate-800 dark:text-slate-200 focus:outline-none"
                                        />
                                        <div className="flex items-center gap-1">
                                            <span className="text-[10px] text-slate-400 font-bold uppercase mr-1">Max Marks</span>
                                            <input
                                                type="number"
                                                min="1"
                                                required
                                                value={param.max_marks}
                                                onChange={(e) => handleCriterionChange(pIdx, 'max_marks', parseInt(e.target.value) || 0)}
                                                className="w-12 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg py-1 px-1.5 text-xs font-black text-center text-indigo-600 dark:text-indigo-400 focus:outline-none"
                                            />
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveCriterion(pIdx)}
                                            className="p-1 text-slate-400 hover:text-red-500 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                                        >
                                            <X className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                ))}
                                {(!formState.evaluation_parameters || formState.evaluation_parameters.length === 0) && (
                                    <div className="text-xs text-amber-500 font-bold italic">No rubric criteria added. Panel evaluations will fall back to default criteria.</div>
                                )}
                            </div>
                        </div>

                        <div className="md:col-span-2 lg:col-span-3 flex justify-end gap-3 mt-2">
                            <button type="button" onClick={() => { setShowForm(false); setEditingCycle(null); }} className="px-6 py-2.5 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-xl font-bold text-sm">Cancel</button>
                            <button type="submit" className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-bold text-sm flex items-center"><Save className="w-4 h-4 mr-2"/> Save Cycle</button>
                        </div>
                    </form>
                </motion.div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {cycles.length === 0 && !showForm && (
                    <div className="col-span-full py-12 text-center bg-slate-50 dark:bg-slate-800/50 rounded-3xl border border-dashed border-slate-200 dark:border-slate-700">
                        <Target className="w-12 h-12 text-slate-300 mx-auto mb-3"/>
                        <h3 className="text-lg font-bold text-slate-500">No Cycles Found</h3>
                        <p className="text-sm text-slate-400">Click "New Cycle" to setup presentation tracking.</p>
                    </div>
                )}
                
                {cycles.map(cycle => (
                    <motion.div key={cycle.id} initial={{opacity:0, scale:0.95}} animate={{opacity:1, scale:1}} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700 p-6 flex flex-col shadow-sm">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <div className="flex gap-2 items-center mb-1">
                                    <span className={`px-2 py-0.5 text-[10px] font-black uppercase rounded-md ${
                                        cycle.status === 'draft' ? 'bg-slate-100 text-slate-600' :
                                        cycle.status === 'active' ? 'bg-emerald-100 text-emerald-600' :
                                        cycle.status === 'closed' ? 'bg-amber-100 text-amber-600' :
                                        'bg-blue-100 text-blue-600'
                                    }`}>
                                        {cycle.status}
                                    </span>
                                    <span className="px-2 py-0.5 bg-indigo-50 text-indigo-600 text-[10px] font-black uppercase rounded-md">{cycle.type}</span>
                                </div>
                                <h3 className="font-black text-slate-800 dark:text-white text-lg">{cycle.title}</h3>
                            </div>
                        </div>
                        
                        <div className="space-y-3 mb-6 flex-1">
                            <div className="flex items-center text-sm text-slate-600 dark:text-slate-400 font-medium">
                                <Calendar className="w-4 h-4 mr-2 text-slate-400"/>
                                Deadline: {new Date(cycle.deadline).toLocaleString()}
                            </div>
                            <div className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400 font-medium">
                                <div className="flex items-center">
                                    <Target className="w-4 h-4 mr-2 text-slate-400"/>
                                    Weightage: {cycle.weightage}%
                                </div>
                                <span className="font-mono text-xs font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-200 dark:border-indigo-500/30">
                                    Total: {(cycle.evaluation_parameters || []).reduce((sum, p) => sum + (parseInt(p.max_marks) || 0), 0)} Marks
                                </span>
                            </div>
                            {cycle.enable_mentor_eval && (
                                <div className="flex items-center text-xs text-purple-600 dark:text-purple-400 font-bold bg-purple-50 dark:bg-purple-500/10 px-2.5 py-1 rounded-lg border border-purple-200 dark:border-purple-500/30 w-fit">
                                    Mentor Evaluation Enabled ({cycle.mentor_max_marks || 0} Marks)
                                </div>
                            )}

                            {/* Rubrics Criteria Display */}
                            <div className="pt-2 border-t border-slate-100 dark:border-slate-700/50 mt-2">
                                <span className="block text-[10px] uppercase tracking-widest font-black text-slate-400 mb-1">Rubric Criteria ({cycle.evaluation_parameters?.length || 0})</span>
                                <div className="space-y-1">
                                    {(cycle.evaluation_parameters || []).map((p, idx) => (
                                        <div key={p.id || idx} className="flex justify-between items-center text-xs bg-slate-50 dark:bg-slate-900/50 px-2.5 py-1.5 rounded-lg border border-slate-100 dark:border-slate-700/50">
                                            <span className="font-semibold text-slate-700 dark:text-slate-300 truncate max-w-[170px]" title={p.criterion}>{p.criterion}</span>
                                            <span className="font-bold text-indigo-600 dark:text-indigo-400 shrink-0">Max: {p.max_marks}</span>
                                        </div>
                                    ))}
                                    {(!cycle.evaluation_parameters || cycle.evaluation_parameters.length === 0) && (
                                        <div className="text-[10px] text-amber-500 font-semibold italic">No rubric criteria. Legacy fallback.</div>
                                    )}
                                </div>
                            </div>
                        </div>
                        
                        <div className="pt-4 border-t border-slate-100 dark:border-slate-700 flex flex-wrap gap-2 justify-between items-center">
                            <div className="flex gap-2">
                                <select 
                                    value={cycle.status}
                                    onChange={(e) => handleUpdateStatus(cycle, e.target.value)}
                                    className="px-3 py-1.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-xs font-bold text-slate-700 dark:text-slate-300"
                                >
                                    <option value="draft">Draft</option>
                                    <option value="active">Active</option>
                                    <option value="closed">Closed</option>
                                    <option value="frozen">Frozen</option>
                                </select>
                            </div>
                            <div className="flex gap-1">
                                <button onClick={() => { setEditingCycle({ ...cycle }); setShowForm(true); }} className="p-2 text-slate-400 hover:text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 rounded-lg transition-colors" title="Edit Cycle">
                                    <Edit2 className="w-4 h-4" />
                                </button>
                                <button onClick={() => handleDelete(cycle)} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors" title="Delete Cycle">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
}
