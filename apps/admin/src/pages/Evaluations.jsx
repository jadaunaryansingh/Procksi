import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity, CheckCircle, BarChart2, Star,
  ShieldAlert, RefreshCw, Loader2, AlertCircle, AlertTriangle,
  Search, Filter
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { getAllEvaluations, getAlerts, acknowledgeAlert } from '../services/panelSync';
import { getActiveSemesterId, apiFetchTable } from '../lib/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamLabel, cleanUUIDsFromText } from '../lib/teamUtils';

function _parseTime(timeStr) {
  const clean = (timeStr || '').trim();
  const ampm = /([ap]m)/i.exec(clean);
  const parts = clean.replace(/[apm]/gi, '').trim().split(':');
  let hours = parseInt(parts[0], 10) || 0;
  const minutes = parseInt(parts[1], 10) || 0;
  if (ampm) {
    if (/pm/i.test(ampm[1]) && hours !== 12) hours += 12;
    if (/am/i.test(ampm[1]) && hours === 12) hours = 0;
  }
  return { hours, minutes };
}

function _buildWindowStart(date, timeRange) {
  const start = (timeRange || '').split('-')[0];
  const { hours, minutes } = _parseTime(start);
  const d = new Date(date);
  d.setHours(hours, minutes, 0, 0);
  return d;
}

function _buildWindowEnd(date, timeRange) {
  const parts = (timeRange || '').split('-');
  const end = parts[1] || parts[0];
  const { hours, minutes } = _parseTime(end);
  const d = new Date(date);
  d.setHours(hours, minutes, 0, 0);
  return d;
}

const toNumericId = (teamStr) => {
    if (!teamStr) return 0;
    const str = String(teamStr).trim();
    const parseWithLeadingZero = (numStr) => {
        const val = parseInt(numStr, 10);
        if (numStr.startsWith('0') && val !== 0) {
            return 10000 + val;
        }
        return val;
    };
    const tMatch = str.match(/-T(\d+)/i);
    if (tMatch) return parseWithLeadingZero(tMatch[1]);
    const lastDashMatch = str.match(/-(\d+)$/);
    if (lastDashMatch) return parseWithLeadingZero(lastDashMatch[1]);
    const allNums = str.match(/\d+/g);
    if (allNums && allNums.length > 0) return parseWithLeadingZero(allNums[allNums.length - 1]);
    return 0;
};

