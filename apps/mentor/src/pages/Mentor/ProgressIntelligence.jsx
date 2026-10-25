import React, { useState, useEffect } from 'react';
import { Calendar, ChevronDown, CheckCircle2, AlertCircle, TrendingUp, Loader2, LayoutDashboard } from 'lucide-react';
import { Chart as ChartJS, ArcElement, Tooltip as ChartTooltip, Legend, CategoryScale, LinearScale, BarElement, Filler } from 'chart.js';
import { Doughnut, Bar } from 'react-chartjs-2';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

ChartJS.register(ArcElement, ChartTooltip, Legend, CategoryScale, LinearScale, BarElement, Filler);

// Fallback data used when the API isn't available yet

// ---------- tiny helper ----------
const riskBadgeClasses = (color) => {
  const map = {
    rose: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border-rose-200 dark:border-rose-500/30',
    emerald: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500/30',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 border-amber-200 dark:border-amber-500/30',
  };
  return map[color] || map.amber;
};

// ---------- Chart sub-components ----------
const ProgressDoughnut = ({ progress }) => {
  const remaining = 100 - progress;
  const data = {
    labels: ['Completed', 'Remaining'],
    datasets: [{
      data: [progress, remaining],
      backgroundColor: ['#6366f1', '#e2e8f0'],
      borderWidth: 0,
      cutout: '78%',
    }],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { enabled: false } },
  };

  return (
    <div className="relative w-24 h-24 shrink-0">
      <Doughnut data={data} options={options} />
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-lg font-black text-slate-800 dark:text-slate-100">{progress}%</span>
      </div>
    </div>
  );
};

const TimelineBar = ({ timeline }) => {
  const data = {
    labels: (timeline || []).map(t => t.week),
    datasets: [{
      label: 'Progress',
      data: (timeline || []).map(t => t.progress),
      backgroundColor: 'rgba(99, 102, 241, 0.7)',
      borderRadius: 4,
      barThickness: 14,
    }],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { grid: { display: false }, ticks: { font: { size: 10, weight: 'bold' }, color: '#94a3b8' } },
      y: { display: false, max: 100 },
    },
    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.raw}%` } } },
  };
  return (
    <div className="h-[100px] w-full">
      <Bar data={data} options={options} />
    </div>
  );
};

const MilestoneRow = ({ milestones }) => (
  <div className="space-y-2">
    {(milestones || []).map((m, i) => (
      <div key={i} className="flex items-center gap-3">
        <span className="text-xs font-bold text-slate-500 dark:text-slate-400 w-24 truncate">{m.name}</span>
        <div className="flex-1 h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${m.pct === 100 ? 'bg-emerald-500' : m.pct > 0 ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}`}
            style={{ width: `${m.pct}%` }}
          />
        </div>
        <span className={`text-[10px] font-black uppercase tracking-wider ${m.status === 'Completed' ? 'text-emerald-600 dark:text-emerald-400' : m.status === 'In Progress' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400'}`}>
          {m.status}
        </span>
      </div>
    ))}
  </div>
);

