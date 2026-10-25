import React, { useState, useEffect } from 'react';
import { Users, FileText, ShieldCheck, Activity, ChevronRight, TrendingUp, UploadCloud, Calendar as CalendarIcon, FileBarChart, Clock, CalendarDays, Loader2, ChevronDown } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';

export default function Dashboard() {
    const { filters, updateFilter } = useGlobalFilters();
    const [stats, setStats] = useState(null);
    const [deadlines, setDeadlines] = useState([]);
    const [auditLogs, setAuditLogs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [activeSemesters, setActiveSemesters] = useState([]);
    const selectedSemester = filters.semesterId === 'all' ? 'ALL' : filters.semesterId;

    useEffect(() => {
        let isMounted = true;

        const loadDashboardConfigs = async () => {
            setIsLoading(true);
            try {
                const [semsRes, logsRes] = await Promise.all([
                    api.getSemesterConfig(),
                    api.getAuditLogs(1, 4),
                ]);

                if (!isMounted) return;

                const active = semsRes?.data?.filter(s => s.is_active) || [];
                setActiveSemesters(active);
                setAuditLogs(Array.isArray(logsRes?.data) ? logsRes.data : []);
            } catch (err) {
                console.error('Dashboard load error:', err);
            } finally {
                if (isMounted) setIsLoading(false);
            }
        };

        loadDashboardConfigs();
        return () => { isMounted = false; };
    }, []);

    useEffect(() => {
        let isMounted = true;

        const loadStats = async () => {
            try {
                const targetSemId = selectedSemester === 'ALL' ? null : selectedSemester;
                const [statusRes, deadlinesRes] = await Promise.all([
                    api.getDashboardStats(selectedSemester),
                    api.getDeadlines(targetSemId)
                ]);
                if (isMounted) {
                    setStats(statusRes?.data || null);
                    setDeadlines(Array.isArray(deadlinesRes?.data) ? deadlinesRes.data : []);
                }
            } catch (err) {
                console.error('Failed to update stats on semester change:', err);
            }
        };

        loadStats();
        return () => { isMounted = false; };
    }, [selectedSemester]);

    const handleSemesterChange = (semId) => {
        const targetFilterVal = semId === 'ALL' ? 'all' : semId;
        updateFilter('semesterId', targetFilterVal);
    };

    const STAT_CARDS = stats ? [
        { label: 'Total Students', value: stats.total_students, icon: Users, color: 'text-blue-500 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-500/20' },
        { label: 'Pending Proposals', value: stats.pending_proposals, icon: FileText, color: 'text-amber-500 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-500/20' },
        { label: 'Teams Validated', value: stats.validated_teams, icon: ShieldCheck, color: 'text-emerald-500 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-500/20' },
        { label: 'Total Mentors', value: stats.total_mentors, icon: Activity, color: 'text-indigo-500 dark:text-indigo-400', bg: 'bg-indigo-50 dark:bg-indigo-500/20' }
    ] : [];

    const semesterProgress = stats?.semester_progress ?? 0;

    const getDeadlineUrgency = (dateStr) => {
        if (!dateStr) return 'low';
        const diff = (new Date(dateStr) - new Date()) / (1000 * 60 * 60 * 24);
        if (diff < 3) return 'high';
        if (diff < 10) return 'medium';
        return 'low';
    };

    const getDeadlineTimeRemaining = (dateStr) => {
        if (!dateStr) return { text: 'Not set', color: 'text-slate-400' };
        const diffMs = new Date(dateStr) - new Date();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        
        if (diffMs < 0) {
            return { text: 'Passed', color: 'text-slate-400 dark:text-slate-500' };
        }
        if (diffDays === 0) {
            if (diffHours === 0) {
                const diffMins = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                return { text: `${diffMins}m remaining`, color: 'text-rose-500 font-extrabold animate-pulse' };
            }
            return { text: `${diffHours}h remaining`, color: 'text-rose-500 font-extrabold animate-pulse' };
        }
        if (diffDays < 3) {
            return { text: `${diffDays}d ${diffHours}h remaining`, color: 'text-rose-500 font-bold' };
        }
        if (diffDays < 10) {
            return { text: `${diffDays} days remaining`, color: 'text-amber-500 font-semibold' };
        }
        return { text: `${diffDays} days remaining`, color: 'text-emerald-500 font-semibold' };
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };

    const formatTime = (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    };

    const getTimeAgo = (isoStr) => {
        if (!isoStr) return '';
        const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
        if (diff < 60) return 'Just now';
        if (diff < 3600) return `${Math.floor(diff / 60)} mins ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
        return `${Math.floor(diff / 86400)} days ago`;
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[60vh]">
                <div className="flex flex-col items-center gap-4">
                    <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
                    <p className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">Loading Dashboard...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-8 relative z-10">
            <div className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-purple-800 rounded-3xl p-8 sm:p-10 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden flex flex-col md:flex-row items-center border border-indigo-500/30">
                {/* Background SVG abstract shape */}
                <div className="absolute inset-0 opacity-20 dark:opacity-30 mix-blend-overlay pointer-events-none">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                        <path d="M0,150 C250,300 750,0 1000,150 L1000,300 L0,300 Z" fill="currentColor"></path>
                    </svg>
                </div>
                
                <div className="relative z-10 flex-1">
                    <div className="inline-flex items-center px-3 py-1 bg-white/10 border border-white/20 rounded-full text-xs font-bold uppercase tracking-wider mb-4 text-indigo-100 shadow-sm backdrop-blur-sm">
                        <TrendingUp className="w-4 h-4 mr-2" /> {
                            stats?.semester_details 
                                ? Array.isArray(stats.semester_details)
                                    ? stats.semester_details.map(sem => `${sem.branch} Y${sem.academic_level}`).join(" & ")
                                    : `${stats.semester_details.branch} • Year ${stats.semester_details.academic_level} (${stats.semester_details.year} ${stats.semester_details.semester_type} semester)`
                                : stats?.active_semester && stats.active_semester !== 'NONE'
                                    ? `Semester ${stats.active_semester}`
                                    : 'Semester Ongoing'
                        }
                    </div>
                    <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black mb-4 tracking-tight leading-tight">Welcome back, <br/>{sessionStorage.getItem('admin_name') || 'Administrator'}.</h1>
                    <p className="text-indigo-100/90 max-w-lg leading-relaxed text-base sm:text-lg">Here is a comprehensive overview of the ongoing project evaluations, mentor allocations, and student team statuses for this semester.</p>
                </div>
                
                {/* 3D-ish SVG Graphic */}
                <div className="hidden lg:block relative z-10 w-64 h-64 shrink-0 transform hover:scale-105 transition-transform duration-700 pointer-events-none mr-8">
                    <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" className="w-full h-full drop-shadow-2xl">
                        <defs>
                            <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#818cf8" stopOpacity="0.9" />
                                <stop offset="100%" stopColor="#c084fc" stopOpacity="0.9" />
                            </linearGradient>
                            <filter id="glow">
                                <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
                                <feMerge>
                                    <feMergeNode in="coloredBlur"/>
                                    <feMergeNode in="SourceGraphic"/>
                                </feMerge>
                            </filter>
                        </defs>
                        <path d="M40,100 L100,20 L160,100 L100,180 Z" fill="url(#grad1)" />
                        <circle cx="100" cy="100" r="40" fill="white" fillOpacity="0.2" filter="url(#glow)" />
                        <path d="M60,100 L100,60 L140,100 L100,140 Z" fill="white" fillOpacity="0.9" />
                        <circle cx="100" cy="100" r="15" fill="#4f46e5" />
                    </svg>
                </div>
            </div>

            {/* Semester Filter Dropdown */}
            {activeSemesters.length > 0 && (
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white/60 dark:bg-slate-800/60 backdrop-blur-md p-5 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                    <div>
                        <h2 className="text-lg font-bold text-slate-800 dark:text-white flex items-center">
                            Filter Batch Metrics
                        </h2>
                        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-0.5">Filter stats cards below by a specific active semester/batch</p>
                    </div>
                    <div className="relative min-w-[240px]">
                        <select
                            value={selectedSemester}
                            onChange={(e) => handleSemesterChange(e.target.value)}
                            className="w-full appearance-none pl-4 pr-10 py-3 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 text-sm font-bold rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer transition-all duration-300"
                        >
                            <option value="ALL">All Active Semesters</option>
                            {activeSemesters.map(sem => (
                                <option key={sem.id} value={sem.id}>
                                    {sem.branch} Year {sem.academic_level} ({sem.year})
                                </option>
                            ))}
                        </select>
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-slate-500 dark:text-slate-400">
                            <ChevronDown className="w-4 h-4" />
                        </div>
                    </div>
                </div>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {STAT_CARDS.map((stat, idx) => {
                    const Icon = stat.icon;
                    return (
                        <div key={idx} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-6 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex items-center hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1 group">
                            <div className={`${stat.bg} ${stat.color} p-4 rounded-2xl mr-4 group-hover:scale-110 transition-transform duration-300 ring-1 ring-inset ring-slate-900/5 dark:ring-white/10`}>
                                <Icon className="w-7 h-7" />
                            </div>
                            <div>
                                <p className="text-sm font-bold text-slate-500 dark:text-slate-400 tracking-wide uppercase">{stat.label}</p>
                                <h3 className="text-3xl font-black text-slate-800 dark:text-white mt-1">{stat.value}</h3>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pb-2">
                <Link to="/admin/students" className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-4 rounded-2xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col items-center justify-center text-center hover:bg-indigo-50 dark:hover:bg-indigo-500/10 hover:border-indigo-200 dark:hover:border-indigo-500/30 transition-all group">
                    <div className="p-3 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-xl mb-3 group-hover:scale-110 transition-transform"><UploadCloud className="w-5 h-5" /></div>
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Upload Students</span>
                </Link>
                <Link to="/admin/proposals" className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-4 rounded-2xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col items-center justify-center text-center hover:bg-amber-50 dark:hover:bg-amber-500/10 hover:border-amber-200 dark:hover:border-amber-500/30 transition-all group">
                    <div className="p-3 bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-xl mb-3 group-hover:scale-110 transition-transform"><FileText className="w-5 h-5" /></div>
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Review Proposals</span>
                </Link>
                <Link to="/admin/schedule" className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-4 rounded-2xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col items-center justify-center text-center hover:bg-emerald-50 dark:hover:bg-emerald-500/10 hover:border-emerald-200 dark:hover:border-emerald-500/30 transition-all group">
                    <div className="p-3 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-xl mb-3 group-hover:scale-110 transition-transform"><CalendarIcon className="w-5 h-5" /></div>
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Schedule Panels</span>
                </Link>
                <Link to="/admin/results" className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md p-4 rounded-2xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 flex flex-col items-center justify-center text-center hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:border-blue-200 dark:hover:border-blue-500/30 transition-all group">
                    <div className="p-3 bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 rounded-xl mb-3 group-hover:scale-110 transition-transform"><FileBarChart className="w-5 h-5" /></div>
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">View Reports</span>
                </Link>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                
                <div className="lg:col-span-2">
                    {/* Activity Feed */}
                    <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6 sm:p-8">
                        <div className="flex justify-between items-center mb-8">
                            <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center">
                                <Activity className="w-5 h-5 mr-2 text-indigo-500" /> Recent System Activity
                            </h2>
                            <Link to="/admin/governance" className="text-sm font-bold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 bg-indigo-50 dark:bg-indigo-500/10 px-4 py-2 rounded-xl flex items-center transition-colors">
                                Audit Log <ChevronRight className="w-4 h-4 ml-1" />
                            </Link>
                        </div>
                        {auditLogs.length > 0 ? (
                            <div className="space-y-6 relative before:absolute before:inset-0 before:ml-[11px] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 dark:before:via-slate-700 before:to-transparent">
                                {auditLogs.map((log, idx) => {
                                    const statusColors = ['emerald', 'indigo', 'blue', 'amber'];
                                    const statusColor = statusColors[idx % statusColors.length];
                                    return (
                                        <div key={log.id || idx} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                                            <div className={`flex items-center justify-center w-6 h-6 rounded-full border-4 border-white dark:border-slate-800 bg-${statusColor}-500 dark:bg-${statusColor}-400 shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-sm z-10`}></div>
                                            <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] bg-slate-50 dark:bg-slate-900/50 p-4 rounded-2xl border border-slate-100 dark:border-slate-700/50 shadow-sm transition-all hover:shadow-md">
                                                <p className="text-sm font-bold text-slate-700 dark:text-slate-200">
                                                    {log.action}
                                                </p>
                                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{getTimeAgo(log.timestamp || log.time)}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-8">No recent activity recorded yet.</p>
                        )}
                    </div>
                </div>

                {/* Sidebar Column */}
                <div className="lg:col-span-1">
                    {/* Progress Circle Visual */}
                    <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-md rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6 sm:p-8 flex flex-col items-center justify-center text-center relative overflow-hidden h-full">
                        <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-b from-indigo-50 dark:from-indigo-500/5 to-transparent"></div>
                        
                        <div className="relative w-48 h-48 mb-8 mt-4">
                            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                                {/* Background Track */}
                                <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="8" className="text-slate-100 dark:text-slate-700/50"></circle>
                                {/* Progress Indicator */}
                                <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="8" strokeDasharray="282.7" strokeDashoffset={282.7 - (282.7 * semesterProgress / 100)} className="text-indigo-600 dark:text-indigo-400 drop-shadow-md" strokeLinecap="round"></circle>
                            </svg>
                            <div className="absolute inset-0 flex flex-col items-center justify-center">
                                <span className="text-4xl font-black text-slate-800 dark:text-white">{semesterProgress}%</span>
                                <span className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Completion</span>
                            </div>
                        </div>

                        <h3 className="text-xl font-black text-slate-800 dark:text-white mb-3">Semester Progression</h3>
                        <p className="text-sm text-slate-500 dark:text-slate-400 max-w-sm leading-relaxed">
                            {stats?.total_teams > 0
                                ? `${stats.validated_teams} of ${stats.total_teams} teams validated. ${semesterProgress}% of scheduled panels have been processed.`
                                : 'No teams have been formed yet for this semester.'}
                        </p>
                        
                        <Link to="/admin/semester-settings" className="mt-8 px-6 py-3 w-full bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg shadow-indigo-500/30 text-sm font-bold rounded-xl transition-all transform hover:-translate-y-0.5 focus:ring-4 focus:ring-indigo-500/20">
                            Manage Semester Rules
                        </Link>
                    </div>
                </div>
            </div>
            {/* Redesigned Upcoming Deadlines — full width below the grid */}
            <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-md border border-slate-200/50 dark:border-slate-700/50 p-6 sm:p-8">
                <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 mb-8">
                    <div>
                        <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center">
                            <CalendarDays className="w-6 h-6 mr-2 text-rose-500 animate-bounce" /> Academic Milestones & Deadlines
                        </h2>
                        <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1">Real-time status check on current semester milestone cutoffs.</p>
                    </div>
                    <Link to="/admin/governance" className="inline-flex items-center justify-center px-4 py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-xs font-black uppercase tracking-widest rounded-xl transition-all shadow-sm">
                        Configure Deadlines <ChevronRight className="w-4 h-4 ml-1" />
                    </Link>
                </div>
                {deadlines.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                        {deadlines.map((deadline, idx) => {
                            const urgency = getDeadlineUrgency(deadline.deadline_date);
                            const remaining = getDeadlineTimeRemaining(deadline.deadline_date);
                            return (
                                <div key={deadline.id || idx} className="bg-slate-50/50 dark:bg-slate-900/30 p-5 rounded-3xl border border-slate-100 dark:border-slate-700/50 hover:border-indigo-500/30 dark:hover:border-indigo-400/30 transition-all hover:-translate-y-1 hover:shadow-md flex flex-col justify-between group">
                                    <div>
                                        <div className="flex items-center justify-between mb-4">
                                            <span className={`w-8 h-8 rounded-2xl flex items-center justify-center ${urgency === 'high' ? 'bg-rose-50 text-rose-500 dark:bg-rose-500/20 dark:text-rose-400' : urgency === 'medium' ? 'bg-amber-50 text-amber-500 dark:bg-amber-500/20 dark:text-amber-400' : 'bg-emerald-50 text-emerald-500 dark:bg-emerald-500/20 dark:text-emerald-400'}`}>
                                                <Clock className="w-4.5 h-4.5" />
                                            </span>
                                            <span className={`text-[9px] uppercase font-black tracking-widest px-2.5 py-1 rounded-md ${urgency === 'high' ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400' : urgency === 'medium' ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400' : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400'}`}>
                                                {urgency} Priority
                                            </span>
                                        </div>
                                        <h4 className="text-sm font-black text-slate-800 dark:text-slate-200 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{deadline.title}</h4>
                                    </div>
                                    <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800/80">
                                        <div className="flex items-center text-xs font-bold text-slate-600 dark:text-slate-300">
                                            <CalendarIcon className="w-3.5 h-3.5 mr-2 text-slate-400" /> {formatDate(deadline.deadline_date) || 'No date set'}
                                        </div>
                                        <div className="flex items-center text-xs font-bold text-slate-600 dark:text-slate-300 mt-2">
                                            <Clock className="w-3.5 h-3.5 mr-2 text-slate-400" /> {formatTime(deadline.deadline_date) || 'No time set'}
                                        </div>
                                        <div className={`text-xs font-black mt-4 flex items-center gap-1.5 ${remaining.color}`}>
                                            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse"></span>
                                            {remaining.text}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-12">No deadlines configured for this semester yet.</p>
                )}
            </div>
        </div>
    );
}
