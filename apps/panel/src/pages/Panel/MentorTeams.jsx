import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Users, GitBranch, Clock, CheckCircle2, AlertTriangle, Search,
  ChevronRight, GitCommit, ExternalLink, UserCircle2, BookOpen,
  Layers, Filter, RefreshCw, TrendingUp, Video,
} from 'lucide-react';
import { mentorAPI } from '../../services/api';
import { requirePanelId, getMentorName } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

// ── Status badge helpers ────────────────────────────────────────────────────

const STATUS_META = {
  submitted: {
    label: 'Evaluated',
    cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30',
    dot: 'bg-emerald-500',
    icon: CheckCircle2,
  },
  Active: {
    label: 'Live Now',
    cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/30',
    dot: 'bg-indigo-500',
    icon: Clock,
  },
  Upcoming: {
    label: 'Upcoming',
    cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 border-amber-200 dark:border-amber-500/30',
    dot: 'bg-amber-500',
    icon: Clock,
  },
  missed: {
    label: 'Missed',
    cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-400 border-rose-200 dark:border-rose-500/30',
    dot: 'bg-rose-500',
    icon: AlertTriangle,
  },
};

const statusMeta = (team) => {
  if (team.is_evaluated) return STATUS_META.submitted;
  const statusKey = team.status?.toLowerCase();
  let meta = null;
  if (statusKey === 'active') meta = STATUS_META.Active;
  else if (statusKey === 'upcoming') meta = STATUS_META.Upcoming;
  else if (statusKey === 'missed') meta = STATUS_META.missed;
  return meta ?? {
    label: team.status ?? 'Unknown',
    cls: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-600',
    dot: 'bg-slate-400',
    icon: Clock,
  };
};

// ── Small helpers ───────────────────────────────────────────────────────────

const relativeTime = (iso) => {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso)) / 86400000);
  if (diff === 0) return 'today';
  if (diff === 1) return 'yesterday';
  return `${diff}d ago`;
};

const fmtSlot = (label) => label || '—';

// ── Team Card ───────────────────────────────────────────────────────────────

