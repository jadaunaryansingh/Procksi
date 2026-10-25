import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, Lock, LogOut, Plus, Search, UserPlus, Hourglass, Check, X, Eye } from 'lucide-react';
import {
    useProfile,
    useTeam,
    useAvailableStudents,
    useJoinRequests,
    useDeadlines,
    fetchWithAuth
} from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';
import PsArchitecturePlanModal from '../components/PsArchitecturePlanModal';

// Same reasoning as DASHBOARD_POLL_MS — a 3s poll of four endpoints per open tab.
const TEAM_POLL_MS = 30000;


const getTeamDisplayName = (t) => {
    if (!t) return '';
    const title = t.title || t.name || '';
    let yearNum = t.year || (t.members && t.members[0]?.student?.year) || (t.members && t.members[0]?.year) || 3;
    let yearStr = `${yearNum}${yearNum === 1 ? 'st' : yearNum === 2 ? 'nd' : yearNum === 3 ? 'rd' : 'th'} Year`;

    const match = t.id ? (
        String(t.id).match(/[-_]?[Tt](\d+)$/i) || 
        String(t.id).match(/[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)/i) || 
        String(t.id).match(/[-_](\d+)/)
    ) : null;
    
    let teamNum = match ? match[1] : null;
    if (!teamNum && t.id) {
        const digits = String(t.id).replace(/\D/g, '');
        if (digits) {
            teamNum = digits.length >= 3 ? digits.slice(-3) : digits;
        }
    }

    const teamNo = teamNum ? `Team ${teamNum}` : 'Team 1';

    if (title && !title.toLowerCase().startsWith('team') && !title.toLowerCase().startsWith('custom team')) {
        return `${yearStr} - ${title}`;
    }
    return `${yearStr} - ${teamNo}`;
};

