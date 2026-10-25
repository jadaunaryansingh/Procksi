import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Clock, MonitorPlay, ChevronRight,
  CheckCircle2, Loader2, AlertCircle, FileText, Activity
} from 'lucide-react';
import { motion } from 'framer-motion';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const statusColor = (status = '') => {
  const s = status.toLowerCase();
  if (s === 'valid' || s === 'approved') return 'emerald';
  if (s.includes('revision')) return 'amber';
  if (s === 'rejected') return 'rose';
  return 'slate';
};

const STATUS_COLORS = {
  valid: '#059669',      // emerald-600 (darker green)
  approved: '#34d399',   // emerald-400 (lighter green)
  revision: '#f59e0b',   // amber-500
  rejected: '#f43f5e',   // rose-500
  pending: '#3b82f6',    // blue-500
  default: '#64748b'     // slate-500
};

// Animation Variants
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 300, damping: 24 } }
};

const cardHoverVariants = {
  hover: { y: -5, transition: { type: 'spring', stiffness: 300 } }
};

const MentorHome = () => {
  const navigate = useNavigate();
  const { filterRows, semesterMap } = useGlobalFilters();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/dashboard')
      .then(r => {
        const payload = r.data?.data !== undefined ? r.data.data : r.data;
        setData(payload);
      })
      .catch(err => setError(err.response?.data?.detail || err.message || 'Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex justify-center items-center min-h-[400px]">
      <Loader2 className="w-10 h-10 animate-spin text-emerald-500" />
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center min-h-[400px] text-rose-500">
      <AlertCircle className="w-10 h-10 mb-4" />
      <p className="font-bold">{error}</p>
    </div>
  );

  const mentor = data?.mentor || {};
  const stats = data?.stats || {};
  const teams = data?.teams || [];
  const recentProposals = data?.recent_proposals || [];

  const filteredTeams = filterRows(teams);
  const filteredProposals = filterRows(recentProposals);

  const totalTeams = stats.assigned_teams ?? 0;
  const pendingReviews = stats.pending_proposals ?? 0;
  const pendingEvaluations = stats.pending_evaluations ?? 0;

  // Process data for the Chart
  const statusCounts = filteredTeams.reduce((acc, t) => {
    const s = t.status || 'Unknown';
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const chartData = Object.keys(statusCounts).map((key) => ({
    name: key,
    value: statusCounts[key]
  }));

  return (
    <motion.div
      className="max-w-7xl mx-auto space-y-4"
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      {/* Header */}
      <motion.div variants={itemVariants} className="flex justify-between items-end mb-1">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Dashboard Overview</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 font-medium">Welcome back, {mentor.name || '—'}</p>
        </div>
      </motion.div>

      {/* Bento Grid Top Row: Banner + Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Profile Banner */}
        <motion.div
          variants={itemVariants}
          className="lg:col-span-2 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-2xl p-6 relative overflow-hidden flex flex-col justify-between shadow-lg shadow-emerald-500/20"
        >
          {/* Decorative Background SVG */}
          <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`}}></div>
          
          <div className="relative z-10 flex flex-col sm:flex-row justify-between items-start sm:items-center h-full">
            <div>
              <h3 className="text-2xl font-black text-white mb-1">{mentor.name || '—'}</h3>
              <p className="text-sm text-emerald-100 font-medium mb-4">
                {mentor.expertise ? `Department of ${mentor.expertise}` : 'Faculty Mentor'} • Semester: {data?.semester?.name || '—'}
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex items-center gap-2 px-4 py-2 bg-white/20 backdrop-blur-md rounded-xl text-sm font-bold text-white border border-white/20 shadow-sm">
                  <Users size={16} /> {totalTeams} Team{totalTeams !== 1 ? 's' : ''} Assigned
                </span>
              </div>
            </div>

            <div className="mt-4 sm:mt-0 p-4 bg-white/10 rounded-2xl border border-white/20 backdrop-blur-md text-right shrink-0">
              <p className="text-xs font-bold text-emerald-100 uppercase tracking-widest mb-1">Pending Reviews</p>
              <p className="text-2xl font-black text-white">{pendingReviews}</p>
            </div>
          </div>
        </motion.div>

        {/* Analytics Mini-Chart Box */}
        <motion.div 
          variants={itemVariants}
          className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl p-5 border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] flex flex-col relative overflow-hidden transition-all duration-300 hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)]"
        >
          <div className="absolute top-0 right-0 w-32 h-32 bg-teal-500/10 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none"></div>
          <h3 className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2 relative z-10">
            <Activity size={16} className="text-teal-500" /> Team Status
          </h3>
          {/* The card is a grid item stretched to the height of its col-span-2
              sibling, so `flex-1` alone resolves against an indefinite height and
              ResponsiveContainer measures a box far taller than the donut is sized
              for — it overflowed the card padding and got clipped by overflow-hidden.
              A definite height gives the chart something real to measure. */}
          <div className="flex-1 min-h-[160px] h-[160px] relative z-10">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="50%"
                    innerRadius="55%"
                    outerRadius="80%"
                    paddingAngle={chartData.length > 1 ? 5 : 0}
                    dataKey="value"
                  >
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={STATUS_COLORS[entry.name.toLowerCase()] || STATUS_COLORS.default} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)', fontWeight: 'bold' }}
                    itemStyle={{ color: '#1e293b' }}
                  />
                  <Legend 
                    verticalAlign="bottom" 
                    align="center"
                    height={24} 
                    iconType="circle"
                    formatter={(value) => <span className="text-slate-600 dark:text-slate-400 capitalize">{value}</span>}
                    wrapperStyle={{ fontSize: '11px', fontWeight: 'bold', paddingTop: '10px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-400 font-medium text-sm">
                No teams to analyze
              </div>
            )}
          </div>
        </motion.div>
      </div>

      {/* Stat Cards Row */}
      <motion.div variants={containerVariants} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <motion.div data-tour="stat-total-teams" whileHover="hover" variants={cardHoverVariants} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl p-4 border border-white/50 dark:border-slate-700/50 flex justify-between items-center shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
          <div>
            <p className="text-xs font-bold text-slate-500 dark:text-slate-400 mb-1 tracking-widest uppercase">Total Teams</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-slate-100">{totalTeams}</h3>
          </div>
          <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-500/20 shadow-inner">
            <Users size={20} />
          </div>
        </motion.div>

        <motion.div data-tour="stat-pending-proposals" whileHover="hover" variants={cardHoverVariants} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl p-4 border border-white/50 dark:border-slate-700/50 flex justify-between items-center shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
          <div>
            <p className="text-xs font-bold text-slate-500 dark:text-slate-400 mb-1 tracking-widest uppercase">Pending Proposals</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-slate-100">{pendingReviews}</h3>
          </div>
          <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 text-amber-500 border border-amber-100 dark:border-amber-500/20 shadow-inner">
            <Clock size={20} />
          </div>
        </motion.div>

        <motion.div whileHover="hover" variants={cardHoverVariants} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl p-4 border border-white/50 dark:border-slate-700/50 flex justify-between items-center shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300">
          <div>
            <p className="text-xs font-bold text-slate-500 dark:text-slate-400 mb-1 tracking-widest uppercase">Evaluations</p>
            <h3 className="text-2xl font-black text-slate-800 dark:text-slate-100">{pendingEvaluations}</h3>
          </div>
          <div className="p-3 rounded-xl bg-teal-50 dark:bg-teal-500/10 text-teal-600 dark:text-teal-400 border border-teal-100 dark:border-teal-500/20 shadow-inner">
            <MonitorPlay size={20} />
          </div>
        </motion.div>
      </motion.div>

      {/* Two panels: Teams list + Recent proposals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Assigned teams Panel */}
        <motion.div variants={itemVariants} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] overflow-hidden flex flex-col relative transition-all duration-300">
          <div className="absolute top-0 left-0 w-40 h-40 bg-emerald-500/5 rounded-full blur-3xl -ml-10 -mt-10 pointer-events-none"></div>

          <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center relative z-10">
            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3 tracking-tight">
              <div className="p-2 bg-emerald-50 dark:bg-emerald-500/10 rounded-lg"><Users size={18} className="text-emerald-500" /></div>
              Assigned Teams
            </h3>
            <button onClick={() => navigate('/mentor/teams')} className="text-xs font-bold text-slate-500 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors flex items-center bg-slate-50 dark:bg-slate-800 px-3 py-1.5 rounded-full border border-slate-200 dark:border-slate-700 shadow-sm">
              View All <ChevronRight size={14} className="ml-1" />
            </button>
          </div>
          <motion.div 
            className="divide-y divide-slate-100 dark:divide-slate-700/50 flex-1 overflow-y-auto max-h-72 relative z-10 p-2"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {filteredTeams.length === 0 ? (
              <div className="p-10 text-center text-slate-400">
                <Users size={40} className="mx-auto mb-4 opacity-20" />
                <p className="font-bold text-sm">No teams assigned yet</p>
              </div>
            ) : filteredTeams.map(t => {
              const col = statusColor(t.status);
              return (
                <motion.div variants={itemVariants} key={t.id} className="flex items-center justify-between p-3 hover:bg-slate-50 dark:hover:bg-slate-700/40 rounded-xl transition-colors group">
                  <div className="min-w-0 flex-1">
                    <p className="font-bold text-slate-800 dark:text-slate-100 truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                      {t.project_title ? `${teamDisplayLabel(t.id, t, semesterMap)} - ${t.project_title}` : teamDisplayLabel(t.id, t, semesterMap)}
                    </p>
                    <p className="text-xs font-medium text-slate-500 mt-1 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                      {t.member_count} member{t.member_count !== 1 ? 's' : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 ml-4 shrink-0">
                    <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1 rounded-full border
                      bg-${col}-50 text-${col}-700 border-${col}-200
                      dark:bg-${col}-500/10 dark:text-${col}-400 dark:border-${col}-500/20 shadow-sm`}>
                      {t.status}
                    </span>
                    <button onClick={() => navigate(`/mentor/teams/${t.id}`)}
                      className="w-8 h-8 flex items-center justify-center bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-full text-slate-500 dark:text-slate-400 hover:bg-emerald-50 hover:text-emerald-600 dark:hover:bg-emerald-500/20 dark:hover:text-emerald-400 hover:border-emerald-200 dark:hover:border-emerald-500/30 shadow-sm opacity-0 group-hover:opacity-100 transition-all transform group-hover:scale-110">
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </motion.div>

        {/* Recent proposals Panel */}
        <motion.div variants={itemVariants} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-2xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] overflow-hidden flex flex-col relative transition-all duration-300">
          <div className="absolute top-0 right-0 w-40 h-40 bg-amber-500/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none"></div>

          <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center relative z-10">
            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3 tracking-tight">
              <div className="p-2 bg-amber-50 dark:bg-amber-500/10 rounded-lg"><FileText size={18} className="text-amber-500" /></div>
              Pending Proposals
            </h3>
          </div>
          <motion.div 
            className="divide-y divide-slate-100 dark:divide-slate-700/50 flex-1 overflow-y-auto max-h-72 relative z-10 p-2"
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            {filteredProposals.length === 0 ? (
              <div className="p-10 text-center text-slate-400">
                <CheckCircle2 size={40} className="mx-auto mb-4 opacity-20" />
                <p className="font-bold text-sm">No pending proposals</p>
                <p className="text-xs mt-1 text-slate-500">You're all caught up!</p>
              </div>
            ) : filteredProposals.map(p => (
              <motion.div variants={itemVariants} key={p.id} className="p-3 hover:bg-slate-50 dark:hover:bg-slate-700/40 rounded-xl transition-colors group flex items-center justify-between cursor-pointer" onClick={() => navigate(`/mentor/teams/${p.team_id || p.team_name}`)}>
                <div>
                  <p className="font-bold text-slate-800 dark:text-slate-100 truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">{p.title}</p>
                  <p className="text-xs font-medium text-slate-500 mt-1 flex items-center gap-1.5">
                     <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                     {teamDisplayLabel(p.team_id || p.team_name, p, semesterMap)}
                  </p>
                </div>
                {p.submitted_at && (
                  <div className="text-right shrink-0">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Submitted</p>
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-300">{p.submitted_at}</p>
                  </div>
                )}
              </motion.div>
            ))}
          </motion.div>
        </motion.div>
      </div>
    </motion.div>
  );
};

export default MentorHome;
