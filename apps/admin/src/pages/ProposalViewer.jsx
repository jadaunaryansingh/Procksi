import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, FileText, CheckCircle, XCircle, RotateCcw, BrainCircuit, Users, Target, Activity, Loader2, ExternalLink, Download } from 'lucide-react';
import { motion } from 'framer-motion';
import { api } from '../services/api';
import { apiFetchTable } from '../lib/api';
import { findMatchingTeam } from '../lib/teamUtils';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { safeFrameUrl } from '../lib/safeUrl';

export default function ProposalViewer() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { semesterMap } = useGlobalFilters();
    
    const [proposal, setProposal] = useState(null);
    const [team, setTeam] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isUpdating, setIsUpdating] = useState(false);
    // Default to 'direct': proof/proposal files are public Supabase storage
    // URLs served with the correct PDF content-type and no framing
    // restriction, so Chrome renders them natively without needing Google's
    // viewer — which is a third-party dependency some browser extensions
    // (security/DLP tools) block outright, showing "This page has been
    // blocked by Chrome" for no fault of the file itself.
    const [viewerMode, setViewerMode] = useState('direct'); // 'gdocs' | 'direct' | 'summary'

    // Custom Reason Modal States
    const [showReasonModal, setShowReasonModal] = useState(false);
    const [modalAction, setModalAction] = useState(null); // 'Reject' or 'Revision'
    const [feedbackReason, setFeedbackReason] = useState('');

    useEffect(() => {
        let isMounted = true;
        const loadData = async () => {
            try {
                const [proposalsRes, allTeams] = await Promise.all([
                    api.getProposals(),
                    apiFetchTable('teams_validation', { semesterOverride: 'all' })
                ]);
                
                if (isMounted) {
                    const proposalsData = Array.isArray(proposalsRes) ? proposalsRes : proposalsRes.data || [];
                    const teamsData = Array.isArray(allTeams) ? allTeams : allTeams.data || [];
                    
                    const foundProposal = proposalsData.find(p => p.id === id);
                    if (foundProposal) {
                        setProposal(foundProposal);
                        const matchedTeam = findMatchingTeam(foundProposal, teamsData, semesterMap);
                        if (matchedTeam) {
                            setTeam(matchedTeam);
                        }
                    }
                }
            } catch (err) {
                console.error("Failed to load proposal details", err);
            } finally {
                if (isMounted) setIsLoading(false);
            }
        };
        loadData();
        return () => { isMounted = false; };
    }, [id, semesterMap]);



    const handleAction = async (action) => {
        if (!proposal || isUpdating) return;
        if (action === 'Approve') {
            if (window.confirm('Are you sure you want to approve this proposal?')) {
                setIsUpdating(true);
                try {
                    await api.approveProposal({ proposal_id: id });
                    navigate('/admin/proposals');
                } catch (error) {
                    console.error('Failed to Approve proposal:', error);
                    alert(`Failed to Approve proposal: ${error.message}`);
                } finally {
                    setIsUpdating(false);
                }
            }
        } else {
            // Reject or Revision Requested: open feedback modal
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
        setIsUpdating(true);
        setShowReasonModal(false);
        try {
            if (modalAction === 'Reject') {
                await api.rejectProposal({ proposal_id: id, feedback: feedbackReason.trim() });
            } else if (modalAction === 'Revision') {
                await api.revisionProposal({ proposal_id: id, feedback: feedbackReason.trim() });
            }
            navigate('/admin/proposals');
        } catch (error) {
            console.error(`Failed to ${modalAction} proposal:`, error);
            alert(`Failed to ${modalAction} proposal: ${error.message}`);
        } finally {
            setIsUpdating(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[50vh]">
                <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
            </div>
        );
    }

    if (!proposal) {
        return (
            <div className="text-center py-20">
                <h2 className="text-2xl font-bold text-slate-700">Proposal not found</h2>
                <button onClick={() => navigate(-1)} className="mt-4 text-indigo-600 hover:underline">Return to list</button>
            </div>
        );
    }

    const title = proposal.title || "Untitled Proposal";
    const description = team?.description || proposal.abstract || "No description provided.";
    
    // Process members
    let teamMembers = [];
    if (team) {
        if (team.leader) teamMembers.push(`${team.leader} (Leader)`);
        
        const extractString = (m) => {
            if (!m) return "Unknown Member";
            if (typeof m === 'string') return m;
            return m.name || m.id || m.student_id || "Unknown Member";
        };
        
        let rawMembers = [];
        if (Array.isArray(team.members)) {
            rawMembers = team.members.map(extractString);
        } else if (typeof team.members === 'string') {
            try {
                const parsed = JSON.parse(team.members);
                if (Array.isArray(parsed)) rawMembers = parsed.map(extractString);
            } catch { /* non-fatal: fall through to the default below */ }
        }
        
        const filteredMembers = rawMembers.filter(m => {
            const mName = typeof m === 'string' ? m : (m.name || m.student?.name || '');
            return !team.leader || mName.trim().toLowerCase() !== team.leader.trim().toLowerCase();
        });
        
        teamMembers = [...teamMembers, ...filteredMembers];
    }
    if (teamMembers.length === 0) teamMembers = ["No members found"];
    
    
    return (
        <div className="space-y-6 relative z-10">
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <button onClick={() => navigate(-1)} className="flex items-center px-4 py-2 text-sm font-bold text-slate-600 bg-white/70 dark:bg-slate-800/70 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-700/50 backdrop-blur-md rounded-xl transition-all shadow-sm hover:shadow-md">
                    <ChevronLeft className="w-5 h-5 mr-1" /> Return to Proposals
                </button>
                <div className="flex flex-wrap gap-3 w-full sm:w-auto">
                    {['approved', 'accepted', 'completed'].includes(String(proposal.status || '').trim().toLowerCase()) ? (
                        <span className="inline-flex items-center px-4 py-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 rounded-xl text-sm font-black uppercase tracking-wider">
                            <CheckCircle className="w-4 h-4 mr-2" /> Approved
                        </span>
                    ) : (
                        <>
                            <button onClick={() => handleAction('Approve')} disabled={isUpdating} className="disabled:opacity-50 flex-1 sm:flex-none justify-center flex items-center px-5 py-2.5 bg-gradient-to-tr from-emerald-600 to-emerald-500 hover:from-emerald-700 hover:to-emerald-600 border border-emerald-500/50 text-white rounded-xl text-sm font-black uppercase tracking-widest transition-all shadow-lg shadow-emerald-500/30 active:scale-95">
                                <CheckCircle className="w-4 h-4 mr-2" /> Approve
                            </button>
                            <button onClick={() => handleAction('Revision')} disabled={isUpdating} className="disabled:opacity-50 flex-1 sm:flex-none justify-center flex items-center px-5 py-2.5 bg-gradient-to-tr from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 border border-amber-500/50 text-white rounded-xl text-sm font-black uppercase tracking-widest transition-all shadow-lg shadow-amber-500/30 active:scale-95">
                                <RotateCcw className="w-4 h-4 mr-2" /> Revision
                            </button>
                            <button onClick={() => handleAction('Reject')} disabled={isUpdating} className="disabled:opacity-50 flex-1 sm:flex-none justify-center flex items-center px-5 py-2.5 bg-gradient-to-tr from-red-600 to-rose-600 hover:from-red-700 hover:to-rose-700 border border-red-500/50 text-white rounded-xl text-sm font-black uppercase tracking-widest transition-all shadow-lg shadow-red-500/30 active:scale-95">
                                <XCircle className="w-4 h-4 mr-2" /> Reject
                            </button>
                        </>
                    )}
                </div>
            </motion.div>

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                
                {/* PDF Viewer Simulation */}
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="xl:col-span-2 bg-slate-900/5 dark:bg-slate-900/50 rounded-3xl shadow-inline border border-slate-200/50 dark:border-slate-700/60 flex flex-col overflow-hidden min-h-[700px] relative backdrop-blur-3xl">
                    {(() => {
                        const docUrl = proposal.proposalFile || proposal.proposal_file || proposal.document_url;
                        const safeDocUrl = safeFrameUrl(docUrl);
                        const googleDocsUrl = safeDocUrl ? `https://docs.google.com/viewer?url=${encodeURIComponent(safeDocUrl)}&embedded=true` : null;

                        return (
                            <>
                                <div className="p-4 border-b border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between bg-white/50 dark:bg-slate-800/50 backdrop-blur-xl gap-3 flex-wrap sm:flex-nowrap">
                                    <div className="flex items-center space-x-3 min-w-0 flex-1">
                                        <div className="p-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg shrink-0"><FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400" /></div>
                                        <h2 className="font-bold text-slate-800 dark:text-white truncate">Document Viewer ─ <span className="font-mono text-indigo-600 dark:text-indigo-400 ml-1">{id}.pdf</span></h2>
                                    </div>

                                    {safeDocUrl && (
                                        <div className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-900/80 p-1 rounded-xl border border-slate-200/60 dark:border-slate-700/60 shrink-0">
                                            <button
                                                type="button"
                                                onClick={() => setViewerMode('gdocs')}
                                                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${viewerMode === 'gdocs' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'}`}
                                            >
                                                PDF Viewer
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setViewerMode('direct')}
                                                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${viewerMode === 'direct' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'}`}
                                            >
                                                Direct Embed
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setViewerMode('summary')}
                                                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${viewerMode === 'summary' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'}`}
                                            >
                                                Abstract Text
                                            </button>
                                        </div>
                                    )}

                                    {safeDocUrl && (
                                        <div className="flex items-center space-x-2 shrink-0">
                                            <a
                                                href={safeDocUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="inline-flex items-center px-3 py-1.5 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200/50 dark:border-indigo-500/30 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 rounded-xl text-xs font-bold transition-all shadow-sm"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5 mr-1" /> Open Fullscreen
                                            </a>
                                            <a
                                                href={safeDocUrl}
                                                download
                                                className="inline-flex items-center px-3 py-1.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600 rounded-xl text-xs font-bold transition-all shadow-sm"
                                            >
                                                <Download className="w-3.5 h-3.5 mr-1" /> Download
                                            </a>
                                        </div>
                                    )}
                                </div>
                                
                                <div className="flex-1 flex flex-col items-center justify-center p-4 overflow-y-auto w-full relative">
                                    {safeDocUrl && viewerMode === 'gdocs' ? (
                                        <iframe
                                            src={googleDocsUrl}
                                            title="Proposal Document (Cloud Viewer)"
                                            className="w-full h-full min-h-[650px] border-none rounded-2xl shadow-sm bg-white"
                                        />
                                    ) : safeDocUrl && viewerMode === 'direct' ? (
                                        <iframe
                                            src={safeDocUrl}
                                            referrerPolicy="no-referrer"
                                            title="Proposal Document (Direct)"
                                            className="w-full h-full min-h-[650px] border-none rounded-2xl shadow-sm bg-white"
                                        />
                                    ) : (
                                        /* Mock / Abstract Text Viewer Canvas */
                                        <div className="w-full max-w-2xl bg-white shadow-2xl rounded-sm border border-slate-200 flex flex-col relative z-10 transition-transform origin-top my-4">
                                            <div className="p-12 xl:p-16 space-y-6 text-slate-800">
                                                <h1 className="text-3xl font-black text-center pt-8 border-b-2 border-slate-100 pb-8 tracking-tight">{title}</h1>
                                                <p className="text-sm font-bold text-center uppercase tracking-widest text-slate-400 mb-12">Submission: {id}</p>
                                                
                                                <div className="space-y-4">
                                                    <h3 className="text-lg font-black text-indigo-900 flex items-center"><Target className="w-5 h-5 mr-2" /> 1. Abstract & Objectives</h3>
                                                    <p className="text-sm leading-8 text-slate-600 text-justify border-l-4 border-indigo-100 pl-4 py-1">
                                                        {description}
                                                    </p>
                                                </div>

                                                <div className="space-y-4 mt-12">
                                                    <h3 className="text-lg font-black text-indigo-900 flex items-center"><Activity className="w-5 h-5 mr-2" /> 2. Rationale / Notes</h3>
                                                    <p className="text-sm leading-8 text-slate-600 text-justify border-l-4 border-indigo-100 pl-4 py-1">
                                                        {proposal.aiRationale || proposal.ai_rationale || "No additional rationale available."}
                                                    </p>
                                                </div>
                                            </div>
                                            <div className="mt-auto p-4 text-center text-[10px] font-bold uppercase tracking-widest text-slate-400 bg-slate-50 border-t border-slate-100">
                                                PROPOSAL SUBMISSION ABSTRACT — RECORD DATA
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </>
                        );
                    })()}
                </motion.div>

                {/* Sidebar Details */}
                <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="space-y-6">
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
                                    className="w-full text-sm p-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl text-slate-850 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
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

                    {/* Team Details */}
                    <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 xl:p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 relative overflow-hidden">
                        <div className="absolute -right-6 -bottom-6 opacity-5 dark:opacity-20 pointer-events-none transform -rotate-12">
                            <Users className="w-32 h-32 text-indigo-500" />
                        </div>
                        <h3 className="text-xs font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-6 flex items-center relative z-10 border-b border-slate-100 dark:border-slate-700/50 pb-4">
                            <Users className="w-4 h-4 mr-2 text-indigo-500" /> Team Roster Database
                        </h3>
                        <ul className="space-y-4 relative z-10">
                            {teamMembers.map((member, idx) => (
                                <li key={idx} className="flex items-center text-sm font-bold text-slate-700 dark:text-slate-200">
                                    <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 flex items-center justify-center mr-4 shrink-0 font-black text-[10px] text-slate-400 shadow-sm">
                                        0{idx + 1}
                                    </div>
                                    {member.includes('(Leader)') ? (
                                        <span className="flex flex-col">
                                            <span className="text-indigo-600 dark:text-indigo-400">{member.replace(' (Leader)', '')}</span>
                                            <span className="text-[10px] uppercase tracking-widest text-slate-400 mt-0.5 font-black">Project Lead</span>
                                        </span>
                                    ) : (
                                        member
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                </motion.div>
                
            </div>
        </div>
    );
}
