import React from 'react';
import { 
    CheckCircle2, 
    Hourglass, 
    Circle, 
    AlertTriangle, 
    XCircle,
    FileText,
    Users,
    UserCheck,
    Presentation,
    Award,
    Calendar,
    ChevronRight,
    Check
} from 'lucide-react';
import {
    useProfile,
    useTeam,
    useProposals,
    useEvaluations,
    useResults,
    useMentor,
    useDeadlines,
    useMilestones
} from '../hooks/useStudentData';

export const StageIndicator = () => {
    const { data: profile } = useProfile();
    const { data: team } = useTeam();
    const { data: proposals } = useProposals();
    const { data: evaluations } = useEvaluations();
    const { data: results } = useResults();
    const { data: mentor } = useMentor();
    const { data: deadlines } = useDeadlines();
    const { data: milestones } = useMilestones();

    // 1. Proposal Submission & 2. Proposal Approval
    let proposalSubmitStatus = 'pending';
    let proposalApprovalStatus = 'pending';
    let proposalStatusText = 'Draft';

    if (proposals && proposals.length > 0) {
        proposalSubmitStatus = 'completed';
        proposalStatusText = 'Submitted';
        // Assume first proposal is the latest
        const latest = proposals[0];
        const statusLower = String(latest.status).toLowerCase();
        
        if (statusLower === 'approved') {
            proposalApprovalStatus = 'completed';
            proposalStatusText = 'Approved';
        } else if (statusLower === 'rejected') {
            proposalApprovalStatus = 'rejected';
            proposalStatusText = 'Rejected';
        } else {
            proposalApprovalStatus = 'current'; // Awaiting Approval
        }
    } else {
        proposalSubmitStatus = 'current'; // First action required
    }

    // 3. Team Formation
    let teamStatus = 'pending';
    let teamStatusText = 'Not Formed';
    
    if (team && team.id && team.id !== 'Unassigned') {
        teamStatus = 'completed';
        teamStatusText = team.status === 'Locked' ? 'Locked' : 'Formed';
    } else if (profile && profile.team && profile.team.id) {
        teamStatus = 'completed';
        teamStatusText = 'Formed';
    } else if (proposalApprovalStatus === 'completed') {
        teamStatus = 'current';
    } else if (proposalSubmitStatus === 'completed') {
        // Fallback: If proposal submitted but not approved yet, maybe team formation can happen parallelly?
        // Sticking to strict sequential logic for UI display:
        teamStatus = 'pending';
    } else {
        // If no proposal submitted, but maybe team is formed first in some DB states?
        if (profile?.team?.id) {
            teamStatus = 'completed';
            teamStatusText = 'Formed';
        }
    }

    // 4. Mentor Allocation
    let mentorStatus = 'pending';
    let mentorStatusText = 'Awaiting Allocation';
    let mentorNameText = '';
    const mentorList = Array.isArray(mentor) ? mentor : (mentor && Object.keys(mentor).length > 0 ? [mentor] : []);
    
    if (mentorList.length > 0) {
        mentorStatus = 'completed';
        mentorStatusText = 'Assigned';
        mentorNameText = mentorList[0].name;
    } else if (teamStatus === 'completed') {
        mentorStatus = 'current';
    }

    // 5. Synopsis Submission
    let synopsisStatus = 'pending';
    let synopsisStatusText = 'Not Submitted';
    if (milestones && Array.isArray(milestones)) {
        const synopsis = milestones.find(m => m.title && m.title.toLowerCase().includes('synopsis'));
        if (synopsis) {
            const statusLower = String(synopsis.status).toLowerCase();
            if (statusLower === 'completed' || statusLower === 'approved') {
                synopsisStatus = 'completed';
                synopsisStatusText = 'Approved';
            } else if (statusLower === 'submitted' || statusLower === 'pending_review') {
                synopsisStatus = 'current';
                synopsisStatusText = 'Submitted';
            } else if (statusLower === 'revision') {
                synopsisStatus = 'blocked';
                synopsisStatusText = 'Revision Required';
            }
        }
    }
    // Advance current pointer
    if (mentorStatus === 'completed' && synopsisStatus === 'pending') {
        synopsisStatus = 'current';
    }

    // 6. Presentation Round 1, 7. Presentation Round 2, 8. Final Presentation
    let p1Status = 'pending';
    let p2Status = 'pending';
    let p3Status = 'pending';
    let presentationStatusText = 'Upcoming';
    let evalStatusText = 'Pending';

    // Mock Evaluation structure based on PRD/Common Patterns (could be proposal, mid, final)
    const hasEval = evaluations && typeof evaluations === 'object';
    
    // Check Round 1 (e.g. proposal eval or mid eval depending on exact naming, assuming proposal/mid/final for the 3 rounds)
    if (hasEval && evaluations.proposal && evaluations.proposal.score !== null) {
        p1Status = 'completed';
    } else if (synopsisStatus === 'completed') {
        p1Status = 'current';
        presentationStatusText = 'Scheduled';
    }

    // Check Round 2
    if (hasEval && evaluations.mid && evaluations.mid.score !== null) {
        p2Status = 'completed';
    } else if (p1Status === 'completed') {
        p2Status = 'current';
        presentationStatusText = 'Scheduled';
    }

    // Check Final
    if (hasEval && evaluations.final && evaluations.final.score !== null) {
        p3Status = 'completed';
        presentationStatusText = 'Completed';
        evalStatusText = 'Evaluated';
    } else if (p2Status === 'completed') {
        p3Status = 'current';
        presentationStatusText = 'Scheduled';
    }

    // Evaluation general status
    if (p1Status === 'completed' || p2Status === 'completed' || p3Status === 'completed') {
        evalStatusText = 'Under Review';
    }
    if (p3Status === 'completed') {
        evalStatusText = 'Evaluated';
    }

    // 9. Result Publication
    let resultStatus = 'pending';
    // MOCK_RESULTS object has overallScore
    if (results && results.overallScore !== undefined) {
        resultStatus = 'completed';
    } else if (p3Status === 'completed') {
        resultStatus = 'current';
    }

    // Deadlines
    let nextDeadlineName = 'No active deadline';
    let nextDeadlineDays = '';
    let deadlineIsPast = false;
    if (deadlines && Array.isArray(deadlines) && deadlines.length > 0) {
        nextDeadlineName = deadlines[0].name || 'Upcoming Task';
        deadlineIsPast = deadlines[0].is_past;
        nextDeadlineDays = deadlineIsPast ? 'Past Due' : `${deadlines[0].days_remaining} Days`;
    }

    const stages = [
        { id: 'prop_sub', label: 'Proposal Submission', status: proposalSubmitStatus },
        { id: 'prop_app', label: 'Proposal Approval', status: proposalApprovalStatus },
        { id: 'team_form', label: 'Team Formation', status: teamStatus },
        { id: 'mentor_alloc', label: 'Mentor Allocation', status: mentorStatus },
        { id: 'synopsis', label: 'Synopsis Submission', status: synopsisStatus },
        { id: 'pres_1', label: 'Presentation Round 1', status: p1Status },
        { id: 'pres_2', label: 'Presentation Round 2', status: p2Status },
        { id: 'pres_final', label: 'Final Presentation', status: p3Status },
        { id: 'results', label: 'Result Publication', status: resultStatus },
    ];

    const renderIcon = (status) => {
        switch(status) {
            case 'completed': return <CheckCircle2 className="w-5 h-5 text-emerald-500" aria-label="Completed" />;
            case 'current': return <Hourglass className="w-5 h-5 text-indigo-500 animate-pulse" aria-label="Current" />;
            case 'blocked': return <AlertTriangle className="w-5 h-5 text-amber-500" aria-label="Blocked" />;
            case 'rejected': return <XCircle className="w-5 h-5 text-red-500" aria-label="Rejected" />;
            case 'pending': 
            default: return <Circle className="w-5 h-5 text-slate-300 dark:text-slate-600" aria-label="Pending" />;
        }
    };

    const renderBgColor = (status) => {
        switch(status) {
            case 'completed': return 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20';
            case 'current': return 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/20 shadow-md';
            case 'blocked': return 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20';
            case 'rejected': return 'bg-red-50 dark:bg-red-500/10 border-red-200 dark:border-red-500/20';
            case 'pending': 
            default: return 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/50 opacity-60';
        }
    };

    return (
        <div className="w-full space-y-6 mb-8" role="region" aria-label="Project Lifecycle Tracker">
            
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

            {/* Detailed Status Section */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {/* Proposal Status */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${renderBgColor(proposalApprovalStatus === 'rejected' ? 'rejected' : proposalSubmitStatus === 'completed' && proposalApprovalStatus === 'completed' ? 'completed' : proposalSubmitStatus === 'completed' ? 'current' : 'pending')}`}>
                    <div className="flex justify-between items-start mb-2">
                        <FileText className="w-5 h-5 opacity-70 text-slate-700 dark:text-slate-300" />
                        {renderIcon(proposalApprovalStatus === 'rejected' ? 'rejected' : proposalSubmitStatus === 'completed' && proposalApprovalStatus === 'completed' ? 'completed' : proposalSubmitStatus === 'completed' ? 'current' : 'pending')}
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Proposal</p>
                        <p className="text-sm font-black text-slate-800 dark:text-slate-100">{proposalStatusText}</p>
                    </div>
                </div>

                {/* Team Status */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${renderBgColor(teamStatus)}`}>
                    <div className="flex justify-between items-start mb-2">
                        <Users className="w-5 h-5 opacity-70 text-slate-700 dark:text-slate-300" />
                        {renderIcon(teamStatus)}
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Team Status</p>
                        <p className="text-sm font-black text-slate-800 dark:text-slate-100">{teamStatusText}</p>
                    </div>
                </div>

                {/* Mentor Status */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${renderBgColor(mentorStatus)}`}>
                    <div className="flex justify-between items-start mb-2">
                        <UserCheck className="w-5 h-5 opacity-70 text-slate-700 dark:text-slate-300" />
                        {renderIcon(mentorStatus)}
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Mentor</p>
                        <p className="text-sm font-black text-slate-800 dark:text-slate-100 leading-tight">
                            {mentorStatusText}
                            {mentorNameText && <span className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mt-1 truncate">{mentorNameText}</span>}
                        </p>
                    </div>
                </div>

                {/* Synopsis / Presentation Status */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${renderBgColor(synopsisStatus === 'blocked' ? 'blocked' : p1Status === 'completed' && p2Status === 'completed' && p3Status === 'completed' ? 'completed' : p1Status === 'current' || p2Status === 'current' || p3Status === 'current' ? 'current' : 'pending')}`}>
                    <div className="flex justify-between items-start mb-2">
                        <Presentation className="w-5 h-5 opacity-70 text-slate-700 dark:text-slate-300" />
                        {renderIcon(synopsisStatus === 'blocked' ? 'blocked' : p1Status === 'completed' && p2Status === 'completed' && p3Status === 'completed' ? 'completed' : p1Status === 'current' || p2Status === 'current' || p3Status === 'current' ? 'current' : 'pending')}
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Presentations</p>
                        <p className="text-sm font-black text-slate-800 dark:text-slate-100">{synopsisStatus === 'blocked' ? synopsisStatusText : presentationStatusText}</p>
                    </div>
                </div>

                {/* Evaluation Status */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${renderBgColor(resultStatus === 'completed' ? 'completed' : evalStatusText === 'Under Review' ? 'current' : 'pending')}`}>
                    <div className="flex justify-between items-start mb-2">
                        <Award className="w-5 h-5 opacity-70 text-slate-700 dark:text-slate-300" />
                        {renderIcon(resultStatus === 'completed' ? 'completed' : evalStatusText === 'Under Review' ? 'current' : 'pending')}
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Evaluation</p>
                        <p className="text-sm font-black text-slate-800 dark:text-slate-100">{evalStatusText}</p>
                    </div>
                </div>

                {/* Deadline */}
                <div className={`rounded-2xl p-4 border transition-colors flex flex-col justify-between h-full ${deadlineIsPast ? 'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/20' : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/50'}`}>
                    <div className="flex justify-between items-start mb-2">
                        <Calendar className={`w-5 h-5 opacity-70 ${deadlineIsPast ? 'text-rose-600' : 'text-slate-700 dark:text-slate-300'}`} />
                        <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded ${deadlineIsPast ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400' : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'}`}>
                            {nextDeadlineDays || 'No Deadline'}
                        </span>
                    </div>
                    <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-0.5">Upcoming Deadline</p>
                        <p className={`text-sm font-black truncate leading-tight ${deadlineIsPast ? 'text-rose-700 dark:text-rose-400' : 'text-slate-800 dark:text-slate-100'}`} title={nextDeadlineName}>
                            {nextDeadlineName}
                        </p>
                    </div>
                </div>
            </div>
            
        </div>
    );
};

export default StageIndicator;
