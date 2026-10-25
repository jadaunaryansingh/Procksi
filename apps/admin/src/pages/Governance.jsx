import React, { useState, useEffect } from 'react';
import { Shield, Lock, Power, Calendar, Terminal, ShieldAlert, RefreshCw, UploadCloud, Plus, Pencil, Trash2, X, Check, Clock, Mail, Send, Download } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { apiFetchTable, getAuthHeaders } from '../lib/api';
import { getApiBaseUrl } from '../lib/apiBase';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { downloadGovernanceExcel } from '../lib/governanceExport';

const COLOR_OPTIONS = [
    { name: 'Indigo', value: 'indigo', bg: 'bg-indigo-500', ring: 'ring-indigo-500' },
    { name: 'Blue', value: 'blue', bg: 'bg-blue-500', ring: 'ring-blue-500' },
    { name: 'Amber', value: 'amber', bg: 'bg-amber-500', ring: 'ring-amber-500' },
    { name: 'Emerald', value: 'emerald', bg: 'bg-emerald-500', ring: 'ring-emerald-500' },
    { name: 'Rose', value: 'rose', bg: 'bg-rose-500', ring: 'ring-rose-500' },
    { name: 'Purple', value: 'purple', bg: 'bg-purple-500', ring: 'ring-purple-500' }
];

const PROTOCOL_OPTIONS = [
    {
        key: 'teamFormation',
        label: '👥 Team Formation',
        title: 'Team Formation',
        description: 'Last day to form or join a team.',
        color: 'indigo'
    },
    {
        key: 'proposalUpload',
        label: '📄 Proposal Submission',
        title: 'Proposal Submission',
        description: 'Last day to submit the project proposal.',
        color: 'blue'
    },
    {
        key: 'midTerm',
        label: '📊 Mid-Term Evaluation',
        title: 'Mid-Term Evaluation',
        description: 'Mid-term presentation and marking date.',
        color: 'amber'
    },
    {
        key: 'finalEvaluation',
        label: '🏆 Final Evaluation',
        title: 'Final Evaluation',
        description: 'Final presentation and result date.',
        color: 'emerald'
    },
    {
        key: 'problemStatementSelection',
        label: '📌 Problem Statement Selection',
        title: 'Problem Statement Selection',
        description: 'Freeze problem statement selection and topic reservation.',
        color: 'purple'
    },
    {
        key: 'extraActivities',
        label: '🎯 Extra Activities Submission',
        title: 'Extra Activities Submission',
        description: 'Lock extra activity applications and certificate uploads.',
        color: 'rose'
    },
    {
        key: 'githubRepoSubmission',
        label: '🐙 GitHub Repository Submission Vault',
        title: 'GitHub Repository Submission',
        description: 'Lock GitHub repository URL submission and automated commit sync.',
        color: 'purple'
    },
    {
        key: 'custom',
        label: '⚙️ Custom Protocol Deadline',
        title: '',
        description: '',
        color: 'indigo'
    }
];

