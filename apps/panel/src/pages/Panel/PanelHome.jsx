import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Clock, ShieldAlert, CheckCircle, Search, UserCheck, Video } from 'lucide-react';
import { panelAPI } from '../../services/api';
import { requirePanelId, getMentorName } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const PanelHome = () => {
  const navigate = useNavigate();
  const [currentTime, setCurrentTime] = useState(new Date());
  const [dashboardData, setDashboardData] = useState(null);
  const [teamsData, setTeamsData] = useState([]);
  const [teamsLoaded, setTeamsLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const { semesterMap, filterRows } = useGlobalFilters();
  const mentorName = getMentorName();

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const panelId = requirePanelId();
        // Only fetch the dashboard — teams are loaded lazily on first search
        const dashboard = await panelAPI.getDashboard(panelId);
        setDashboardData(dashboard);
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  // Lazily load teams list when user starts typing in the search box
  const handleSearchChange = async (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    if (query.trim() && !teamsLoaded) {
      try {
        const panelId = requirePanelId();
        const teams = await panelAPI.getTeams(panelId);
        setTeamsData(teams || []);
        setTeamsLoaded(true);
      } catch (err) {
        console.error('Failed to load teams for search:', err);
      }
    }
  };

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', { 
      hour12: true, 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
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
          Failed to load dashboard: {error}
        </div>
      </div>
    );
  }

  const data = dashboardData || {};
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredTeams = normalizedQuery
    ? filterRows(teamsData).filter((team) => {
        const key = `${team.team_id} ${team.team_name || ''} ${team.project_title || ''}`.toLowerCase();
        return key.includes(normalizedQuery);
      }).slice(0, 5)
    : [];

  const openTeam = (team) => {
    if (team.status === 'Active') {
      navigate(`/panel/evaluation/${team.team_id}`);
      return;
    }
    if (team.status === 'Submitted') {
      navigate(`/panel/receipt/${team.team_id}`);
      return;
    }
    navigate('/panel/slots');
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Dynamic Header with Real-time Clock */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
            {mentorName ? `Welcome, ${mentorName}` : 'Panel Dashboard'}
          </h2>
          <p className="text-slate-500 font-medium">{data.assigned_round || 'Mid-Term Evaluation - Round 1'}</p>
        </div>
        
        <div className="flex items-center gap-4 bg-white dark:bg-slate-800 px-6 py-3 rounded-2xl border border-emerald-200 dark:border-emerald-500/30 shadow-sm">
          <Clock className="text-emerald-500 dark:text-emerald-400 animate-pulse" size={24} />
          <div className="flex flex-col">
             <span className="text-xs text-slate-500 uppercase font-black tracking-widest">System Time</span>
             <span className="text-xl font-mono font-bold text-slate-800 dark:text-emerald-50 tracking-wide">{formatTime(currentTime)}</span>
          </div>
        </div>
      </div>

      {/* Live Evaluation Progress Tracker */}
      <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-6 md:p-8 shadow-sm relative overflow-hidden group">
        <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 blur-[80px] rounded-full pointer-events-none transition-all group-hover:bg-indigo-500/10" />
        
        <div className="flex flex-col md:flex-row md:justify-between items-start md:items-center border-b border-slate-100 dark:border-slate-700/50 pb-5 mb-6 relative z-10 gap-3">
           <div className="flex items-center gap-3">
             <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-500/20 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
               <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
             </div>
             <div data-tour="panel-progress">
               <h3 className="font-black text-xl text-slate-800 dark:text-slate-100 tracking-tight">Live Evaluation Progress</h3>
               <p className="text-slate-500 text-sm font-medium">Tracking completion coverage across all assigned defense groups</p>
             </div>
           </div>
           
           <span className="bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 font-bold px-4 py-2 rounded-xl text-sm border border-slate-200 dark:border-slate-700 shadow-sm flex items-center gap-2">
             <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
             {data.evaluated_count || 0} / {data.total_teams || 0} Teams Evaluated
           </span>
        </div>
        
        <div className="relative z-10">
          <div className="w-full h-4 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden flex shadow-inner mb-3 border border-slate-200 dark:border-slate-800">
             <motion.div 
               initial={{ width: 0 }}
               animate={{ width: `${(data.progress_fraction || 0)*100}%` }}
               transition={{ duration: 1.5, ease: "easeOut", delay: 0.2 }}
               className="h-full bg-gradient-to-r from-emerald-400 to-emerald-600 rounded-full relative overflow-hidden"
             >
               <motion.div 
                 animate={{ x: ['-100%', '200%'] }} 
                 transition={{ repeat: Infinity, duration: 2, ease: "linear" }} 
                 className="absolute inset-0 w-1/2 bg-gradient-to-r from-transparent via-white/30 to-transparent skew-x-12" 
               />
             </motion.div>
          </div>
          <div className="flex justify-between items-center text-xs font-bold text-slate-500">
            <span>0%</span>
            <span className="text-emerald-600 dark:text-emerald-400">{Math.round((data.progress_fraction || 0)*100)}% Complete</span>
            <span>100%</span>
          </div>
        </div>
      </div>

      {/* Main Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 blur-[50px] rounded-full" />
          <div className="flex justify-between items-start relative z-10">
            <div>
              <p className="text-slate-500 font-bold mb-1">Assigned Slots</p>
              <h3 className="text-4xl font-black text-slate-800 dark:text-slate-100">{data.total_teams || 0}</h3>
            </div>
            <div className="p-3 bg-emerald-50 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-xl">
              <UserCheck size={24} />
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 blur-[50px] rounded-full" />
          <div className="flex justify-between items-start relative z-10">
            <div>
              <p className="text-slate-500 font-bold mb-1">Pending Evaluations</p>
              <h3 className="text-4xl font-black text-amber-500 dark:text-amber-400">{data.pending_count || 0}</h3>
            </div>
            <div className="p-3 bg-amber-50 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 rounded-xl">
              <Clock size={24} />
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 blur-[50px] rounded-full" />
          <div className="flex justify-between items-start relative z-10">
            <div>
              <p className="text-slate-500 font-bold mb-1">Completed</p>
              <h3 className="text-4xl font-black text-indigo-500 dark:text-indigo-400">{data.completed_count || 0}</h3>
            </div>
            <div className="p-3 bg-indigo-50 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-xl">
              <CheckCircle size={24} />
            </div>
          </div>
        </div>
      </div>

      {/* Active Session & Schedule */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Active Session Card (Takes 2 columns) */}
        <div className="lg:col-span-2 bg-gradient-to-br from-emerald-50 to-white dark:from-emerald-900/30 dark:to-slate-900/50 border border-emerald-200 dark:border-emerald-500/30 rounded-3xl p-8 relative overflow-hidden shadow-sm">
          <div className="absolute -top-10 -right-10 w-64 h-64 bg-emerald-500/20 blur-[100px] rounded-full pointer-events-none" />
          
          <div className="flex items-center gap-3 mb-6 relative z-10">
             <div className="w-3 h-3 bg-emerald-500 rounded-full animate-ping absolute" />
             <div data-tour="panel-live-slot" className="w-3 h-3 bg-emerald-500 rounded-full relative" />
             <h3 className="text-emerald-700 dark:text-emerald-400 font-bold tracking-widest uppercase text-sm">Live Slot</h3>
          </div>

          <div className="relative z-10">
            <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
              {data.active_slot_detail ? teamDisplayLabel(data.active_slot_detail.team_id, data.active_slot_detail, semesterMap) : 'No Active Slot'}
            </h2>
            <p className="text-slate-600 dark:text-slate-300 font-medium mb-6">
              {data.active_slot_detail?.project_title || 'Waiting for next scheduled evaluation'}
            </p>
            
            <div className="flex flex-wrap gap-4 mb-8">
              <div className="bg-white dark:bg-slate-800/80 backdrop-blur-md border border-slate-200 dark:border-slate-700/50 px-4 py-2 rounded-xl text-slate-700 dark:text-slate-200 font-bold flex items-center gap-2">
                <Clock size={16} className="text-emerald-500" />
                {data.active_slot_detail?.time_range || 'No active time slot'}
              </div>
              <div className="bg-white dark:bg-slate-800/80 backdrop-blur-md border border-slate-200 dark:border-slate-700/50 px-4 py-2 rounded-xl text-slate-700 dark:text-slate-200 font-bold">
                {data.active_slot_detail?.meet_link || data.active_slot_detail?.venue_mode === 'online' || data.active_slot_detail?.venue === 'Online' ? 'Online' : (data.active_slot_detail?.venue || data.active_slot_detail?.room || 'Main Hall')}
              </div>
            </div>

            {data.active_slot_detail && (
              <div className="flex flex-wrap gap-4">
                <button 
                  onClick={() => navigate(`/panel/evaluation/${data.active_slot_detail.team_id}`)}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-lg shadow-emerald-600/20 active:scale-95 flex items-center gap-2"
                >
                   Enter Evaluation Form <ShieldAlert size={18} />
                </button>
                {data.active_slot_detail.meet_link && (
                  <a 
                    href={data.active_slot_detail.meet_link} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-lg shadow-blue-600/20 active:scale-95 flex items-center gap-2"
                  >
                    <Video size={18} /> Join Meet
                  </a>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Quick Search & Next Up */}
        <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-6 flex flex-col shadow-sm">
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-6">Quick Actions</h3>
          
          <div className="relative mb-6">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input 
              type="text" 
              placeholder="Search team by ID or name..." 
              value={searchQuery}
              onChange={handleSearchChange}
              className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl pl-10 pr-4 py-3 text-slate-700 dark:text-slate-200 font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            {filteredTeams.length > 0 && (
              <div className="absolute mt-2 w-full z-20 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg overflow-hidden">
                {filteredTeams.map((team) => (
                  <button
                    key={`${team.team_id}-${team.slot || ''}`}
                    onClick={() => openTeam(team)}
                    className="w-full text-left px-3 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  >
                    <p className="font-bold text-slate-800 dark:text-slate-200">{teamDisplayLabel(team.team_id, team, semesterMap)}</p>
                    <p className="text-xs text-slate-500">{team.status === 'Submitted' ? 'Completed' : team.status} {team.slot ? `• ${team.slot}` : ''}</p>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div data-tour="panel-next-up" className="flex-1">
            <h4 className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-4">Next Up</h4>
            {data.next_up ? (
              <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700/50 p-4 rounded-xl border-l-4 border-l-amber-500">
                 <p className="font-bold text-slate-800 dark:text-slate-200">{teamDisplayLabel(data.next_up.team_id || data.next_up.team_name, data.next_up, semesterMap)}</p>
                 <p className="text-sm font-medium text-slate-500 mb-3">{data.next_up.slot}</p>
                 {data.next_up.meet_link && (
                   <a
                     href={data.next_up.meet_link}
                     target="_blank"
                     rel="noopener noreferrer"
                     className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-all"
                   >
                     <Video size={14} /> Join Meet
                   </a>
                 )}
              </div>
            ) : (
              <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700/50 p-4 rounded-xl">
                 <p className="text-sm font-medium text-slate-500">No upcoming slots scheduled</p>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

export default PanelHome;
