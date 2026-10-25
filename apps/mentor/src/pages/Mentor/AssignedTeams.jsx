import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Search, Filter, MessageSquare, Flag, Users, Loader2, AlertCircle, LayoutDashboard } from 'lucide-react';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const StatusBadge = ({ status = '' }) => {
  const s = status.toLowerCase();
  if (s === 'valid' || s === 'approved')
    return <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-400 text-[10px] font-black uppercase tracking-wider">Valid</div>;
  if (s === 'pending')
    return <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-100 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-black uppercase tracking-wider">Pending</div>;
  return <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 text-[10px] font-black uppercase tracking-wider">{status || 'Unknown'}</div>;
};

const AssignedTeams = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { filterRows, semesterMap } = useGlobalFilters();

  useEffect(() => {
    const fetchTeams = async () => {
      try {
        const r = await api.get('/teams');
        const list = Array.isArray(r.data) ? r.data : (r.data?.data || r.data?.teams || []);
        setTeams(list);
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to load assigned teams');
      } finally {
        setLoading(false);
      }
    };
    fetchTeams();
  }, []);

  const filteredTeams = filterRows(teams).filter(team => 
      (team.name || '').toLowerCase().includes(searchTerm.toLowerCase()) || 
      (team.projectTitle || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) {
    return <div className="flex justify-center items-center min-h-[400px]"><Loader2 className="w-10 h-10 animate-spin text-indigo-500" /></div>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-rose-500">
        <AlertCircle className="w-10 h-10 mb-4" />
        <p className="font-bold">{error}</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header Section */}
      <div className="mb-4">
        <h2 className="text-3xl font-bold text-slate-900 dark:text-slate-100 mb-2 mt-4">My Teams</h2>
        <p className="text-slate-500 dark:text-slate-400">View and manage assigned teams</p>
      </div>

      {/* Toolbar / Search */ }
      <div className="flex flex-col sm:flex-row gap-4 justify-between items-center bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl p-4 rounded-3xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] mb-6 transition-all duration-300">
          <div className="relative w-full sm:w-96">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
              <input 
                  type="text" 
                  placeholder="Search teams or projects..." 
                  className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 transition-shadow text-sm font-medium text-slate-800 dark:text-slate-100 placeholder:text-slate-400"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
              />
          </div>
          <div className="relative w-full sm:w-auto">
              {/* Fake filter select */}
              <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold text-slate-600 dark:text-slate-300 cursor-pointer">
                  <Filter size={16} />
                  <span>All Teams</span>
                  <ChevronRight size={16} className="rotate-90 ml-2" />
              </div>
          </div>
      </div>

      {/* Cards Grid */ }
      {filteredTeams.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] text-center transition-all duration-300">
              <div className="w-16 h-16 bg-slate-100 dark:bg-slate-700 rounded-full flex items-center justify-center mb-4">
                  <LayoutDashboard className="w-8 h-8 text-slate-400" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">No teams found</h3>
              <p className="text-slate-500 dark:text-slate-400 font-medium">Try adjusting your search or filters.</p>
          </div>
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 relative z-10">
          {filteredTeams.map((team) => (
              <div key={team.id} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-all duration-300 flex flex-col group overflow-hidden">
                  <div className="p-6 flex-1">
                      <div className="flex justify-between items-start mb-2">
                          <div className="flex items-center gap-3">
                              <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">{teamDisplayLabel(team.id || team.name, team, semesterMap)}</h3>
                              <span className="text-xs font-bold text-slate-500 bg-slate-100 dark:bg-slate-700 py-1 px-2 rounded-lg border border-slate-200 dark:border-slate-600">{team.tag || 'TEAM'}</span>
                          </div>
                          <StatusBadge status={team.status || team.risk || 'Pending'} />
                      </div>
                      
                      <p className="font-bold text-slate-800 dark:text-slate-200 tracking-tight">{team.projectTitle}</p>
                      <p className="text-sm font-medium text-slate-500 dark:text-slate-400 italic mb-4">{team.domain || 'General'}</p>
                      
                      <div className="flex items-center gap-4 text-sm font-bold text-slate-500 dark:text-slate-400 mb-6">
                           <span className="flex items-center gap-1"><Users size={16}/> {team.membersInfo || `${team.members?.length || 0} members`}</span>
                           {team.lastActive && (
                               <>
                                   <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                                   <span>{team.lastActive}</span>
                               </>
                           )}
                      </div>

                      <div className="flex flex-wrap gap-2">
                          {(team.members || []).map((member, idx) => (
                              <span key={idx} className="px-3 py-1.5 rounded-full bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300">
                                  {member.name || member}
                              </span>
                          ))}
                      </div>
                  </div>

                  <div className="grid grid-cols-2 divide-x divide-slate-200/50 dark:divide-slate-700/50 border-t border-slate-200/50 dark:border-slate-700/50 bg-white/30 dark:bg-slate-900/30 backdrop-blur-md">
                      <button 
                          onClick={() => navigate(`/mentor/teams/${team.id}`)}
                          className="flex items-center justify-center gap-2 py-4 text-sm font-bold text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                      >
                          <Users size={16} /> View Details
                      </button>
                      <div className="flex items-center">
                          <button className="flex-1 flex items-center justify-center gap-2 py-4 text-sm font-bold text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                              <MessageSquare size={16} /> Feedback
                          </button>
                          <button className="px-5 py-4 border-l border-slate-100 dark:border-slate-700/50 text-slate-400 hover:text-rose-500 dark:hover:text-rose-400 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors group-hover:text-slate-500">
                              <Flag size={16} />
                          </button>
                      </div>
                  </div>
              </div>
          ))}
      </div>
      )}
    </div>
  );
};

export default AssignedTeams;