export default function Governance() {
    const { data: auditLog, setData: setAuditLog } = useSupabaseTableState('governance_audit', [], { orderBy: 'id', ascending: false });
    const { semesterMap } = useGlobalFilters();
    const [refreshing, setRefreshing] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [sendingEmail, setSendingEmail] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [activeSemesterId, setActiveSemesterId] = useState(null);
    const [systemFrozen, setSystemFrozen] = useState(false);
    const [semestersList, setSemestersList] = useState([]);
    const [selectedBatchFilter, setSelectedBatchFilter] = useState('all');

    // Dynamic Deadlines state list: [{ id, type, title, description, due_date, color, semester_id }]
    const [deadlinesList, setDeadlinesList] = useState([]);

    const formatForDatetimeLocal = (dateStr) => {
        if (!dateStr) return '';
        try {
            let s = String(dateStr).trim();
            s = s.replace(' ', 'T');
            s = s.split('+')[0].replace('Z', '');
            if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
                return `${s}T00:00`;
            }
            if (s.includes('T')) {
                const [datePart, timePart] = s.split('T');
                if (datePart && timePart) {
                    const cleanTime = timePart.substring(0, 5);
                    if (/^\d{2}:\d{2}$/.test(cleanTime)) {
                        return `${datePart}T${cleanTime}`;
                    }
                }
            }
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return '';
            const pad = (num) => String(num).padStart(2, '0');
            const yyyy = date.getFullYear();
            const mm = pad(date.getMonth() + 1);
            const dd = pad(date.getDate());
            const hh = pad(date.getHours());
            const min = pad(date.getMinutes());
            return `${yyyy}-${mm}-${dd}T${hh}:${min}`;
        } catch {
            return '';
        }
    };

    const getBatchLabel = (semId) => {
        if (!semId || semId === 'all' || semId === 'global') return '🌐 All Batches (Global)';
        const sem = semestersList.find(s => String(s.id) === String(semId));
        if (!sem) return '🎓 Batch Scoped';
        const levelStr = sem.academic_level ? `${sem.academic_level}${sem.academic_level === 1 ? 'st' : sem.academic_level === 2 ? 'nd' : sem.academic_level === 3 ? 'rd' : 'th'} Year` : sem.year;
        return `🎓 ${sem.branch || 'BTech'} - ${levelStr} (${sem.semester_type?.toUpperCase() || ''} ${sem.year || ''})`;
    };

    const getStatusBadge = (startDate, dueDate) => {
        if (!startDate && !dueDate) return null;
        const now = new Date();

        let start = startDate ? new Date(startDate.replace(' ', 'T').split('+')[0].replace('Z', '')) : null;
        let due = dueDate ? new Date(dueDate.replace(' ', 'T').split('+')[0].replace('Z', '')) : null;

        if (start && isNaN(start.getTime())) start = null;
        if (due && isNaN(due.getTime())) due = null;

        if (start && now < start) {
            return (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-widest bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                    UPCOMING
                </span>
            );
        }
        if (due && now > due) {
            return (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-widest bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300">
                    CLOSED / LOCKED
                </span>
            );
        }
        return (
            <span className="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-widest bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                ACTIVE / OPEN
            </span>
        );
    };

    const handleSendDeadlineEmail = async () => {
        if (!window.confirm("Are you sure you want to send a mass email announcement of all active platform deadlines to all students and mentors?")) return;
        setSendingEmail(true);
        try {
            await api.sendDeadlineEmail();
            AuditLogger.log(
                getCurrentUser(),
                'Dispatched manual mass email announcement of platform deadlines',
                'high'
            );
            refreshAuditLogs();
            alert("Mass deadline announcement emails sent successfully!");
        } catch (e) {
            console.error('Failed to send mass deadline email:', e);
            alert("Failed to send mass deadline emails: " + (e.message || e));
        } finally {
            setSendingEmail(false);
        }
    };

    const handleExportExcel = async () => {
        setExporting(true);
        try {
            const apiBase = getApiBaseUrl();
            const [teamsRes, proposalsRes, psRes, github] = await Promise.all([
                apiFetchTable('teams_validation', { semesterOverride: 'all' }).catch(() => []),
                apiFetchTable('proposals').catch(() => []),
                apiFetchTable('problem_statements').catch(() => []),
                fetch(`${apiBase}/api/data/github_data?select=team_uid,team_ref,team_id,repository_url,analysis_status`, { headers: getAuthHeaders() })
                    .then(r => r.json())
                    .then(j => j.data || [])
                    .catch(() => []),
            ]);

            const teams = Array.isArray(teamsRes) ? teamsRes : (teamsRes.data || []);
            const proposals = Array.isArray(proposalsRes) ? proposalsRes : (proposalsRes.data || []);
            const problemStatements = Array.isArray(psRes) ? psRes : (psRes.data || []);

            if (teams.length === 0) {
                alert('No teams found to export.');
                return;
            }

            const { totalRows, sheetCount, stats } = downloadGovernanceExcel({
                teams, proposals, github, problemStatements, semesterMap,
            });
            AuditLogger.log(
                getCurrentUser(),
                `Exported governance master workbook — ${totalRows} teams / ${sheetCount} batch sheet(s) / ${stats.reposMatched} repos / ${stats.proposalsMatched} proposals`,
                'low'
            );
            refreshAuditLogs();

            if (stats.githubFetched === 0) {
                alert('Workbook downloaded, but the GitHub repository data could not be loaded (github_data returned 0 rows). Repository URL columns will be empty.');
            } else if (stats.reposMatched === 0) {
                alert(`Workbook downloaded. ${stats.githubFetched} GitHub records were loaded but none matched a team by uid/ref — Repository URL columns are empty. Check the console log tagged [governanceExport].`);
            }
        } catch (e) {
            console.error('Failed to export governance Excel:', e);
            alert('Failed to export Excel: ' + (e.message || e));
        } finally {
            setExporting(false);
        }
    };

    // Modal state for Add/Edit
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingItem, setEditingItem] = useState(null); // null when adding
    const [formData, setFormData] = useState({
        protocolKey: 'teamFormation',
        title: 'Team Formation',
        description: 'Last day to form or join a team.',
        start_date: '',
        due_date: new Date().toISOString().substring(0, 16),
        color: 'indigo',
        semester_id: 'all'
    });

    useEffect(() => {
        const loadInitialData = async () => {
            try {
                const sems = await apiFetchTable('semester_config').catch(() => []);
                setSemestersList(sems || []);

                const semRes = await api.getActiveSemester();
                if (semRes.success !== false && semRes.data) {
                    setSystemFrozen(semRes.data.is_locked);
                    setActiveSemesterId(semRes.data.id);
                }
                const deadlinesRes = await api.getDeadlines('all');
                if (deadlinesRes && deadlinesRes.data && Array.isArray(deadlinesRes.data)) {
                    setDeadlinesList(deadlinesRes.data);
                }
            } catch (err) {
                console.error('Failed to load governance init data', err);
            }
        };
        loadInitialData();
    }, []);

    const handleFreezeToggle = async () => {
        const newStatus = !systemFrozen;
        setSystemFrozen(newStatus);
        try {
            if (activeSemesterId) {
                await api.lockSemester(activeSemesterId, newStatus);
                AuditLogger.log(
                    getCurrentUser(),
                    newStatus ? 'Activated System Freeze Protocol' : 'Deactivated System Freeze Protocol',
                    newStatus ? 'high' : 'medium'
                );
                refreshAuditLogs();
            }
        } catch (e) {
            console.error('Failed to toggle freeze:', e);
            setSystemFrozen(!newStatus);
        }
    };

    const handleDateChangeDirect = async (id, newDate) => {
        const updated = deadlinesList.map(item => (item.id === id || item.type === id || item.db_id === id) ? { ...item, due_date: newDate } : item);
        setDeadlinesList(updated);
        try {
            await api.updateDeadlines(updated);
        } catch (e) {
            console.error('Failed to update due date in DB:', e);
        }
    };

    const handleStartDateChangeDirect = async (id, newDate) => {
        const updated = deadlinesList.map(item => (item.id === id || item.type === id || item.db_id === id) ? { ...item, start_date: newDate } : item);
        setDeadlinesList(updated);
        try {
            await api.updateDeadlines(updated);
        } catch (e) {
            console.error('Failed to update start date in DB:', e);
        }
    };

    const handleOpenAddModal = () => {
        setEditingItem(null);
        setFormData({
            protocolKey: 'teamFormation',
            title: 'Team Formation',
            description: 'Last day to form or join a team.',
            start_date: '',
            due_date: new Date().toISOString().split('T')[0] + 'T23:59',
            color: 'indigo',
            semester_id: selectedBatchFilter === 'all' ? 'all' : selectedBatchFilter
        });
        setIsModalOpen(true);
    };

    const handleOpenEditModal = (item) => {
        setEditingItem(item);
        const matchedProto = PROTOCOL_OPTIONS.find(p => p.key === item.type);
        setFormData({
            protocolKey: matchedProto ? matchedProto.key : 'custom',
            title: item.title || item.name || '',
            description: item.description || '',
            start_date: item.start_date || '',
            due_date: item.due_date || item.deadline_date || '',
            color: item.color || (matchedProto ? matchedProto.color : 'indigo'),
            semester_id: item.semester_id || 'all'
        });
        setIsModalOpen(true);
    };

    const handleProtocolSelect = (selectedKey) => {
        const matched = PROTOCOL_OPTIONS.find(p => p.key === selectedKey);
        if (matched) {
            if (selectedKey === 'custom') {
                setFormData(prev => ({
                    ...prev,
                    protocolKey: 'custom',
                    title: prev.title || '',
                    description: prev.description || ''
                }));
            } else {
                setFormData(prev => ({
                    ...prev,
                    protocolKey: matched.key,
                    title: matched.title,
                    description: matched.description,
                    color: matched.color
                }));
            }
        }
    };

    const handleSaveModalItem = async () => {
        if (!formData.title.trim()) {
            alert("Please enter a deadline title.");
            return;
        }
        if (!formData.due_date) {
            alert("Please select a due date.");
            return;
        }

        const finalType = (formData.protocolKey && formData.protocolKey !== 'custom') 
            ? formData.protocolKey 
            : (editingItem ? editingItem.type : `custom_${Date.now()}`);

        const targetSemId = (!formData.semester_id || formData.semester_id === 'all') ? null : formData.semester_id;

        let updatedList = [];
        if (editingItem) {
            // Edit existing item
            updatedList = deadlinesList.map(item => {
                if (item.id === editingItem.id || item.type === editingItem.id || (editingItem.db_id && item.db_id === editingItem.db_id)) {
                    return {
                        ...item,
                        type: finalType,
                        title: formData.title.trim(),
                        description: formData.description.trim(),
                        start_date: formData.start_date,
                        due_date: formData.due_date,
                        color: formData.color,
                        semester_id: targetSemId
                    };
                }
                return item;
            });
        } else {
            // Add new item
            const newItem = {
                id: finalType,
                type: finalType,
                title: formData.title.trim(),
                description: formData.description.trim(),
                start_date: formData.start_date,
                due_date: formData.due_date,
                color: formData.color,
                semester_id: targetSemId
            };
            updatedList = [...deadlinesList, newItem];
        }

        setDeadlinesList(updatedList);
        setIsModalOpen(false);

        // Instantly save to database so the deadline persists on refresh
        try {
            await api.updateDeadlines(updatedList);
            const freshRes = await api.getDeadlines('all');
            if (freshRes && freshRes.data && Array.isArray(freshRes.data)) {
                setDeadlinesList(freshRes.data);
            }
        } catch (err) {
            console.error('Failed to save deadline to database:', err);
            alert('Failed to save deadline: ' + (err.message || err));
        }
    };

    const handleDeleteDeadline = async (item) => {
        const title = item.title || item.type;
        if (!window.confirm(`Are you sure you want to delete deadline "${title}"?`)) return;

        setDeadlinesList(prev => prev.filter(d => d.id !== item.id && d.type !== item.id));

        try {
            await api.deleteDeadline(item.db_id || item.id);
            AuditLogger.log(
                getCurrentUser(),
                `Deleted platform deadline "${title}"`,
                'medium'
            );
            refreshAuditLogs();
        } catch (e) {
            console.error('Failed to delete deadline from DB:', e);
        }
    };

    const handlePublishDeadlines = async () => {
        setPublishing(true);
        try {
            await api.updateDeadlines(deadlinesList);
            const freshRes = await api.getDeadlines('all');
            if (freshRes && freshRes.data && Array.isArray(freshRes.data)) {
                setDeadlinesList(freshRes.data);
            }
            AuditLogger.log(
                getCurrentUser(),
                'Published updated platform deadlines',
                'high'
            );
            refreshAuditLogs();
            alert("Deadlines published successfully!");
        } catch (e) {
            console.error('Failed to publish deadlines:', e);
            alert("Failed to publish deadlines. Please try again.");
        } finally {
            setPublishing(false);
        }
    };

    const refreshAuditLogs = async () => {
        setRefreshing(true);
        try {
            const logs = await apiFetchTable('governance_audit', { orderBy: 'id', ascending: false });
            setAuditLog(logs);
        } catch (error) {
            console.error('Failed to refresh audit logs:', error);
        } finally {
            setRefreshing(false);
        }
    };

    useEffect(() => {
        const interval = setInterval(() => {
            refreshAuditLogs();
        }, 30000);

        return () => clearInterval(interval);
    }, []);

    const getColorDotClass = (color) => {
        switch (color) {
            case 'blue': return 'bg-blue-500';
            case 'amber': return 'bg-amber-500';
            case 'emerald': return 'bg-emerald-500';
            case 'rose': return 'bg-rose-500';
            case 'purple': return 'bg-purple-500';
            default: return 'bg-indigo-500';
        }
    };

    const filteredDeadlines = deadlinesList.filter(item => {
        if (selectedBatchFilter === 'all') return true;
        return !item.semester_id || String(item.semester_id) === String(selectedBatchFilter);
    });

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header / Emergency Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} 
                className={`flex flex-col sm:flex-row justify-between items-start sm:items-center p-6 xl:p-8 rounded-3xl shadow-xl relative overflow-hidden transition-all duration-700 border ${systemFrozen ? 'bg-gradient-to-r from-red-600 via-rose-700 to-red-900 border-red-500/50 shadow-red-500/30' : 'bg-gradient-to-r from-slate-800 to-slate-900 border-slate-700 shadow-slate-900/40'}`}>
                
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,300 C300,0 700,300 1000,0 L1000,300 Z" fill="currentColor"></path>
                    </svg>
                </div>

                <div className="flex items-center space-x-6 relative z-10 mb-6 sm:mb-0">
                    <motion.div 
                        animate={systemFrozen ? { scale: [1, 1.2, 1], rotate: [0, 5, -5, 0] } : {}} 
                        transition={systemFrozen ? { repeat: Infinity, duration: 2 } : {}}
                        className={`p-4 rounded-2xl shadow-inner ${systemFrozen ? 'bg-red-500/20 text-red-100' : 'bg-white/10 text-slate-300'}`}>
                        {systemFrozen ? <ShieldAlert className="w-8 h-8" /> : <Shield className="w-8 h-8" />}
                    </motion.div>
                    <div>
                        <div className="flex items-center space-x-3 mb-1">
                            <h1 className="text-3xl font-black text-white tracking-tight">System Control</h1>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest ${systemFrozen ? 'bg-white text-red-600 animate-pulse' : 'bg-emerald-500 text-emerald-950'}`}>
                                {systemFrozen ? 'STATUS: READ-ONLY' : 'STATUS: ONLINE'}
                            </span>
                        </div>
                        <p className={`text-sm font-medium ${systemFrozen ? 'text-red-200' : 'text-slate-400'}`}>
                            {systemFrozen ? 'Catastrophic override active. All database mutations strictly prohibited.' : 'Manage global system deadlines and catastrophic state overrides.'}
                        </p>
                    </div>
                </div>
                
                <div className="relative z-10 flex flex-col sm:flex-row items-stretch gap-3 w-full sm:w-auto">
                    <button
                        onClick={handleExportExcel}
                        disabled={exporting}
                        title="Download an Excel workbook with one sheet per batch/year — team no, members, mentors, project statement, repository URL and proposal details"
                        className="flex items-center justify-center px-6 py-4 w-full sm:w-auto rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-xl active:scale-95 bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
                    >
                        <Download className={`w-5 h-5 mr-3 ${exporting ? 'animate-pulse' : ''}`} />
                        {exporting ? 'Exporting...' : 'Export Master Excel'}
                    </button>

                    <button onClick={handleFreezeToggle} className={`relative flex items-center justify-center px-8 py-4 w-full sm:w-auto rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-xl active:scale-95 group overflow-hidden ${systemFrozen ? 'bg-white text-red-600 hover:bg-red-50' : 'bg-rose-600 text-white hover:bg-red-700'}`}>
                        <div className="absolute inset-0 w-1/4 h-full bg-white/20 -skew-x-12 -translate-x-full group-hover:translate-x-[400%] transition-transform duration-700 ease-in-out"></div>
                        <Power className={`w-5 h-5 mr-3 ${systemFrozen ? 'animate-pulse' : ''}`} />
                        {systemFrozen ? 'DEACTIVATE PROTOCOL' : 'FREEZE SYSTEM EXECUTIONS'}
                    </button>
                </div>
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 xl:gap-8 relative">
                
                <AnimatePresence>
                    {systemFrozen && (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-red-950/20 backdrop-blur-[2px] z-20 rounded-3xl pointer-events-auto flex items-center justify-center border-2 border-red-500/30">
                            <div className="bg-red-900/90 text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center space-x-3 border border-red-500/50">
                                <Lock className="w-6 h-6 text-red-200 animate-bounce" />
                                <div>
                                    <h4 className="font-bold text-sm">SYSTEM EXECUTIONS FROZEN</h4>
                                    <p className="text-xs text-red-200">Deactivate system freeze protocol to modify platform deadlines.</p>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Deadlines Management Card */}
                <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1 }} className={`bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 xl:p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col transition-opacity duration-300 ${systemFrozen ? 'opacity-50 grayscale-[30%]' : ''}`}>
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 dark:border-slate-700/50 pb-6 mb-4 gap-4">
                        <div className="flex items-center">
                            <div className="w-10 h-10 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500 rounded-xl flex items-center justify-center mr-4 shadow-inner">
                                <Calendar className="w-5 h-5" />
                            </div>
                            <div>
                                <h2 className="text-xl font-black text-slate-800 dark:text-white">Platform Deadlines</h2>
                                <p className="text-xs text-slate-400 font-semibold mt-0.5">Manage, add, and configure batch-scoped milestone target dates</p>
                            </div>
                        </div>

                        <button
                            onClick={handleOpenAddModal}
                            disabled={systemFrozen}
                            className="flex items-center justify-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow-md transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                        >
                            <Plus className="w-4 h-4" />
                            <span>Add Deadline</span>
                        </button>
                    </div>

                    {/* Batch / Semester Filter Selector */}
                    <div className="flex items-center gap-2 overflow-x-auto pb-3 mb-4 custom-scrollbar">
                        <span className="text-[11px] font-black uppercase text-slate-400 shrink-0 mr-1">Filter Batch:</span>
                        <button
                            onClick={() => setSelectedBatchFilter('all')}
                            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 cursor-pointer ${
                                selectedBatchFilter === 'all'
                                    ? 'bg-indigo-600 text-white shadow-sm'
                                    : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300 hover:bg-slate-200'
                            }`}
                        >
                            🌐 All Batches ({deadlinesList.length})
                        </button>
                        {semestersList.map(s => {
                            const count = deadlinesList.filter(d => String(d.semester_id) === String(s.id)).length;
                            const label = `${s.branch || 'BTech'} - ${s.academic_level ? `${s.academic_level}rd Yr` : s.year}`;
                            return (
                                <button
                                    key={s.id}
                                    onClick={() => setSelectedBatchFilter(s.id)}
                                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 cursor-pointer ${
                                        selectedBatchFilter === s.id
                                            ? 'bg-indigo-600 text-white shadow-sm'
                                            : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300 hover:bg-slate-200'
                                    }`}
                                >
                                    🎓 {label} ({count})
                                </button>
                            );
                        })}
                    </div>
                    
                    <div className="space-y-4 flex-1 max-h-[480px] overflow-y-auto pr-1 custom-scrollbar">
                        {filteredDeadlines.length === 0 ? (
                            <div className="p-8 text-center border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-2xl">
                                <Calendar className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                                <p className="text-sm font-bold text-slate-500 dark:text-slate-400">No deadlines configured for this batch filter</p>
                                <button onClick={handleOpenAddModal} className="mt-3 text-xs font-black text-indigo-600 dark:text-indigo-400 hover:underline">
                                    + Add a deadline for this batch
                                </button>
                            </div>
                        ) : (
                            filteredDeadlines.map((item) => (
                                <div key={item.id || item.type} className="p-5 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 shadow-sm hover:shadow-md transition-all space-y-3 group">
                                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/50 dark:border-slate-700/50 pb-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <div className={`w-3 h-3 rounded-full ${getColorDotClass(item.color)} shrink-0 shadow-sm`}></div>
                                            <h3 className="font-black text-slate-800 dark:text-slate-100 text-sm tracking-tight">{item.title || item.name || item.type}</h3>
                                            {getStatusBadge(item.start_date, item.due_date || item.deadline_date)}
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wider ${
                                                !item.semester_id || item.semester_id === 'all'
                                                    ? 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
                                                    : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800'
                                            }`}>
                                                {getBatchLabel(item.semester_id)}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => handleOpenEditModal(item)}
                                                disabled={systemFrozen}
                                                title="Edit deadline name, description & settings"
                                                className="p-1.5 rounded-xl text-slate-400 hover:text-indigo-600 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                                            >
                                                <Pencil className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleDeleteDeadline(item)}
                                                disabled={systemFrozen}
                                                title="Delete deadline"
                                                className="p-1.5 rounded-xl text-slate-400 hover:text-rose-600 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>

                                    {item.description && (
                                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 leading-relaxed">{item.description}</p>
                                    )}

                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1 flex items-center gap-1">
                                                <Clock className="w-3 h-3 text-emerald-500" /> Start / Allowed From
                                            </span>
                                            <input
                                                type="datetime-local"
                                                value={formatForDatetimeLocal(item.start_date || '')}
                                                onChange={e => handleStartDateChangeDirect(item.id || item.type, e.target.value)} 
                                                disabled={systemFrozen}
                                                placeholder="Opening date & time"
                                                className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl text-xs font-black text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm cursor-pointer disabled:cursor-not-allowed"
                                            />
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400 mb-1 flex items-center gap-1">
                                                <Calendar className="w-3 h-3 text-indigo-500" /> Due / Closing Date
                                            </span>
                                            <input
                                                type="datetime-local"
                                                value={formatForDatetimeLocal(item.due_date || item.deadline_date || '')}
                                                onChange={e => handleDateChangeDirect(item.id || item.type, e.target.value)} 
                                                disabled={systemFrozen}
                                                className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl text-xs font-black text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm cursor-pointer disabled:cursor-not-allowed"
                                            />
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                    
                    <div className="mt-6 border-t border-slate-100 dark:border-slate-700/50 pt-6 flex flex-wrap items-center justify-end gap-3">
                        <button
                            onClick={handleSendDeadlineEmail}
                            disabled={sendingEmail || systemFrozen || deadlinesList.length === 0}
                            title="Broadcast current platform deadlines schedule to all students and faculty mentors via email"
                            className={`flex items-center justify-center px-5 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-md active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
                                sendingEmail ? 'bg-purple-400 text-white' : 'bg-purple-600 text-white hover:bg-purple-700'
                            }`}
                        >
                            <Mail className="w-4 h-4 mr-2" />
                            {sendingEmail ? 'Sending Mass Email...' : 'Mass Email Deadline'}
                        </button>

                        <button
                            onClick={handlePublishDeadlines}
                            disabled={publishing || systemFrozen}
                            className={`flex items-center justify-center px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all shadow-md active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${
                                publishing ? 'bg-indigo-400 text-white' : 'bg-indigo-600 text-white hover:bg-indigo-700'
                            }`}
                        >
                            <UploadCloud className="w-4 h-4 mr-2" />
                            {publishing ? 'Publishing...' : 'Publish Deadlines'}
                        </button>
                    </div>

                </motion.div>

                {/* Audit Logs */}
                <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.2 }} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 xl:p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col h-full z-10">
                    <div className="flex justify-between items-center border-b border-slate-100 dark:border-slate-700/50 pb-6 mb-6">
                        <div className="flex items-center">
                            <div className="w-10 h-10 bg-slate-900 dark:bg-black text-emerald-400 rounded-xl flex items-center justify-center mr-4 shadow-inner ring-2 ring-slate-800 dark:ring-slate-700">
                                <Terminal className="w-5 h-5" />
                            </div>
                            <h2 className="text-xl font-black text-slate-800 dark:text-white">Audit Sequence Log</h2>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="text-[10px] font-black uppercase tracking-widest bg-slate-100 text-slate-500 dark:bg-slate-700/50 dark:text-slate-400 px-3 py-1.5 rounded-lg shadow-inner">T-MINUS 7D</span>
                            <button 
                                onClick={refreshAuditLogs}
                                disabled={refreshing}
                                className="text-xs font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 transition-colors inline-flex items-center disabled:opacity-50"
                            >
                                <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
                                {refreshing ? 'Refreshing...' : 'Refresh'}
                            </button>
                        </div>
                    </div>
                    
                    <div className="overflow-y-auto flex-1 h-[350px] pr-3 custom-scrollbar relative">
                        <div className="absolute left-4 top-0 bottom-0 w-px bg-slate-100 dark:bg-slate-700/50 z-0"></div>
                        
                        <div className="space-y-5 relative z-10">
                            {auditLog.length > 0 ? (
                                auditLog.map((log, idx) => (
                                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 * idx }} key={log.id} className="relative pl-10">
                                        <div className={`absolute left-[-5px] top-1.5 w-3 h-3 rounded-full border-2 border-white dark:border-slate-800 ${log.severity === 'high' ? 'bg-red-500' : log.severity === 'medium' ? 'bg-amber-500' : 'bg-indigo-500'}`}></div>
                                        
                                        <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700/50 shadow-sm hover:shadow-md transition-shadow group">
                                            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start mb-2 gap-2">
                                                <span className="text-xs font-black text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-2 py-1 rounded inline-flex items-center w-fit shadow-sm">
                                                    <span className="text-indigo-500 mr-1">@</span>{log.user}
                                                </span>
                                                <span className="text-[10px] font-mono text-slate-400 flex items-center">
                                                    <Clock className="w-3 h-3 mr-1" />
                                                    {log.timestamp}
                                                </span>
                                            </div>
                                            
                                            <p className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                                                {log.action}
                                            </p>
                                        </div>
                                    </motion.div>
                                ))
                            ) : (
                                <div className="text-center py-12 text-slate-400 font-medium text-xs">
                                    No audit sequence records found in history.
                                </div>
                            )}
                        </div>
                    </div>
                </motion.div>
            </div>

            {/* ADD / EDIT DEADLINE MODAL */}
            <AnimatePresence>
                {isModalOpen && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 10 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 10 }}
                            className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-3xl shadow-2xl max-w-md w-full p-6 sm:p-8 space-y-5"
                        >
                            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-700/60 pb-4">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-black">
                                        <Calendar className="w-5 h-5" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-black text-slate-800 dark:text-white">
                                            {editingItem ? 'Edit Platform Deadline' : 'Add New Platform Deadline'}
                                        </h3>
                                        <p className="text-xs text-slate-400 font-semibold">
                                            {editingItem ? 'Modify deadline protocol, batch scope, name & dates' : 'Select a protocol and set target deadline for a batch'}
                                        </p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setIsModalOpen(false)}
                                    className="p-1.5 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                        Target Academic Batch / Semester *
                                    </label>
                                    <select
                                        value={formData.semester_id || 'all'}
                                        onChange={e => setFormData({ ...formData, semester_id: e.target.value })}
                                        className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all cursor-pointer"
                                    >
                                        <option value="all">🌐 All Batches (Global - Applies Platform-Wide)</option>
                                        {semestersList.map(s => (
                                            <option key={s.id} value={s.id}>
                                                🎓 {s.branch || 'BTech'} - {s.academic_level ? `${s.academic_level}rd Year` : s.year} ({s.semester_type?.toUpperCase() || ''} {s.year})
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                        Deadline Protocol / Feature Action *
                                    </label>
                                    <select
                                        value={formData.protocolKey}
                                        onChange={e => handleProtocolSelect(e.target.value)}
                                        className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all cursor-pointer"
                                    >
                                        {PROTOCOL_OPTIONS.map(proto => (
                                            <option key={proto.key} value={proto.key}>
                                                {proto.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                        Deadline Title / Name *
                                    </label>
                                    <input
                                        type="text"
                                        placeholder="e.g. Team Formation"
                                        value={formData.title}
                                        onChange={e => setFormData({ ...formData, title: e.target.value })}
                                        className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all"
                                    />
                                </div>

                                <div>
                                    <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                        Description
                                    </label>
                                    <textarea
                                        rows={2}
                                        placeholder="Brief summary of what locks or unlocks on this date..."
                                        value={formData.description}
                                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all resize-none"
                                    />
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                            Start Date & Time (Opening)
                                        </label>
                                        <input
                                            type="datetime-local"
                                            value={formatForDatetimeLocal(formData.start_date)}
                                            onChange={e => setFormData({ ...formData, start_date: e.target.value })}
                                            className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all cursor-pointer"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                                            Due Date & Time (Closing / Lock) *
                                        </label>
                                        <input
                                            type="datetime-local"
                                            value={formatForDatetimeLocal(formData.due_date)}
                                            onChange={e => setFormData({ ...formData, due_date: e.target.value })}
                                            className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-800 dark:text-white focus:ring-2 focus:ring-indigo-500 outline-none transition-all cursor-pointer"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-xs font-black uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
                                        Badge Color Accent
                                    </label>
                                    <div className="flex items-center gap-3">
                                        {COLOR_OPTIONS.map(c => (
                                            <button
                                                key={c.value}
                                                type="button"
                                                onClick={() => setFormData({ ...formData, color: c.value })}
                                                className={`w-7 h-7 rounded-full ${c.bg} flex items-center justify-center transition-all cursor-pointer ${
                                                    formData.color === c.value ? `ring-4 ${c.ring} ring-offset-2 dark:ring-offset-slate-800 scale-110` : 'hover:scale-105'
                                                }`}
                                                title={c.name}
                                            >
                                                {formData.color === c.value && <Check className="w-4 h-4 text-white" />}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center justify-end gap-3 border-t border-slate-100 dark:border-slate-700/60 pt-4">
                                <button
                                    type="button"
                                    onClick={() => setIsModalOpen(false)}
                                    className="px-5 py-2.5 rounded-xl font-bold text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors cursor-pointer"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={handleSaveModalItem}
                                    className="px-6 py-2.5 rounded-xl font-black text-xs uppercase tracking-wider bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-500/25 transition-all active:scale-95 cursor-pointer"
                                >
                                    {editingItem ? 'Save Changes' : 'Create Deadline'}
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