const TeamCard = ({ team, index, onEvaluate, onReceipt, semesterMap }) => {
  const meta = statusMeta(team);
  const StatusIcon = meta.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.04 }}
      className="group relative bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700/60 rounded-2xl p-5 hover:border-emerald-300 dark:hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/5 transition-all duration-200 cursor-default"
    >
      {/* Active pulse indicator */}
      {team.status === 'Active' && !team.is_evaluated && (
        <span className="absolute top-4 right-4 flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500" />
        </span>
      )}

      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-100 dark:from-emerald-900/30 dark:to-teal-900/20 flex items-center justify-center border border-emerald-200 dark:border-emerald-500/30 shrink-0">
            <Users size={18} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="min-w-0">
            <p className="font-black text-slate-900 dark:text-slate-100 text-sm truncate">
              {teamDisplayLabel(team.team_id, team, semesterMap)}
            </p>
          </div>
        </div>

        <span className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold rounded-full border ${meta.cls}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot} ${team.status === 'Active' && !team.is_evaluated ? 'animate-pulse' : ''}`} />
          {meta.label}
        </span>
      </div>

      {/* Project title */}
      {team.project_title && (
        <div className="mb-3 flex items-start gap-2">
          <BookOpen size={13} className="text-slate-400 shrink-0 mt-0.5" />
          <p className="text-xs text-slate-600 dark:text-slate-300 font-medium leading-tight line-clamp-2">
            {team.project_title}
          </p>
        </div>
      )}

      {/* Slot info */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 mb-4 text-xs text-slate-500 dark:text-slate-400">
        {team.slot_label && (
          <span className="flex items-center gap-1">
            <Clock size={11} /> {fmtSlot(team.slot_label)}
          </span>
        )}
        {team.venue && (
          <span className="flex items-center gap-1">
            <Layers size={11} /> {team.venue}
          </span>
        )}
      </div>

      {/* GitHub metrics */}
      {team.github_url && (
        <div className="mb-4 flex items-center justify-between bg-slate-50 dark:bg-slate-900/40 rounded-xl px-3 py-2 border border-slate-100 dark:border-slate-700/50">
          <div className="flex items-center gap-2">
            <GitBranch size={13} className="text-slate-400" />
            <span className="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[120px]" title={team.github_url}>
              {team.github_url.replace('https://github.com/', '')}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
            {team.commit_count_30d != null && (
              <span className="flex items-center gap-1">
                <GitCommit size={11} />
                {team.commit_count_30d} commits
              </span>
            )}
            {team.last_commit_at && (
              <span className="flex items-center gap-1">
                <TrendingUp size={11} />
                {relativeTime(team.last_commit_at)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {team.meet_link && !team.is_evaluated && (
          <a
            href={team.meet_link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold shadow-md shadow-blue-500/20 transition-all"
          >
            <Video size={13} /> Join Meet
          </a>
        )}
        {team.is_evaluated ? (
          <button
            onClick={() => onReceipt(team.team_id)}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30 rounded-xl text-xs font-bold hover:bg-emerald-100 dark:hover:bg-emerald-500/20 transition-colors"
          >
            <CheckCircle2 size={13} /> View Receipt
          </button>
        ) : team.status === 'Active' ? (
          <button
            onClick={() => onEvaluate(team.team_id)}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-md shadow-indigo-500/20 transition-all active:scale-95"
          >
            Enter Evaluation <ChevronRight size={13} />
          </button>
        ) : (
          <button
            disabled
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-100 dark:bg-slate-700/50 text-slate-400 rounded-xl text-xs font-medium cursor-not-allowed"
          >
            <Clock size={13} /> {team.status?.toLowerCase() === 'missed' ? 'Missed' : 'Not Started'}
          </button>
        )}

        {team.github_url && (
          <a
            href={team.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-xl bg-slate-100 dark:bg-slate-700/50 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            title="Open GitHub repository"
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>
    </motion.div>
  );
};

// ── Main Page ───────────────────────────────────────────────────────────────

const FILTER_OPTIONS = ['All', 'Upcoming', 'Active', 'Evaluated', 'Missed'];

const MentorTeams = () => {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(null);
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('All');
  const [refreshing, setRefreshing] = useState(false);
  const { filterRows, semesterMap } = useGlobalFilters();

  const mentorName = getMentorName();

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const panelId = requirePanelId();
      const [p, t] = await Promise.all([
        mentorAPI.getProfile(panelId),
        mentorAPI.getTeams(panelId),
      ]);
      setProfile(p);
      setTeams(t || []);
      setError(null);
    } catch (err) {
      console.error('MentorTeams: failed to load', err);
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    let list = filterRows(teams);
    if (filter === 'Evaluated') list = list.filter(t => t.is_evaluated);
    else if (filter === 'Missed') list = list.filter(t => t.status?.toLowerCase() === 'missed' && !t.is_evaluated);
    else if (filter === 'Active') list = list.filter(t => t.status === 'Active' && !t.is_evaluated);
    else if (filter === 'Upcoming') list = list.filter(t => t.status === 'Upcoming' && !t.is_evaluated);

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(t =>
        String(t.team_id).includes(q) ||
        (t.team_name || '').toLowerCase().includes(q) ||
        (t.project_title || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [teams, filter, search, filterRows]);

  // Stats
  const stats = useMemo(() => ({
    total: teams.length,
    evaluated: teams.filter(t => t.is_evaluated).length,
    active: teams.filter(t => t.status === 'Active' && !t.is_evaluated).length,
    upcoming: teams.filter(t => t.status === 'Upcoming' && !t.is_evaluated).length,
    missed: teams.filter(t => t.status?.toLowerCase() === 'missed' && !t.is_evaluated).length,
  }), [teams]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-emerald-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto mt-8">
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 px-5 py-4 rounded-2xl font-medium">
          Failed to load teams: {error}
        </div>
      </div>
    );
  }

  const progressPct = stats.total > 0 ? Math.round((stats.evaluated / stats.total) * 100) : 0;

  return (
    <div className="max-w-7xl mx-auto space-y-6">

      {/* ── Hero Header ── */}
      <div className="relative bg-gradient-to-br from-emerald-600 via-teal-700 to-emerald-800 rounded-3xl p-8 text-white overflow-hidden shadow-xl shadow-emerald-900/20">
        {/* Background pattern */}
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='30' height='30' viewBox='0 0 30 30' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M15 0 L30 15 L15 30 L0 15 Z' fill='none' stroke='white' stroke-width='0.5'/%3E%3C/svg%3E")` }} />
        <div className="absolute -top-20 -right-20 w-80 h-80 bg-white/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center backdrop-blur-md border border-white/30">
                <UserCircle2 size={22} className="text-white" />
              </div>
              <span className="text-emerald-200 text-sm font-bold uppercase tracking-widest">Mentor Portal</span>
            </div>
            <h2 className="text-3xl font-black tracking-tight mb-1">
              {mentorName ?? profile?.mentor_name ?? 'My Teams'}
            </h2>
            {profile?.assigned_round && (
              <p className="text-emerald-200/80 font-medium">{profile.assigned_round}</p>
            )}
          </div>

          {/* Progress ring area */}
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-4xl font-black">{stats.evaluated}</p>
              <p className="text-emerald-200 text-xs font-bold uppercase tracking-wider">Evaluated</p>
            </div>
            <div className="w-px h-12 bg-white/20" />
            <div className="text-center">
              <p className="text-4xl font-black">{stats.total}</p>
              <p className="text-emerald-200 text-xs font-bold uppercase tracking-wider">Assigned</p>
            </div>
            <div className="w-px h-12 bg-white/20" />
            <div className="text-center">
              <p className="text-4xl font-black text-amber-300">{stats.pending ?? stats.upcoming}</p>
              <p className="text-emerald-200 text-xs font-bold uppercase tracking-wider">Pending</p>
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div className="relative z-10 mt-6">
          <div data-tour="panel-teams-progress" className="flex justify-between text-xs text-emerald-200 font-bold mb-1.5">
            <span>Evaluation Progress</span>
            <span>{progressPct}% Complete</span>
          </div>
          <div className="w-full h-2.5 bg-white/20 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 1.2, ease: 'easeOut', delay: 0.3 }}
              className="h-full bg-white rounded-full relative overflow-hidden"
            >
              <motion.div
                animate={{ x: ['-100%', '200%'] }}
                transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}
                className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-emerald-300/40 to-transparent"
              />
            </motion.div>
          </div>
        </div>
      </div>

      {/* ── Stat chips row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Active Now', value: stats.active, color: 'indigo', icon: Clock },
          { label: 'Upcoming', value: stats.upcoming, color: 'amber', icon: Clock },
          { label: 'Evaluated', value: stats.evaluated, color: 'emerald', icon: CheckCircle2 },
          { label: 'Missed', value: stats.missed, color: 'rose', icon: AlertTriangle },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className={`bg-white dark:bg-slate-800 rounded-2xl border border-${color}-100 dark:border-${color}-500/20 p-4 flex items-center gap-3 shadow-sm`}>
            <div className={`w-9 h-9 rounded-xl bg-${color}-50 dark:bg-${color}-500/10 flex items-center justify-center text-${color}-500 dark:text-${color}-400 shrink-0`}>
              <Icon size={18} />
            </div>
            <div data-tour="panel-teams-filter">
              <p className={`text-2xl font-black text-${color}-600 dark:text-${color}-400`}>{value}</p>
              <p className="text-xs text-slate-500 font-bold">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* ── Search + Filter bar ── */}
      <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search team name, ID, or project..."
            className="w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl pl-9 pr-4 py-2.5 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500 font-medium"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Filter size={14} className="text-slate-400 shrink-0" />
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt}
              onClick={() => setFilter(opt)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                filter === opt
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-500/20'
                  : 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:border-emerald-300'
              }`}
            >
              {opt}
            </button>
          ))}
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-emerald-600 hover:border-emerald-300 transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* ── Teams Grid ── */}
      <AnimatePresence mode="wait">
        {filtered.length === 0 ? (
          <motion.div
            key="empty"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-center py-16 text-slate-400 dark:text-slate-500"
          >
            <Users size={40} className="mx-auto mb-3 opacity-40" />
            <p className="font-bold text-lg">No teams found</p>
            <p className="text-sm">Try adjusting the search or filter</p>
          </motion.div>
        ) : (
          <motion.div
            key="grid"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4"
          >
            {filtered.map((team, idx) => (
              <TeamCard
                key={team.team_id}
                team={team}
                index={idx}
                onEvaluate={id => navigate(`/panel/evaluation/${id}`)}
                onReceipt={id => navigate(`/panel/receipt/${id}`)}
                semesterMap={semesterMap}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MentorTeams;
