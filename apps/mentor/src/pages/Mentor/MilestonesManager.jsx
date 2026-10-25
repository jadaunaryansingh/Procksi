import React, { useState, useEffect, useMemo } from 'react';
import { 
    AlertCircle, CheckCircle, Calendar, Plus, Loader2, Save, 
    Trash2, Github, ExternalLink, AlertTriangle, Award, 
    FileText, Check, Search, Users, RefreshCw
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';
import { safeLinkUrl } from '../../lib/safeUrl';

const getTeamNumericId = (teamIdStr) => {
    if (!teamIdStr) return null;
    let match = String(teamIdStr).match(/T(\d+)/);
    if (match && match[1]) {
        return parseInt(match[1], 10);
    }
    match = String(teamIdStr).match(/\d+/g);
    if (match && match.length > 0) {
        return parseInt(match[match.length - 1], 10);
    }
    return null;
};

export default function MilestonesManager() {
    const { filterRows, semesterMap } = useGlobalFilters();
    const [loading, setLoading] = useState(true);
    
    // Core state
    const [teams, setTeams] = useState([]);
    const [milestones, setMilestones] = useState([]);

    const filteredTeams = useMemo(() => {
        return filterRows(teams);
    }, [teams, filterRows]);
    
    // Form state
    const [newMilestone, setNewMilestone] = useState({
        title: '',
        description: '',
        deadline: ''
    });
    const [formFields, setFormFields] = useState([]);
    const [targetTeamsSelection, setTargetTeamsSelection] = useState('all');
    const [selectedTeamIds, setSelectedTeamIds] = useState([]);
    const [viewingSubmission, setViewingSubmission] = useState(null);
    
    // Filters & Grid settings
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedMilestoneFilter, setSelectedMilestoneFilter] = useState('ALL');
    const [submittingForm, setSubmittingForm] = useState(false);
    const [actionLoadingId, setActionLoadingId] = useState(null);

    const addFormField = (type) => {
        const newField = {
            id: `field_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
            type: type,
            label: '',
            required: false,
            options: type === 'mcq' || type === 'checkbox' ? ['Option 1'] : []
        };
        setFormFields(prev => [...prev, newField]);
    };

    const updateFormField = (id, updates) => {
        setFormFields(prev => prev.map(f => f.id === id ? { ...f, ...updates } : f));
    };

    const removeFormField = (id) => {
        setFormFields(prev => prev.filter(f => f.id !== id));
    };

    const addFieldOption = (fieldId) => {
        setFormFields(prev => prev.map(f => {
            if (f.id === fieldId) {
                return { ...f, options: [...f.options, `Option ${f.options.length + 1}`] };
            }
            return f;
        }));
    };

    const updateFieldOption = (fieldId, index, value) => {
        setFormFields(prev => prev.map(f => {
            if (f.id === fieldId) {
                const newOpts = [...f.options];
                newOpts[index] = value;
                return { ...f, options: newOpts };
            }
            return f;
        }));
    };

    const removeFieldOption = (fieldId, index) => {
        setFormFields(prev => prev.map(f => {
            if (f.id === fieldId) {
                return { ...f, options: f.options.filter((_, idx) => idx !== index) };
            }
            return f;
        }));
    };
    
    const loadData = async () => {
        setLoading(true);
        try {
            const [teamsRes, milestonesRes] = await Promise.all([
                api.get('/teams'),
                api.get('/milestones')
            ]);
            const teamsList = Array.isArray(teamsRes.data) ? teamsRes.data : (teamsRes.data?.data || teamsRes.data?.teams || []);
            const milestonesList = Array.isArray(milestonesRes.data) ? milestonesRes.data : (milestonesRes.data?.data || milestonesRes.data?.milestones || []);
            setTeams(teamsList);
            setMilestones(milestonesList);
        } catch (err) {
            console.error("Failed to load milestones data:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    // Unique milestones configured
    const uniqueMilestoneSpecs = useMemo(() => {
        const specsMap = new Map();
        milestones.forEach(m => {
            if (!specsMap.has(m.title)) {
                specsMap.set(m.title, {
                    title: m.title,
                    description: m.description,
                    deadline: m.deadline,
                    count: 0
                });
            }
            specsMap.get(m.title).count += 1;
        });
        return Array.from(specsMap.values());
    }, [milestones]);

    // Handle Create Milestone
    const handleCreateMilestone = async (e) => {
        e.preventDefault();
        if (!newMilestone.title.trim() || !newMilestone.description.trim() || !newMilestone.deadline) {
            alert("Please fill in all fields.");
            return;
        }
        
        if (teams.length === 0) {
            alert("There are no assigned teams to assign this milestone to.");
            return;
        }

        const selectedTeams = targetTeamsSelection === 'all' 
            ? teams.map(t => t.id)
            : selectedTeamIds;

        if (selectedTeams.length === 0) {
            alert("Please select at least one team.");
            return;
        }

        setSubmittingForm(true);
        try {
            await api.post('/milestones', {
                title: newMilestone.title.trim(),
                description: newMilestone.description.trim(),
                deadline: new Date(newMilestone.deadline).toISOString(),
                form_schema: formFields.length > 0 ? formFields : null,
                target_teams: selectedTeams
            });

            alert(`Milestone successfully assigned!`);
            
            // Reset form and reload
            setNewMilestone({ title: '', description: '', deadline: '' });
            setFormFields([]);
            setSelectedTeamIds([]);
            setTargetTeamsSelection('all');
            loadData();
        } catch (err) {
            alert("Failed to create milestone: " + (err.response?.data?.detail || err.message));
        } finally {
            setSubmittingForm(false);
        }
    };

    // Delete Milestone for all my teams
    const handleDeleteMilestone = async (milestoneItem) => {
        if (!window.confirm(`Are you sure you want to delete this specific milestone?`)) {
            return;
        }
        
        try {
            await api.delete(`/milestones/${milestoneItem.id}`);
            alert(`Deleted milestone successfully.`);
            loadData();
            if (viewingSubmission?.id === milestoneItem.id) {
                setViewingSubmission(null);
            }
        } catch (err) {
            alert("Failed to delete milestone: " + (err.response?.data?.detail || err.message));
        }
    };

    // Approve a submission
    const handleApproveSubmission = async (milestoneItem) => {
        setActionLoadingId(milestoneItem.id);
        try {
            await api.patch(`/milestones/${milestoneItem.id}`, { status: 'approved' });
            alert("Milestone approved!");
            loadData();
            if (viewingSubmission?.id === milestoneItem.id) {
                setViewingSubmission(prev => ({ ...prev, status: 'approved' }));
            }
        } catch (err) {
            alert("Failed to approve milestone: " + (err.response?.data?.detail || err.message));
        } finally {
            setActionLoadingId(null);
        }
    };

    // Revoke milestone approval / Request revision
    const handleRequestRevision = async (milestoneItem) => {
        if (!window.confirm(`Request revision on "${milestoneItem.title}"?`)) {
            return;
        }
        setActionLoadingId(milestoneItem.id);
        try {
            await api.patch(`/milestones/${milestoneItem.id}`, { status: 'in_progress' });
            alert("Revision requested.");
            loadData();
            if (viewingSubmission?.id === milestoneItem.id) {
                setViewingSubmission(prev => ({ ...prev, status: 'in_progress' }));
            }
        } catch (err) {
            alert("Failed to update status: " + (err.response?.data?.detail || err.message));
        } finally {
            setActionLoadingId(null);
        }
    };

    // Filtered roster data mapping
    const gridData = useMemo(() => {
        return filteredTeams.map(team => {
            const teamNumId = getTeamNumericId(team.id);
            const teamMilestones = milestones.filter(m => 
                m.team_str_id === team.id || 
                (teamNumId && m.team_id === teamNumId) ||
                (!m.team_id && !m.team_str_id)
            );
            
            const targetMilestones = selectedMilestoneFilter === 'ALL'
                ? teamMilestones
                : teamMilestones.filter(m => m.title === selectedMilestoneFilter);

            return {
                team,
                teamNumId,
                targetMilestones
            };
        }).filter(item => {
            const matchSearch = searchTerm ? (
                String(item.team.id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                String(item.team.projectTitle || '').toLowerCase().includes(searchTerm.toLowerCase())
            ) : true;
            return matchSearch;
        });
    }, [filteredTeams, milestones, selectedMilestoneFilter, searchTerm]);

    const handleSelectTeamCheckbox = (teamId) => {
        if (selectedTeamIds.includes(teamId)) {
            setSelectedTeamIds(selectedTeamIds.filter(id => id !== teamId));
        } else {
            setSelectedTeamIds([...selectedTeamIds, teamId]);
        }
    };

    if (loading) {
        return (
            <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            </div>
        );
    }

    return (
        <div className="space-y-8 relative z-10 min-h-[calc(100vh-8rem)] max-w-7xl mx-auto">
            
            {/* Header Banner */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50">
                <div>
                    <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Synopsis Submission Page</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Configure synopsis submission requests and evaluate student synopsis submissions.</p>
                </div>
                <button onClick={loadData} className="flex items-center justify-center px-4 py-2.5 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm">
                    <RefreshCw className="w-4 h-4 mr-2" /> Sync Records
                </button>
            </div>

            {/* Split Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                
                {/* Form to Assign New Milestone */}
                <div className="lg:col-span-1 bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 p-6 space-y-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
                    <div className="flex items-center space-x-3 border-b border-slate-100 dark:border-slate-700 pb-4">
                        <div className="p-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg text-indigo-500"><Plus className="w-5 h-5" /></div>
                        <h2 className="text-lg font-black text-slate-800 dark:text-white">Assign Synopsis Request</h2>
                    </div>

                    <form onSubmit={handleCreateMilestone} className="space-y-4 text-left">
                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Synopsis Request Title</label>
                            <input 
                                type="text"
                                placeholder="e.g. SRS & Architecture Document"
                                value={newMilestone.title}
                                onChange={e => setNewMilestone({ ...newMilestone, title: e.target.value })}
                                className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all"
                            />
                        </div>

                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Description / Deliverable Specs</label>
                            <textarea 
                                rows="3"
                                placeholder="e.g. Describe questions or files you want students to submit."
                                value={newMilestone.description}
                                onChange={e => setNewMilestone({ ...newMilestone, description: e.target.value })}
                                className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all resize-none"
                            />
                        </div>

                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Deadline Date</label>
                            <input 
                                type="date"
                                value={newMilestone.deadline}
                                onChange={e => setNewMilestone({ ...newMilestone, deadline: e.target.value })}
                                className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all text-slate-750 dark:text-slate-300"
                            />
                        </div>

                        {/* Team assignment targeting */}
                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Target Teams</label>
                            <div className="flex gap-4 mb-2">
                                <label className="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                                    <input 
                                        type="radio" 
                                        name="targetTeams" 
                                        checked={targetTeamsSelection === 'all'} 
                                        onChange={() => setTargetTeamsSelection('all')} 
                                    />
                                    All Teams
                                </label>
                                <label className="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                                    <input 
                                        type="radio" 
                                        name="targetTeams" 
                                        checked={targetTeamsSelection === 'specific'} 
                                        onChange={() => setTargetTeamsSelection('specific')} 
                                    />
                                    Specific Teams
                                </label>
                            </div>
                            
                            {targetTeamsSelection === 'specific' && (
                                <div className="space-y-1.5 max-h-32 overflow-y-auto border border-slate-200 dark:border-slate-700 p-2.5 rounded-xl bg-slate-50 dark:bg-slate-900">
                                    {teams.map(team => (
                                        <label key={team.id} className="flex items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300 cursor-pointer">
                                            <input 
                                                type="checkbox"
                                                checked={selectedTeamIds.includes(team.id)}
                                                onChange={() => handleSelectTeamCheckbox(team.id)}
                                                className="rounded text-indigo-600 focus:ring-indigo-500"
                                            />
                                            {teamDisplayLabel(team.id || team.name, team, semesterMap)}
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Form Builder Widget */}
                        <div className="border-t border-slate-100 dark:border-slate-700 pt-4 space-y-4">
                            <div className="flex justify-between items-center">
                                <label className="block text-xs uppercase tracking-widest font-black text-slate-500 dark:text-slate-400">Form Questions</label>
                                <span className="text-[10px] text-slate-400 font-bold">Google Forms Mode</span>
                            </div>

                            {formFields.map((field, index) => (
                                <div key={field.id} className="p-3 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 space-y-3 relative group">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] font-black text-indigo-500 uppercase">Q{index + 1}: {field.type.toUpperCase()}</span>
                                        <button 
                                            type="button" 
                                            onClick={() => removeFormField(field.id)}
                                            className="text-slate-400 hover:text-red-500 transition-colors"
                                        >
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    </div>

                                    <input 
                                        type="text"
                                        placeholder="Question/Label Text"
                                        value={field.label}
                                        onChange={e => updateFormField(field.id, { label: e.target.value })}
                                        className="w-full px-3 py-1.5 bg-white dark:bg-slate-955 border border-slate-200 dark:border-slate-800 rounded-lg text-xs outline-none focus:ring-1 focus:ring-indigo-500 dark:text-white"
                                    />

                                    {(field.type === 'mcq' || field.type === 'checkbox') && (
                                        <div className="space-y-1.5 pl-2 border-l border-slate-200 dark:border-slate-800">
                                            <span className="text-[9px] uppercase font-bold text-slate-400">Options:</span>
                                            {field.options.map((opt, oIdx) => (
                                                <div key={oIdx} className="flex items-center gap-1.5">
                                                    <input 
                                                        type="text"
                                                        value={opt}
                                                        onChange={e => updateFieldOption(field.id, oIdx, e.target.value)}
                                                        className="flex-1 px-2 py-1 bg-white dark:bg-slate-955 border border-slate-200 dark:border-slate-800 rounded-md text-[11px] outline-none"
                                                    />
                                                    {field.options.length > 1 && (
                                                        <button 
                                                            type="button"
                                                            onClick={() => removeFieldOption(field.id, oIdx)}
                                                            className="text-slate-400 hover:text-red-500"
                                                        >
                                                            &times;
                                                        </button>
                                                    )}
                                                </div>
                                            ))}
                                            <button 
                                                type="button"
                                                onClick={() => addFieldOption(field.id)}
                                                className="text-[10px] text-indigo-500 hover:underline font-bold"
                                            >
                                                + Add Option
                                            </button>
                                        </div>
                                    )}

                                    <label className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400">
                                        <input 
                                            type="checkbox"
                                            checked={field.required}
                                            onChange={e => updateFormField(field.id, { required: e.target.checked })}
                                            className="w-3.5 h-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                        />
                                        Required field
                                    </label>
                                </div>
                            ))}

                            <div className="grid grid-cols-2 gap-2 pt-2">
                                <button type="button" onClick={() => addFormField('text')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors">
                                    + Short Answer
                                </button>
                                <button type="button" onClick={() => addFormField('paragraph')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors">
                                    + Long Answer
                                </button>
                                <button type="button" onClick={() => addFormField('mcq')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors">
                                    + Multiple Choice
                                </button>
                                <button type="button" onClick={() => addFormField('checkbox')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors">
                                    + Checkboxes
                                </button>
                                <button type="button" onClick={() => addFormField('github')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors col-span-2">
                                    + GitHub Link
                                </button>
                                <button type="button" onClick={() => addFormField('file')} className="py-1.5 px-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-100 rounded-lg text-[10px] font-bold text-slate-600 dark:text-slate-300 transition-colors col-span-2">
                                    + File / PDF Link
                                </button>
                            </div>
                        </div>

                        <button 
                            type="submit" 
                            disabled={submittingForm}
                            className="w-full py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white font-black uppercase tracking-widest text-xs rounded-xl shadow-lg shadow-indigo-500/20 active:scale-95 transition-all flex items-center justify-center disabled:opacity-50"
                        >
                            {submittingForm ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                            Publish Synopsis Request
                        </button>
                    </form>
                </div>

                {/* Active Milestones Specifications List */}
                <div className="lg:col-span-2 bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 p-6 space-y-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
                    <div className="flex items-center space-x-3 border-b border-slate-100 dark:border-slate-700 pb-4">
                        <div className="p-2 bg-violet-50 dark:bg-violet-500/10 rounded-lg text-violet-500"><Award className="w-5 h-5" /></div>
                        <h2 className="text-lg font-black text-slate-800 dark:text-white">Active Synopsis Requirements ({uniqueMilestoneSpecs.length})</h2>
                    </div>

                    {uniqueMilestoneSpecs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400">
                            <AlertCircle className="w-12 h-12 mb-3 text-slate-300" />
                            <p className="font-bold text-slate-500">No Synopsis Requirements Defined Yet</p>
                            <p className="text-xs max-w-sm mt-1">Configure and assign a milestone using the creator form to initiate project tracking.</p>
                        </div>
                    ) : (
                        <div className="space-y-4 max-h-[440px] overflow-y-auto pr-2">
                            {uniqueMilestoneSpecs.map(spec => (
                                <div key={spec.title} className="flex justify-between items-start p-4 bg-slate-50/50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-850 rounded-2xl group transition-all hover:shadow-sm text-left">
                                    <div className="space-y-1.5 flex-1 pr-4">
                                        <h4 className="font-black text-slate-800 dark:text-white text-sm flex items-center gap-2">
                                            {spec.title}
                                            <span className="px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-[10px] font-bold">
                                                Assigned to {spec.count} teams
                                            </span>
                                        </h4>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed font-medium">{spec.description}</p>
                                        <div className="flex items-center text-[11px] text-slate-400 dark:text-slate-500 font-bold gap-1 mt-2">
                                            <Calendar className="w-3.5 h-3.5 text-indigo-500" />
                                            Deadline: {new Date(spec.deadline).toLocaleDateString()}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Submissions Review Roster */}
            <div className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 p-6 space-y-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
                
                {/* Roster Controls */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-4 border-b border-slate-100 dark:border-slate-700">
                    <div className="flex items-center space-x-3 text-left">
                        <div className="p-2 bg-emerald-50 dark:bg-emerald-500/10 rounded-lg text-emerald-500"><Users className="w-5 h-5" /></div>
                        <div>
                            <h2 className="text-lg font-black text-slate-800 dark:text-white">Submission Verification</h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400 font-semibold">Verify team uploads, responses, and approve completion status.</p>
                        </div>
                    </div>
                    
                    <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
                        
                        {/* Search field */}
                        <div className="relative flex-1 sm:w-64">
                            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                            <input 
                                type="text"
                                placeholder="Search by team or project title..."
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold outline-none focus:ring-2 focus:ring-indigo-500 dark:text-white transition-all"
                            />
                        </div>

                        {/* Milestone spec filter */}
                        <select 
                            value={selectedMilestoneFilter}
                            onChange={e => setSelectedMilestoneFilter(e.target.value)}
                            className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-3 py-2 text-xs font-black uppercase text-slate-600 dark:text-slate-300 outline-none cursor-pointer"
                        >
                            <option value="ALL">All Milestones</option>
                            {uniqueMilestoneSpecs.map(spec => (
                                <option key={spec.title} value={spec.title}>{spec.title}</option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Grid Roster Table */}
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b border-slate-100 dark:border-slate-800 text-[10px] uppercase tracking-widest font-black text-slate-400 dark:text-slate-500">
                                <th className="pb-3 pl-4">Team</th>
                                <th className="pb-3">Project Details</th>
                                <th className="pb-3">Milestone Deliverable</th>
                                <th className="pb-3">Verification Status</th>
                                <th className="pb-3">Student Uploads</th>
                                <th className="pb-3 pr-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300">
                            {gridData.length === 0 ? (
                                <tr>
                                    <td colSpan="6" className="text-center py-12 text-slate-400 font-bold">
                                        No submissions match filters or teams.
                                    </td>
                                </tr>
                            ) : (
                                gridData.map(({ team, _teamNumId, targetMilestones }) => {
                                    if (targetMilestones.length === 0) {
                                        return (
                                            <tr key={team.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30 transition-colors">
                                                <td className="py-4 pl-4 font-black text-slate-800 dark:text-white">
                                                    {teamDisplayLabel(team.id, team, semesterMap)}
                                                </td>
                                                <td className="py-4">
                                                    <div className="font-bold text-slate-700 dark:text-slate-200">{team.projectTitle || 'Unallocated Project'}</div>
                                                    <div className="text-[10px] text-slate-400 mt-0.5">{team.domain || 'N/A'}</div>
                                                </td>
                                                <td colSpan="4" className="py-4 text-slate-400 text-[11px] font-bold">
                                                    No milestones assigned/created for this team.
                                                </td>
                                            </tr>
                                        );
                                    }

                                    return targetMilestones.map((m, idx) => {
                                        const statusColors = {
                                            not_started: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
                                            in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
                                            submitted: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400',
                                            completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400',
                                            approved: 'bg-emerald-500 text-white font-black'
                                        };

                                        return (
                                            <tr key={m.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30 transition-colors">
                                                {idx === 0 && (
                                                    <>
                                                        <td rowSpan={targetMilestones.length} className="py-4 pl-4 font-black text-slate-800 dark:text-white align-top border-r border-slate-100 dark:border-slate-800/80 pr-4">
                                                            {teamDisplayLabel(team.id, team, semesterMap)}
                                                        </td>
                                                        <td rowSpan={targetMilestones.length} className="py-4 align-top border-r border-slate-100 dark:border-slate-800/80 pr-4">
                                                            <div className="font-black text-slate-700 dark:text-slate-200">{team.projectTitle || 'Unallocated Project'}</div>
                                                            <div className="text-[10px] text-slate-400 mt-0.5 font-bold">{team.domain || 'N/A'}</div>
                                                        </td>
                                                    </>
                                                )}
                                                <td className="py-4 pl-3 text-left">
                                                    <div className="font-bold text-slate-800 dark:text-slate-100">{m.title}</div>
                                                    <div className="text-[10px] text-slate-400 font-bold mt-0.5">Deadline: {new Date(m.deadline).toLocaleDateString()}</div>
                                                </td>
                                                <td className="py-4">
                                                    <span className={`text-[10px] px-2.5 py-1 rounded-full font-black uppercase tracking-wider ${statusColors[m.status] || 'bg-slate-100'}`}>
                                                        {m.status.replace('_', ' ')}
                                                    </span>
                                                </td>
                                                <td className="py-4">
                                                    {m.form_schema ? (
                                                        <button 
                                                            onClick={() => setViewingSubmission(m)}
                                                            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-600 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 dark:border-indigo-500/30 dark:text-indigo-400 rounded-lg transition-colors font-black text-[10px] uppercase tracking-wider"
                                                        >
                                                            <FileText className="w-3.5 h-3.5" />
                                                            View Responses
                                                        </button>
                                                    ) : (
                                                        <div className="flex space-x-2.5">
                                                            {m.github_url ? (
                                                                <a 
                                                                    href={safeLinkUrl(m.github_url) || undefined} 
                                                                    target="_blank" 
                                                                    rel="noopener noreferrer" 
                                                                    className="flex items-center gap-1.5 px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-200 transition-colors"
                                                                    title="Open GitHub Repository"
                                                                >
                                                                    <Github className="w-3.5 h-3.5" />
                                                                    <span className="text-[10px] font-bold">Code</span>
                                                                </a>
                                                            ) : (
                                                                <span className="text-[10px] text-slate-400 italic">No repo</span>
                                                            )}
                                                            {m.file_url ? (
                                                                <a 
                                                                    href={safeLinkUrl(m.file_url) || undefined} 
                                                                    target="_blank" 
                                                                    rel="noopener noreferrer" 
                                                                    className="flex items-center gap-1.5 px-2 py-1 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-200 transition-colors"
                                                                    title="Open Uploaded Document"
                                                                >
                                                                    <FileText className="w-3.5 h-3.5 text-indigo-500" />
                                                                    <span className="text-[10px] font-bold">Doc</span>
                                                                </a>
                                                            ) : (
                                                                <span className="text-[10px] text-slate-400 italic">No doc</span>
                                                            )}
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="py-4 pr-4 text-right">
                                                    <div className="flex justify-end space-x-2">
                                                        {m.status !== 'approved' ? (
                                                            <button 
                                                                onClick={() => handleApproveSubmission(m)}
                                                                disabled={actionLoadingId === m.id || m.status !== 'submitted'}
                                                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[10px] font-black uppercase tracking-wider disabled:opacity-40 transition-colors flex items-center gap-1 shadow-sm shadow-emerald-500/10 active:scale-95"
                                                            >
                                                                {actionLoadingId === m.id ? (
                                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                                ) : (
                                                                    <Check className="w-3 h-3" />
                                                                )}
                                                                Approve
                                                            </button>
                                                        ) : (
                                                            <button 
                                                                onClick={() => handleRequestRevision(m)}
                                                                disabled={actionLoadingId === m.id}
                                                                className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 border border-rose-200 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 dark:border-rose-500/30 text-rose-700 dark:text-rose-400 rounded-lg text-[10px] font-black uppercase tracking-wider transition-colors flex items-center gap-1 active:scale-95"
                                                            >
                                                                {actionLoadingId === m.id ? (
                                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                                ) : (
                                                                    <AlertTriangle className="w-3 h-3 text-rose-500" />
                                                                )}
                                                                Reject / Revoke
                                                            </button>
                                                        )}
                                                        <button 
                                                            onClick={() => handleDeleteMilestone(m)}
                                                            className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
                                                            title="Delete Milestone"
                                                        >
                                                            <Trash2 className="w-3.5 h-3.5" />
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    });
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* View Responses Modal */}
            <AnimatePresence>
                {viewingSubmission && (() => {
                    const schema = typeof viewingSubmission.form_schema === 'string' 
                        ? JSON.parse(viewingSubmission.form_schema) 
                        : viewingSubmission.form_schema;
                    const responses = typeof viewingSubmission.submission_data === 'string'
                        ? JSON.parse(viewingSubmission.submission_data)
                        : (viewingSubmission.submission_data || {});
                    
                    const teamObj = teams.find(t => getTeamNumericId(t.id) === viewingSubmission.team_id || t.id === viewingSubmission.team_str_id);
                    const displayName = teamObj ? teamDisplayLabel(teamObj.id, teamObj, semesterMap) : `Team ${viewingSubmission.team_id}`;

                    return (
                        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                            <motion.div 
                                initial={{ opacity: 0, scale: 0.95 }} 
                                animate={{ opacity: 1, scale: 1 }} 
                                exit={{ opacity: 0, scale: 0.95 }}
                                className="bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-200 dark:border-slate-700/50 max-w-xl w-full p-6 space-y-6 relative overflow-hidden"
                            >
                                <div className="flex justify-between items-start">
                                    <div className="space-y-1">
                                        <h3 className="text-lg font-black text-slate-800 dark:text-white leading-tight">{viewingSubmission.title}</h3>
                                        <p className="text-xs text-indigo-600 dark:text-indigo-400 font-bold">{displayName}</p>
                                    </div>
                                    <button 
                                        onClick={() => setViewingSubmission(null)}
                                        className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 font-black text-lg p-1"
                                    >
                                        &times;
                                    </button>
                                </div>

                                <div className="space-y-4 max-h-[380px] overflow-y-auto pr-2">
                                    {schema && schema.map((q) => {
                                        const ans = responses[q.id];
                                        const hasAnswer = ans !== undefined && ans !== null && ans !== '' && (!Array.isArray(ans) || ans.length > 0);
                                        return (
                                            <div key={q.id} className="p-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl space-y-1.5 text-left">
                                                <span className="text-[10px] uppercase font-black tracking-wider text-slate-400">{q.label}</span>
                                                
                                                {!hasAnswer ? (
                                                    <div className="text-slate-400 dark:text-slate-500 italic text-xs">No Response</div>
                                                ) : q.type === 'github' ? (
                                                    <a 
                                                        href={safeLinkUrl(ans) || undefined} 
                                                        target="_blank" 
                                                        rel="noopener noreferrer" 
                                                        className="flex items-center gap-2 w-fit px-3 py-1.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-200"
                                                    >
                                                        <Github className="w-3.5 h-3.5" />
                                                        <span>Open GitHub Repository</span>
                                                        <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                                                    </a>
                                                ) : q.type === 'file' ? (
                                                    <a 
                                                        href={safeLinkUrl(ans) || undefined} 
                                                        target="_blank" 
                                                        rel="noopener noreferrer" 
                                                        className="flex items-center gap-2 w-fit px-3 py-1.5 bg-white dark:bg-slate-955 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-200"
                                                    >
                                                        <FileText className="w-3.5 h-3.5 text-indigo-500" />
                                                        <span>Open Uploaded File</span>
                                                        <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                                                    </a>
                                                ) : Array.isArray(ans) ? (
                                                    <div className="flex flex-wrap gap-1.5">
                                                        {ans.map(o => (
                                                            <span key={o} className="px-2.5 py-1 rounded-lg bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-xs font-bold">
                                                                {o}
                                                            </span>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="text-xs font-bold text-slate-800 dark:text-slate-200 whitespace-pre-wrap">{ans}</div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>

                                <div className="flex justify-end gap-2 border-t border-slate-100 dark:border-slate-700 pt-4">
                                    <button 
                                        onClick={() => setViewingSubmission(null)}
                                        className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 rounded-xl text-xs uppercase tracking-widest font-black transition-all"
                                    >
                                        Close
                                    </button>
                                </div>
                            </motion.div>
                        </div>
                    );
                })()}
            </AnimatePresence>
        </div>
    );
}
