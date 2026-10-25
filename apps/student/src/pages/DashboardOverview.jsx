import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Users, FileBadge, Clock, CheckCircle, Sparkles,
    Activity, FileText, ArrowRight, Github, GitPullRequest,
    ShieldAlert, Trophy, ClipboardList
} from 'lucide-react';
import {
    useProfile,
    useTeam,
    useMilestones,
    useAnnouncements,
    useMentor,
    useDeadlines,
    useDeadlineCompletion,
    useProposals
} from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';
import StageIndicator from '../components/StageIndicator';
import { formatDeadlineName } from '../lib/reminders';
import RichText from '../components/RichText';

// Background refresh cadence for the dashboard. This was 3s, which — combined
// with one request per hook instance — put ~140 requests/minute on the API for
// every open tab. Reads are also served from the shared query cache now, so a
// slower poll no longer costs responsiveness: anything the user does triggers
// an explicit refetch.
const DASHBOARD_POLL_MS = 30000;

const formatDateUTC = (dateStr) => {
    if (!dateStr) return '';
    if (dateStr.includes('T')) {
        const [dPart, tPart] = dateStr.split('T');
        const [yyyy, mm, dd] = dPart.split('-');
        const timeClean = tPart.substring(0, 5);
        return `${dd}-${mm}-${yyyy} at ${timeClean}`;
    }
    const date = new Date(dateStr);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    return `${day}-${month}-${year}`;
};