// ---------- Completion Statistics Bar Chart ----------
const CompletionStatsChart = ({ teamsData }) => {
  const { semesterMap } = useGlobalFilters();
  const data = {
    labels: teamsData.map(t => teamDisplayLabel(t.id || t.name, t, semesterMap)),
    datasets: [{
      label: 'Progress %',
      data: teamsData.map(t => t.progress),
      backgroundColor: teamsData.map(t =>
        t.progress >= 70 ? 'rgba(16,185,129,0.7)' :
        t.progress >= 40 ? 'rgba(99,102,241,0.7)' :
        'rgba(244,63,94,0.7)'
      ),
      borderRadius: 6,
      barThickness: 28,
    }],
  };
  const options = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { max: 100, grid: { color: 'rgba(148,163,184,0.1)' }, ticks: { font: { size: 10, weight: 'bold' }, color: '#94a3b8', callback: v => `${v}%` } },
      y: { grid: { display: false }, ticks: { font: { size: 11, weight: 'bold' }, color: '#64748b' } },
    },
    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.raw}% complete` } } },
  };
  return (
    <div style={{ height: Math.max(teamsData.length * 52, 120) }}>
      <Bar data={data} options={options} />
    </div>
  );
};

// ============ MAIN COMPONENT ============
const ProgressIntelligence = () => {
  const [teams, setTeams] = useState([]);
  const [teamsProgress, setTeamsProgress] = useState([]);
  const [loading, setLoading] = useState(true);
  // Nothing calls the setter, so the error branch below can never render.
  // Kept as a constant because that branch still reads the value.
  const error = null;
  const [selectedTeamId, setSelectedTeamId] = useState('all');
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // MUST stay above the `if (loading)` / `if (error)` early returns below —
  // hooks have to run in the same order on every render. Called after them, the
  // first (loading) render ran one fewer hook than the next, so React threw
  // "Rendered more hooks than during the previous render" as soon as the data
  // arrived, on every visit to this page.
  const { filterRows, semesterMap } = useGlobalFilters();

  useEffect(() => {
    const fetchData = async () => {
      try {
        // 1. Fetch teams list
        const teamsRes = await api.get('/teams');
        const teamsList = Array.isArray(teamsRes.data) ? teamsRes.data : teamsRes.data.teams || [];
        setTeams(teamsList);

        // 2. Fetch progress for each team
        const progressResults = await Promise.allSettled(
          teamsList.map(t => api.get(`/teams/${t.id}/progress`))
        );

        const progressData = teamsList.map((t, i) => {
          if (progressResults[i].status === 'fulfilled') {
            return { ...t, ...progressResults[i].value.data };
          }
          // API not ready for this team — return minimal structure
          return {
            id: t.id,
            name: t.name,
            week: 7,
            risk: 'Unknown',
            riskColor: 'slate',
            progress: 0,
            summary: 'Progress data not yet available.',
            achievements: [],
            blockers: [],
            milestones: [],
            timeline: [],
          };
        });

        setTeamsProgress(progressData);
      } catch (err) {
        // Teams endpoint itself failed — show empty state
        setTeamsProgress([]);
        setTeams([]);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return <div className="flex justify-center items-center min-h-[400px]"><Loader2 className="w-10 h-10 animate-spin text-indigo-500" /></div>;
  }

  if (error && teamsProgress.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-rose-500">
        <AlertCircle className="w-10 h-10 mb-4" />
        <p className="font-bold">{error}</p>
      </div>
    );
  }

  const filteredTeams = filterRows(teams);
  const filteredTeamsProgress = filterRows(teamsProgress);

  const displayedTeams = selectedTeamId === 'all'
    ? filteredTeamsProgress
    : filteredTeamsProgress.filter(t => t.id === selectedTeamId);

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="mb-4 mt-2">
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
           Weekly Progress
        </h2>
        <p className="text-sm font-medium text-slate-500">AI-generated progress summaries</p>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-center gap-4 bg-white dark:bg-slate-800 p-2 rounded-xl border border-slate-200 dark:border-slate-700/50 shadow-sm mb-6">
          {/* Team filter dropdown */}
          <div className="relative">
            <div
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg cursor-pointer"
            >
              <Calendar size={16} className="text-slate-500" />
              <span className="text-sm font-bold text-slate-700 dark:text-slate-200">
                {selectedTeamId === 'all' ? 'All Teams' : (() => {
                  const t = teams.find(x => x.id === selectedTeamId);
                  return t ? teamDisplayLabel(t.id || t.name, t, semesterMap) : 'Select';
                })()}
              </span>
              <ChevronDown size={16} className={`text-slate-500 ml-2 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </div>
            {dropdownOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setDropdownOpen(false)} />
                <div className="absolute left-0 mt-2 w-56 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl z-50 overflow-hidden">
                  <button
                    onClick={() => { setSelectedTeamId('all'); setDropdownOpen(false); }}
                    className={`w-full text-left px-4 py-2.5 text-sm font-bold transition-colors ${selectedTeamId === 'all' ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50'}`}
                  >
                    All Teams
                  </button>
                  {filteredTeams.map(t => (
                    <button
                      key={t.id}
                      onClick={() => { setSelectedTeamId(t.id); setDropdownOpen(false); }}
                      className={`w-full text-left px-4 py-2.5 text-sm font-bold transition-colors ${t.id === selectedTeamId ? 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50'}`}
                    >
                      {teamDisplayLabel(t.id || t.name, t, semesterMap)}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
          <p className="text-sm font-medium text-slate-500 hidden sm:block">Showing AI-generated summaries based on student logs and GitHub activity</p>
      </div>

      {/* Completion Statistics Overview (only show when viewing all teams) */}
      {selectedTeamId === 'all' && teamsProgress.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700/50 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2 mb-6">
            <TrendingUp size={18} className="text-indigo-500" /> Completion Statistics
          </h3>
          <CompletionStatsChart teamsData={filteredTeamsProgress} />
        </div>
      )}

      {/* Empty state */}
      {displayedTeams.length === 0 && (
        <div className="flex flex-col items-center justify-center p-12 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
          <div className="w-16 h-16 bg-slate-100 dark:bg-slate-700 rounded-full flex items-center justify-center mb-4">
            <LayoutDashboard className="w-8 h-8 text-slate-400" />
          </div>
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">No progress data</h3>
          <p className="text-slate-500 dark:text-slate-400 font-medium">No progress reports available for this team yet.</p>
        </div>
      )}

      {/* Grid of Team Progress Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {displayedTeams.map((team) => (
            <div key={team.id} className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700/50 shadow-sm flex flex-col">
                {/* Card Header */}
                <div className="flex justify-between items-start mb-4">
                    <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">{teamDisplayLabel(team.id || team.name, team, semesterMap)}</h3>
                    <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1 text-xs font-bold text-slate-500"><Calendar size={12}/> Week {team.week || 7}</span>
                        <span className={`text-[10px] uppercase font-black tracking-wider px-2 py-0.5 rounded-full border ${riskBadgeClasses(team.riskColor || 'amber')}`}>
                          {team.risk || 'Unknown'}
                        </span>
                    </div>
                </div>

                {/* Progress Ring + Summary */}
                <div className="flex items-center gap-5 mb-6">
                  <ProgressDoughnut progress={team.progress ?? 0} />
                  <p className="text-sm font-medium text-slate-600 dark:text-slate-300 leading-relaxed flex-1 flex items-start gap-2">
                    <TrendingUp size={16} className="text-indigo-500 shrink-0 mt-0.5" />
                    <span>{team.summary || 'No summary available.'}</span>
                  </p>
                </div>

                {/* Milestones */}
                {team.milestones && team.milestones.length > 0 && (
                  <div className="mb-5">
                    <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">Milestones</h4>
                    <MilestoneRow milestones={team.milestones} />
                  </div>
                )}

                {/* Timeline Chart */}
                {team.timeline && team.timeline.length > 0 && (
                  <div className="mb-5">
                    <h4 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">Timeline</h4>
                    <TimelineBar timeline={team.timeline} />
                  </div>
                )}

                {/* Achievements + Blockers */}
                <div className="space-y-4 flex-1">
                    {team.achievements && team.achievements.length > 0 && (
                      <div>
                        <h4 className="text-sm font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 mb-2">
                            <CheckCircle2 size={16} /> Achievements
                        </h4>
                        <ul className="space-y-1.5 list-disc list-inside text-sm font-medium text-slate-600 dark:text-slate-400">
                            {team.achievements.map((a, i) => <li key={i}>{a}</li>)}
                        </ul>
                      </div>
                    )}
                    {team.blockers && team.blockers.length > 0 && (
                      <div>
                        <h4 className="text-sm font-bold text-amber-600 dark:text-amber-400 flex items-center gap-1.5 mb-2">
                            <AlertCircle size={16} /> Blockers
                        </h4>
                        <ul className="space-y-1.5 list-disc list-inside text-sm font-medium text-slate-600 dark:text-slate-400">
                            {team.blockers.map((b, i) => <li key={i}>{b}</li>)}
                        </ul>
                      </div>
                    )}
                </div>
            </div>
          ))}
      </div>
    </div>
  );
};

export default ProgressIntelligence;
