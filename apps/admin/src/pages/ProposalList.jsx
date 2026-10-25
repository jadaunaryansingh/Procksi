import React, { useState, useEffect } from 'react';
import { Eye, CheckCircle, XCircle, RotateCcw, Search, Filter, FileText, CheckCircle2, Trash2, MoreVertical } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { api } from '../services/api';
import { apiDeleteRows, apiFetchTable } from '../lib/api';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamLabel, findMatchingTeam } from '../lib/teamUtils';

export default function ProposalList() {
    const navigate = useNavigate();
    const { semesterMap, filterRows } = useGlobalFilters();
    const { data: teams } = useSupabaseTableState('teams_validation', []);
    const [allTeams, setAllTeams] = useState([]);
    const [proposals, setProposals] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('All');
    const [activeMenuId, setActiveMenuId] = useState(null);

    // Custom Reason Modal States
    const [showReasonModal, setShowReasonModal] = useState(false);
    const [selectedProposalId, setSelectedProposalId] = useState(null);
    const [modalAction, setModalAction] = useState(null); // 'Reject' or 'Revision'
    const [feedbackReason, setFeedbackReason] = useState('');

    useEffect(() => {
        let isMounted = true;
        apiFetchTable('teams_validation', { semesterOverride: 'all' })
            .then(res => { if (isMounted) setAllTeams(Array.isArray(res) ? res : res.data || []); })
            .catch(err => console.error("Could not load all teams for proposals", err));

        api.getProposals()
            .then(res => {
                if (isMounted) {
                    // Extract data from paginated response format
                    const proposalsData = Array.isArray(res) ? res : res.data || [];
                    const mapped = proposalsData.map(p => {
                        let mappedStatus = 'Pending';
                        if (p.status === 'approved') mappedStatus = 'Approved';
                        else if (p.status === 'rejected') mappedStatus = 'Rejected';
                        else if (p.status === 'revision') mappedStatus = 'Revision Requested';
                        else if (p.status) mappedStatus = p.status.charAt(0).toUpperCase() + p.status.slice(1);

                        return {
                            id: p.id,
                            teamId: p.team_id || p.teamId || 'N/A',
                            title: p.title || 'Untitled',
                            aiScore: p.ai_score !== undefined ? p.ai_score : (p.aiScore || 0),
                            aiRationale: p.ai_rationale || p.aiRationale || 'AI evaluation complete.',
                            status: mappedStatus,
                            submittedDate: p.submitted_at ? new Date(p.submitted_at).toLocaleDateString() : (p.submittedDate || 'N/A'),
                            proposalFile: p.proposalFile || p.proposal_file || p.document_url || null
                        };
                    });
                    setProposals(mapped);
                }
            })
            .catch(err => console.error("Could not load proposals", err));
        return () => { isMounted = false; };
    }, []);

    const handleAction = async (id, action) => {
        if (action === 'Approve') {
            if (window.confirm('Are you sure you want to approve this proposal?')) {
                try {
                    await api.approveProposal({ proposal_id: id });
                    setProposals(prev => prev.map(p => {
                        if (p.id === id) return { ...p, status: 'Approved' };
                        return p;
                    }));
                } catch (error) {
                    console.error("Failed to approve proposal:", error);
                    alert("Failed to approve proposal: " + error.message);
                }
            }
        } else {
            // Reject or Revision Requested: open feedback reason modal
            setSelectedProposalId(id);
            setModalAction(action);
            setFeedbackReason('');
            setShowReasonModal(true);
        }
    };

    const handleConfirmActionWithReason = async () => {
        if (!feedbackReason.trim()) {
            alert('Please enter a reason.');
            return;
        }
        try {
            if (modalAction === 'Reject') {
                await api.rejectProposal({ proposal_id: selectedProposalId, feedback: feedbackReason.trim() });
            } else if (modalAction === 'Revision') {
                await api.revisionProposal({ proposal_id: selectedProposalId, feedback: feedbackReason.trim() });
            }
            
            setProposals(prev => prev.map(p => {
                if (p.id === selectedProposalId) {
                    if (modalAction === 'Reject') return { ...p, status: 'Rejected' };
                    if (modalAction === 'Revision') return { ...p, status: 'Revision Requested' };
                }
                return p;
            }));
            setShowReasonModal(false);
        } catch (error) {
            console.error(`Failed to ${modalAction} proposal:`, error);
            alert(`Failed to ${modalAction} proposal: ${error.message}`);
        }
    };

    const handleDelete = async (proposalId) => {
        if (!window.confirm("Are you sure you want to delete this proposal? This action is irreversible.")) return;
        try {
            await apiDeleteRows('proposals', { id: `eq.${proposalId}` });
            setProposals(prev => prev.filter(p => p.id !== proposalId));
        } catch (error) {
            console.error("Failed to delete proposal:", error);
            alert("Failed to delete proposal: " + error.message);
        }
    };

    const findTeamForProp = (p) => {
        const teamPool = allTeams.length > 0 ? allTeams : teams;
        return findMatchingTeam(p, teamPool, semesterMap);
    };

    const isCustomProposal = (p) => {
        // 1. If proposal has an uploaded proposal file, it is definitely a student-submitted proposal
        const hasFile = Boolean(p.proposalFile || p.proposal_file || p.document_url);
        if (hasFile) return true;

        // 2. Check associated team in teams_validation
        const teamObj = findTeamForProp(p);
        if (teamObj) {
            const psId = teamObj.problem_statement_id;
            // If team has an allocated catalog problem statement (e.g. PS-SW-01), it is NOT a custom proposal
            if (psId && String(psId).trim() !== '' && String(psId).toLowerCase() !== 'null') {
                return false;
            }
            return true;
        }

        // 3. Ignore auto-generated administrative placeholder rows if team object isn't found
        if (String(p.id).startsWith('PROP-ADM-')) return false;

        return true;
    };

    const filtered = filterRows(proposals.map(p => {
        const teamObj = findTeamForProp(p);
        return {
            ...p,
            semester_id: p.semester_id || teamObj?.semester_id || ''
        };
    }))
    .filter(isCustomProposal)
    .filter(p => {
        const teamObj = findTeamForProp(p);
        const formattedTeamLabel = teamLabel(p.teamId || p.team_id, teamObj, semesterMap);
        const matchesSearch = p.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                              formattedTeamLabel.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = statusFilter === 'All' || p.status === statusFilter;
        return matchesSearch && matchesStatus;
    });


    const getStatusStyle = (status) => {
        switch (status) {
            case 'Approved': return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30';
            case 'Rejected': return 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400 border-red-200 dark:border-red-500/30';
            case 'Revision Requested': return 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border-amber-200 dark:border-amber-500/30';
            default: return 'bg-slate-100 text-slate-700 dark:bg-slate-700/50 dark:text-slate-300 border-slate-200 dark:border-slate-600/50';
        }
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} 
                className="bg-gradient-to-br from-blue-600 via-sky-700 to-indigo-800 rounded-3xl p-8 text-white shadow-xl shadow-blue-500/20 relative overflow-hidden flex items-center justify-between border border-blue-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,150 C300,50 600,250 1000,100 L1000,300 L0,300 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 lg:w-2/3 flex-1">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20 shadow-sm">
                        <FileText className="w-4 h-4 mr-2" /> Evaluation Hub
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3 tracking-tight">Project Proposals</h1>
                    <p className="text-blue-100/90 leading-relaxed text-sm md:text-base max-w-lg font-medium">Review submitted project abstracts from constituent teams. Utilize the AI semantic scoring heuristics to efficiently grade and sanitize incoming proposals.</p>
                </div>
                <div className="hidden lg:block relative z-10 ml-8 opacity-90 drop-shadow-2xl">
                    <svg viewBox="0 0 150 150" fill="none" className="w-48 h-48 text-blue-100 animate-pulse-slow">
                        <circle cx="75" cy="75" r="50" stroke="currentColor" strokeWidth="8" strokeDasharray="15 15"/>
                        <path d="M50 75 L65 90 L100 55" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-4 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col sm:flex-row gap-4 shadow-sm">
                <div className="relative flex-1 group">
                    <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                    <input type="text" placeholder="Search proposals by team ID or title..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-11 pr-5 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium focus:ring-2 focus:ring-blue-500 dark:text-white outline-none transition-shadow focus:shadow-md" />
                </div>
                <div className="relative shrink-0">
                    <Filter className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="appearance-none w-full sm:w-auto pl-11 pr-10 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-xl text-sm font-bold hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors shadow-sm outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
                    >
                        <option value="All">All Statuses</option>
                        <option value="Pending">Pending</option>
                        <option value="Approved">Approved</option>
                        <option value="Rejected">Rejected</option>
                        <option value="Revision Requested">Revision Requested</option>
                    </select>
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                    </div>
                </div>
            </motion.div>

            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse table-fixed min-w-[1050px]">
                        <colgroup>
                            <col className="w-[5%]" />
                            <col className="w-[17%]" />
                            <col className="w-[24%]" />
                            <col className="w-[23%]" />
                            <col className="w-[11%]" />
                            <col className="w-[10%]" />
                            <col className="w-[10%]" />
                        </colgroup>
                        <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 backdrop-blur-md">
                            <tr>
                                <th className="py-4 pl-6 pr-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">S. No.</th>
                                <th className="py-4 px-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Team ID</th>
                                <th className="py-4 px-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Project Title</th>
                                <th className="py-4 px-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">AI Feasibility Analysis</th>
                                <th className="py-4 px-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Pipeline Status</th>
                                <th className="py-4 px-3 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Timestamp</th>
                                <th className="py-4 pl-3 pr-6 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest text-right">Directives</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {filtered.map((p, index) => {
                                const matchedTeamObj = findTeamForProp(p);
                                const displayTeamLabel = teamLabel(p.teamId || p.team_id, matchedTeamObj, semesterMap);
                                return (
                                <tr key={p.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-700/30 transition-colors group">
                                    <td className="py-4 pl-6 pr-3 text-sm font-bold text-slate-500 dark:text-slate-400">{index + 1}</td>
                                    <td className="py-4 px-3 whitespace-nowrap">
                                        <span title={displayTeamLabel} className="inline-flex items-center max-w-full whitespace-nowrap truncate text-xs font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1.5 rounded-lg border border-indigo-100 dark:border-indigo-500/20 shadow-sm cursor-pointer hover:bg-indigo-100 dark:hover:bg-indigo-500/20 transition-colors">{displayTeamLabel}</span>
                                    </td>
                                    <td className="py-4 px-3 text-sm font-bold text-slate-800 dark:text-slate-200 break-words">{p.title}</td>
                                    <td className="py-4 px-3">
                                        <div className="flex items-start space-x-3">
                                            <div className={`shrink-0 inline-flex items-center justify-center w-10 h-10 rounded-full text-xs font-black ring-4 shadow-sm ${
                                                p.aiScore >= 75 ? 'bg-emerald-100 text-emerald-700 ring-emerald-50 dark:bg-emerald-500/20 dark:text-emerald-400 dark:ring-emerald-500/10' : 
                                                p.aiScore >= 60 ? 'bg-amber-100 text-amber-700 ring-amber-50 dark:bg-amber-500/20 dark:text-amber-400 dark:ring-amber-500/10' : 
                                                'bg-red-100 text-red-700 ring-red-50 dark:bg-red-500/20 dark:text-red-400 dark:ring-red-500/10'
                                            }`}>
                                                {p.aiScore}
                                            </div>
                                            <div className="min-w-0 flex-1">
                                                <div className="text-[10px] font-black uppercase tracking-widest text-indigo-500 dark:text-indigo-400 mb-0.5">AI Rationale</div>
                                                <div title={p.aiRationale} className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed line-clamp-3">{p.aiRationale}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="py-4 px-3">
                                        <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border shadow-sm ${getStatusStyle(p.status)}`}>
                                            {p.status === 'Approved' && <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />}
                                            {p.status}
                                        </span>
                                    </td>
                                    <td className="py-4 px-3 text-sm font-medium text-slate-500 dark:text-slate-400">{p.submittedDate}</td>
                                    <td className="py-4 pl-3 pr-6 relative">
                                        <div className="flex items-center justify-end space-x-1">
                                            <button onClick={() => navigate(`/admin/proposals/view/${p.id}`)} title="View Proposal Analysis" className="p-2 text-blue-600 hover:bg-blue-100 dark:text-blue-400 dark:hover:bg-blue-500/20 rounded-xl transition-all shadow-sm"><Eye className="w-4 h-4" /></button>
                                            <div className="relative">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setActiveMenuId(activeMenuId === p.id ? null : p.id);
                                                    }}
                                                    title="More Actions"
                                                    className={`p-2 rounded-xl transition-all shadow-sm ${
                                                        activeMenuId === p.id
                                                            ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400'
                                                            : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700/50'
                                                    }`}
                                                >
                                                    <MoreVertical className="w-4 h-4" />
                                                </button>

                                                {activeMenuId === p.id && (
                                                    <>
                                                        <div
                                                            className="fixed inset-0 z-40"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                setActiveMenuId(null);
                                                            }}
                                                        />
                                                        <div className="absolute right-0 top-full mt-1.5 w-48 bg-white dark:bg-slate-800 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-700 py-1.5 z-50 text-left">
                                                            <div className="px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-slate-700/60 mb-1">
                                                                Directives
                                                            </div>
                                                            {!['approved', 'accepted', 'completed'].includes(String(p.status || '').trim().toLowerCase()) && (
                                                                <>
                                                                    <button
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            setActiveMenuId(null);
                                                                            handleAction(p.id, 'Approve');
                                                                        }}
                                                                        className="w-full text-left px-3 py-2 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 flex items-center gap-2.5 transition-colors"
                                                                    >
                                                                        <CheckCircle className="w-4 h-4 shrink-0" />
                                                                        Approve
                                                                    </button>
                                                                    <button
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            setActiveMenuId(null);
                                                                            handleAction(p.id, 'Revision');
                                                                        }}
                                                                        className="w-full text-left px-3 py-2 text-xs font-bold text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10 flex items-center gap-2.5 transition-colors"
                                                                    >
                                                                        <RotateCcw className="w-4 h-4 shrink-0" />
                                                                        Request Revision
                                                                    </button>
                                                                    <button
                                                                        onClick={(e) => {
                                                                            e.stopPropagation();
                                                                            setActiveMenuId(null);
                                                                            handleAction(p.id, 'Reject');
                                                                        }}
                                                                        className="w-full text-left px-3 py-2 text-xs font-bold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 flex items-center gap-2.5 transition-colors"
                                                                    >
                                                                        <XCircle className="w-4 h-4 shrink-0" />
                                                                        Reject Proposal
                                                                    </button>
                                                                    <div className="my-1 border-t border-slate-100 dark:border-slate-700/60" />
                                                                </>
                                                            )}
                                                            <button
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setActiveMenuId(null);
                                                                    handleDelete(p.id);
                                                                }}
                                                                className="w-full text-left px-3 py-2 text-xs font-bold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 flex items-center gap-2.5 transition-colors"
                                                            >
                                                                <Trash2 className="w-4 h-4 shrink-0" />
                                                                Delete Proposal
                                                            </button>
                                                        </div>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            );
                            })}
                            {filtered.length === 0 && <tr><td colSpan="7" className="p-16 text-center text-slate-500 font-medium">No active proposals in the pipeline match your criteria.</td></tr>}
                        </tbody>
                    </table>
                </div>
            </motion.div>

            {/* Custom Reason Modal */}
            {showReasonModal && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                    <motion.div 
                        initial={{ scale: 0.95, opacity: 0 }} 
                        animate={{ scale: 1, opacity: 1 }} 
                        className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700 p-6 max-w-md w-full shadow-2xl space-y-4"
                    >
                        <div>
                            <h3 className="text-lg font-black text-slate-800 dark:text-white">
                                Reason for {modalAction === 'Revision' ? 'Revision Request' : 'Rejection'}
                            </h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                Please specify the reason below. This feedback will be displayed directly on the student's portal.
                            </p>
                        </div>
                        <textarea
                            value={feedbackReason}
                            onChange={(e) => setFeedbackReason(e.target.value)}
                            placeholder="Enter description/feedback details here..."
                            rows={4}
                            className="w-full text-sm p-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl text-slate-850 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <div className="flex justify-end gap-3 pt-2">
                            <button
                                onClick={() => setShowReasonModal(false)}
                                className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirmActionWithReason}
                                className={`px-5 py-2 rounded-xl text-xs font-black text-white uppercase tracking-wider shadow-md hover:shadow-lg transition-all ${
                                    modalAction === 'Reject' 
                                        ? 'bg-gradient-to-r from-red-600 to-rose-600 shadow-red-500/25' 
                                        : 'bg-gradient-to-r from-amber-500 to-orange-500 shadow-amber-500/25'
                                }`}
                            >
                                Submit & {modalAction === 'Revision' ? 'Request Revision' : 'Reject'}
                            </button>
                        </div>
                    </motion.div>
                </div>
            )}
        </div>
    );
}