export const TeamProposalView = () => {
    const { data: profile, loading: profileLoading, error: profileError, refetch: refetchProfile } = useProfile();
    const { data: team, loading: teamLoading, error: teamError, refetch: refetchTeam } = useTeam();
    const { data: availableStudents, refetch: refetchAvailable } = useAvailableStudents();
    const { data: joinRequests, refetch: refetchJoinRequests } = useJoinRequests();
    const { data: deadlines } = useDeadlines();

    const [searchTerm, setSearchTerm] = useState('');
    const [isSearchFocused, setIsSearchFocused] = useState(false);
    const [selectedPsForAnalysis, setSelectedPsForAnalysis] = useState(null);

    const [teamsList, setTeamsList] = useState([]);
    const [teamsLoading, setTeamsLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);
    const [teamSearchTerm, setTeamSearchTerm] = useState('');

    const maxMembers = team?.teamSizeMax || team?.team_size_max || profile?.teamSizeMax || profile?.team_size_max || 4;

    useEffect(() => {
        if (teamError === "Student is not assigned to a team" || !team) {
            let isMounted = true;
            fetchWithAuth('/api/student/teams')
                .then(payload => {
                    if (isMounted) setTeamsList(Array.isArray(payload) ? payload : []);
                })
                .catch(err => console.error("Failed to load teams", err))
                .finally(() => {
                    if (isMounted) setTeamsLoading(false);
                });
        }
    }, [team, teamError]);

    const _autoRefetchRef = React.useRef({});
    useEffect(() => {
        _autoRefetchRef.current = { refetchProfile, refetchTeam, refetchAvailable, refetchJoinRequests };
    });

    useEffect(() => {
        const interval = setInterval(() => {
            const r = _autoRefetchRef.current;
            r.refetchProfile(true);
            r.refetchTeam(true);
            r.refetchAvailable(true);
            r.refetchJoinRequests(true);
        }, TEAM_POLL_MS);
        return () => clearInterval(interval);
    }, []);

    if (profileLoading || teamLoading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={8} />
            </div>
        );
    }

    const handleRetry = () => {
        refetchProfile();
        refetchTeam();
        refetchAvailable();
        refetchJoinRequests();
    };

    if (profileError || teamError) {
        const errMsg = profileError || teamError;
        if (errMsg !== "Student is not assigned to a team" && !errMsg.includes("not been published")) {
            return <ErrorCard message={errMsg} onRetry={handleRetry} />;
        }
    }

    if (teamError === "Student is not assigned to a team" || !team) {
        // Filter incoming requests where I am the recipient
        const incomingInvites = (joinRequests || []).filter(r => r.is_recipient && r.status === 'pending');

        // Filter outgoing requests where I am the sender
        const outgoingRequests = (joinRequests || []).filter(r => !r.is_recipient && r.status === 'pending');

        // Filter teams based on teamSearchTerm and ensure they have less than maxMembers
        const filteredTeams = teamsList.filter(t => {
            if (!teamSearchTerm.trim()) return true;
            const term = teamSearchTerm.toLowerCase();
            const titleMatches = (t.name || t.project_title || '').toLowerCase().includes(term);
            const idMatches = String(t.id).toLowerCase().includes(term);
            
            let parsedMembers = [];
            if (Array.isArray(t.members)) {
                parsedMembers = t.members;
            } else if (typeof t.members === 'string') {
                try {
                    parsedMembers = JSON.parse(t.members);
                } catch (e) {
                    parsedMembers = [];
                }
            }
            const leaderMatches = (t.leader || '').toLowerCase().includes(term);
            
            const memberMatches = parsedMembers.some(m => {
                if (!m) return false;
                if (typeof m === 'string') return m.toLowerCase().includes(term);
                const mName = m.name || m.student_name || (m.student && m.student.name) || '';
                const mId = m.id || m.student_id || m.roll || '';
                return String(mName).toLowerCase().includes(term) || String(mId).toLowerCase().includes(term);
            });
            
            const matchesSearch = titleMatches || idMatches || leaderMatches || memberMatches;
            return matchesSearch && parsedMembers.length < maxMembers;
        });

        const handleCreateTeam = async (e) => {
            if (e) e.preventDefault();
            setActionLoading(true);
            try {
                await fetchWithAuth('/api/student/team/create', {
                    method: 'POST',
                    body: {}
                });
                alert('Team formed successfully!');
                handleRetry();
            } catch (err) {
                const msg = String(err?.message || '');
                // The server already sees this student on a team (e.g. the team
                // was created a moment ago and this view is still showing the
                // stale "unassigned" state). Don't leave the user stuck on the
                // form — refetch so the page flips to the real team view.
                if (/already (in|on|a member of) .*team|already in team/i.test(msg)) {
                    alert(msg);
                    handleRetry();
                } else {
                    alert(msg);
                }
            } finally {
                setActionLoading(false);
            }
        };

        const handleRequestJoin = async (teamId, teamName) => {
            if (!window.confirm(`Send request to join ${teamName}?`)) return;
            setActionLoading(true);
            try {
                await fetchWithAuth(`/api/student/team/request-join?team_id=${teamId}`, {
                    method: 'POST'
                });
                alert('Join request sent!');
                handleRetry();
            } catch (err) {
                const msg = String(err?.message || '');
                if (/already (in|on|a member of) .*team|already in team/i.test(msg)) {
                    alert(msg);
                    handleRetry();
                } else {
                    alert(msg);
                }
            } finally {
                setActionLoading(false);
            }
        };

        return (
            <div className="max-w-4xl mx-auto space-y-8 p-4">
                {/* Main Card */}
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-200 dark:border-slate-700/50 shadow-xl relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 blur-[100px] rounded-full pointer-events-none" />
                    <div className="flex flex-col items-center text-center">
                        <div className="p-5 bg-gradient-to-br from-indigo-100 to-purple-100 dark:from-indigo-500/20 dark:to-purple-500/20 rounded-2xl mb-6 text-indigo-600 dark:text-indigo-400 shadow-inner">
                            <Users className="w-16 h-16 animate-pulse" />
                        </div>
                        <h3 className="text-3xl font-black text-slate-800 dark:text-slate-100">Unassigned Student</h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-3 max-w-md">
                            You do not belong to any active project team for this academic semester. You can accept a team invitation below, request to join an existing team, or form a new team as a leader.
                        </p>
                    </div>
                </div>

                {/* Incoming Invitations */}
                {incomingInvites.length > 0 && (
                    <div className="space-y-4 animate-fade-in">
                        <h4 className="text-lg font-extrabold text-slate-800 dark:text-white flex items-center gap-2">
                            <UserPlus className="w-5 h-5 text-purple-500" /> Incoming Team Invitations ({incomingInvites.length})
                        </h4>
                        <div className="grid gap-4">
                            {incomingInvites.map((req) => {
                                const members = req.team_members || [];
                                return (
                                    <div key={req.id} className="p-6 rounded-3xl border border-purple-200 dark:border-purple-500/40 bg-purple-50/50 dark:bg-purple-900/10 flex flex-col gap-4 shadow-sm backdrop-blur-md">
                                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-purple-100 dark:border-purple-800/40 pb-4">
                                            <div>
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="font-black text-slate-900 dark:text-white text-lg">
                                                        {req.team_name}
                                                    </span>
                                                    {req.project_title && req.project_title !== req.team_name && (
                                                        <span className="text-xs font-bold px-2.5 py-0.5 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 rounded-full border border-indigo-200 dark:border-indigo-800">
                                                            {req.project_title}
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                                    Invitation sent on {new Date(req.requested_at).toLocaleDateString()}
                                                </p>
                                            </div>
                                            <div className="flex gap-2 shrink-0">
                                                <button
                                                    disabled={actionLoading}
                                                    onClick={async () => {
                                                        if (window.confirm(`Accept invitation and join ${req.team_name}?`)) {
                                                            setActionLoading(true);
                                                            try {
                                                                await fetchWithAuth(`/api/student/join-requests/${req.id}/accept`, { method: 'POST' });
                                                                handleRetry();
                                                            } catch (e) {
                                                                alert(e.message);
                                                            } finally {
                                                                setActionLoading(false);
                                                            }
                                                        }
                                                    }}
                                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all shadow-sm active:scale-95 flex items-center gap-1 cursor-pointer"
                                                >
                                                    <Check className="w-3.5 h-3.5" /> Accept & Join
                                                </button>
                                                <button
                                                    disabled={actionLoading}
                                                    onClick={async () => {
                                                        if (window.confirm(`Decline invitation to join ${req.team_name}?`)) {
                                                            setActionLoading(true);
                                                            try {
                                                                await fetchWithAuth(`/api/student/join-requests/${req.id}/decline`, { method: 'POST' });
                                                                handleRetry();
                                                            } catch (e) {
                                                                alert(e.message);
                                                            } finally {
                                                                setActionLoading(false);
                                                            }
                                                        }
                                                    }}
                                                    className="px-4 py-2 bg-white dark:bg-slate-700 hover:bg-red-50 dark:hover:bg-red-500/20 text-slate-600 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 rounded-xl text-xs font-bold transition-all border border-slate-200 dark:border-slate-600 active:scale-95 flex items-center gap-1 cursor-pointer"
                                                >
                                                    <X className="w-3.5 h-3.5" /> Decline
                                                </button>
                                            </div>
                                        </div>

                                        {/* Current Team Members List */}
                                        <div>
                                            <div className="text-xs font-bold uppercase tracking-wider text-purple-900 dark:text-purple-300 mb-2 flex items-center gap-1.5">
                                                <Users className="w-3.5 h-3.5 text-purple-500" /> Current Team Members ({members.length > 0 ? members.length : '1'} / {maxMembers})
                                            </div>
                                            <div className="flex flex-wrap gap-2.5">
                                                {members.length > 0 ? (
                                                    members.map((m, idx) => (
                                                        <div key={idx} className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-slate-800 rounded-xl border border-purple-200/60 dark:border-purple-700/50 shadow-xs">
                                                            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
                                                                {(m.name || m.student_name || 'M').charAt(0).toUpperCase()}
                                                            </div>
                                                            <div>
                                                                <div className="text-xs font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1">
                                                                    {m.name || m.student_name || 'Member'}
                                                                    {(m.role === 'LEADER' || m.isLeader || idx === 0 || m.name === req.team_leader) && (
                                                                        <span className="text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 rounded-md border border-amber-200/60 dark:border-amber-700/40">Leader</span>
                                                                    )}
                                                                </div>
                                                                <div className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">
                                                                    {m.roll || m.id || m.student_id || ''} {m.branch ? `· ${m.branch}` : ''}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-slate-800 rounded-xl border border-purple-200/60 dark:border-purple-700/50 shadow-xs">
                                                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white flex items-center justify-center font-bold text-xs shrink-0">
                                                            {(req.team_leader || 'L').charAt(0).toUpperCase()}
                                                        </div>
                                                        <div>
                                                            <div className="text-xs font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1">
                                                                {req.team_leader || req.leader_id || 'Team Leader'}
                                                                <span className="text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/40 px-1.5 py-0.5 rounded-md border border-amber-200/60 dark:border-amber-700/40">Leader</span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Outgoing Requests */}
                {outgoingRequests.length > 0 && (
                    <div className="space-y-4 animate-fade-in">
                        <h4 className="text-lg font-extrabold text-slate-800 dark:text-white flex items-center gap-2">
                            <Hourglass className="w-5 h-5 text-amber-500 animate-pulse" /> Sent Join Requests ({outgoingRequests.length})
                        </h4>
                        <div className="grid gap-4">
                            {outgoingRequests.map((req) => (
                                <div key={req.id} className="p-6 rounded-2xl border border-amber-200 dark:border-amber-500/40 bg-amber-50/50 dark:bg-amber-900/10 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm backdrop-blur-md">
                                    <div>
                                        <div className="font-bold text-slate-900 dark:text-white text-base">
                                            {req.team_name}
                                        </div>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className="text-xs text-slate-500 dark:text-slate-400">
                                                Request sent on {new Date(req.requested_at).toLocaleDateString()}
                                            </span>
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-bold uppercase rounded-full">
                                                Pending Approval
                                            </span>
                                        </div>
                                    </div>
                                    <div>
                                        <button
                                            disabled={actionLoading}
                                            onClick={async () => {
                                                if (window.confirm(`Withdraw request to join ${req.team_name}?`)) {
                                                    setActionLoading(true);
                                                    try {
                                                        await fetchWithAuth(`/api/student/join-requests/${req.id}/decline`, { method: 'POST' });
                                                        handleRetry();
                                                    } catch (e) {
                                                        alert(e.message);
                                                    } finally {
                                                        setActionLoading(false);
                                                    }
                                                }
                                            }}
                                            className="px-4 py-2 bg-white dark:bg-slate-700 hover:bg-rose-50 dark:hover:bg-rose-500/20 text-slate-600 dark:text-slate-300 hover:text-rose-600 dark:hover:text-rose-400 rounded-xl text-xs font-bold transition-all border border-slate-200 dark:border-slate-600 active:scale-95 flex items-center gap-1"
                                        >
                                            <X className="w-3.5 h-3.5" /> Cancel Request
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Form & Join Sections */}
                <div className="grid md:grid-cols-2 gap-8">
                    {/* Form Team */}
                    <div className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-200 dark:border-slate-700/50 shadow-md flex flex-col justify-between">
                        <div>
                            <h4 className="text-xl font-bold text-slate-800 dark:text-white flex items-center gap-2 mb-3">
                                <Plus className="w-5 h-5 text-indigo-500" /> Form a New Team
                            </h4>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">
                                Start a brand new team for this semester. You will be automatically assigned a team number, designated as the team leader, and can invite other unassigned students.
                            </p>
                        </div>
                        <button
                            onClick={handleCreateTeam}
                            disabled={actionLoading}
                            className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all shadow-md active:scale-95 disabled:opacity-50"
                        >
                            {actionLoading ? 'Creating...' : 'Form Team as Leader'}
                        </button>
                    </div>

                    {/* Join Team */}
                    <div className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-200 dark:border-slate-700/50 shadow-md flex flex-col justify-between min-h-[300px]">
                        <div>
                            <h4 className="text-xl font-bold text-slate-800 dark:text-white flex items-center gap-2 mb-3">
                                <Search className="w-5 h-5 text-emerald-500" /> Request to Join a Team
                            </h4>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                                Browse active teams in your academic batch and request to be added as a member.
                            </p>
                            <input
                                type="text"
                                placeholder="Search teams by name..."
                                value={teamSearchTerm}
                                onChange={(e) => setTeamSearchTerm(e.target.value)}
                                className="w-full px-4 py-2 mb-4 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none transition-all dark:text-white"
                            />
                        </div>
                        <div className="flex-1 max-h-48 overflow-y-auto border border-slate-100 dark:border-slate-800 rounded-xl p-2 space-y-2 mb-4 scrollbar-thin">
                            {teamsLoading ? (
                                <p className="text-xs text-slate-400 text-center py-4">Loading teams...</p>
                            ) : filteredTeams.length === 0 ? (
                                <p className="text-xs text-slate-400 text-center py-4">No teams found</p>
                            ) : (
                                filteredTeams.map((t) => {
                                    // Check if student is already in members list of this team
                                    let mList = [];
                                    if (Array.isArray(t.members)) {
                                        mList = t.members;
                                    } else if (typeof t.members === 'string') {
                                        try {
                                            mList = JSON.parse(t.members);
                                        } catch (e) {
                                            mList = [];
                                        }
                                    }
                                    const isFull = mList.length >= maxMembers;
                                    const teamDisplayName = getTeamDisplayName(t);
                                    const hasPendingRequest = outgoingRequests.some(r => String(r.team_id) === String(t.id) || r.team_id === `TEAM-${t.id}`);
                                    return (
                                        <div key={t.id} className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/30 dark:bg-slate-900/20 flex items-center justify-between gap-4">
                                            <div>
                                                <div className="font-bold text-slate-800 dark:text-slate-200 text-xs">{teamDisplayName}</div>
                                                <div className="text-[10px] text-slate-400">Members: {mList.length}/{maxMembers}</div>
                                                {mList.length > 0 && (
                                                    <div className="text-[10px] text-slate-500 dark:text-slate-400 italic mt-0.5 truncate max-w-[250px]" title={mList.map(m => m.name || m.student?.name || '').filter(Boolean).join(', ')}>
                                                        ({mList.map(m => m.name || m.student?.name || '').filter(Boolean).join(', ')})
                                                    </div>
                                                )}
                                            </div>
                                            <button
                                                disabled={actionLoading || isFull || hasPendingRequest}
                                                onClick={() => handleRequestJoin(t.id, teamDisplayName)}
                                                className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-all active:scale-95 ${
                                                    isFull 
                                                        ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-not-allowed'
                                                        : hasPendingRequest
                                                            ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30 cursor-default'
                                                            : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm'
                                                }`}
                                            >
                                                {isFull ? 'Full' : hasPendingRequest ? 'Requested' : 'Request Join'}
                                            </button>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    const isTeamLeader = profile?.team_membership?.role === 'LEADER';
    const outgoingInvitations = isTeamLeader 
        ? (joinRequests || []).filter(req => !req.is_recipient && req.status === 'pending')
        : [];
    
    // Check if team deadline has passed
    const teamDeadline = deadlines?.find(d => d.name === 'team' || d.name === 'teamFormation' || d.type === 'team' || d.type === 'teamFormation' || d.id === 'deadline-team' || d.id === 'teamFormation' || d.id === 'deadline-teamFormation');
    const teamDeadlinePassed = teamDeadline ? teamDeadline.is_past : false;

    // FIX (Bug 3): If team validation status is 'Invalid', unlock roster edits
    const teamValidationStatus = (team?.status || '').toLowerCase();
    const isTeamUnlocked = teamValidationStatus === 'invalid';

    const isPlaceholderTitle = (title, teamName = '') => {
        if (!title) return true;
        const clean = title.trim().toLowerCase();
        if (!clean || clean === 'custom team' || clean.startsWith('pending') || clean.startsWith('admin-team')) return true;
        if (teamName && clean === teamName.trim().toLowerCase()) return true;
        if (/^team\s*-?\s*\d+$/i.test(clean)) return true;
        if (/^\d{4}(?:-\d{4})?[-_\s]+\d+$/i.test(clean)) return true;
        return false;
    };

    const hasAllocatedPS = team && (() => {
        if (team.allocated_ps_id) return true;
        const title = team.project_title;
        if (title && !isPlaceholderTitle(title, team.name)) return true;
        return false;
    })();
    const isProjectAllocated = hasAllocatedPS;

    // disableTeamEdits: locked unless team is explicitly unlocked by admin, or lockTeams/isLocked is active, or project is allocated
    const disableTeamEdits = isProjectAllocated || !!(profile?.lockTeams || profile?.isLocked || (isTeamUnlocked ? false : teamDeadlinePassed));

    const handleAddMember = async (student) => {
        const hasPendingInvite = outgoingInvitations.some(inv => String(inv.student_id) === String(student.id));
        if (hasPendingInvite) {
            alert('An invitation has already been sent to this student and is pending approval.');
            return;
        }
        if (team.members && team.members.length >= maxMembers) {
            alert(`Team has reached maximum limit of ${maxMembers} members.`);
            return;
        }
        if (!window.confirm(`Invite ${student.name} (${student.id}) to join the team?`)) return;
        try {
            await fetchWithAuth(`/api/student/team/add-member?student_id=${student.id}`, {
                method: 'POST'
            });
            alert('Invitation sent successfully.');
            refetchJoinRequests();
            handleRetry();
        } catch (err) {
            alert('Failed to send invitation: ' + err.message);
        }
        setSearchTerm('');
    };

    const handleRemoveMember = async (id) => {
        if (id === profile.id) return;
        if (!window.confirm('Are you sure you want to remove this student from the team?')) return;
        try {
            await fetchWithAuth(`/api/student/team/remove-member?student_id=${id}`, {
                method: 'POST'
            });
            alert('Member removed successfully.');
            handleRetry();
        } catch (err) {
            alert('Failed to remove member: ' + err.message);
        }
    };

    const handleAcceptRequest = async (requestId) => {
        try {
            await fetchWithAuth(`/api/student/join-requests/${requestId}/accept`, { method: 'POST' });
            alert('Join request accepted! Student has been added to the team.');
            refetchJoinRequests();
            handleRetry();
        } catch (err) {
            alert('Failed to accept request: ' + (err.message || err));
        }
    };

    const handleDeclineRequest = async (requestId) => {
        try {
            await fetchWithAuth(`/api/student/join-requests/${requestId}/decline`, { method: 'POST' });
            refetchJoinRequests();
            handleRetry();
        } catch (err) {
            alert('Failed to decline request: ' + (err.message || err));
        }
    };

    const handleDisbandTeam = async () => {
        if (!window.confirm('This will permanently delete your empty team. You can then browse and send a request to join another team. Continue?')) return;
        setActionLoading(true);
        try {
            await fetchWithAuth('/api/student/team/disband', { method: 'POST' });
            alert('Team disbanded. You can now browse and join another team.');
            refetchJoinRequests();
            handleRetry();
        } catch (err) {
            alert('Failed to disband team: ' + (err.message || err));
        } finally {
            setActionLoading(false);
        }
    };

    const membersList = team.members || [];

    const filteredStudents = (availableStudents || []).filter(s => {
        const term = searchTerm.toLowerCase().trim();
        const sName = String(s.name || '').toLowerCase();
        const sId = String(s.id || '').toLowerCase();
        const sRoll = String(s.roll || s.student_id || '').toLowerCase();
        const sBranch = String(s.branch || '').toLowerCase();

        const matchesSearch = !term || sName.includes(term) || sId.includes(term) || sRoll.includes(term) || sBranch.includes(term);
        
        const isAlreadyInTeam = membersList.some(m => {
            const mId = String(m.student_id || m.id || m.roll || '').toLowerCase();
            const mName = String(m.student?.name || m.name || '').toLowerCase();
            return (mId && (mId === sId || mId === sRoll)) || (mName && mName === sName);
        });

        return matchesSearch && !isAlreadyInTeam;
    });

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">

            {/* Banners for join requests */}
            <AnimatePresence>
                {isTeamLeader && (joinRequests || [])
                    .filter(req => req.is_recipient && (String(req.team_id) === String(team?.id) || req.team_id === `TEAM-${team?.id}`))
                    .map((req, idx) => (
                    <motion.div
                        key={req.id}
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: 40 }}
                        transition={{ delay: idx * 0.05 }}
                        className="p-4 rounded-2xl border border-purple-200 dark:border-purple-500/40 bg-purple-50 dark:bg-purple-900/20 flex flex-col sm:flex-row sm:items-center gap-4 shadow-sm"
                    >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-100 to-indigo-100 dark:from-purple-500/20 dark:to-indigo-500/20 flex items-center justify-center shrink-0 shadow-inner">
                                <UserPlus className="w-5 h-5 text-purple-500" />
                            </div>
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                                    <span className="font-bold text-slate-800 dark:text-white text-sm">{req.student_name || 'A student'}</span>
                                    <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">({req.student_roll || req.student_id})</span>
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-black uppercase tracking-widest rounded-full border border-amber-200 dark:border-amber-500/30">
                                        <Hourglass className="w-2.5 h-2.5" /> Awaiting Decision
                                    </span>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-slate-400">
                                    {req.initiated_by === 'admin' 
                                        ? 'Admin requested to add this student to ' 
                                        : `${req.student_name || 'Student'} has requested to join `}
                                    <span className="font-semibold text-purple-700 dark:text-purple-400">your team</span>
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <button
                                onClick={async () => {
                                     if (window.confirm(`Accept request and add ${req.student_name || 'this student'} to your team?`)) {
                                         try {
                                             await fetchWithAuth(`/api/student/join-requests/${req.id}/accept`, { method: 'POST' });
                                             refetchJoinRequests();
                                             handleRetry();
                                         } catch (e) {
                                             alert(e.message);
                                         }
                                     }
                                }}
                                disabled={disableTeamEdits}
                                className="flex items-center px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition-all active:scale-95 shadow-sm shadow-emerald-500/20 disabled:opacity-50 disabled:pointer-events-none"
                            >
                                <Check className="w-3.5 h-3.5 mr-1.5" /> Accept & Add
                            </button>
                            <button
                                onClick={async () => {
                                     if (window.confirm(`Decline the request to add ${req.student_name || 'this student'} to your team?`)) {
                                         try {
                                             await fetchWithAuth(`/api/student/join-requests/${req.id}/decline`, { method: 'POST' });
                                             refetchJoinRequests();
                                         } catch (e) {
                                             alert(e.message);
                                         }
                                     }
                                }}
                                disabled={disableTeamEdits}
                                className="flex items-center px-4 py-2 bg-white dark:bg-slate-700 hover:bg-red-50 dark:hover:bg-red-500/20 text-slate-600 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 rounded-xl text-xs font-bold transition-all active:scale-95 border border-slate-200 dark:border-slate-600 disabled:opacity-50 disabled:pointer-events-none"
                            >
                                <X className="w-3.5 h-3.5 mr-1.5" /> Decline
                            </button>
                        </div>
                    </motion.div>
                ))}
            </AnimatePresence>

            {/* Banners for outgoing invitations */}
            <AnimatePresence>
                {isTeamLeader && outgoingInvitations.map((req, idx) => (
                    <motion.div
                        key={req.id}
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: 40 }}
                        transition={{ delay: idx * 0.05 }}
                        className="p-4 rounded-2xl border border-amber-200 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-900/20 flex flex-col sm:flex-row sm:items-center gap-4 shadow-sm"
                    >
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-100 to-orange-100 dark:from-amber-500/20 dark:to-orange-500/20 flex items-center justify-center shrink-0 shadow-inner">
                                <UserPlus className="w-5 h-5 text-amber-500" />
                            </div>
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-0.5">
                                    <span className="font-bold text-slate-800 dark:text-white text-sm">{req.student_name || 'A student'}</span>
                                    <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">({req.student_roll || req.student_id})</span>
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-black uppercase tracking-widest rounded-full border border-amber-200 dark:border-amber-500/30">
                                        <Hourglass className="w-2.5 h-2.5 animate-pulse" /> Sent Invitation Pending
                                    </span>
                                </div>
                                <p className="text-xs text-slate-600 dark:text-slate-400">
                                    You invited this student to join <span className="font-semibold text-purple-700 dark:text-purple-400">your team</span>
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2 shrink-0">
                            <button
                                onClick={async () => {
                                     if (window.confirm(`Withdraw invitation to ${req.student_name || 'this student'}?`)) {
                                         try {
                                             await fetchWithAuth(`/api/student/join-requests/${req.id}/decline`, { method: 'POST' });
                                             refetchJoinRequests();
                                         } catch (e) {
                                             alert(e.message);
                                         }
                                     }
                                }}
                                disabled={disableTeamEdits}
                                className="flex items-center px-4 py-2 bg-white dark:bg-slate-700 hover:bg-rose-50 dark:hover:bg-rose-500/20 text-slate-600 dark:text-slate-300 hover:text-rose-600 dark:hover:text-rose-400 rounded-xl text-xs font-bold transition-all border border-slate-200 dark:border-slate-600 active:scale-95 flex items-center gap-1 disabled:opacity-50"
                            >
                                <X className="w-3.5 h-3.5" /> Cancel Invitation
                            </button>
                        </div>
                    </motion.div>
                ))}
            </AnimatePresence>

            {isProjectAllocated && (
                <div className="bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10 border border-indigo-500/20 dark:border-indigo-500/30 rounded-3xl p-6 shadow-xl relative overflow-hidden backdrop-blur-md">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-full blur-3xl -z-10"></div>
                    <div className="absolute bottom-0 left-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl -z-10"></div>
                    
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex-1">
                            <div className="flex items-center gap-3 mb-3 flex-wrap">
                                <span className="inline-flex items-center px-3 py-1 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-400 text-xs rounded-xl font-bold uppercase tracking-wider border border-purple-200 dark:border-purple-800">
                                    {team.name ? (team.name.toLowerCase().startsWith('team') ? team.name : `Team ${team.name}`) : (team.id ? `Team ${team.id}` : 'N/A')}
                                </span>
                                <span className="inline-flex items-center px-3 py-1 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-400 text-xs rounded-xl font-bold uppercase tracking-wider border border-indigo-200 dark:border-indigo-800">
                                    🌟 Allocated Project
                                </span>
                                {team.description && team.allocated_ps_id && (
                                    <button
                                        type="button"
                                        onClick={() => setSelectedPsForAnalysis({
                                            id: team.id,
                                            title: team.project_title || team.title,
                                            description: team.description,
                                            domain: Array.isArray(team.domain) ? team.domain[0] : (team.domain || 'General'),
                                            difficulty: 'Medium'
                                        })}
                                        className="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-xl font-bold border border-indigo-700 transition-all cursor-pointer shadow-sm"
                                    >
                                        <Eye className="w-3.5 h-3.5" /> View Blueprint
                                    </button>
                                )}
                            </div>
                            <h3 className="text-2xl font-black text-slate-800 dark:text-white leading-tight">
                                {team.project_title}
                            </h3>

                            
                            <div className="flex flex-wrap gap-2.5 mt-4">
                                {team.domain && team.domain.length > 0 && team.domain.map((d, i) => (
                                    <span key={i} className="text-xs font-bold bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400 px-3 py-1 rounded-lg border border-slate-200 dark:border-slate-700/50">
                                        Domain: {d}
                                    </span>
                                ))}
                                {team.mentor && (
                                    <span className="text-xs font-bold bg-indigo-50 dark:bg-indigo-555/10 text-indigo-600 dark:text-indigo-400 px-3 py-1 rounded-lg border border-indigo-100 dark:border-indigo-900/30">
                                        Mentor: {team.mentor.name}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* TEAM SECTION */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm hover:shadow-md transition-shadow text-slate-800 dark:text-slate-100">
                <div className="p-5 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center rounded-t-2xl bg-slate-50/50 dark:bg-slate-800/50">
                    <div>
                        <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center">
                            <Users className="w-5 h-5 mr-2 text-indigo-500" /> Team Configuration
                        </h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                            {membersList.length}/{maxMembers} members · {Math.max(0, maxMembers - membersList.length)} slot{Math.max(0, maxMembers - membersList.length) !== 1 ? 's' : ''} available
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {teamDeadlinePassed && !isTeamUnlocked && <span className="flex items-center text-xs font-bold text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-1.5 rounded-lg"><Lock className="w-3.5 h-3.5 mr-1" /> Locked</span>}
                        {isTeamUnlocked && <span className="flex items-center text-xs font-bold text-amber-600 bg-amber-50 dark:bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-500/30">Unlocked for Editing</span>}
                        {!disableTeamEdits && isTeamLeader && membersList.length === 1 && (
                            <button
                                type="button"
                                onClick={handleDisbandTeam}
                                disabled={actionLoading}
                                title="Disband this empty team and join another team instead"
                                className="flex items-center gap-1.5 text-xs font-bold text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10 hover:bg-red-100 dark:hover:bg-red-500/20 border border-red-200 dark:border-red-500/30 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
                            >
                                <LogOut className="w-3.5 h-3.5" /> Disband &amp; Join Another Team
                            </button>
                        )}
                    </div>
                </div>

                <div className="p-6">
                    {/* Members Table */}
                    <div className="w-full overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-700 mb-5">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700">
                                    <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-10">#</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Member</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider hidden sm:table-cell">Email</th>
                                    <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-24">Role</th>
                                    {!disableTeamEdits && isTeamLeader && (
                                        <th className="px-4 py-3 text-center text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-20">Action</th>
                                    )}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                                <AnimatePresence>
                                    {membersList.map((m, idx) => (
                                        <motion.tr
                                            key={m.id}
                                            initial={{ opacity: 0, x: -10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            exit={{ opacity: 0, x: 10 }}
                                            transition={{ delay: idx * 0.05 }}
                                            className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                                        >
                                            <td className="px-4 py-3 text-slate-400 dark:text-slate-500 font-mono text-xs">{idx + 1}</td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-sm shrink-0 shadow-sm">
                                                        {(m.student?.name || 'S').charAt(0).toUpperCase()}
                                                    </div>
                                                    <span className="font-semibold text-slate-800 dark:text-slate-200">{m.student?.name}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-slate-500 dark:text-slate-400 hidden sm:table-cell">{m.student?.email || '—'}</td>
                                            <td className="px-4 py-3">
                                                {m.role === 'LEADER' ? (
                                                    <span className="inline-flex items-center px-2.5 py-1 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-400 text-[10px] rounded-full font-bold uppercase tracking-wide border border-indigo-200 dark:border-slate-700">
                                                        Leader
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex items-center px-2.5 py-1 bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 text-[10px] rounded-full font-medium uppercase tracking-wide">
                                                        Member
                                                    </span>
                                                )}
                                            </td>
                                            {!disableTeamEdits && isTeamLeader && (
                                                <td className="px-4 py-3 text-center">
                                                    {m.student_id !== profile.id ? (
                                                        <button
                                                            onClick={() => handleRemoveMember(m.student_id)}
                                                            className="inline-flex items-center justify-center w-8 h-8 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all"
                                                            title="Remove member"
                                                        >
                                                            <LogOut className="w-4 h-4" />
                                                        </button>
                                                    ) : (
                                                        <span className="text-slate-300 dark:text-slate-600 text-xs">—</span>
                                                    )}
                                                </td>
                                            )}
                                        </motion.tr>
                                    ))}
                                </AnimatePresence>

                                {/* Empty slots */}
                                {Array.from({ length: Math.max(0, maxMembers - membersList.length) }).map((_, i) => (
                                    <tr key={`empty-${i}`} className="opacity-50">
                                        <td className="px-4 py-3 text-slate-300 dark:text-slate-600 font-mono text-xs">{membersList.length + i + 1}</td>
                                        <td className="px-4 py-3" colSpan={!disableTeamEdits && isTeamLeader ? 4 : 3}>
                                            <div className="flex items-center gap-3">
                                                <div data-tour="student-team-members" className="w-9 h-9 rounded-full border-2 border-dashed border-slate-300 dark:border-slate-600 flex items-center justify-center">
                                                    <Plus className="w-4 h-4 text-slate-300 dark:text-slate-600" />
                                                </div>
                                                <span className="text-slate-400 dark:text-slate-500 italic text-sm">Empty Slot</span>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* PENDING JOIN REQUESTS & INVITATIONS PANEL */}
                    {joinRequests && joinRequests.length > 0 && (
                        <div className="bg-amber-50/60 dark:bg-amber-950/20 rounded-2xl border border-amber-200 dark:border-amber-500/30 p-5 mb-5 shadow-sm">
                            <div className="flex items-center gap-2 mb-3">
                                <Hourglass className="w-4 h-4 text-amber-600 dark:text-amber-400 animate-pulse" />
                                <h4 className="text-xs font-bold text-amber-900 dark:text-amber-200 uppercase tracking-wider">
                                    Pending Join Requests &amp; Invitations ({joinRequests.length})
                                </h4>
                            </div>
                            <div className="space-y-3">
                                {joinRequests.map(req => {
                                    let titleName = '';
                                    let statusSubtitle = '';
                                    const isRecipient = req.is_recipient !== false;
                                    
                                    if (isRecipient) {
                                        if (req.initiated_by === 'student') {
                                            titleName = req.student_name || 'Student Request';
                                            statusSubtitle = `Requested to join your team (${req.student_branch || 'Student'})`;
                                        } else if (req.initiated_by === 'leader') {
                                            titleName = req.team_name || 'Team Invitation';
                                            statusSubtitle = `Invited you to join team ${req.team_name || ''}`;
                                        } else {
                                            titleName = req.team_name || 'Admin Request';
                                            statusSubtitle = `Admin requested to add you to team ${req.team_name || ''}`;
                                        }
                                    } else {
                                        if (req.initiated_by === 'leader') {
                                            titleName = req.student_name || 'Student Invitation';
                                            statusSubtitle = `You invited ${req.student_name || 'this student'} to join your team`;
                                        } else {
                                            titleName = req.team_name || 'Team Request';
                                            statusSubtitle = `You requested to join team ${req.team_name || ''}`;
                                        }
                                    }

                                    return (
                                        <div key={req.id} className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-amber-200/60 dark:border-amber-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
                                            <div className="flex items-center gap-3">
                                                <div className="w-9 h-9 rounded-full bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 flex items-center justify-center font-bold text-xs shrink-0">
                                                    {(titleName || 'S').charAt(0).toUpperCase()}
                                                </div>
                                                <div>
                                                    <div className="text-sm font-bold text-slate-800 dark:text-slate-100">
                                                        {titleName}
                                                    </div>
                                                    <div className="text-xs text-slate-500 dark:text-slate-400">
                                                        {statusSubtitle}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-2 self-end sm:self-center">
                                                {isRecipient ? (
                                                    <>
                                                        <button
                                                            onClick={() => handleAcceptRequest(req.id)}
                                                            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-all shadow-xs flex items-center gap-1 cursor-pointer"
                                                        >
                                                            <Check className="w-3.5 h-3.5" /> Accept
                                                        </button>
                                                        <button
                                                            onClick={() => handleDeclineRequest(req.id)}
                                                            className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 rounded-lg text-xs font-bold transition-all flex items-center gap-1 cursor-pointer border border-rose-200/50 dark:border-rose-500/20"
                                                        >
                                                            <X className="w-3.5 h-3.5" /> Decline
                                                        </button>
                                                    </>
                                                ) : (
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-bold text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-200/60 dark:border-amber-500/20">
                                                            Pending Approval
                                                        </span>
                                                        <button
                                                            onClick={() => handleDeclineRequest(req.id)}
                                                            className="px-2.5 py-1.5 bg-slate-100 hover:bg-rose-50 dark:bg-slate-700 dark:hover:bg-rose-500/20 text-slate-600 dark:text-slate-300 hover:text-rose-600 rounded-lg text-xs font-bold transition-all flex items-center gap-1 cursor-pointer border border-slate-200 dark:border-slate-600"
                                                            title="Cancel Invitation"
                                                        >
                                                            <X className="w-3.5 h-3.5" /> Cancel
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Add Member Search */}
                    {!disableTeamEdits && isTeamLeader && membersList.length < maxMembers && (
                        <div className="mt-1">
                            <div className="bg-slate-50 dark:bg-slate-800/50 p-4 rounded-xl border border-slate-100 dark:border-slate-700">
                                <label data-tour="student-team-add" className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Add Team Member</label>
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                                    <input
                                        type="text"
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        onFocus={() => setIsSearchFocused(true)}
                                        onBlur={() => setTimeout(() => setIsSearchFocused(false), 150)}
                                        placeholder="Search by name or roll number..."
                                        className="w-full pl-9 pr-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none text-sm dark:text-slate-200"
                                    />
                                </div>

                                {/* Results list */}
                                {(searchTerm || isSearchFocused) && (
                                    <div className="mt-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
                                        {filteredStudents.length > 0 ? (
                                            <table className="w-full text-sm">
                                                <thead>
                                                    <tr className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-100 dark:border-slate-700">
                                                        <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Name</th>
                                                        <th className="px-4 py-2.5 text-left text-xs font-bold text-slate-400 uppercase tracking-wider hidden sm:table-cell">Roll No. / Branch</th>
                                                        <th className="px-4 py-2.5 w-14 text-center text-xs font-bold text-slate-400 uppercase tracking-wider">Add</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-50 dark:divide-slate-800">
                                                    {filteredStudents.slice(0, 8).map(student => {
                                                        const hasPendingInvite = outgoingInvitations.some(inv => 
                                                            String(inv.student_id) === String(student.id) ||
                                                            String(inv.student_id) === String(student.roll) ||
                                                            String(inv.student_id) === String(student.student_id)
                                                        );
                                                        return (
                                                            <tr
                                                                key={student.id || student.roll}
                                                                className={`hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors cursor-pointer ${hasPendingInvite ? 'opacity-75 cursor-default' : ''}`}
                                                                onMouseDown={() => handleAddMember(student)}
                                                            >
                                                                <td className="px-4 py-3">
                                                                    <div className="flex items-center gap-2.5">
                                                                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-xs shrink-0">
                                                                            {(student.name || '?').charAt(0).toUpperCase()}
                                                                        </div>
                                                                        <span className="font-semibold text-slate-800 dark:text-slate-200">{student.name}</span>
                                                                    </div>
                                                                </td>
                                                                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 text-xs hidden sm:table-cell">{student.roll || student.student_id || student.id} · {(student.branch === 'B.Tech CS' ? 'BTech CSE' : student.branch) || 'BTech CSE'}</td>
                                                                <td className="px-4 py-3 text-center">
                                                                    {hasPendingInvite ? (
                                                                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-bold uppercase rounded-lg border border-amber-200 dark:border-amber-500/30">
                                                                            <Hourglass className="w-3 h-3 animate-pulse" /> Pending
                                                                        </span>
                                                                    ) : (
                                                                        <span className="inline-flex items-center justify-center w-7 h-7 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-400 rounded-lg hover:bg-indigo-200 dark:hover:bg-indigo-800 transition-colors">
                                                                            <Plus className="w-4 h-4" />
                                                                        </span>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        ) : (
                                            <div className="px-4 py-4 text-sm text-slate-400 dark:text-slate-500 text-center italic">
                                                {searchTerm ? (
                                                    membersList.some(m => (m.student?.name || m.name || '').toLowerCase().includes(searchTerm.toLowerCase().trim()))
                                                        ? `"${searchTerm}" is already a member of your team.`
                                                        : `No unassigned students found matching "${searchTerm}"`
                                                ) : 'Start typing to search students...'}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        {/* PS Blueprint Modal */}
        {selectedPsForAnalysis && (
            <PsArchitecturePlanModal
                ps={selectedPsForAnalysis}
                onClose={() => setSelectedPsForAnalysis(null)}
                isStudent={true}
            />
        )}
        </motion.div>
    );
};

export default TeamProposalView;
