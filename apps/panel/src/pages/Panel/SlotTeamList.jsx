import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlayCircle, CheckCircle2, XCircle, Clock, ChevronRight, Video, RefreshCw } from 'lucide-react';
import { panelAPI } from '../../services/api';
import { invalidateCache } from '../../services/api';
import { requirePanelId } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const StatusBadge = ({ status }) => {
  switch (status) {
    case 'Active':
      return (
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/20 text-sm font-bold max-w-max">
          <PlayCircle size={14} className="animate-pulse" /> Active
        </span>
      );
    case 'Submitted':
      return (
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-500/20 text-sm font-bold max-w-max">
          <CheckCircle2 size={14} /> Completed
        </span>
      );
    case 'Missed':
      return (
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-rose-100 dark:bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-500/20 text-sm font-bold max-w-max">
          <XCircle size={14} /> Missed
        </span>
      );
    case 'Upcoming':
    default:
      return (
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20 text-sm font-bold max-w-max">
          <Clock size={14} /> Upcoming
        </span>
      );
  }
};

const SlotTeamList = () => {
  const navigate = useNavigate();
  const [teamsData, setTeamsData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const { semesterMap, filterRows } = useGlobalFilters();

  const fetchTeamsData = useCallback(async (isManual = false) => {
    try {
      const panelId = requirePanelId();
      // Force-bust cache on manual refresh
      if (isManual) {
        invalidateCache(`/panel/${panelId}/teams`);
        invalidateCache(`/panel/${panelId}/dashboard`);
        setRefreshing(true);
      }
      const data = await panelAPI.getTeams(panelId, isManual);
      setTeamsData(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      console.error('Failed to fetch teams data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchTeamsData();
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => fetchTeamsData(), 30_000);
    // Also refresh when window regains focus (user switches back from admin portal)
    const onFocus = () => fetchTeamsData(true);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchTeamsData]);

  const handleRowClick = (team) => {
    if (team.status === 'Active' || team.status === 'Upcoming' || team.status === 'Missed') {
      navigate(`/panel/evaluation/${team.team_id}`);
    } else if (team.status === 'Submitted') {
      navigate(`/panel/receipt/${team.team_id}`);
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          Failed to load teams: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
            My Evaluation Slots
          </h2>
          <p className="text-slate-500 font-medium">Manage your schedule and access active team evaluations.</p>
          {lastUpdated && (
            <p className="text-xs text-slate-400 mt-1">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>
        <button
          onClick={() => fetchTeamsData(true)}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 border border-emerald-500 rounded-xl text-sm font-bold text-white transition-all shadow-sm disabled:opacity-50 active:scale-95"
        >
          <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
          {refreshing ? 'Syncing...' : 'Sync & Hard Refresh'}
        </button>
      </div>

      {/* Teams Table */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 overflow-hidden shadow-sm relative">
        <div data-tour="panel-slots-table" className="absolute top-1/2 left-0 w-64 h-64 bg-emerald-500/5 blur-[100px] rounded-full pointer-events-none" />
        
        <table className="w-full text-left border-collapse relative z-10">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-300 text-sm uppercase tracking-wider">
              <th className="py-4 px-6 font-bold w-1/4">Time Slot</th>
              <th className="py-4 px-6 font-bold">Team Name</th>
              <th className="py-4 px-6 font-bold w-40">Status</th>
              <th data-tour="panel-slots-action" className="py-4 px-6 font-bold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700/50">
            {filterRows(teamsData).map((team) => {
              const rowClass = team.status === 'Active' 
                ? "bg-emerald-50/50 dark:bg-emerald-900/10 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors cursor-pointer group"
                : team.status === 'Submitted'
                ? "hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors cursor-pointer group"
                : "hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors";

              return (
                <tr key={`${team.team_id}-${team.slot || ''}`} onClick={() => handleRowClick(team)} className={rowClass}>
                  <td className="py-4 px-6">
                    <div className="font-mono font-bold text-slate-600 dark:text-slate-300">{team.slot}</div>
                  </td>
                  <td className="py-4 px-6">
                    <div>
                      <div className="font-bold text-slate-900 dark:text-slate-100">{teamDisplayLabel(team.team_id || team.team_name, team, semesterMap)}</div>
                      {team.project_title && (
                        <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">{team.project_title}</div>
                      )}
                    </div>
                  </td>
                  <td className="py-4 px-6">
                    <StatusBadge status={team.status} />
                  </td>
                  <td className="py-4 px-6 text-right">
                    <div className="flex items-center gap-2 justify-end" onClick={(e) => e.stopPropagation()}>
                      {team.meet_link && team.status !== 'Submitted' && (
                        <a 
                          href={team.meet_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold transition-all shadow-sm flex items-center gap-1.5"
                        >
                          <Video size={14} /> Join Meet
                        </a>
                      )}
                      
                      {(team.status === 'Active' || team.status === 'Upcoming') && (
                        <button 
                          onClick={() => navigate(`/panel/evaluation/${team.team_id}`)}
                          className={`px-4 py-2 ${team.status === 'Active' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-slate-600 hover:bg-slate-700'} text-white rounded-lg text-sm font-bold transition-all shadow-sm flex items-center gap-2 group-hover:scale-105`}
                        >
                          Evaluate <ChevronRight size={16} />
                        </button>
                      )}
                      {team.status === 'Submitted' && (
                        <button 
                          onClick={() => navigate(`/panel/receipt/${team.team_id}`)}
                          className="text-slate-500 hover:text-emerald-600 dark:hover:text-emerald-400 text-sm font-bold transition-colors flex items-center justify-end gap-1"
                        >
                          View Receipt <ChevronRight size={14} />
                        </button>
                      )}
                      {team.status === 'Missed' && (
                        <span className="text-rose-500/70 font-bold text-sm">Escalated</span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default SlotTeamList;
