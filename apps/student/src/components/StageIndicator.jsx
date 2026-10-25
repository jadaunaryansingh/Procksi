import React from 'react';
import { 
    CheckCircle2, 
    Hourglass, 
    AlertTriangle, 
    XCircle,
    Check
} from 'lucide-react';
import {
    useProfile,
    useTeam,
    useProposals,
    useEvaluations,
    useResults,
    useMentor,
    useMilestones
} from '../hooks/useStudentData';

export const StageIndicator = () => {
    const { data: profile } = useProfile();
    const { data: team } = useTeam();
    const { data: proposals } = useProposals();
    const { data: evaluations } = useEvaluations();
    const { data: results } = useResults();
    const { data: mentor } = useMentor();
    const { data: milestones } = useMilestones();

    // Robust check for Admin-allocated PS
    const hasAllocatedPS = team && (() => {
        const p_title = team.project_title || team.name;
        const desc = team.description || '';
        const cleanTitle = p_title ? p_title.trim().toLowerCase() : '';
        const isTitleAllocated = cleanTitle && cleanTitle !== "custom team" && !(/^team\s*-?\s*\d+$/i.test(cleanTitle)) && !cleanTitle.startsWith("pending");
        if (isTitleAllocated) return true;
        const cleanDesc = desc.trim().toLowerCase();
        if (cleanDesc === "" || cleanDesc === "custom team") return false;
        return !(/^team\s*-?\s*\d+$/i.test(cleanDesc));
    })();

    // 1. Proposal Submission & 2. Proposal Approval
    let proposalSubmitStatus = 'pending';
    let proposalApprovalStatus = 'pending';

    if (team && team.allocated_ps_id) {
        // Explicitly chose an Admin PS
        proposalSubmitStatus = 'completed';
        proposalApprovalStatus = 'completed';
    } else if (proposals && proposals.length > 0) {
        proposalSubmitStatus = 'completed';
        // Always evaluate the LATEST proposal
        const latest = proposals[proposals.length - 1];
        const statusLower = String(latest.status).toLowerCase().trim();
        
        if (statusLower === 'approved') {
            proposalApprovalStatus = 'completed';
        } else if (statusLower === 'rejected') {
            proposalApprovalStatus = 'rejected'; // Maps to Red Cross
        } else if (statusLower === 'revision' || statusLower === 'revision required' || statusLower === 'revision requested' || statusLower === 'revision_requested' || statusLower === 'resubmit') {
            proposalApprovalStatus = 'blocked'; // Maps to Orange Warning
        } else {
            proposalApprovalStatus = 'current'; // Awaiting Approval (Hourglass)
        }
    } else if (hasAllocatedPS) {
        // Fallback for Admin PS if allocated_ps_id isn't directly available
        proposalSubmitStatus = 'completed';
        proposalApprovalStatus = 'completed';
    } else {
        proposalSubmitStatus = 'current'; // First action required
    }

    // 3. Team Formation
    let teamStatus = 'pending';
    
    if (team && team.id && team.id !== 'Unassigned') {
        teamStatus = 'completed';
    } else if (profile && profile.team && profile.team.id) {
        teamStatus = 'completed';
    } else if (proposalApprovalStatus === 'completed') {
        teamStatus = 'current';
    } else if (proposalSubmitStatus === 'completed') {
        teamStatus = 'pending';
    } else {
        if (profile?.team?.id) {
            teamStatus = 'completed';
        }
    }

    // 4. Mentor Allocation
    let mentorStatus = 'pending';
    const mentorList = Array.isArray(mentor) ? mentor : (mentor && Object.keys(mentor).length > 0 ? [mentor] : []);
    
    if (mentorList.length > 0) {
        mentorStatus = 'completed';
    } else if (teamStatus === 'completed') {
        mentorStatus = 'current';
    }

    // 5. Synopsis Submission
    let synopsisStatus = 'pending';
    if (milestones && Array.isArray(milestones)) {
        const synopsis = milestones.find(m => m.title && m.title.toLowerCase().includes('synopsis'));
        if (synopsis) {
            const statusLower = String(synopsis.status).toLowerCase();
            if (statusLower === 'completed' || statusLower === 'approved') {
                synopsisStatus = 'completed';
            } else if (statusLower === 'submitted' || statusLower === 'pending_review') {
                synopsisStatus = 'current';
            } else if (statusLower === 'revision') {
                synopsisStatus = 'blocked';
            }
        }
    }
    if (mentorStatus === 'completed' && synopsisStatus === 'pending') {
        synopsisStatus = 'current';
    }

    // 6. Presentation Round 1, 7. Presentation Round 2, 8. Final Presentation
    let p1Status = 'pending';
    let p2Status = 'pending';
    let p3Status = 'pending';

    const hasEval = evaluations && typeof evaluations === 'object';
    
    if (hasEval && evaluations.proposal && evaluations.proposal.score !== null) {
        p1Status = 'completed';
    } else if (synopsisStatus === 'completed') {
        p1Status = 'current';
    }

    if (hasEval && evaluations.mid && evaluations.mid.score !== null) {
        p2Status = 'completed';
    } else if (p1Status === 'completed') {
        p2Status = 'current';
    }

    if (hasEval && evaluations.final && evaluations.final.score !== null) {
        p3Status = 'completed';
    } else if (p2Status === 'completed') {
        p3Status = 'current';
    }

    // 9. Result Publication
    let resultStatus = 'pending';
    if (results && results.overallScore !== undefined) {
        resultStatus = 'completed';
    } else if (p3Status === 'completed') {
        resultStatus = 'current';
    }

    const stages = [
        { id: 'team_form', label: 'Team Formation', status: teamStatus },
        { id: 'prop_sub', label: 'Proposal Submission', status: proposalSubmitStatus },
        { id: 'prop_app', label: 'Proposal Approval', status: proposalApprovalStatus },
        { id: 'mentor_alloc', label: 'Mentor Allocation', status: mentorStatus },
        { id: 'synopsis', label: 'Synopsis Submission', status: synopsisStatus },
        { id: 'pres_1', label: 'Presentation Round 1', status: p1Status },
        { id: 'pres_2', label: 'Presentation Round 2', status: p2Status },
        { id: 'pres_final', label: 'Final Presentation', status: p3Status },
        { id: 'results', label: 'Result Publication', status: resultStatus },
    ];

    return (
        <div className="w-full mb-8" role="region" aria-label="Project Lifecycle Tracker">
            {/* Visual Timeline Tracker */}
            <div className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-100 dark:border-slate-700/50 shadow-sm overflow-hidden">
                <h2 className="text-lg font-black text-slate-800 dark:text-white flex items-center mb-6">
                    <CheckCircle2 className="w-5 h-5 mr-2 text-indigo-500" /> Project Lifecycle Progress
                </h2>
                
                {/* Horizontal Scrolling Container for Mobile */}
                <div className="overflow-x-auto custom-scrollbar pb-4 -mx-2 px-2">
                    <div className="flex items-start min-w-[800px] relative mt-2">
                        {/* Connecting Lines */}
                        <div className="absolute top-5 left-8 right-8 h-1 bg-slate-100 dark:bg-slate-800 rounded-full -z-10">
                            <div 
                                className="h-full bg-emerald-500 rounded-full transition-all duration-1000"
                                style={{ 
                                    width: `${(stages.filter(s => s.status === 'completed').length / (stages.length - 1)) * 100}%` 
                                }}
                            />
                        </div>

                        {stages.map((stage, idx) => (
                            <div key={stage.id} className="flex-1 flex flex-col items-center relative z-10 group">
                                <div className={`w-10 h-10 rounded-full flex items-center justify-center border-4 transition-all duration-300 ${stage.status === 'completed' ? 'border-emerald-100 dark:border-emerald-900 bg-emerald-500 text-white' : stage.status === 'current' ? 'border-indigo-100 dark:border-indigo-900 bg-indigo-500 text-white ring-4 ring-indigo-500/20' : stage.status === 'rejected' ? 'border-red-100 dark:border-red-900 bg-red-500 text-white' : stage.status === 'blocked' ? 'border-amber-100 dark:border-amber-900 bg-amber-500 text-white' : 'border-slate-50 dark:border-slate-800 bg-slate-200 dark:bg-slate-700 text-slate-400'}`} title={stage.label}>
                                    {stage.status === 'completed' ? <Check className="w-5 h-5" /> : 
                                     stage.status === 'current' ? <Hourglass className="w-4 h-4 animate-pulse" /> : 
                                     stage.status === 'rejected' ? <XCircle className="w-5 h-5" /> :
                                     stage.status === 'blocked' ? <AlertTriangle className="w-4 h-4" /> :
                                     <span className="text-xs font-bold">{idx + 1}</span>}
                                </div>
                                <div className="mt-3 text-center px-1">
                                    <p className={`text-[11px] font-bold uppercase tracking-wider leading-tight ${stage.status === 'completed' ? 'text-emerald-600 dark:text-emerald-400' : stage.status === 'current' ? 'text-indigo-600 dark:text-indigo-400' : stage.status === 'rejected' ? 'text-red-600 dark:text-red-400' : stage.status === 'blocked' ? 'text-amber-600 dark:text-amber-400' : 'text-slate-400 dark:text-slate-500'}`}>
                                        {stage.label.split(' ').map((word, i) => <React.Fragment key={i}>{word}<br/></React.Fragment>)}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StageIndicator;