export const DashboardOverview = () => {
    const navigate = useNavigate();

    const { data: profile, loading: profileLoading, error: profileError, refetch: refetchProfile } = useProfile();
    const { data: team, refetch: refetchTeam } = useTeam();
    const { data: milestones, refetch: refetchMilestones } = useMilestones();
    const { data: announcements, refetch: refetchAnnouncements } = useAnnouncements();
    const { data: mentor, refetch: refetchMentor } = useMentor();
    const { data: deadlines, refetch: refetchDeadlines } = useDeadlines();
    const completion = useDeadlineCompletion();
    const { data: proposals, refetch: refetchProposals } = useProposals();

    const handleRetry = () => {
        refetchProfile();
        refetchTeam();
        refetchMilestones();
        refetchAnnouncements();
        refetchMentor();
        refetchDeadlines();
        refetchProposals();
    };

    // Keep latest refetch functions in a ref so the interval can call them
    // without needing them as useEffect dependencies (which would reset the
    // interval on every render and prevent it from ever firing).
    // The write happens in an effect, not during render: refs must not be
    // mutated while rendering. The interval below only reads this after the
    // first DASHBOARD_POLL_MS, well after the initial commit.
    const refetchRef = React.useRef({});
    useEffect(() => {
        refetchRef.current = {
            refetchProfile, refetchTeam, refetchMilestones,
            refetchAnnouncements, refetchMentor, refetchDeadlines, refetchProposals
        };
    });

    useEffect(() => {
        const interval = setInterval(() => {
            const r = refetchRef.current;
            r.refetchProfile(true);
            r.refetchTeam(true);
            r.refetchMilestones(true);
            r.refetchAnnouncements(true);
            r.refetchMentor(true);
            r.refetchDeadlines(true);
            r.refetchProposals(true);
        }, DASHBOARD_POLL_MS);
        return () => clearInterval(interval);
    }, []);

    // Progressive render: wait only on the core profile (which decides team
    // assignment and the page shape). Every widget below reads its data null-safely,
    // so team / milestones / announcements / mentor / deadlines fill in as they
    // arrive — one slow or failed secondary endpoint never blocks the whole page.
    if (profileLoading) {
        return (
            <div className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                    <LoadingSkeleton lines={5} />
                </div>
            </div>
        );
    }

    // Only a core-profile failure blanks the page. Secondary endpoints degrade
    // gracefully (empty/placeholder) instead of replacing the dashboard with an error.
    if (profileError) {
        if (profileError !== "Student is not assigned to a team" && profileError !== "No mentor assigned to your team yet" && !profileError.includes("not been published")) {
            return (
                <div className="space-y-6">
                    <ErrorCard message={profileError} onRetry={handleRetry} />
                </div>
            );
        }
    }

    // Handlers for optional or unassigned team state
    if (!profile?.team) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm text-center flex flex-col items-center justify-center min-h-[300px]">
                    <div data-tour="student-status-cards" className="p-4 bg-indigo-50 dark:bg-indigo-500/10 rounded-2xl mb-4 text-indigo-500">
                        <Users className="w-12 h-12" />
                    </div>
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100">No Team Assigned</h3>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 max-w-sm">
                        You are currently in the unassigned student pool. You can join a team once invited by a team leader or assigned by an administrator.
                    </p>
                </div>
                {/* Announcements */}
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 mt-6">
                    <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                        <FileText className="w-5 h-5 mr-2 text-indigo-500" /> Announcements
                    </h3>
                    <div className="space-y-4">
                        {(announcements || []).map((ann) => (
                            <div key={ann.id} className="p-3.5 bg-indigo-50/50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800">
                                <div className="flex justify-between items-center mb-1">
                                    <p className="font-bold text-sm text-indigo-900 dark:text-indigo-100">{ann.title}</p>
                                    <span className="text-[10px] font-bold text-indigo-500">{new Date(ann.created_at).toLocaleDateString()}</span>
                                </div>
                                <RichText text={ann.body} className="text-xs text-indigo-700 dark:text-indigo-300 leading-relaxed" />
                            </div>
                        ))}
                    </div>
                </div>
            </motion.div>
        );
    }

    const mList = milestones || [];
    const completedMilestones = mList.filter(m => m.status === 'completed' || m.status === 'approved').length;
    const progress = mList.length > 0 ? Math.round((completedMilestones / mList.length) * 100) : 0;

    let teamStatus = team?.project_title ? (team.status || 'Formed') : 'Formation In Progress';
    let teamStatusColor = teamStatus === 'Locked' || teamStatus === 'Valid' ? 'text-emerald-500' : 'text-amber-500';

    if (team && !team.allocated_ps_id && proposals && proposals.length > 0) {
        const latest = proposals[proposals.length - 1];
        const statusLower = String(latest.status).toLowerCase().trim();
        if (statusLower === 'approved') {
            teamStatus = '✔ Approved';
            teamStatusColor = 'text-emerald-500';
        } else if (statusLower === 'rejected') {
            teamStatus = '❌ Rejected';
            teamStatusColor = 'text-rose-500';
        } else if (statusLower === 'revision' || statusLower === 'revision required' || statusLower === 'revision requested' || statusLower === 'revision_requested' || statusLower === 'resubmit') {
            teamStatus = '🟠 Revision Requested';
            teamStatusColor = 'text-orange-500';
        } else {
            teamStatus = '⏳ Pending Approval';
            teamStatusColor = 'text-amber-500';
        }
    }

    const countdownText = deadlines && deadlines.length > 0
        ? `${deadlines[0].days_remaining} days remaining`
        : 'No active deadline';

    const formatTeamVal = (name, id) => {
        const str = String(name || '').trim();
        const isCorrupt = /^team\s*\d{6,}$/i.test(str) || /^team\s*[0-9a-f-]{8,}$/i.test(str);
        if (str && !isCorrupt) {
            return str.toLowerCase().startsWith('team') ? str : `Team ${str}`;
        }
        const idStr = String(id || '').trim();
        const m = /[-_]?[Tt](\d+)/i.exec(idStr) || /[-_](\d+)$/.exec(idStr);
        if (m) {
            const val = parseInt(m[1], 10);
            if (val > 0 && val < 100000) return `Team ${val}`;
        }
        const target = isCorrupt ? str : idStr;
        const digits = target.replace(/\D/g, '');
        if (digits.length > 0) {
            const val = parseInt(digits.slice(-3) || digits.slice(0, 3), 10);
            if (val > 0) return `Team ${val}`;
        }
        return 'N/A';
    };
    const teamNameVal = formatTeamVal(team?.name || profile?.team?.name, team?.id || profile?.team?.id);
    const cards = [
        { title: 'Team Number', value: teamNameVal, icon: Users, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-500/10' },
        { title: 'Project Status', value: teamStatus, icon: FileBadge, color: teamStatusColor, bg: 'bg-indigo-50 dark:bg-indigo-500/10' },
        { title: 'Next Deadline', value: countdownText, icon: Clock, color: 'text-rose-500', bg: 'bg-rose-50 dark:bg-rose-500/10' },
        { title: 'Overall Progress', value: `${progress}%`, icon: CheckCircle, color: progress === 100 ? 'text-emerald-500' : 'text-indigo-500', bg: progress === 100 ? 'bg-emerald-50 dark:bg-emerald-500/10' : 'bg-indigo-50 dark:bg-indigo-500/10' },
    ];

    const containerVariants = {
        hidden: { opacity: 0 },
        show: { opacity: 1, transition: { staggerChildren: 0.1 } }
    };

    const itemVariants = {
        hidden: { opacity: 0, y: 20 },
        show: { opacity: 1, y: 0 }
    };

    // FIX (Bug 1): Build list of all mentors regardless of single-object or array response
    const mentorList = Array.isArray(mentor) ? mentor : (mentor ? [mentor] : []);
    const isUnassigned = mentorList.length === 0;

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <StageIndicator />
            <motion.div variants={containerVariants} initial="hidden" animate="show" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {cards.map((card, idx) => (
                    <motion.div variants={itemVariants} key={idx} className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-100 dark:border-slate-700/50 shadow-sm hover:shadow-xl hover:-translate-y-1.5 transition-all duration-300 group relative overflow-hidden cursor-pointer">
                        <card.icon className={`absolute -right-4 -bottom-4 w-24 h-24 ${card.color} opacity-[0.03] dark:opacity-10 pointer-events-none z-0 group-hover:scale-110 group-hover:-rotate-12 transition-transform duration-500`} />
                        <div className="absolute right-0 top-0 w-32 h-32 bg-gradient-to-br from-transparent to-slate-50 dark:to-slate-700/20 rounded-bl-full -z-10 group-hover:scale-125 transition-transform duration-500"></div>
                        <div className="flex items-center justify-between mb-4 relative z-10">
                            <div className={`p-3 rounded-2xl ${card.bg}`}>
                                <card.icon className={`w-6 h-6 ${card.color}`} />
                            </div>
                        </div>
                        <h3 className="text-sm font-semibold text-slate-500 dark:text-slate-400 relative z-10">{card.title}</h3>
                        <p className="text-xl font-black text-slate-800 dark:text-slate-100 mt-1 relative z-10 tracking-tight">{card.value}</p>
                    </motion.div>
                ))}
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-2">
                <div className="lg:col-span-2 space-y-6">
                    {/* Main UI Row */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Active Deadlines */}
                        <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 hover:shadow-md transition-shadow relative overflow-hidden group">
                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                                <Clock className="w-5 h-5 mr-2 text-rose-500" /> Active Deadlines
                            </h3>
                            <div className="space-y-4">
                                {(deadlines || []).map((d) => {
                                    const rawId = String(d.id || '').replace(/^deadline-/, '');
                                    const met = completion[d.name] === true || completion[d.type] === true || completion[d.id] === true || completion[rawId] === true;
                                    return (
                                    <div key={d.id} className={`flex justify-between items-center p-3 rounded-xl border ${met ? 'bg-slate-50 dark:bg-slate-800/40 border-slate-200/60 dark:border-slate-700/50 opacity-70' : 'bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-700'}`}>
                                        <div>
                                            <p className={`font-bold text-sm ${met ? 'text-slate-500 dark:text-slate-400 line-through' : 'text-slate-800 dark:text-slate-200'}`}>{formatDeadlineName(d.name || 'Deadline')}</p>
                                            <p className="text-xs text-slate-500 mt-0.5">{formatDateUTC(d.deadline_date)}</p>
                                        </div>
                                        <div className="text-right">
                                            {met ? (
                                                <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 rounded-full">
                                                    <CheckCircle className="w-3 h-3" /> Done
                                                </span>
                                            ) : (
                                                <span className="text-xs font-bold text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2.5 py-1 rounded-full">
                                                    {d.is_past ? 'Past Due' : `${d.days_remaining} days`}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    );
                                })}
                                {(!deadlines || deadlines.length === 0) && (
                                    <div data-tour="student-deadlines" className="text-sm text-slate-500 text-center p-4">No active deadlines</div>
                                )}
                            </div>
                        </div>

                        {/* Announcements */}
                        <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 hover:shadow-md transition-shadow">
                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                                <FileText className="w-5 h-5 mr-2 text-indigo-500" /> Announcements
                            </h3>
                            <div className="space-y-4 max-h-[300px] overflow-y-auto">
                                {(announcements || []).map((ann) => (
                                    <div key={ann.id} className="p-3.5 bg-indigo-50/50 dark:bg-indigo-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800">
                                        <div className="flex justify-between items-center mb-1">
                                            <p className="font-bold text-sm text-indigo-900 dark:text-indigo-100">{ann.title}</p>
                                            <span className="text-[10px] font-bold text-indigo-500">{new Date(ann.created_at).toLocaleDateString()}</span>
                                        </div>
                                        <RichText text={ann.body} className="text-xs text-indigo-700 dark:text-indigo-300 leading-relaxed" />
                                    </div>
                                ))}
                                {(!announcements || announcements.length === 0) && (
                                    <div data-tour="student-announcements" className="p-6 text-center text-sm text-slate-400 bg-slate-50/50 dark:bg-slate-900/30 rounded-2xl border border-dashed border-slate-200 dark:border-slate-700/50 flex flex-col items-center justify-center space-y-1">
                                        <p className="font-semibold text-slate-600 dark:text-slate-400">No announcements published yet</p>
                                        <p className="text-xs text-slate-400">Official updates from coordinators will appear here.</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Team Contribution */}
                    <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 hover:shadow-md transition-shadow">
                        <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                            <Users className="w-5 h-5 mr-2 text-indigo-500" /> Team Contribution
                        </h3>

                        {(() => {
                            const hasGithubRepo = !!(team?.github?.repository_url || team?.repository_url);
                            const hasGithubContrib = hasGithubRepo && team?.github?.contribution_distribution && team.github.contribution_distribution.length > 0;
                            const items = hasGithubContrib 
                                ? team.github.contribution_distribution 
                                : (team?.members || []);
                                
                            const totalCommits = hasGithubContrib
                                ? items.reduce((sum, c) => sum + (c.commits || 0), 0)
                                : items.reduce((sum, m) => sum + (m.github_stats?.commits || 0), 0);

                            const hasValidAnalysis = hasGithubRepo && (hasGithubContrib || totalCommits > 0);

                            if (!hasValidAnalysis) {
                                return (
                                    <div className="flex flex-col items-center justify-center py-8 text-center bg-slate-50/50 dark:bg-slate-900/30 rounded-2xl border border-dashed border-slate-200 dark:border-slate-700/60 p-6">
                                        <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/50 text-indigo-500 dark:text-indigo-400 flex items-center justify-center mb-3 border border-indigo-100 dark:border-indigo-900/50">
                                            <Github className="w-6 h-6" />
                                        </div>
                                        <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 mb-1">Repo Not Submitted Yet</h4>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm leading-relaxed">
                                            No project or repository URL has been submitted yet. Contribution analysis will appear once the GitHub repository is submitted and analyzed.
                                        </p>
                                    </div>
                                );
                            }

                            const segmentColors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6', '#f43f5e'];
                            const bgColors = ['bg-indigo-500', 'bg-emerald-500', 'bg-amber-500', 'bg-pink-500', 'bg-purple-500', 'bg-blue-500', 'bg-rose-500'];
                            const textColors = ['text-indigo-600 dark:text-indigo-400', 'text-emerald-600 dark:text-emerald-400', 'text-amber-600 dark:text-amber-400', 'text-pink-600 dark:text-pink-400', 'text-purple-600 dark:text-purple-400', 'text-blue-600 dark:text-blue-400', 'text-rose-600 dark:text-rose-400'];

                            // Each arc starts where the previous ones ended. Precomputing the
                            // running offsets keeps render pure — the previous version mutated a
                            // `prevTotal` captured from the enclosing scope inside .map, so a
                            // re-render that reused the closure could start from a stale total.
                            const percentOf = (item) => hasGithubContrib
                                ? (item.percentage !== undefined ? item.percentage : (item.contributionPercentage || 0))
                                : (totalCommits > 0 ? (item.github_stats?.contribution_percentage || 0) : 0);
                            const offsets = items.reduce((acc, item) => {
                                acc.push((acc[acc.length - 1] ?? 0) + percentOf(item));
                                return acc;
                            }, []);

                            return (
                                <div className="flex flex-col sm:flex-row items-center gap-6 mt-2">
                                    {/* SVG Donut Chart */}
                                    <div className="relative w-40 h-40 shrink-0">
                                        <svg viewBox="0 0 100 100" className="w-full h-full transform -rotate-90">
                                            {items.map((item, index) => {
                                                const percent = percentOf(item);
                                                const currentPrevTotal = index === 0 ? 0 : offsets[index - 1];

                                                return (
                                                    <motion.circle
                                                        key={item.id || item.contributorName || index}
                                                        cx="50"
                                                        cy="50"
                                                        r="40"
                                                        fill="transparent"
                                                        stroke={segmentColors[index % segmentColors.length]}
                                                        strokeWidth="15"
                                                        strokeDasharray="251.2"
                                                        strokeDashoffset={251.2}
                                                        animate={{ strokeDashoffset: 251.2 - (251.2 * percent) / 100 }}
                                                        transition={{ duration: 1.5, ease: "easeOut", delay: index * 0.2 }}
                                                        className="drop-shadow-sm"
                                                        style={{ transformOrigin: 'center', transform: `rotate(${(currentPrevTotal / 100) * 360}deg)` }}
                                                    />
                                                );
                                            })}
                                            <circle cx="50" cy="50" r="32" className="fill-white dark:fill-slate-800" />
                                        </svg>

                                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                                            <Trophy className="w-6 h-6 text-slate-300 dark:text-slate-600 mb-1" />
                                        </div>
                                    </div>

                                    {/* Legend */}
                                    <div className="flex-1 space-y-3 w-full">
                                        {items.map((item, index) => {
                                            let name = "Member";
                                            let commits = 0;
                                            let percent = 0;
                                            let avatarUrl = "";
                                            
                                            if (hasGithubContrib) {
                                                name = item.contributorName || item.name || "Contributor";
                                                commits = item.commits || 0;
                                                percent = Math.round(item.percentage !== undefined ? item.percentage : (item.contributionPercentage || 0));
                                                avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=random`;
                                            } else {
                                                const s = item.student || {};
                                                name = s.name || "Member";
                                                commits = item.github_stats?.commits || 0;
                                                percent = totalCommits > 0
                                                    ? Math.round(item.github_stats?.contribution_percentage || 0)
                                                    : 0;
                                                avatarUrl = s.avatar_url || `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=random`;
                                            }

                                            return (
                                                <div key={item.id || name || index} className="flex justify-between items-center p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors">
                                                    <div className="flex items-center gap-3">
                                                        <div className={`w-3 h-3 rounded-full ${bgColors[index % bgColors.length]} shadow-sm`} />
                                                        <div className="flex items-center gap-2">
                                                            <img src={avatarUrl} alt="avatar" className="w-6 h-6 rounded-full border border-slate-200 dark:border-slate-700" />
                                                            <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">{name}</span>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        {commits > 0 && (
                                                            <span className="text-xs text-slate-400">({commits} commits)</span>
                                                        )}
                                                        <span className={`text-sm font-black ${textColors[index % textColors.length]}`}>{percent}%</span>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })()}
                    </div>
                </div>

                <div className="flex flex-col gap-6">
                    {/* GitHub Activity */}
                    <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden text-slate-100">
                        <Github className="absolute -right-6 -bottom-6 w-32 h-32 text-white/5 rotate-12 pointer-events-none" />
                        <h3 className="text-lg font-bold flex items-center mb-6">
                            <Github className="w-5 h-5 mr-2" /> GitHub Status
                        </h3>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white/5 border border-white/10 rounded-2xl p-4 text-center backdrop-blur-sm flex flex-col justify-center min-h-[90px]">
                                {team?.github?.repository_url ? (
                                    <>
                                        <p className="text-sm font-bold text-white mb-1 truncate max-w-full" title={team.github.repository_url.split("/").pop().replace(".git", "")}>
                                            {team.github.repository_url.split("/").pop().replace(".git", "")}
                                        </p>
                                        <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider">
                                            {team.github.status === "completed" ? "Active Repo" : team.github.status}
                                        </p>
                                    </>
                                ) : (
                                    <>
                                        <p className="text-xs font-bold text-slate-400 mb-1">Repo Not Submitted</p>
                                        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">No URL Submitted</p>
                                    </>
                                )}
                            </div>
                            <div className="space-y-3">
                                <div className="bg-white/5 border border-white/10 rounded-xl p-3 flex items-center justify-between backdrop-blur-sm relative group">
                                    <div className="flex items-center text-sm font-medium"><GitPullRequest className="w-4 h-4 mr-2 text-emerald-400" /> Commits</div>
                                    <span className="font-bold">{team?.github?.commit_count || 0}</span>
                                </div>
                                <div className="bg-white/5 border border-white/10 rounded-xl p-3 flex items-center justify-between backdrop-blur-sm relative group">
                                    <div className="flex items-center text-sm font-medium"><ShieldAlert className="w-4 h-4 mr-2 text-purple-400" /> Quality</div>
                                    <span className="font-bold">{team?.github?.scores?.quality || 0}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 flex flex-col">
                        <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                            <ArrowRight className="w-5 h-5 mr-2 text-indigo-500" /> Quick Actions
                        </h3>
                        <div className="grid grid-cols-1 gap-3 flex-1">
                            <button onClick={() => navigate('/student/preferences')} className="flex items-center justify-between p-3.5 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700/50 hover:bg-indigo-50 hover:border-indigo-200 dark:hover:bg-indigo-900/20 dark:hover:border-indigo-800 transition-colors group">
                                <div className="flex items-center text-slate-700 dark:text-slate-300 font-medium text-sm group-hover:text-indigo-600 dark:group-hover:text-indigo-400">
                                    <ClipboardList className="w-4 h-4 mr-3 text-slate-400 group-hover:text-indigo-500 transition-colors" /> Project Preferences
                                </div>
                                <div className="w-6 h-6 rounded-full bg-white dark:bg-slate-800 shadow-sm flex items-center justify-center text-slate-400 group-hover:text-indigo-500 transition-colors">
                                    <ArrowRight className="w-3 h-3" />
                                </div>
                            </button>

                            <button onClick={() => navigate('/student/milestones')} className="flex items-center justify-between p-3.5 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700/50 hover:bg-emerald-50 hover:border-emerald-200 dark:hover:bg-emerald-900/20 dark:hover:border-emerald-800 transition-colors group">
                                <div className="flex items-center text-slate-700 dark:text-slate-300 font-medium text-sm group-hover:text-emerald-600 dark:group-hover:text-emerald-400">
                                    <CheckCircle className="w-4 h-4 mr-3 text-slate-400 group-hover:text-emerald-500 transition-colors" /> Synopsis Submissions
                                </div>
                                <div className="w-6 h-6 rounded-full bg-white dark:bg-slate-800 shadow-sm flex items-center justify-center text-slate-400 group-hover:text-emerald-500 transition-colors">
                                    <ArrowRight className="w-3 h-3" />
                                </div>
                            </button>

                            <button onClick={() => navigate('/student/team')} className="flex items-center justify-between p-3.5 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700/50 hover:bg-purple-50 hover:border-purple-200 dark:hover:bg-purple-900/20 dark:hover:border-purple-800 transition-colors group">
                                <div className="flex items-center text-slate-700 dark:text-slate-300 font-medium text-sm group-hover:text-purple-600 dark:group-hover:text-purple-400">
                                    <Users className="w-4 h-4 mr-3 text-slate-400 group-hover:text-purple-500 transition-colors" /> View Team Roster
                                </div>
                                <div className="w-6 h-6 rounded-full bg-white dark:bg-slate-800 shadow-sm flex items-center justify-center text-slate-400 group-hover:text-purple-500 transition-colors">
                                    <ArrowRight className="w-3 h-3" />
                                </div>
                            </button>
                        </div>
                    </div>

                    {/* Mentor Info — FIX (Bug 1): render one entry per assigned mentor */}
                    {isUnassigned ? (
                        <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 flex flex-col items-center justify-center text-center min-h-[250px]">
                            <Users className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
                            <h4 className="font-bold text-slate-800 dark:text-slate-200 mb-1">No Mentor Assigned</h4>
                            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[200px]">A mentor will be assigned to your team shortly.</p>
                        </div>
                    ) : (
                        <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 flex flex-col">
                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-4">
                                <Users className="w-5 h-5 mr-2 text-indigo-500" />
                                Assigned Mentor{mentorList.length > 1 ? 's' : ''}
                            </h3>
                            <div className="space-y-3 mb-5 flex-1">
                                {mentorList.map((m, idx) => (
                                    <div key={m.id || idx} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                                        <img
                                            src={`https://ui-avatars.com/api/?name=${encodeURIComponent(m.name || 'M')}&background=6366f1&color=fff`}
                                            alt={m.name}
                                            className="w-10 h-10 rounded-full border-2 border-indigo-100 dark:border-indigo-900 shrink-0"
                                        />
                                        <div className="min-w-0">
                                            <p className="font-bold text-slate-800 dark:text-slate-200 text-sm truncate">{m.name}</p>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate">{m.email || 'No Email'}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <button onClick={() => navigate('/student/mentor')} className="w-full bg-slate-900 dark:bg-indigo-600 hover:bg-slate-800 dark:hover:bg-indigo-700 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors shadow-sm active:scale-95">
                                View Full Profile{mentorList.length > 1 ? 's' : ''}
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </motion.div>
    );
};

export default DashboardOverview;
