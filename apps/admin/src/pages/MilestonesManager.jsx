import React, { useState, useEffect, useMemo } from 'react';
import { 
    AlertCircle, CheckCircle, Calendar, Plus, Loader2, Save, 
    Trash2, Github, ExternalLink, AlertTriangle, Award, 
    FileText, Check, Search, Users, RefreshCw
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { apiFetchTable, apiUpsertTable, apiDeleteRows, getActiveSemesterIds } from '../lib/api';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamDisplayLabel } from '../lib/globalFilters';
import { safeLinkUrl } from '../lib/safeUrl';

// Helper to extract numeric ID (e.g. "TEAM-12", "admin-team-T200", or "12" -> 12/200)
const getTeamNumericId = (teamIdStr) => {
    if (!teamIdStr) return null;
    // First, try to find T followed by digits (common pattern like T200)
    let match = String(teamIdStr).match(/T(\d+)/);
    if (match && match[1]) {
        return parseInt(match[1], 10);
    }
    // If that fails, just find any digits
    match = String(teamIdStr).match(/\d+/g);
    if (match && match.length > 0) {
        return parseInt(match[match.length - 1], 10);
    }
    return null;
};

const formatMentor = (mentorField) => {
    if (!mentorField) return 'None';
    try {
        const parsed = JSON.parse(mentorField);
        if (Array.isArray(parsed)) {
            return parsed.map(m => m.name || m).join(', ');
        }
        return String(parsed);
    } catch (e) {
        return String(mentorField);
    }
};