export default function Evaluations() {
  const navigate = useNavigate();
  const { semesterMap, filterRows } = useGlobalFilters();
  const [activeSemesterId, setActiveSemesterId] = useState(null);
  const [checkingSemester, setCheckingSemester] = useState(true);
  const [cycles, setCycles] = useState([]);
  const [cycleEvals, setCycleEvals] = useState([]);

  const [feed, setFeed] = useState([]);
  const [slots, setSlots] = useState([]);
  const [teams, setTeams] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [alerts, setAlerts] = useState([]);


  const loadEvaluations = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      let evalData = [];
      try {
        evalData = await getAllEvaluations();
      } catch (panelErr) {
        console.warn('Panel portal unreachable, falling back to local feed:', panelErr.message);
        // Fall back to evaluation_feed table stored locally in Supabase
        try {
          evalData = await apiFetchTable('evaluation_feed');
        } catch (_) {
          evalData = [];
        }
      }
      setFeed(evalData || []);

      const [scheduleData, teamsData, pCycles, pEvals] = await Promise.all([
        apiFetchTable('schedule_slots'),
        apiFetchTable('teams_validation'),
        apiFetchTable('presentation_cycles'),
        apiFetchTable('presentation_evaluations')
      ]);
      setCycles(pCycles || []);
      setCycleEvals(pEvals || []);
      setTeams(teamsData || []);

      const combined = (scheduleData || []).map(ss => {
        const teamVal = (teamsData || []).find(t => t.id === ss.team);
        const teamIdNum = toNumericId(ss.team);
        const panelId = ss.panel?.replace(/\s+/g, '-').toUpperCase() || 'PANEL-UNKNOWN';
        
        const evaluation = (evalData || []).find(e => {
          // Normalize both sides for comparison - handle "Panel A" vs "PANEL-A" vs "PANEL-UNKNOWN"
          const ePanelNorm = String(e.panel_id || '').toUpperCase().replace(/\s+/g, '-');
          const sPanelNorm = String(panelId || '').toUpperCase().replace(/\s+/g, '-');
          const panelMatch = ePanelNorm === sPanelNorm || 
            // Also try matching panel name directly (without transformation)
            String(e.panel_id || '').toUpperCase() === String(ss.panel || '').toUpperCase();
          const teamMatch = Number(e.team_id) === Number(teamIdNum);
          return panelMatch && teamMatch;
        });
        
        const ws = _buildWindowStart(ss.date, ss.time);
        const we = _buildWindowEnd(ss.date, ss.time);
        const now = new Date();
        
        let displayStatus = 'upcoming';
        if (evaluation) {
          displayStatus = 'completed';
        } else if (now > we) {
          displayStatus = 'pending';
        } else if (now >= ws && now <= we) {
          displayStatus = 'pending';
        }
        
        return {
          id: ss.id,
          panel_id: panelId,
          panel_name: ss.panel,
          team_id: teamIdNum,
          team_name: ss.team,
          semester_id: ss.semester_id || teamVal?.semester_id || '',
          project_title: teamVal?.title || ss.team,
          slot_label: ss.time,
          window_start: ws.toISOString(),
          window_end: we.toISOString(),
          venue: ss.room,
          evaluation,
          displayStatus
        };
      });

      setSlots(combined);
    } catch (e) {
      setError(e.message);
      setFeed([]);
      setSlots([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const filteredSlots = useMemo(() => {
    return filterRows(slots).filter(s => {
      const teamObj = teams.find(t => t.id === s.team_name);
      const formattedTeamLabel = teamLabel(s.team_name, teamObj, semesterMap);
      const matchesSearch = 
        formattedTeamLabel.toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(s.project_title || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(s.panel_name || s.panel_id).toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesStatus = 
        statusFilter === 'All' || 
        s.displayStatus === statusFilter.toLowerCase();

      return matchesSearch && matchesStatus;
    });
  }, [slots, teams, filterRows, semesterMap, searchTerm, statusFilter]);

  const loadAlerts = useCallback(async (silent = false) => {
    if (!silent && !feed.length) setLoading(true);
    try {
      const data = await getAlerts({ unacknowledged_only: true });
      setAlerts(data || []);
    } catch (_) {
      setAlerts([]);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    async function checkSem() {
      try {
        const semId = await getActiveSemesterId();
        if (isMounted) {
          setActiveSemesterId(semId);
        }
      } catch (err) {
        console.error(err);
        if (isMounted) {
          setActiveSemesterId('NONE');
        }
      } finally {
        if (isMounted) {
          setCheckingSemester(false);
        }
      }
    }
    checkSem();
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    if (checkingSemester || activeSemesterId === 'NONE') {
      setLoading(false);
      return;
    }
    loadEvaluations();
    loadAlerts();
    const interval = setInterval(() => {
      loadEvaluations(true);
      loadAlerts(true);
    }, 3000);
    return () => clearInterval(interval);
  }, [loadEvaluations, loadAlerts, checkingSemester, activeSemesterId]);

  const handleAcknowledgeAlert = async (alertId) => {
    try {
      await acknowledgeAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    } catch { /* non-fatal: fall through to the default below */ }
  };

  const activeCycle = useMemo(() => {
    return cycles.find(c => c.semester_id === activeSemesterId && c.status === 'active') || { title: 'Evaluation', weightage: 30 };
  }, [cycles, activeSemesterId]);


  const timeAgo = (iso) => {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins} min${mins > 1 ? 's' : ''} ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hr${hrs > 1 ? 's' : ''} ago`;
    return new Date(iso).toLocaleDateString();
  };

  if (checkingSemester) {
    return (
      <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (activeSemesterId === 'NONE') {
    return (
      <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)] flex items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-8 rounded-3xl shadow-xl border border-slate-200/50 dark:border-slate-700/50 max-w-lg w-full text-center space-y-6"
        >
          <div className="mx-auto w-16 h-16 bg-amber-50 dark:bg-amber-500/10 rounded-2xl flex items-center justify-center text-amber-500">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">No Active Semester</h2>
            <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
              Evaluations are managed within the context of an active semester.
              Please configure and activate a semester to continue.
            </p>
          </div>
          <button
            onClick={() => navigate('/admin/semester-settings')}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-black uppercase tracking-widest text-xs rounded-xl shadow-lg shadow-indigo-500/20 active:scale-95 transition-all"
          >
            Go to Semester Settings
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50"
      >
        <div>
          <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Active Evaluations</h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
            Live feed of panel submissions from the Panel Portal. Refreshes automatically every 15 seconds.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => { loadEvaluations(); loadAlerts(); }}
            disabled={loading}
            className="p-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-500 hover:text-indigo-500 transition-colors shadow-sm"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <div className="flex items-center px-4 py-2 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl text-xs font-black uppercase tracking-widest border border-emerald-100 dark:border-emerald-500/20 shadow-sm whitespace-nowrap">
            <Activity className="w-4 h-4 mr-2 animate-pulse" /> Live System Active
          </div>
        </div>
      </motion.div>

      <AnimatePresence>
        {alerts.length > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-2"
          >
            {alerts.slice(0, 3).map((alert) => (
              <div
                key={alert.id}
                className="flex items-start justify-between bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-2xl px-5 py-3"
              >
                <div>
                  <p className="text-sm font-bold text-amber-800 dark:text-amber-300">{cleanUUIDsFromText(alert.title)}</p>
                  {alert.body && <p className="text-xs text-amber-700/70 dark:text-amber-400/70 mt-1">{cleanUUIDsFromText(alert.body)}</p>}
                </div>
                <button
                  onClick={() => handleAcknowledgeAlert(alert.id)}
                  className="ml-4 shrink-0 text-xs font-black uppercase tracking-widest text-amber-700 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-200 transition-colors"
                >
                  Dismiss
                </button>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
          {cycles.filter(c=>c.semester_id === activeSemesterId).map((cycle, i) => {
             const evaluated = Array.from(new Set(cycleEvals.filter(e=>e.cycle_id === cycle.id).map(e=>e.team_id))).length;
             const total = Math.max(slots.length, 1);
             const pct = Math.round((evaluated / total) * 100);
             return (
               <motion.div key={cycle.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 * i }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="font-bold text-slate-800 dark:text-slate-200 flex items-center truncate max-w-[120px]">
                      <BarChart2 className="w-5 h-5 mr-2 text-indigo-500" /> {cycle.title}
                    </h3>
                    <span className="text-xs font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-1 rounded border border-indigo-100 dark:border-indigo-500/20">{pct}%</span>
                  </div>
                  <div className="h-4 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden shadow-inner p-0.5">
                    <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 1, ease: 'easeOut' }} className="h-full bg-indigo-500 rounded-full" />
                  </div>
                  <div className="mt-3 flex justify-between text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">
                    <span>{evaluated} Evaluated</span><span>{Math.max(total - evaluated, 0)} Pending</span>
                  </div>
               </motion.div>
             );
          })}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold flex items-center text-slate-800 dark:text-slate-200"><ShieldAlert className="w-5 h-5 mr-2 text-indigo-500" /> System Status</h3>
              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400">ACTIVE</span>
            </div>
            <p className="text-xs font-semibold flex-1 text-slate-500 dark:text-slate-400">Panels are actively grading presentation cycles.</p>
          </motion.div>
        </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 relative">
        {/* Searchable and Filterable Evaluation Registry */}
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="xl:col-span-2 bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col h-[550px]"
        >
          {/* Header & Controls */}
          <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 space-y-4">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <h2 className="text-lg font-black text-slate-800 dark:text-white flex items-center">
                <Filter className="w-5 h-5 mr-2 text-indigo-500" /> Evaluation Registry
              </h2>
              {/* Filter Band */}
              <div className="flex gap-1.5 bg-slate-100 dark:bg-slate-905 p-1 rounded-xl border border-slate-200/50 dark:border-slate-700">
                {['All', 'Completed', 'Upcoming', 'Pending'].map((status) => (
                  <button
                    key={status}
                    type="button"
                    onClick={() => setStatusFilter(status)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-wider transition-all ${
                      statusFilter === status
                        ? 'bg-indigo-600 text-white shadow-sm'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>
            </div>
            {/* Search Input */}
            <div className="relative group">
              <Search className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
              <input
                type="text"
                placeholder="Search by team, panel, or project title..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-11 pr-5 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow"
              />
            </div>
          </div>

          {/* Table Container */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-full text-sm text-red-500 space-y-2">
                <AlertCircle className="w-6 h-6" />
                <p>Could not connect to Panel portal</p>
                <p className="text-xs text-slate-400">{error}</p>
              </div>
            ) : filteredSlots.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm font-medium text-slate-400">
                No slots found matching your criteria.
              </div>
            ) : (
              <table className="w-full text-left border-collapse">
                <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 backdrop-blur-md sticky top-0 z-10">
                  <tr>
                    <th className="p-4 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest pl-6">Team</th>
                    <th className="p-4 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Panel / Slot</th>
                    <th className="p-4 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Status / Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                  {filteredSlots.map((slot, idx) => (
                    <tr key={slot.id || idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-700/20 transition-colors">
                      <td className="p-4 pl-6 whitespace-nowrap">
                        <div className="font-bold text-slate-800 dark:text-slate-200 text-sm whitespace-nowrap">
                          {teamLabel(slot.team_name, teams.find(t => t.id === slot.team_name), semesterMap)}
                        </div>
                        <div className="text-xs text-slate-400 dark:text-slate-500 truncate max-w-[220px]">
                          {slot.project_title || 'No Project Title'}
                        </div>
                      </td>
                      <td className="p-4">
                        <div className="font-bold text-xs text-indigo-600 dark:text-indigo-400">
                          {slot.panel_name || slot.panel_id}
                        </div>
                        <div className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mt-0.5">
                          {slot.slot_label}
                        </div>
                      </td>
                      <td className="p-4">
                        {slot.displayStatus === 'completed' ? (
                          <div className="flex items-center gap-2">
                            <span className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-100 dark:border-emerald-500/20">
                              Completed
                            </span>
                            {slot.evaluation && (
                              <div className="flex flex-col items-start gap-0.5">
                                <span
                                  className="inline-flex items-center justify-center px-2.5 py-1 rounded-lg bg-emerald-500 text-white font-black text-xs shadow-sm"
                                  title={`Panel score: ${slot.evaluation.final_score_normalized}/100 → ${activeCycle.title} mark: ${Math.round((slot.evaluation.final_score_normalized / 100) * activeCycle.weightage)}/${activeCycle.weightage}`}
                                >
                                  {Math.round((slot.evaluation.final_score_normalized / 100) * activeCycle.weightage)}
                                  <span className="font-normal opacity-70">/{activeCycle.weightage}</span>
                                </span>
                                <span className="text-[10px] font-bold text-slate-400">
                                  Panel: {slot.evaluation.final_score_normalized}/100
                                </span>
                              </div>
                            )}
                          </div>
                        ) : slot.displayStatus === 'pending' ? (
                          <span className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-2.5 py-1 rounded-lg border border-amber-100 dark:border-amber-500/20 animate-pulse">
                            Pending Evaluation
                          </span>
                        ) : (
                          <span className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 px-2.5 py-1 rounded-lg border border-blue-100 dark:border-blue-500/20">
                            Upcoming
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </motion.div>

        {/* Live Evaluation Feed */}
        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4 }}
          className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col h-[550px] relative"
        >
          <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 flex items-center justify-between">
            <h2 className="text-lg font-black text-slate-800 dark:text-white flex items-center">
              <Activity className="w-5 h-5 mr-2 text-emerald-500" /> Evaluation Feed
            </h2>
            <span className="flex items-center text-[10px] uppercase font-black tracking-widest text-emerald-600 dark:text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse mr-2"></span> Live
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5 custom-scrollbar">
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
              </div>
            ) : feed.length === 0 ? (
              <div className="flex items-center justify-center h-full text-sm font-medium text-slate-400">
                No submissions received yet.
              </div>
            ) : (
              <AnimatePresence>
                {(() => {
                  const filteredFeed = filterRows(feed.map(item => ({
                    ...item,
                    semester_id: item.semester_id || teams.find(t => t.id === item.team_name)?.semester_id || ''
                  })));
                  return filteredFeed.map((item) => (
                    <motion.div
                      layout
                      initial={{ opacity: 0, x: 20, scale: 0.95 }}
                      animate={{ opacity: 1, x: 0, scale: 1 }}
                      key={item.receipt_id}
                      className="relative pl-8 before:absolute before:left-[15px] before:top-10 before:bottom-[-28px] before:w-0.5 before:bg-slate-200 dark:before:bg-slate-700 last:before:hidden"
                    >
                    <div className="absolute left-[3.5px] top-3 w-6 h-6 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center ring-4 ring-white dark:ring-slate-800 z-10">
                      <CheckCircle className="w-3 h-3" />
                    </div>
                    <div className="bg-slate-50 dark:bg-slate-900/50 rounded-2xl p-4 border border-slate-100 dark:border-slate-700/50 flex justify-between items-center group hover:bg-emerald-50/50 dark:hover:bg-emerald-500/5 hover:border-emerald-200 dark:hover:border-emerald-500/30 transition-all shadow-sm">
                      <div>
                        <div className="flex items-center space-x-3 mb-1">
                          <span className="text-sm font-black text-slate-800 dark:text-slate-200 whitespace-nowrap">
                            {teamLabel(item.team_name, teams.find(t => t.id === item.team_name), semesterMap)}
                          </span>
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                            {timeAgo(item.submitted_at)}
                          </span>
                        </div>
                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-1">
                          Panel{' '}
                          <span className="font-bold text-slate-700 dark:text-slate-300">{item.panel_id}</span>
                          {item.project_title && (
                            <span className="ml-2 text-slate-400">• {item.project_title}</span>
                          )}
                        </p>
                      </div>
                      <div className="flex flex-col items-center justify-center w-14 h-12 rounded-xl bg-emerald-500 text-white shadow-lg shadow-emerald-500/30 group-hover:scale-110 transition-transform"
                        title={`Panel score: ${item.final_score_normalized}/100 → ${activeCycle.title} mark: ${Math.round((item.final_score_normalized / 100) * activeCycle.weightage)}/${activeCycle.weightage}`}
                      >
                        <span className="font-black text-base leading-none">{Math.round((item.final_score_normalized / 100) * activeCycle.weightage)}</span>
                        <span className="text-[9px] font-bold opacity-75 leading-none mt-0.5">/ {activeCycle.weightage}</span>
                      </div>
                    </div>
                  </motion.div>
                  ));
                })()}
              </AnimatePresence>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
