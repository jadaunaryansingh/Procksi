import React, { useState, useEffect } from 'react';
import { 
    Github, RefreshCw, Eye, Search, AlertTriangle, AlertOctagon, 
    BrainCircuit, Award, Shield, GitCommit, GraduationCap, X, 
    CheckCircle2, XCircle, ArrowRight, ExternalLink, Users, Cpu, FileText, Activity, Code, Clock, BarChart4, Loader2, Sparkles, User, FolderSync, GitBranch, Zap
} from 'lucide-react';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamDisplayLabel } from '../lib/globalFilters';

const ScoreBar = ({ value = 0 }) => {
    const color = value >= 75 ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]' : value >= 45 ? 'bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.3)]' : 'bg-rose-500 shadow-[0_0_10px_rgba(239,68,68,0.3)]';
    return (
        <div className="h-2 w-full bg-slate-100 dark:bg-slate-700/60 rounded-full overflow-hidden mt-2">
            <div className={`h-full rounded-full transition-all duration-700 ease-out ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
        </div>
    );
};

const ScoreCircle = ({ value = 0, size = 'md' }) => {
    const cls = value >= 75 ? 'text-emerald-500 border-emerald-500/20 dark:border-emerald-500/40 bg-emerald-500/5' : value >= 45 ? 'text-amber-500 border-amber-500/20 dark:border-amber-500/40 bg-amber-500/5' : 'text-rose-500 border-rose-500/20 dark:border-rose-500/40 bg-rose-500/5';
    const dim = size === 'lg' ? 'w-28 h-28 text-3xl' : 'w-14 h-14 text-lg';
    return (
        <div className={`rounded-full border-2 flex flex-col items-center justify-center font-black transition-all ${cls} ${dim} shadow-inner`}>
            <span>{Math.round(value)}</span>
            {size === 'lg' && <span className="text-[10px] uppercase font-black tracking-widest text-slate-400 mt-1">Score</span>}
        </div>
    );
};

const Chip = ({ children, color = 'slate' }) => {
    const map = {
        slate:   'bg-slate-100 animate-pulse dark:bg-slate-700/60 text-slate-600 dark:text-slate-300 border-slate-200/55 dark:border-slate-600/35',
        indigo:  'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 border-indigo-100 dark:border-indigo-900/30',
        emerald: 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-900/30',
        rose:    'bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-900/30',
        amber:   'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-900/30',
    };
    return <span className={`inline-block px-3 py-1 rounded-xl text-[10px] font-black tracking-wider uppercase border ${map[color] || map.slate}`}>{children}</span>;
};

const SectionHead = ({ icon: Icon, label }) => (
    <h4 className="font-extrabold text-slate-800 dark:text-slate-200 flex items-center gap-2.5 text-sm mb-4">
        <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-500">
            <Icon size={15} />
        </div>
        {label}
    </h4>
);

export default function RepoAnalysis() {
    const [teams, setTeams] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    
    // Detailed View State
    const [selectedTeamId, setSelectedTeamId] = useState(null);
    const [detailData, setDetailData] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState(null);
    const [activeTab, setActiveTab] = useState('overview');
    
    // Trigger / Refresh Status
    const [triggeringTeamId, setTriggeringTeamId] = useState(null);
    const [triggerMsg, setTriggerMsg] = useState(null);
    const [triggerAllLoading, setTriggerAllLoading] = useState(false);

    const { filterRows, semesterMap } = useGlobalFilters();

    const fetchTeams = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await api.getTeamsAnalysis();
            setTeams(Array.isArray(data) ? data : []);
        } catch (err) {
            setError(err.message || 'Failed to fetch repository analysis list');
        } finally {
            setLoading(false);
        }
    };

    const silentFetchTeams = async () => {
        try {
            const data = await api.getTeamsAnalysis();
            setTeams(Array.isArray(data) ? data : []);
        } catch (err) {
            console.error('Silent fetch teams analysis failed:', err);
        }
    };

    useEffect(() => {
        fetchTeams();
        const interval = setInterval(silentFetchTeams, 3000);
        return () => clearInterval(interval);
    }, []);

    // Poll for queued or running jobs on open detail view
    useEffect(() => {
        if (!selectedTeamId || !detailData) return;
        const status = detailData.analysis?.analysis_status;
        if (status === 'queued' || status === 'running') {
            const interval = setInterval(async () => {
                try {
                    const res = await api.getTeamAnalysisDetail(selectedTeamId);
                    setDetailData(res);
                    if (res.analysis?.analysis_status !== 'queued' && res.analysis?.analysis_status !== 'running') {
                        clearInterval(interval);
                        // Refresh main list
                        const listData = await api.getTeamsAnalysis();
                        setTeams(Array.isArray(listData) ? listData : []);
                    }
                } catch (e) {
                    console.error('Polling error:', e);
                }
            }, 3000);
            return () => clearInterval(interval);
        }
    }, [selectedTeamId, detailData]);

    const handleViewDetail = async (teamId) => {
        setSelectedTeamId(teamId);
        setDetailData(null);
        setDetailLoading(true);
        setDetailError(null);
        setActiveTab('overview');
        try {
            const data = await api.getTeamAnalysisDetail(teamId);
            setDetailData(data);
        } catch (err) {
            setDetailError(err.message || 'Failed to fetch team details');
        } finally {
            setDetailLoading(false);
        }
    };

    const handleTrigger = async (e, teamId) => {
        e.stopPropagation();
        setTriggeringTeamId(teamId);
        setTriggerMsg(null);
        try {
            const res = await api.triggerTeamAnalysis(teamId);
            setTriggerMsg({ type: 'success', text: res.message || 'Analysis triggered successfully!' });
            
            // Reload list and detail if active
            const listData = await api.getTeamsAnalysis();
            setTeams(Array.isArray(listData) ? listData : []);
            
            if (selectedTeamId === teamId) {
                const detailRes = await api.getTeamAnalysisDetail(teamId);
                setDetailData(detailRes);
            }
        } catch (err) {
            setTriggerMsg({ type: 'error', text: err.message || 'Failed to trigger analysis' });
        } finally {
            setTriggeringTeamId(null);
            setTimeout(() => setTriggerMsg(null), 5000);
        }
    };

    const handleTriggerAll = async () => {
        const teamsToTrigger = filteredTeams.filter(t => t.repository_url && !['queued', 'running'].includes(t.analysis_status));
        if (teamsToTrigger.length === 0) {
            setTriggerMsg({ type: 'error', text: 'No teams with configured repositories available to analyze.' });
            return;
        }
        
        if (!window.confirm(`Are you sure you want to trigger analysis for all ${teamsToTrigger.length} teams in the list?`)) {
            return;
        }
        
        setTriggerAllLoading(true);
        setTriggerMsg({ type: 'success', text: `Starting batch analysis for ${teamsToTrigger.length} teams...` });
        
        let successCount = 0;
        let failCount = 0;
        
        for (const team of teamsToTrigger) {
            try {
                await api.triggerTeamAnalysis(team.id);
                successCount++;
            } catch (err) {
                console.error(`Failed to trigger analysis for team ${team.id}:`, err);
                failCount++;
            }
        }
        
        // Reload list
        const listData = await api.getTeamsAnalysis();
        setTeams(Array.isArray(listData) ? listData : []);
        
        setTriggerAllLoading(false);
        setTriggerMsg({
            type: successCount > 0 ? 'success' : 'error',
            text: `Batch analysis completed: ${successCount} successfully triggered, ${failCount} failed.`
        });
        setTimeout(() => setTriggerMsg(null), 8000);
    };

    const filteredTeams = filterRows(teams).filter(t => {
        const term = searchTerm.toLowerCase();
        return (
            t.team_name?.toLowerCase().includes(term) ||
            t.id?.toLowerCase().includes(term) ||
            t.mentor_name?.toLowerCase().includes(term) ||
            (t.members && t.members.some(m => m.toLowerCase().includes(term))) ||
            (t.repository_url && t.repository_url.toLowerCase().includes(term))
        );
    });

    // Stats calculations
    const totalRepos = filteredTeams.length;
    const completedCount = filteredTeams.filter(t => t.analysis_status === 'completed').length;
    const runningCount = filteredTeams.filter(t => ['queued', 'running'].includes(t.analysis_status)).length;
    const missingOrFailedCount = filteredTeams.filter(t => !t.repository_url || ['failed', 'dlq'].includes(t.analysis_status)).length;

    // Extracting nested metrics for detailed rendering
    const analysisRecord = detailData?.analysis || {};
    const rawReport = (() => {
        if (!analysisRecord.raw_report) return {};
        try {
            return typeof analysisRecord.raw_report === 'string' 
                ? JSON.parse(analysisRecord.raw_report) 
                : analysisRecord.raw_report;
        } catch (e) {
            return {};
        }
    })();

    const scores = {
        quality: rawReport.analysis?.qualityScore ?? analysisRecord.quality_score ?? 0,
        security: rawReport.analysis?.securityScore ?? analysisRecord.security_score ?? 0,
        originality: rawReport.analysis?.originalityScore ?? analysisRecord.originality_score ?? 0,
        architecture: rawReport.analysis?.architectureScore ?? analysisRecord.architecture_score ?? 0,
        documentation: rawReport.analysis?.documentationScore ?? analysisRecord.documentation_score ?? 0,
        implementation: rawReport.analysis?.implementationScore ?? 0,
        engineering: rawReport.analysis?.engineeringScore ?? 0,
        effort: rawReport.analysis?.effortScore ?? 0
    };

    const overallScore = rawReport.analysis?.totalScore ?? scores.quality ?? 0;
    const healthStatus = rawReport.healthStatus || '';
    const riskFlags = rawReport.riskFlags || [];
    const mat = rawReport.maturity || {};
    const commitsBlock = rawReport.commits || {};
    const totalCommits = commitsBlock.total ?? analysisRecord.commit_count_30d ?? 0;
    const lastWeekCommits = commitsBlock.lastWeek ?? 0;
    const contribDist = commitsBlock.contributionDistribution || [];
    const md = rawReport.marksDeduction || {};
    const techStack = (() => {
        const raw = rawReport.techStack || rawReport.tech_stack || analysisRecord.tech_stack || [];
        if (typeof raw === 'string') {
            try {
                const parsed = JSON.parse(raw);
                return Array.isArray(parsed) ? parsed : [parsed];
            } catch (e) {
                return raw.split(',').map(s => s.trim()).filter(Boolean);
            }
        }
        return Array.isArray(raw) ? raw : [];
    })();
    
    const cm = rawReport.codeMetrics || {};
    const languages = (() => {
        const lwp = cm.languagesWithPct;
        if (lwp && typeof lwp === 'object' && !Array.isArray(lwp))
            return Object.entries(lwp).map(([name, pct]) => ({ name, percentage: pct }));
        if (Array.isArray(lwp)) return lwp;
        if (Array.isArray(cm.languages)) {
            return cm.languages.map(n => typeof n === 'object' ? { name: n.name || n.language || '', percentage: n.percentage ?? n.pct ?? 0 } : { name: String(n), percentage: 0 });
        }
        return [];
    })();

    const sec = rawReport.security || {};
    const secIssues = [...(sec.issues || []), ...(sec.leaks || []), ...(sec.hardcodedValues || [])];
    const scoreInsights = rawReport.scoreInsights || [];

    const ai = rawReport.aiAnalysis || {};
    const strengths = ai.strengths || [];
    const improvements = ai.improvements || [];
    const overallRecommendation = ai.overallRecommendation || "";
    const featureAnalysis = ai.featureAnalysis || [];
    const suggestedFeatures = ai.suggestedFeatures || [];
    
    const bestPractices = sec.bestPractices || [];
    const bt = rawReport.branchTracking || {};
    const branches = bt.branchDetails || bt.branches || [];
    const cq = rawReport.commitQuality || {};
    const exampleFakeCommits = cq.exampleFakeCommits || [];

    const tabs = [
        { id: 'overview', label: 'Overview', Icon: Code },
        { id: 'code', label: 'Code & Security', Icon: Shield },
        { id: 'commits', label: 'Commits & Quality', Icon: GitCommit },
        { id: 'ai', label: 'AI Insights & Verdict', Icon: BrainCircuit },
        { id: 'grading', label: 'Student Grading', Icon: GraduationCap },
    ];

    return (
        <div className="space-y-6 max-w-7xl mx-auto px-1">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                    <h2 className="text-2xl font-black text-slate-900 dark:text-slate-100 flex items-center gap-3">
                        <div className="p-2 bg-indigo-600 text-white rounded-2xl shadow-[0_4px_12px_rgba(99,102,241,0.3)] dark:shadow-none">
                            <Github className="w-6 h-6 animate-pulse" />
                        </div>
                        <div>
                            <span>Repository Analysis Hub</span>
                            <span className="text-[10px] ml-3 inline-flex items-center gap-1 px-2.5 py-0.5 bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 font-bold uppercase rounded-full">
                                <Sparkles size={8} /> AI-Powered
                            </span>
                        </div>
                    </h2>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-lg leading-relaxed">
                        Audit project repositories, view granular code contributions, trace security flaws, and let AI score engineering performance.
                    </p>
                </div>
            </div>

            {/* Notification Bar */}
            {triggerMsg && (
                <div className={`p-4 rounded-2xl border text-xs font-bold flex items-center gap-2 shadow-sm animate-bounce ${
                    triggerMsg.type === 'success' 
                        ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200/50 dark:border-emerald-500/25 text-emerald-800 dark:text-emerald-400'
                        : 'bg-rose-50 dark:bg-rose-500/10 border-rose-200/50 dark:border-rose-500/25 text-rose-800 dark:text-rose-400'
                }`}>
                    {triggerMsg.type === 'success' ? <CheckCircle2 size={16} className="text-emerald-500" /> : <AlertOctagon size={16} className="text-rose-500" />}
                    {triggerMsg.text}
                </div>
            )}

            {/* Premium Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 animate-fade-in">
                {[
                    { label: 'Total Repositories', value: totalRepos, desc: 'Registered project groups', icon: FolderSync, colors: 'from-violet-500 to-indigo-600 text-white shadow-violet-500/10 dark:shadow-none' },
                    { label: 'AI Audited Successfully', value: completedCount, desc: 'Analysis reports resolved', icon: CheckCircle2, colors: 'from-emerald-500 to-teal-600 text-white shadow-emerald-500/10 dark:shadow-none' },
                    { label: 'Sync In Progress', value: runningCount, desc: 'Pending processing queue', icon: Clock, colors: 'from-amber-400 to-orange-500 text-white shadow-amber-500/10 dark:shadow-none', spin: runningCount > 0 },
                    { label: 'Failed / Missing Url', value: missingOrFailedCount, desc: 'Action required', icon: AlertTriangle, colors: 'from-rose-500 to-pink-650 text-white shadow-rose-500/10 dark:shadow-none' }
                ].map((stat, i) => (
                    <div key={i} className={`relative overflow-hidden bg-gradient-to-br ${stat.colors} p-5 rounded-3xl shadow-xl flex flex-col justify-between min-h-[120px] transform hover:scale-[1.02] hover:-translate-y-1 transition-all duration-300`}>
                        <div className="absolute right-0 top-0 opacity-10 pointer-events-none transform translate-x-4 -translate-y-4">
                            <stat.icon size={110} />
                        </div>
                        <div className="flex justify-between items-center z-10">
                            <span className="text-[10px] font-black uppercase tracking-wider opacity-80">{stat.label}</span>
                            <stat.icon size={18} className={`opacity-90 ${stat.spin ? 'animate-spin' : ''}`} />
                        </div>
                        <div className="mt-4 z-10">
                            <span className="text-3xl font-black block leading-none">{stat.value}</span>
                            <span className="text-[10px] opacity-75 font-medium mt-1.5 block">{stat.desc}</span>
                        </div>
                    </div>
                ))}
            </div>

            {/* Filter Panel */}
            <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-white dark:bg-slate-800 backdrop-blur-md p-4 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                <div className="relative w-full md:w-96">
                    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input 
                        type="text" 
                        placeholder="Search by team ID, student, mentor, repository..." 
                        value={searchTerm} 
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2.5 border border-slate-200/70 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900 rounded-2xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium transition-all"
                    />
                </div>
                <div className="flex items-center gap-2.5 w-full md:w-auto">
                    <button 
                        onClick={handleTriggerAll}
                        disabled={triggerAllLoading || loading}
                        className="flex-1 md:flex-none flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-750 disabled:opacity-50 text-white rounded-2xl text-xs font-black shadow-md hover:shadow-lg transition-all"
                    >
                        <RefreshCw size={12} className={triggerAllLoading ? 'animate-spin' : ''} /> 
                        {triggerAllLoading ? 'ANALYZING BATCH...' : 'ANALYZE ALL TEAMS'}
                    </button>
                    <button 
                        onClick={fetchTeams} 
                        className="flex-1 md:flex-none flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-900 dark:bg-slate-105 hover:bg-slate-800 dark:hover:bg-slate-200 text-white dark:text-slate-900 rounded-2xl text-xs font-black shadow-md hover:shadow-lg transition-all"
                    >
                        <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> REFRESH LIST
                    </button>
                </div>
            </div>

            {/* Main Content List */}
            {loading ? (
                <div className="flex flex-col items-center justify-center p-24 bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm min-h-[300px]">
                    <div className="p-4 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-500 rounded-full animate-spin mb-4">
                        <RefreshCw className="w-8 h-8" />
                    </div>
                    <span className="text-sm font-bold text-slate-500">Decrypting repository records...</span>
                </div>
            ) : error ? (
                <div className="p-12 text-center bg-white dark:bg-slate-800 rounded-3xl border border-rose-200/40 dark:border-rose-500/20 text-rose-500 shadow-sm">
                    <AlertOctagon className="w-10 h-10 mx-auto mb-3 animate-bounce" />
                    <p className="font-extrabold text-sm mb-1">Failed to Load Records</p>
                    <p className="text-xs text-slate-400">{error}</p>
                </div>
            ) : filteredTeams.length === 0 ? (
                <div className="p-16 text-center bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm text-slate-400">
                    <AlertTriangle className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p className="font-extrabold text-sm mb-1">No matches found</p>
                    <p className="text-xs text-slate-400">Try modifying your global filters or typing a different search query.</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredTeams.map((t) => {
                        const statusColor = t.analysis_status === 'completed' ? 'emerald' : ['failed', 'dlq'].includes(t.analysis_status) ? 'rose' : ['queued', 'running'].includes(t.analysis_status) ? 'amber' : 'slate';
                        return (
                            <div 
                                key={t.id} 
                                className="group relative bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-205 dark:border-slate-700/50 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col justify-between overflow-hidden"
                            >
                                {/* Glowing status mesh corner */}
                                <div className={`absolute top-0 right-0 w-24 h-24 rounded-full filter blur-3xl opacity-5 pointer-events-none ${
                                    statusColor === 'emerald' ? 'bg-emerald-500' : statusColor === 'amber' ? 'bg-amber-500' : statusColor === 'rose' ? 'bg-rose-500' : 'bg-slate-400'
                                }`} />
                                
                                <div>
                                    {/* Header block */}
                                    <div className="flex justify-between items-start gap-2 mb-3">
                                        <div>
                                            <span className="text-[10px] font-black tracking-widest text-slate-400 uppercase font-mono block">TEAM ID: {t.id.split('-T').pop()}</span>
                                            <h3 className="font-black text-slate-900 dark:text-white text-base mt-0.5">{teamDisplayLabel(t.id, t, semesterMap)}</h3>
                                        </div>
                                        <Chip color={statusColor}>
                                            {t.analysis_status === 'queued' ? 'Queued' : t.analysis_status === 'running' ? 'Running' : t.analysis_status === 'completed' ? 'Completed' : t.analysis_status === 'failed' ? 'Failed' : 'No Analysis'}
                                        </Chip>
                                    </div>

                                    {/* Member info */}
                                    <div className="space-y-2 mt-4 text-xs font-semibold text-slate-600 dark:text-slate-350">
                                        <div className="flex items-center gap-2">
                                            <User size={13} className="text-slate-400" />
                                            <span className="text-[11px] truncate max-w-full"><span className="text-slate-400">Mentor: </span>{t.mentor_name}</span>
                                        </div>
                                        <div className="flex items-start gap-2">
                                            <Users size={13} className="text-slate-400 mt-0.5" />
                                            <div className="flex flex-wrap gap-1">
                                                {t.members.length > 0 ? (
                                                    t.members.slice(0, 3).map((m, idx) => (
                                                        <span key={idx} className="bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-700/60 text-[9px] px-2 py-0.5 rounded-full font-bold">
                                                            {m}
                                                        </span>
                                                    ))
                                                ) : <span className="text-[10px] text-slate-400 font-normal">No students allocated</span>}
                                                {t.members.length > 3 && <span className="text-[9px] font-bold text-indigo-500">+{t.members.length - 3} more</span>}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Repository details */}
                                    <div className="mt-4 pt-3.5 border-t border-slate-100 dark:border-slate-700/60">
                                        {t.repository_url ? (
                                            <a 
                                                href={t.repository_url} 
                                                target="_blank" 
                                                rel="noopener noreferrer" 
                                                className="text-xs font-mono font-medium text-indigo-600 dark:text-indigo-405 hover:underline flex items-center gap-1 px-1"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <ExternalLink size={11} className="shrink-0" />
                                                <span className="truncate">{t.repository_url.replace('https://github.com/', '')}</span>
                                            </a>
                                        ) : (
                                            <div className="flex items-center gap-1 text-slate-400 text-xs pl-1">
                                                <AlertTriangle size={11} /> No Git Link Configured
                                            </div>
                                        )}
                                    </div>

                                    {/* Scores display */}
                                    {t.analysis_status === 'completed' && (
                                        <div className="grid grid-cols-3 gap-2 mt-4 bg-slate-50 dark:bg-slate-900/40 p-3 rounded-2xl border border-slate-100 dark:border-slate-700/30 text-center font-mono">
                                            <div>
                                                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block">Quality</span>
                                                <span className="text-xs font-black text-emerald-500 mt-1 block">{t.scores.quality}</span>
                                            </div>
                                            <div>
                                                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block">Security</span>
                                                <span className="text-xs font-black text-amber-500 mt-1 block">{t.scores.security}</span>
                                            </div>
                                            <div>
                                                <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest block">Originality</span>
                                                <span className="text-xs font-black text-purple-500 mt-1 block">{t.scores.originality}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Actions footer */}
                                <div className="mt-5 flex gap-2.5 w-full pt-3 border-t border-slate-100 dark:border-slate-700/40">
                                    <button 
                                        onClick={() => handleViewDetail(t.id)} 
                                        className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-800 dark:text-slate-200 rounded-xl text-xs font-extrabold shadow-sm transition-all"
                                    >
                                        <Eye size={12} /> View Full Report
                                    </button>
                                    <button 
                                        onClick={(e) => handleTrigger(e, t.id)} 
                                        disabled={!t.repository_url || triggeringTeamId === t.id || ['queued', 'running'].includes(t.analysis_status)}
                                        className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-extrabold shadow-md transition-all animate-pulse-slow"
                                    >
                                        {triggeringTeamId === t.id ? (
                                            <>
                                                <RefreshCw size={12} className="animate-spin" />
                                                <span>Syncing...</span>
                                            </>
                                        ) : (
                                            <>
                                                <RefreshCw size={12} />
                                                <span>Trigger Sync</span>
                                            </>
                                        )}
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Analysis Detailed Drawer / Modal */}
            {selectedTeamId && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-md transition-opacity">
                    <div className="absolute inset-0" onClick={() => setSelectedTeamId(null)} />
                    
                    {/* Modal Content */}
                    <div className="relative w-full max-w-4xl bg-slate-50 dark:bg-slate-900 shadow-2xl h-[90vh] rounded-3xl overflow-hidden flex flex-col z-10 border border-slate-200/85 dark:border-slate-800 animate-scale-in">
                        {/* Header */}
                        <div className="p-6 bg-gradient-to-r from-slate-900 to-indigo-950 text-white border-b border-slate-850 flex justify-between items-center shrink-0">
                            <div>
                                <span className="text-[8px] font-black tracking-widest text-indigo-400 uppercase font-mono block">TEAM REPORT AUDIT</span>
                                <h3 className="text-lg font-black flex items-center gap-2 mt-0.5">
                                    <BrainCircuit className="text-indigo-400 w-5 h-5 animate-pulse" />
                                    {teams.find(t => t.id === selectedTeamId)?.team_name || `Team ${selectedTeamId}`}
                                </h3>
                                <p className="text-[10px] text-slate-400 mt-1 max-w-md font-medium">
                                    Repository: {teams.find(t => t.id === selectedTeamId)?.repository_url || 'Unspecified'}
                                </p>
                            </div>
                            <div className="flex items-center gap-3">
                                {teams.find(t => t.id === selectedTeamId)?.repository_url && (
                                    <a 
                                        href={teams.find(t => t.id === selectedTeamId)?.repository_url} 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/85 hover:bg-slate-800 border border-slate-700/80 rounded-xl text-xs font-mono text-slate-400 hover:text-white"
                                    >
                                        <ExternalLink size={11} />
                                        GitHub URL
                                    </a>
                                )}
                                <button 
                                    onClick={(e) => handleTrigger(e, selectedTeamId)}
                                    disabled={detailLoading || ['queued', 'running'].includes(detailData?.analysis?.analysis_status)}
                                    className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-black shadow-md"
                                >
                                    {['queued', 'running'].includes(detailData?.analysis?.analysis_status) ? <RefreshCw size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                                    Sync Repo
                                </button>
                                <button 
                                    onClick={() => setSelectedTeamId(null)}
                                    className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition-all"
                                >
                                    <X size={18} />
                                </button>
                            </div>
                        </div>

                        {/* Modal Body */}
                        <div className="flex-1 overflow-y-auto p-6 space-y-6">
                            {detailLoading ? (
                                <div className="flex flex-col items-center justify-center p-24 min-h-[400px]">
                                    <div className="relative mb-6">
                                        <div className="w-16 h-16 rounded-full border-2 border-dashed border-indigo-500 animate-spin" />
                                        <BrainCircuit className="w-8 h-8 text-indigo-500 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
                                    </div>
                                    <span className="text-sm font-bold text-slate-500">Unpacking engineering scores and audit logs...</span>
                                </div>
                            ) : detailError ? (
                                <div className="p-8 text-center bg-white dark:bg-slate-800 rounded-2xl border border-rose-200/50 dark:border-rose-500/20 text-rose-550">
                                    <AlertOctagon className="w-10 h-10 mx-auto mb-2" />
                                    <p className="font-extrabold text-sm">Failed to Load Details</p>
                                    <p className="text-xs text-slate-400 mt-1">{detailError}</p>
                                </div>
                            ) : !detailData ? (
                                <div className="p-12 text-center bg-white dark:bg-slate-800 rounded-2xl text-slate-450">
                                    <AlertOctagon className="w-10 h-10 mx-auto mb-2 opacity-50" />
                                    <p className="font-extrabold text-sm">No analysis record found.</p>
                                </div>
                            ) : ['queued', 'running'].includes(analysisRecord.analysis_status) ? (
                                <div className="p-10 text-center bg-white dark:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 rounded-3xl flex flex-col items-center justify-center min-h-[400px] shadow-sm">
                                    <div className="w-16 h-16 rounded-full bg-indigo-50 dark:bg-indigo-950/30 flex items-center justify-center mb-6 border-2 border-dashed border-indigo-500 animate-spin" style={{ animationDuration: '8s' }}>
                                        <BrainCircuit className="w-8 h-8 text-indigo-600 dark:text-indigo-400 animate-pulse" />
                                    </div>
                                    <h3 className="text-lg font-black text-slate-800 dark:text-slate-100 mb-2">Analyzing Repository</h3>
                                    <p className="text-slate-400 text-xs max-w-sm mb-6 leading-relaxed">
                                        The remote agent is auditing project quality metrics, inspecting commit histories, and running safety scans.
                                    </p>
                                    <div className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 text-[10px] font-black uppercase rounded-full tracking-wider">
                                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping" />
                                        Sync Status: {analysisRecord.analysis_status}
                                    </div>
                                    {detailData?.analysis?.progress !== undefined && (
                                        <div className="w-48 bg-slate-100 dark:bg-slate-750 h-1.5 rounded-full mt-4 overflow-hidden">
                                            <div className="bg-indigo-600 h-full rounded-full transition-all duration-300" style={{ width: `${detailData.analysis.progress}%` }} />
                                        </div>
                                    )}
                                    <p className="text-slate-400 text-[10px] mt-8 font-medium">This panel updates automatically as synchronization resolves.</p>
                                </div>
                            ) : !analysisRecord.raw_report ? (
                                <div className="p-12 text-center bg-white dark:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 rounded-3xl flex flex-col items-center justify-center min-h-[300px]">
                                    <AlertOctagon className="w-12 h-12 text-slate-300 dark:text-slate-600 mb-3" />
                                    <p className="font-extrabold text-sm text-slate-500">Report Content Pending Sync</p>
                                    <p className="text-xs text-slate-400 max-w-sm mt-2 font-medium">No results data exists yet. Confirm that the repository is public and trigger a fresh synchronization sync using the buttons above.</p>
                                </div>
                            ) : (
                                <div className="space-y-6">
                                    {/* Tabs */}
                                    <div className="flex items-center gap-1.5 border-b border-slate-200 dark:border-slate-800 pb-2.5 overflow-x-auto font-bold">
                                        {tabs.map(({ id, label, Icon }) => (
                                            <button 
                                                key={id} 
                                                onClick={() => setActiveTab(id)}
                                                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-black tracking-wide whitespace-nowrap transition-all ${
                                                    activeTab === id 
                                                        ? 'bg-indigo-600 text-white shadow-md' 
                                                        : 'text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60'
                                                }`}
                                            >
                                                <Icon size={13} /> {label}
                                            </button>
                                        ))}
                                    </div>

                                    {/* Tab content: Overview */}
                                    {activeTab === 'overview' && (
                                        <div className="space-y-5">
                                            {/* Top Strip */}
                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm flex flex-col items-center justify-center text-center">
                                                    <ScoreCircle value={overallScore} size="lg" />
                                                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-4">Total Score Verdict</span>
                                                    {rawReport.projectType && <div className="mt-2.5"><Chip color="indigo">{rawReport.projectType}</Chip></div>}
                                                </div>
                                                
                                                <div className="md:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                    <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm flex flex-col items-center justify-center text-center min-h-[140px]">
                                                        <SectionHead icon={Activity} label="Repository Health" />
                                                        <div className={`text-3.5xl font-black capitalize mt-1.5 ${healthStatus === 'healthy' ? 'text-emerald-500 animate-pulse' : healthStatus === 'warning' ? 'text-amber-500' : 'text-rose-500'}`}>
                                                            {healthStatus || 'Healthy'}
                                                        </div>
                                                        <div className="mt-3.5 flex flex-col items-center gap-1">
                                                            {riskFlags.length > 0 ? (
                                                                riskFlags.slice(0, 3).map((f, i) => (
                                                                    <div key={i} className="flex items-center justify-center gap-1.5 text-[10px] text-slate-500 font-semibold font-mono">
                                                                        <AlertTriangle size={11} className="text-amber-500 shrink-0" />
                                                                        {f.replace(/_/g, ' ').toUpperCase()}
                                                                    </div>
                                                                ))
                                                            ) : (
                                                                <div className="flex items-center justify-center gap-1.5 text-[10px] text-emerald-500 font-bold">
                                                                    <CheckCircle2 size={11} /> PASSES BASIC STRESS FLAGS
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>

                                                    <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm flex flex-col items-center justify-center text-center min-h-[140px]">
                                                        <SectionHead icon={CheckCircle2} label="Code Maturity" />
                                                        <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-2 justify-center">
                                                            {[
                                                                { label: 'Tests',  val: mat.hasTests  },
                                                                { label: 'CI/CD',  val: mat.hasCI    },
                                                                { label: 'Docker', val: mat.hasDocker },
                                                                { label: 'README', val: mat.hasReadme },
                                                            ].map(({ label, val }) => (
                                                                <div key={label} className="flex items-center justify-center gap-1.5 text-xs font-semibold text-slate-655 dark:text-slate-400">
                                                                    {val ? <CheckCircle2 size={13} className="text-emerald-500 shrink-0" /> : <XCircle size={13} className="text-slate-300 dark:text-slate-600 shrink-0" />}
                                                                    {label}
                                                                </div>
                                                            ))}
                                                        </div>
                                                        {mat.testFiles > 0 && <div className="text-[9px] font-mono text-slate-400 mt-2.5">{mat.testFiles} test files detected</div>}
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Score breakdowns */}
                                            <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                <SectionHead icon={Award} label="Core Metric Breakdown" />
                                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                                                    {[
                                                        { label: 'Quality', value: scores.quality },
                                                        { label: 'Security', value: scores.security },
                                                        { label: 'Originality', value: scores.originality },
                                                        { label: 'Architecture', value: scores.architecture },
                                                        { label: 'Documentation', value: scores.documentation },
                                                        { label: 'Implementation', value: scores.implementation },
                                                        { label: 'Engineering', value: scores.engineering },
                                                        { label: 'Effort', value: scores.effort }
                                                    ].map(({ label, value }) => (
                                                        <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-2xl p-4 border border-slate-100 dark:border-slate-750 text-center">
                                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block mb-1">{label}</span>
                                                            <span className={`text-xl font-black ${value >= 75 ? 'text-emerald-500' : value >= 45 ? 'text-amber-500' : 'text-rose-500'} font-mono`}>
                                                                {Math.round(value)}
                                                            </span>
                                                            <ScoreBar value={Math.round(value)} />
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Deductions & Basic stats */}
                                            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                                <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm flex flex-col justify-center">
                                                    <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest block mb-1">Total Commits (30d)</span>
                                                    <span className="text-4xl font-black text-slate-800 dark:text-slate-100 font-mono">{totalCommits}</span>
                                                    {lastWeekCommits > 0 && <span className="text-[9px] font-semibold text-emerald-500 mt-2 inline-flex items-center gap-1">+{lastWeekCommits} commits this week</span>}
                                                </div>

                                                <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm sm:col-span-2">
                                                    <SectionHead icon={AlertTriangle} label="Penalty Deductions Audit" />
                                                    {md.applied ? (
                                                        <div className="p-2.5 bg-rose-500/5 dark:bg-rose-500/10 border border-rose-500/10 rounded-2xl">
                                                            <div className="text-2xl font-black text-rose-500">-{md.marksDeductedPercentage ?? 0}% Penalty Marks</div>
                                                            <p className="text-xs text-rose-600 mt-1.5 font-medium">{md.reason || 'Deductions applied by analyzer triggers.'}</p>
                                                        </div>
                                                    ) : (
                                                        <div className="flex items-center gap-2 text-emerald-500 text-xs font-black mt-2">
                                                            <div className="p-1 rounded-full bg-emerald-500/10">
                                                                <CheckCircle2 size={16} />
                                                            </div>
                                                            <span>No deduction metrics applied to this team repository.</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Low Score insights */}
                                            {scoreInsights.length > 0 && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm space-y-4">
                                                    <SectionHead icon={AlertOctagon} label="Low Score Remediation Guide" />
                                                    {scoreInsights.map((insight, idx) => {
                                                        const scoreVal = insight.score ?? 0;
                                                        const name = insight.dimension || 'Dimension';
                                                        const reasons = insight.likely_reasons || insight.reasons || [];
                                                        const steps = insight.improvement_steps || insight.steps || [];
                                                        return (
                                                            <div key={idx} className="border-l-4 border-rose-500 bg-rose-500/5 dark:bg-rose-950/5 p-4 rounded-r-2xl">
                                                                <div className="font-extrabold text-slate-850 dark:text-slate-100 text-xs mb-2 flex items-center justify-between">
                                                                    <span>{name}</span>
                                                                    <span className="font-mono text-rose-500 bg-rose-500/10 px-2 py-0.5 rounded-lg text-[10px] font-black">{scoreVal}/100</span>
                                                                </div>
                                                                {reasons.length > 0 && (
                                                                    <div className="mb-2 pl-1">
                                                                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block mb-1">Likely Causes:</span>
                                                                        <ul className="list-disc list-inside text-xs text-rose-600 dark:text-rose-400 pl-1 space-y-0.5">
                                                                            {reasons.map((r, i) => <li key={i}>{r}</li>)}
                                                                        </ul>
                                                                    </div>
                                                                )}
                                                                {steps.length > 0 && (
                                                                    <div className="pl-1">
                                                                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block mb-1">Improvement Steps:</span>
                                                                        <ul className="text-xs text-emerald-600 dark:text-emerald-400 pl-1 space-y-0.5 font-medium">
                                                                            {steps.map((s, i) => <li key={i} className="flex items-start gap-1"><span>+</span><span>{s}</span></li>)}
                                                                        </ul>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Tab content: Code & Security */}
                                    {activeTab === 'code' && (
                                        <div className="space-y-5">
                                            {/* Tech Stack & Languages */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={Cpu} label="Identified Stack & Architecture" />
                                                    {techStack.length > 0 ? (
                                                        <div className="flex flex-wrap gap-1.5 mt-2">
                                                            {techStack.map((t, i) => (
                                                                <Chip key={i} color="indigo">{typeof t === 'string' ? t : t.technology || t.name || t}</Chip>
                                                            ))}
                                                        </div>
                                                    ) : <p className="text-xs text-slate-400 font-medium mt-1">No technology nodes parsed.</p>}
                                                    {cm.architecturePattern && (
                                                        <div className="text-xs text-slate-600 dark:text-slate-400 mt-5 border-t border-slate-100 dark:border-slate-700/60 pt-4 font-semibold">
                                                            <span className="text-slate-500 dark:text-slate-400 font-black">Pattern: </span>
                                                            {cm.architecturePattern.toUpperCase()}
                                                        </div>
                                                    )}
                                                </div>

                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={FileText} label="Languages & Line Counts" />
                                                    {languages.length > 0 ? (
                                                        <div className="space-y-3 mt-2">
                                                            {languages.slice(0, 5).map((l, i) => {
                                                                const name = l.name || l.language || l;
                                                                const pct  = l.percentage ?? 0;
                                                                return (
                                                                    <div key={i}>
                                                                        <div className="flex justify-between text-xs font-extrabold text-slate-600 dark:text-slate-400 mb-1 font-mono">
                                                                            <span>{name}</span>
                                                                            <span>{typeof pct === 'number' ? pct.toFixed(1) : pct}%</span>
                                                                        </div>
                                                                        <div className="h-1.5 bg-slate-100 animate-pulse dark:bg-slate-750 rounded-full overflow-hidden">
                                                                            <div className="h-full bg-gradient-to-r from-indigo-500 to-violet-650 rounded-full" style={{ width: `${pct}%` }} />
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    ) : <p className="text-xs text-slate-400 font-medium mt-1">No languages mapped.</p>}
                                                    {cm.totalLinesOfCode > 0 && (
                                                        <div className="text-[10px] text-slate-500 mt-5 border-t border-slate-100 dark:border-slate-700/60 pt-4 font-mono font-bold uppercase tracking-wider">
                                                            Metrics: {cm.totalLinesOfCode.toLocaleString()} lines across {cm.totalFiles} files
                                                        </div>
                                                    )}
                                                </div>
                                            </div>

                                            {/* Security findings */}
                                            <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                <SectionHead icon={Shield} label={`Vulnerabilities & Alerts (${secIssues.length} Risks)`} />
                                                {secIssues.length > 0 ? (
                                                    <div className="space-y-3 mt-3">
                                                        {secIssues.map((issue, idx) => (
                                                            <div key={idx} className="p-4 bg-rose-500/5 dark:bg-rose-950/10 border border-rose-500/10 dark:border-rose-900/35 rounded-2xl flex items-start gap-3">
                                                                <AlertTriangle className="text-rose-500 shrink-0 w-4 h-4 mt-0.5" />
                                                                <div>
                                                                    <div className="flex items-center gap-2 flex-wrap">
                                                                        <span className="text-xs font-black text-slate-800 dark:text-slate-100">{issue.title || issue.message || 'Static Scan Vulnerability'}</span>
                                                                        <span className="px-2 py-0.5 bg-rose-500/15 text-rose-500 text-[8px] font-black rounded uppercase tracking-wider">
                                                                            {issue.severity || 'HIGH'}
                                                                        </span>
                                                                    </div>
                                                                    <p className="text-[11px] text-slate-500 font-medium mt-1.5 font-mono">{issue.description || issue.filePath || 'Potential security vulnerability.'}</p>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-2 text-emerald-500 text-xs font-black py-2">
                                                        <div className="p-1 rounded-full bg-emerald-500/10">
                                                            <CheckCircle2 size={16} />
                                                        </div>
                                                        <span>No severe vulnerabilities, leaks, or credentials exposed.</span>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Best Practices Checklist Audit */}
                                            {bestPractices.length > 0 && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={Eye} label="Best Practices & Quality Checklist Audit" />
                                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                                                        {/* Summary block */}
                                                        <div className="bg-slate-50 dark:bg-slate-900/40 rounded-2xl p-4 border border-slate-100 dark:border-slate-750/30 space-y-2">
                                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block mb-2">Checklist Summary</span>
                                                            {bestPractices.map((bp, i) => {
                                                                const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                                                                return (
                                                                    <div key={i} className="flex items-center gap-2 text-xs font-bold">
                                                                        {ok ? (
                                                                            <span className="text-emerald-500 flex items-center gap-1 font-black shrink-0"><CheckCircle2 size={12} /> OK</span>
                                                                        ) : (
                                                                            <span className="text-rose-500 flex items-center gap-1 font-black shrink-0"><XCircle size={12} /> NO</span>
                                                                        )}
                                                                        <span className="text-slate-700 dark:text-slate-350 truncate">{bp.practice_name || bp.title || bp.name || "Practice"}</span>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                        {/* Detailed recommendations */}
                                                        <div className="md:col-span-2 space-y-3 max-h-[400px] overflow-y-auto pr-1">
                                                            {bestPractices.map((bp, i) => {
                                                                const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                                                                return (
                                                                    <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-2xl p-3.5 bg-slate-50/20 dark:bg-slate-900/20">
                                                                        <div className="flex items-center justify-between mb-1.5">
                                                                            <div className="flex items-center gap-1.5 font-bold text-xs text-slate-800 dark:text-slate-200">
                                                                                {ok ? <CheckCircle2 size={12} className="text-emerald-500 shrink-0" /> : <XCircle size={12} className="text-rose-500 shrink-0" />}
                                                                                {bp.practice_name || bp.title || bp.name || "Practice"}
                                                                            </div>
                                                                            <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${
                                                                                ok ? "bg-emerald-500/10 text-emerald-500" : "bg-rose-500/10 text-rose-500"
                                                                            }`}>
                                                                                {ok ? "PASSED" : bp.severity || "REQUIRED"}
                                                                            </span>
                                                                        </div>
                                                                        {bp.recommendation && <p className="text-[11px] text-slate-500 font-medium leading-relaxed">{bp.recommendation}</p>}
                                                                        {bp.files_found?.length > 0 && (
                                                                            <div className="text-[9px] text-slate-400 mt-2 font-mono truncate">
                                                                                Inspected: {bp.files_found.join(", ")}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Tab content: Commits */}
                                    {activeTab === 'commits' && (
                                        <div className="space-y-5">
                                            {/* Commit timeline */}
                                            <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                <SectionHead icon={GitCommit} label="Commit Contributions Timeline" />
                                                {commitsBlock.timeline && commitsBlock.timeline.length > 0 ? (
                                                    <div className="mt-6 flex items-end gap-1.5 h-48 border-b border-slate-200 dark:border-slate-700 pb-2">
                                                        {(() => {
                                                            const timeline = commitsBlock.timeline.map(t => ({ name: t.date || t.week || '', commits: t.commits || 0 }));
                                                            const maxCommits = Math.max(...timeline.map(t => t.commits), 1);
                                                            return timeline.map((t, idx) => {
                                                                const heightPct = (t.commits / maxCommits) * 100;
                                                                return (
                                                                    <div key={idx} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                                                                        {/* Tooltip */}
                                                                        <div className="absolute bottom-full mb-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none bg-slate-900 text-[10px] text-white px-2 py-1 rounded-xl shadow-2xl font-black whitespace-nowrap z-25 border border-slate-700">
                                                                            {t.name}: {t.commits} commits
                                                                        </div>
                                                                        {/* Bar */}
                                                                        <div 
                                                                            className="w-full bg-gradient-to-t from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 rounded-t transition-all duration-300 shadow-sm cursor-pointer"
                                                                            style={{ height: `${heightPct}%`, minHeight: t.commits > 0 ? '4px' : '1px' }}
                                                                        />
                                                                        {/* Label */}
                                                                        <span className="text-[8px] font-mono text-slate-400 mt-2 truncate max-w-full block">
                                                                            {t.name.split('-').slice(1).join('-') || t.name}
                                                                        </span>
                                                                    </div>
                                                                );
                                                            });
                                                        })()}
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-slate-400 font-medium">No commit timeline activity data available.</p>
                                                )}
                                            </div>

                                            {/* Contributor contributions */}
                                            <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                <SectionHead icon={Users} label="Commit Distribution & Code Metrics" />
                                                {contribDist.length > 0 ? (
                                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
                                                        {contribDist.map((c, i) => (
                                                            <div key={i} className="bg-slate-50/50 dark:bg-slate-900/40 rounded-2xl p-4 border border-slate-100 dark:border-slate-750">
                                                                <div className="flex items-center justify-between mb-2">
                                                                    <span className="font-extrabold text-slate-800 dark:text-slate-100 text-xs block truncate">{c.contributorName || 'Contributor'}</span>
                                                                    <span className="font-extrabold font-mono text-indigo-600 dark:text-indigo-405 text-xs">{c.commits} commits</span>
                                                                </div>
                                                                <div className="space-y-1.5 text-[10px] text-slate-500 font-semibold mt-3">
                                                                    <div className="flex justify-between font-mono">
                                                                        <span>Lines Added:</span>
                                                                        <span className="text-emerald-600">+{c.linesAdded}</span>
                                                                    </div>
                                                                    <div className="flex justify-between font-mono">
                                                                        <span>Lines Deleted:</span>
                                                                        <span className="text-rose-600">-{c.linesDeleted}</span>
                                                                    </div>
                                                                    <div className="mt-3.5 pt-2.5 border-t border-slate-100 dark:border-slate-800">
                                                                        <div className="flex justify-between text-slate-600 dark:text-slate-400 font-bold mb-1">
                                                                            <span>Commit percentage</span>
                                                                            <span>{Math.round(c.percentage)}%</span>
                                                                        </div>
                                                                        <div className="h-1 bg-slate-100 animate-pulse dark:bg-slate-750 rounded-full overflow-hidden">
                                                                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${c.percentage}%` }} />
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : <p className="text-xs text-slate-400 font-medium">No contributor distribution stats found.</p>}
                                            </div>

                                            {/* Commit Quality and Plagiarism Checks */}
                                            {(cq.fakeCommits !== undefined || exampleFakeCommits.length > 0) && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm space-y-4">
                                                    <SectionHead icon={AlertTriangle} label="Commit Quality & Authenticity Audit" />
                                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                        <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-750 rounded-2xl">
                                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block mb-1">Suspicious / Fake Commits</span>
                                                            <span className={`text-2xl font-black font-mono ${cq.fakeCommits > 0 ? "text-rose-500 animate-pulse" : "text-emerald-500"}`}>
                                                                {cq.fakeCommits ?? 0}
                                                            </span>
                                                            {cq.fakeCommitPercentage !== undefined && (
                                                                <span className="text-[10px] text-slate-400 block mt-1">({cq.fakeCommitPercentage}% of total commits)</span>
                                                            )}
                                                        </div>
                                                        <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-750 rounded-2xl flex items-center justify-between">
                                                            <div>
                                                                <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block mb-1">Authenticity Verdict</span>
                                                                <span className={`text-sm font-black uppercase ${cq.fakeCommits > 0 ? "text-rose-500" : "text-emerald-500"}`}>
                                                                    {cq.fakeCommits > 0 ? "SUSPICIOUS INFLATION DETECTED" : "PASSED CODE SIGNATURES"}
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {exampleFakeCommits.length > 0 && (
                                                        <div className="mt-3 space-y-3">
                                                            <span className="text-[9px] font-black text-slate-400 uppercase tracking-wider block pl-1">Exposed Suspicious Commits:</span>
                                                            {exampleFakeCommits.map((item, idx) => (
                                                                <div key={idx} className="p-3.5 bg-rose-500/5 dark:bg-rose-950/15 border border-rose-500/10 rounded-2xl">
                                                                    <div className="flex justify-between items-start gap-2 mb-1.5 flex-wrap">
                                                                        <span className="text-[11px] font-extrabold text-slate-800 dark:text-slate-100 font-mono truncate max-w-sm">
                                                                            Hash: {item.hash?.slice(0, 8) || "N/A"} &mdash; {item.message || "No commit message"}
                                                                        </span>
                                                                        <span className="text-[9px] font-black text-rose-500 uppercase">{item.author || "Unknown"}</span>
                                                                    </div>
                                                                    {item.reason && <p className="text-[11px] text-rose-600 dark:text-rose-400 font-medium font-mono">Flag: {item.reason}</p>}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Git Branch Details */}
                                            {branches.length > 0 && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm overflow-x-auto">
                                                    <SectionHead icon={GitBranch} label={`Git Branch Management (${bt.totalBranches ?? branches.length} active branches)`} />
                                                    <table className="w-full text-left text-xs border-collapse">
                                                        <thead>
                                                            <tr className="border-b border-slate-100 dark:border-slate-750 text-slate-400 font-black uppercase tracking-wider text-[9px] font-mono">
                                                                <th className="py-2.5">Branch Name</th>
                                                                <th className="py-2.5 text-right">Commits</th>
                                                                <th className="py-2.5 text-right">Lead Contributor</th>
                                                                <th className="py-2.5 text-right">Last Action</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-slate-50 dark:divide-slate-750/30 text-xs font-semibold text-slate-700 dark:text-slate-350">
                                                            {branches.map((b, i) => {
                                                                const bname = typeof b === "string" ? b : (b.name || b.branch || "");
                                                                const isMain = bname === bt.mainBranch || bname === 'main' || bname === 'master';
                                                                return (
                                                                    <tr key={i} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/20">
                                                                        <td className="py-3 font-mono">
                                                                            <div className="flex items-center gap-1.5">
                                                                                <GitBranch size={12} className="text-indigo-500 shrink-0" />
                                                                                <span>{bname}</span>
                                                                                {isMain && <span className="ml-1"><Chip color="emerald">default</Chip></span>}
                                                                            </div>
                                                                        </td>
                                                                        <td className="py-3 text-right font-bold font-mono">{b.totalCommits ?? "?"}</td>
                                                                        <td className="py-3 text-right font-medium">{b.primaryAuthor || "?"}</td>
                                                                        <td className="py-3 text-right font-mono text-slate-400 text-[10px]">
                                                                            {b.lastCommitDate ? new Date(b.lastCommitDate).toLocaleDateString() : "?"}
                                                                        </td>
                                                                    </tr>
                                                                );
                                                            })}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Tab content: AI Analysis */}
                                    {activeTab === 'ai' && (
                                        <div className="space-y-5">
                                            {/* AI Verdict */}
                                            {rawReport.aiAnalysis?.verdict && (
                                                <div className="bg-gradient-to-br from-indigo-500/10 to-violet-500/5 dark:from-indigo-955/20 dark:to-violet-955/10 p-5 rounded-3xl border border-indigo-500/10 shadow-sm relative overflow-hidden">
                                                    <div className="absolute right-3 top-3 opacity-30 text-indigo-500 animate-pulse">
                                                        <Sparkles size={32} />
                                                    </div>
                                                    <SectionHead icon={Sparkles} label="AI Recommendation Verdict" />
                                                    <p className="text-xs text-slate-700 dark:text-slate-200 leading-relaxed font-bold italic mb-2 mt-1">
                                                        &ldquo;{rawReport.aiAnalysis.verdict}&rdquo;
                                                    </p>
                                                    {rawReport.aiAnalysis.verdictReasoning && (
                                                        <p className="text-xs text-slate-500 leading-relaxed mt-3 pt-3 border-t border-indigo-500/10">
                                                            {rawReport.aiAnalysis.verdictReasoning}
                                                        </p>
                                                    )}
                                                </div>
                                            )}

                                            {/* Strengths & Improvements */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                                <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={CheckCircle2} label="Key Strengths" />
                                                    {strengths.length > 0 ? (
                                                        <ul className="space-y-2.5 mt-2">
                                                            {strengths.map((str, idx) => (
                                                                <li key={idx} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-300 font-semibold font-medium">
                                                                    <span className="text-emerald-500 font-black text-md mt-[-2px]">&bull;</span>
                                                                    <span>{str}</span>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    ) : <p className="text-xs text-slate-400 font-medium">No highlights compiled.</p>}
                                                </div>

                                                <div className="bg-white dark:bg-slate-800 p-5 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={AlertTriangle} label="Recommended Improvements" />
                                                    {improvements.length > 0 ? (
                                                        <ul className="space-y-2.5 mt-2">
                                                            {improvements.map((imp, idx) => (
                                                                <li key={idx} className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-350 font-semibold font-medium">
                                                                    <span className="text-rose-500 font-black text-md mt-[-2px]">&bull;</span>
                                                                    <span>{imp}</span>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    ) : <p className="text-xs text-slate-400 font-medium">No improvement flags raised.</p>}
                                                </div>
                                            </div>

                                            {/* Feature analysis mapping */}
                                            {featureAnalysis.length > 0 && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={Cpu} label="Detailed Feature-by-Feature Implementation Audit" />
                                                    <div className="space-y-3.5 mt-2">
                                                        {featureAnalysis.map((fa, idx) => {
                                                            const name = fa.feature || fa.name || "Feature";
                                                            const status = fa.status || "N/A";
                                                            const quality = fa.quality || "N/A";
                                                            const details = fa.details || "";
                                                            const isHigh = quality.toLowerCase().includes("good") || quality.toLowerCase().includes("high");
                                                            return (
                                                                <div key={idx} className="border border-slate-100 dark:border-slate-750/70 rounded-2xl p-4">
                                                                    <div className="flex items-center gap-2 flex-wrap mb-2">
                                                                        <span className="font-extrabold text-slate-800 dark:text-slate-200 text-xs">{name}</span>
                                                                        <span className="px-2 py-0.5 rounded text-[8px] font-black uppercase bg-indigo-500/10 text-indigo-500">{status}</span>
                                                                        <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${
                                                                            isHigh 
                                                                                ? "bg-emerald-500/10 text-emerald-500" 
                                                                                : "bg-amber-500/10 text-amber-500"
                                                                        }`}>
                                                                            Quality: {quality}
                                                                        </span>
                                                                    </div>
                                                                    {details && <p className="text-xs text-slate-500 font-medium leading-relaxed">{details}</p>}
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Suggested features */}
                                            {suggestedFeatures.length > 0 && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={Zap} label="AI Suggested Roadmap Features" />
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                                                        {suggestedFeatures.map((sf, idx) => {
                                                            const name = sf.feature || sf.name || "Feature";
                                                            const priority = sf.priority || "Medium";
                                                            const desc = sf.description || "";
                                                            const isCritical = priority.toLowerCase() === "critical" || priority.toLowerCase() === "high";
                                                            return (
                                                                <div key={idx} className="bg-slate-50 dark:bg-slate-900/40 rounded-2xl p-4 border border-slate-100 dark:border-slate-750 flex flex-col justify-between">
                                                                    <div>
                                                                        <div className="flex justify-between items-start gap-2 mb-2">
                                                                            <span className="font-bold text-slate-800 dark:text-slate-200 text-xs">{name}</span>
                                                                            <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${
                                                                                isCritical 
                                                                                    ? "bg-rose-500/10 text-rose-500" 
                                                                                    : "bg-slate-500/10 text-slate-500"
                                                                            }`}>
                                                                                {priority}
                                                                            </span>
                                                                        </div>
                                                                        {desc && <p className="text-[11px] text-slate-500 font-medium leading-relaxed">{desc}</p>}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Overall recommendations */}
                                            {overallRecommendation && (
                                                <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border-l-4 border-l-indigo-500 border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                    <SectionHead icon={Award} label="Overall AI Recommendation Summary" />
                                                    <p className="text-xs text-slate-700 dark:text-slate-200 leading-relaxed font-semibold">{overallRecommendation}</p>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Tab content: Student Grading */}
                                    {activeTab === 'grading' && (
                                        <div className="space-y-5">
                                            <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                                                <SectionHead icon={GraduationCap} label="AI Individual Contributor Grading Suggestion" />
                                                
                                                {rawReport.individualStudentScores && rawReport.individualStudentScores.length > 0 ? (
                                                    <div className="space-y-4 mt-3">
                                                        {rawReport.individualStudentScores.map((score, idx) => {
                                                            const sName = score.name || score.github || 'Contributor';
                                                            const finalScore = score.finalScore ?? 0;
                                                            return (
                                                                <div key={idx} className="p-4 bg-slate-50/50 dark:bg-slate-900/40 rounded-2xl border border-slate-100 dark:border-slate-750 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                                                    <div>
                                                                        <span className="font-black text-slate-900 dark:text-white block text-sm">{sName}</span>
                                                                        {score.github && <span className="text-[9px] text-slate-400 font-mono">@{score.github}</span>}
                                                                        
                                                                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 mt-3 text-[10px] text-slate-500 font-semibold font-mono">
                                                                            <div>Commits: <span className="font-extrabold text-slate-750 dark:text-slate-200">{score.commits ?? 0}</span></div>
                                                                            <div>Added: <span className="font-extrabold text-emerald-600">+{score.linesAdded ?? 0}</span></div>
                                                                            <div>Deleted: <span className="font-extrabold text-rose-600">-{score.linesDeleted ?? 0}</span></div>
                                                                            
                                                                            <div>Quality: <span className="font-extrabold text-slate-750 dark:text-slate-200">{score.qualityScore ?? 0}/100</span></div>
                                                                            <div>Effort: <span className="font-extrabold text-slate-750 dark:text-slate-200">{score.effortScore ?? 0}/100</span></div>
                                                                            <div>Deductions: <span className="font-extrabold text-rose-500">-{score.deductions ?? 0}</span></div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex flex-col items-center shrink-0 min-w-[100px] border-t sm:border-t-0 sm:border-l border-slate-200/60 dark:border-slate-750 pt-3 sm:pt-0 sm:pl-4">
                                                                        <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest text-center">AI Recommend Grade</span>
                                                                        <span className={`text-2xl font-black ${finalScore >= 75 ? 'text-emerald-500' : finalScore >= 45 ? 'text-amber-500' : 'text-rose-500'} font-mono mt-1`}>
                                                                            {Math.round(finalScore)}
                                                                        </span>
                                                                        <div className="w-full mt-2">
                                                                            <ScoreBar value={finalScore} />
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-slate-400 font-medium">No individual grading scores compiled.</p>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