export default function MilestonesManager() {
    const navigate = useNavigate();
    const { filterRows, semesterMap } = useGlobalFilters();
    const [activeSemesterId, setActiveSemesterId] = useState(null);
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
            const ids = await getActiveSemesterIds();
            const primaryId = ids.length > 0 ? ids[0] : 'NONE';
            setActiveSemesterId(primaryId);
            
            if (primaryId !== 'NONE') {
                // Fetch active teams and milestones
                const [teamsData, milestonesData] = await Promise.all([
                    apiFetchTable('teams_validation'),
                    apiFetchTable('milestones')
                ]);
                
                setTeams(teamsData || []);
                setMilestones(milestonesData || []);
            }
        } catch (err) {
            console.error("Failed to load Milestones Manager data:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    // Unique milestones configured (derived from live milestones in database)
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

    // Handle Create Milestone (Distribute to all teams)
    const handleCreateMilestone = async (e) => {
        e.preventDefault();
        if (!newMilestone.title.trim() || !newMilestone.description.trim() || !newMilestone.deadline) {
            alert("Please fill in all fields.");
            return;
        }
        
        if (teams.length === 0) {
            alert("There are no validated teams in the active semester to assign this milestone to.");
            return;
        }

        setSubmittingForm(true);
        try {
            // Create one milestone per team with REAL numeric team IDs to satisfy NOT NULL constraint
            const rowsToInsert = teams.map(team => {
                const teamNumId = getTeamNumericId(team.id);
                return {
                    team_id: teamNumId !== null ? teamNumId : 0, // Use real team numeric ID, fallback to 0
                    semester_id: activeSemesterId,
                    title: newMilestone.title.trim(),
                    description: newMilestone.description.trim(),
                    deadline: new Date(newMilestone.deadline).toISOString(),
                    status: 'not_started',
                    github_url: null,
                    file_url: null,
                    form_schema: formFields.length > 0 ? formFields : null
                };
            });

            console.log('Upserting milestones rows:', rowsToInsert);

            // First delete any existing milestones with the same title (for current semester)
            try {
                await apiDeleteRows('milestones', {
                    title: `eq.${newMilestone.title.trim()}`,
                    semester_id: `eq.${activeSemesterId}`
                });
            } catch (deleteErr) {
                console.warn('Could not delete old milestones (proceeding anyway):', deleteErr);
            }

            // Now upsert the milestones
            try {
                await apiUpsertTable('milestones', rowsToInsert);
            } catch (fkErr) {
                console.error('Milestone upsert error:', fkErr);
                throw fkErr;
            }

            AuditLogger.logAdminAction(getCurrentUser(), `Assigned new milestone "${newMilestone.title}" to all teams`);
            alert(`Milestone "${newMilestone.title}" successfully assigned to ${rowsToInsert.length} teams!`);
            
            // Reset form and reload
            setNewMilestone({ title: '', description: '', deadline: '' });
            setFormFields([]);
            const updatedMilestones = await apiFetchTable('milestones');
            setMilestones(updatedMilestones || []);
        } catch (err) {
            alert("Failed to create milestone: " + err.message);
        } finally {
            setSubmittingForm(false);
        }
    };

    // Bulk Delete Milestone Specs (Delete for all teams)
    const handleDeleteMilestoneSpec = async (title) => {
        if (!window.confirm(`Are you sure you want to delete the milestone "${title}" for all teams? This will permanently delete all student submissions for this milestone.`)) {
            return;
        }
        
        try {
            await apiDeleteRows('milestones', { 
                title: `eq.${title}`,
                semester_id: `eq.${activeSemesterId}`
            });
            AuditLogger.logAdminAction(getCurrentUser(), `Deleted milestone requirement "${title}" and all its submissions`);
            alert(`Deleted milestone "${title}" successfully.`);
            
            // Reload
            const updatedMilestones = await apiFetchTable('milestones');
            setMilestones(updatedMilestones || []);
            if (selectedMilestoneFilter === title) {
                setSelectedMilestoneFilter('ALL');
            }
        } catch (err) {
            alert("Failed to delete milestone: " + err.message);
        }
    };

    // Approve a submission inline
    const handleApproveSubmission = async (milestoneItem) => {
        setActionLoadingId(milestoneItem.id);
        try {
            const updatedRow = {
                ...milestoneItem,
                status: 'approved'
            };
            await apiUpsertTable('milestones', [updatedRow], 'id');
            AuditLogger.logAdminAction(getCurrentUser(), `Approved milestone "${milestoneItem.title}" submission for team ID ${milestoneItem.team_id}`);
            
            // Update local state
            setMilestones(prev => prev.map(m => m.id === milestoneItem.id ? updatedRow : m));
        } catch (err) {
            alert("Failed to approve milestone: " + err.message);
        } finally {
            setActionLoadingId(null);
        }
    };

    // Revoke milestone approval inline (request revision)
    const handleRequestRevision = async (milestoneItem) => {
        const teamObj = teams.find(t => getTeamNumericId(t.id) === milestoneItem.team_id || t.id === milestoneItem.team_str_id);
        const displayLabel = teamObj ? teamDisplayLabel(teamObj.id, teamObj, semesterMap) : `Team ${milestoneItem.team_id}`;
        if (!window.confirm(`Request revision/revoke approval for ${displayLabel} on "${milestoneItem.title}"?`)) {
            return;
        }
        setActionLoadingId(milestoneItem.id);
        try {
            const updatedRow = {
                ...milestoneItem,
                status: 'in_progress'
            };
            await apiUpsertTable('milestones', [updatedRow], 'id');
            AuditLogger.logAdminAction(getCurrentUser(), `Revoked approval/requested revision on milestone "${milestoneItem.title}" for team ID ${milestoneItem.team_id}`);
            
            // Update local state
            setMilestones(prev => prev.map(m => m.id === milestoneItem.id ? updatedRow : m));
        } catch (err) {
            alert("Failed to update status: " + err.message);
        } finally {
            setActionLoadingId(null);
        }
    };

    // Filtered roster data mapping
    const gridData = useMemo(() => {
        return filteredTeams.map(team => {
            const teamNumId = getTeamNumericId(team.id);
            // Find all milestone records for this team — match by team_str_id or team_id
            // If no team identifiers, just show all milestones for this semester
            const teamMilestones = milestones.filter(m => 
                m.team_str_id === team.id || 
                (teamNumId && m.team_id === teamNumId) ||
                (!m.team_id && !m.team_str_id) // If no team identifiers, show for all teams
            );
            
            // If filtering by specific milestone spec
            const targetMilestones = selectedMilestoneFilter === 'ALL'
                ? teamMilestones
                : teamMilestones.filter(m => m.title === selectedMilestoneFilter);

            return {
                team,
                teamNumId,
                targetMilestones
            };
        }).filter(item => {
            // Apply search filter (team name/id or project title)
            const matchSearch = searchTerm ? (
                String(item.team.id || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                String(item.team.title || '').toLowerCase().includes(searchTerm.toLowerCase())
            ) : true;
            return matchSearch;
        });
    }, [filteredTeams, milestones, selectedMilestoneFilter, searchTerm]);

    if (loading) {
        return (
            <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            </div>
        );
    }

    if (activeSemesterId === 'NONE') {
        return (
            <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }} 
                    animate={{ opacity: 1, scale: 1 }} 
                    className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-8 rounded-3xl shadow-xl border border-slate-200/50 dark:border-slate-700/50 max-w-lg w-full text-center space-y-6"
                >
                    <div className="mx-auto w-16 h-16 bg-amber-50 dark:bg-amber-500/10 rounded-2xl flex items-center justify-center text-amber-500">
                        <AlertTriangle className="w-8 h-8" />
                    </div>
                    <div className="space-y-2">
                        <h2 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">No Active Semester</h2>
                        <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
                            Project Milestones are bound to active semester batches. 
                            Please configure and activate a semester to manage deliverables.
                        </p>
                    </div>
                    <button 
                        onClick={() => navigate('/admin/semester-settings')}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-black uppercase tracking-widest text-xs rounded-xl shadow-lg shadow-indigo-500/20 active:scale-95 transition-all"
                    >
                        Go to Semester Settings
                    </button>
                </motion.div>
            </div>
        );
    }

    return (
        <div className="space-y-8 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} 
                className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50">
                <div>
                    <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Synopsis Submissions Manager</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Define, distribute, and verify student project synopsis submissions and deliverables.</p>
                </div>
                <button onClick={loadData} className="flex items-center justify-center px-4 py-2.5 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm">
                    <RefreshCw className="w-4 h-4 mr-2" /> Sync Records
                </button>
            </motion.div>

            {/* Split Panel: Assign Milestone & Unique Specifications */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                
                {/* Form to Assign New Milestone */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="lg:col-span-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-6">
                    <div className="flex items-center space-x-3 border-b border-slate-100 dark:border-slate-700 pb-4">
                        <div className="p-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg text-indigo-500"><Plus className="w-5 h-5" /></div>
                        <h2 className="text-lg font-black text-slate-800 dark:text-white">Assign Synopsis Requirement</h2>
                    </div>

                    <form onSubmit={handleCreateMilestone} className="space-y-4">
                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Milestone Title</label>
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
                                placeholder="e.g. Upload a system architecture flowchart and SRS document. Provide GitHub repository link."
                                value={newMilestone.description}
                                onChange={e => setNewMilestone({ ...newMilestone, description: e.target.value })}
                                className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all resize-none"
                            />
                        </div>

                        <div>
                            <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Deadline Date</label>
                            <div className="relative">
                                <input 
                                    type="date"
                                    value={newMilestone.deadline}
                                    onChange={e => setNewMilestone({ ...newMilestone, deadline: e.target.value })}
                                    className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all text-slate-700 dark:text-slate-300"
                                />
                            </div>
                        </div>

                        {/* Dynamic Form Builder Section */}
                        <div className="border-t border-slate-100 dark:border-slate-700 pt-4 space-y-4">
                            <div className="flex justify-between items-center">
                                <label className="block text-xs uppercase tracking-widest font-black text-slate-500 dark:text-slate-400">Form Questions</label>
                                <span className="text-[10px] text-slate-400 font-bold">Google Forms Mode</span>
                            </div>

                            {formFields.map((field, index) => (
                                <div key={field.id} className="p-3 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 space-y-3 relative group text-left">
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
                                        className="w-full px-3 py-1.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-xs outline-none focus:ring-1 focus:ring-indigo-500 dark:text-white"
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
                                                        className="flex-1 px-2 py-1 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-md text-[11px] outline-none"
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
                            Publish Milestone
                        </button>
                    </form>
                </motion.div>

                {/* Unique Milestones Specifications List */}
                <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="lg:col-span-2 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-6">
                    <div className="flex items-center space-x-3 border-b border-slate-100 dark:border-slate-700 pb-4">
                        <div className="p-2 bg-violet-50 dark:bg-violet-500/10 rounded-lg text-violet-500"><Award className="w-5 h-5" /></div>
                        <h2 className="text-lg font-black text-slate-800 dark:text-white">Active Milestone Targets ({uniqueMilestoneSpecs.length})</h2>
                    </div>

                    {uniqueMilestoneSpecs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400">
                            <AlertCircle className="w-12 h-12 mb-3 text-slate-300" />
                            <p className="font-bold text-slate-500">No Milestones Defined Yet</p>
                            <p className="text-xs max-w-sm mt-1">Configure and assign a milestone using the creator form to initiate project tracking.</p>
                        </div>
                    ) : (
                        <div className="space-y-4 max-h-[340px] overflow-y-auto pr-2">
                            {uniqueMilestoneSpecs.map(spec => (
                                <div key={spec.title} className="flex justify-between items-start p-4 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 rounded-2xl group transition-all hover:shadow-sm">
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
                                    <button 
                                        onClick={() => handleDeleteMilestoneSpec(spec.title)}
                                        className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors"
                                        title="Delete Milestone requirement for all teams"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </motion.div>
            </div>

            {/* Submissions Review Roster */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-6">
                
                {/* Roster Controls */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-4 border-b border-slate-100 dark:border-slate-700">
                    <div className="flex items-center space-x-3">
                        <div className="p-2 bg-emerald-50 dark:bg-emerald-500/10 rounded-lg text-emerald-500"><Users className="w-5 h-5" /></div>
                        <div>
                            <h2 className="text-lg font-black text-slate-800 dark:text-white">Submission Verification</h2>
                            <p className="text-xs text-slate-500 dark:text-slate-400 font-semibold">Verify team uploads, repositories, and review completion rates.</p>
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
                                <th className="pb-3">Project Domain & Details</th>
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
                                                    <div className="font-bold text-slate-700 dark:text-slate-200">{team.title || 'Unallocated Project'}</div>
                                                    <div className="text-[10px] text-slate-400 mt-0.5">{team.domain || 'N/A'} • Mentor: {formatMentor(team.mentor)}</div>
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
                                                            <div className="font-black text-slate-700 dark:text-slate-200">{team.title || 'Unallocated Project'}</div>
                                                            <div className="text-[10px] text-slate-400 mt-0.5 font-bold">{team.domain || 'N/A'} • {team.branch}</div>
                                                            <div className="text-[10px] text-slate-400 mt-0.5">Mentor: {formatMentor(team.mentor)}</div>
                                                        </td>
                                                    </>
                                                )}
                                                <td className="py-4 pl-3">
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
            </motion.div>

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
                                                        <ExternalLink className="w-3 h-3 text-slate-400" />
                                                    </a>
                                                ) : q.type === 'file' ? (
                                                    <a 
                                                        href={safeLinkUrl(ans) || undefined} 
                                                        target="_blank" 
                                                        rel="noopener noreferrer" 
                                                        className="flex items-center gap-2 w-fit px-3 py-1.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-200"
                                                    >
                                                        <FileText className="w-3.5 h-3.5 text-indigo-500" />
                                                        <span>Open Uploaded File</span>
                                                        <ExternalLink className="w-3 h-3 text-slate-400" />
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
