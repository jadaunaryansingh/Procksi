import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Calendar, Award, Loader2, AlertCircle, Users, GitBranch, FileText, Clock, Eye } from 'lucide-react';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';
import PsArchitecturePlanModal from '../../components/Mentor/PsArchitecturePlanModal';

// ─── Sub-tab components receiving real data ──────────────────────────────────

const ProposalTab = ({ team, onViewBlueprint }) => {
  const proposal = team?.proposal || {};
  const members  = team?.members || [];
  const domain   = team?.domain || 'General';

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 border border-slate-200 dark:border-slate-700/50 shadow-sm">
        <div className="flex items-start justify-between mb-2 gap-3 flex-wrap">
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">Project Overview</h3>
          {(proposal.description || team?.description) && (
            <button
              type="button"
              onClick={() => onViewBlueprint && onViewBlueprint({
                id: team?.id,
                title: proposal.title || team?.project_title || team?.title,
                description: proposal.description || team?.description,
                domain: domain,
                difficulty: 'Medium'
              })}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs rounded-xl font-bold transition-all cursor-pointer shadow-sm shrink-0"
            >
              <Eye className="w-3.5 h-3.5" /> View Blueprint
            </button>
          )}
        </div>
        <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400 mb-4 uppercase tracking-wider">{domain}</p>

        {/* Only the title lives here; the full problem statement / blueprint is
            behind the "View Blueprint" button so this card stays scannable. */}
        {(proposal.title || team?.project_title || team?.title) ? (
          <p className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-6">
            {proposal.title || team?.project_title || team?.title}
          </p>
        ) : (
          <p className="text-slate-500 dark:text-slate-400 font-medium mb-6">No project title yet.</p>
        )}

        {proposal.status && (
          <div className="flex items-center gap-3 mb-6">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Proposal Status:</span>
            <span className={`px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider border
              ${proposal.status.toLowerCase() === 'approved'
                ? 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20'
                : proposal.status.toLowerCase() === 'rejected'
                ? 'bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/20'
                : proposal.status.toLowerCase().includes('revision')
                ? 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'
                : 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600'
              }`}>
              {proposal.status}
            </span>
            {proposal.submitted_at && (
              <span className="text-xs text-slate-400 font-medium">Submitted: {proposal.submitted_at}</span>
            )}
          </div>
        )}

        {members.length > 0 && (
          <>
            <h4 className="text-sm font-bold text-slate-500 dark:text-slate-400 mb-3 uppercase tracking-wider flex items-center gap-2">
              <Users size={14} /> Team Members
            </h4>
            <div className="flex flex-wrap gap-2">
              {members.map((m, i) => (
                <span key={i} className="px-3 py-1.5 bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-full text-slate-700 dark:text-slate-300 text-sm font-bold">
                  {typeof m === 'string' ? m : m.name}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

const SchedulesTab = ({ team }) => {
  const schedules = team?.schedules || [];

  if (schedules.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-12 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
        <Calendar size={40} className="mx-auto text-slate-300 dark:text-slate-600 mb-4" />
        <p className="text-lg font-bold text-slate-500">No presentations scheduled yet</p>
        <p className="text-sm text-slate-400 mt-1">Presentation slots will appear here once assigned.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {schedules.map((s, i) => (
        <div key={s.id || i} className="bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200 dark:border-slate-700/50 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="font-bold text-slate-800 dark:text-slate-100 mb-2">{s.type || `Slot ${i + 1}`}</h4>
            <div className="flex flex-wrap gap-3 text-sm font-medium text-slate-500">
              {s.date && !isNaN(new Date(s.date).getTime()) && (
                <span className="flex items-center gap-1.5">
                  <Calendar size={14} />
                  {new Date(s.date).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}
                </span>
              )}
              {s.venue && (
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600" />
                  {s.venue}
                </span>
              )}
            </div>
          </div>
          <span className={`px-3 py-1.5 rounded-full text-xs font-black uppercase tracking-wider border self-start sm:self-center
            ${s.is_evaluated
              ? 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20'
              : 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'
            }`}>
            {s.is_evaluated ? 'Evaluated' : 'Pending'}
          </span>
        </div>
      ))}
    </div>
  );
};

const EvaluationsTab = ({ team }) => {
  const evaluations = team?.evaluations || [];

  if (evaluations.length === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-12 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
        <Award size={40} className="mx-auto text-slate-300 dark:text-slate-600 mb-4" />
        <p className="text-lg font-bold text-slate-500">No evaluations yet</p>
        <p className="text-sm text-slate-400 mt-1">Evaluation records will appear here after submission.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {evaluations.map((e, i) => (
        <div key={e.id || i} className="bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200 dark:border-slate-700/50 shadow-sm">
          <div className="flex justify-between items-start mb-3">
            <h4 className="font-bold text-slate-800 dark:text-slate-100">{e.type || 'Evaluation'}</h4>
            {e.date && (
              <span className="text-xs font-medium text-slate-400 flex items-center gap-1">
                <Clock size={12} /> {e.date}
              </span>
            )}
          </div>
          {e.remarks && (
            <p className="text-sm font-medium text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/50 rounded-xl p-3 border border-slate-100 dark:border-slate-700/50">
              {e.remarks}
            </p>
          )}
        </div>
      ))}
    </div>
  );
};

// ─── Main component ───────────────────────────────────────────────────────────

const DetailedTeamView = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { semesterMap } = useGlobalFilters();
  const [activeTab, setActiveTab] = useState('Proposal');
  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedPsForAnalysis, setSelectedPsForAnalysis] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTeam = async () => {
      try {
        const response = await api.get(`/teams/${id}`);
        setTeam(response.data);
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to load team details');
      } finally {
        setLoading(false);
      }
    };
    fetchTeam();
  }, [id]);

  const tabs = ['Proposal', 'Presentations', 'Evaluations'];

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-rose-500">
        <AlertCircle className="w-10 h-10 mb-4" />
        <p className="font-bold">{error}</p>
        <button onClick={() => navigate(-1)} className="mt-4 px-4 py-2 bg-slate-100 dark:bg-slate-800 rounded-xl text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
          Go Back
        </button>
      </div>
    );
  }

  const teamName     = team?.projectTitle || team?.name || 'Unknown Team';
  const teamTag      = teamDisplayLabel(team?.id || id, team, semesterMap);
  const domain       = team?.domain || 'General';
  const members      = team?.members || [];
  const status       = team?.status || 'Pending';

  return (
    <>
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4 mb-4 mt-2">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-xl bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/50 text-slate-500 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors shadow-sm"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h2 className="text-2xl font-black text-slate-900 dark:text-slate-100">{teamName}</h2>
            <p className="text-slate-500 font-bold text-sm flex items-center gap-2 mt-0.5">
              <span>{teamTag}</span>
              <span className="w-1 h-1 bg-slate-400 rounded-full" />
              <span>{domain}</span>
            </p>
          </div>
          <span className={`ml-auto px-3 py-1.5 rounded-full text-xs font-black uppercase tracking-wider border
            ${status.toLowerCase() === 'valid' || status.toLowerCase() === 'approved'
              ? 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20'
              : 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20'
            }`}>
            {status}
          </span>
        </div>

        {/* Members summary card */}
        {members.length > 0 && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200 dark:border-slate-700/50 shadow-sm">
            <p className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Users size={14} /> Team Members ({members.length})
            </p>
            <div className="flex flex-wrap gap-2">
              {members.map((m, i) => (
                <span key={i} className="px-3 py-1.5 rounded-full bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300">
                  {typeof m === 'string' ? m : m.name}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 overflow-x-auto pb-1 border-b border-slate-200 dark:border-slate-800">
          {tabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-3 rounded-t-xl font-bold text-sm whitespace-nowrap transition-all tracking-wide
                ${activeTab === tab
                  ? 'bg-indigo-50 dark:bg-indigo-600/10 text-indigo-600 dark:text-indigo-400 border-b-2 border-indigo-600 dark:border-indigo-500'
                  : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/50'
                }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="pt-2">
          {activeTab === 'Proposal'      && <ProposalTab    team={team} onViewBlueprint={setSelectedPsForAnalysis} />}
          {activeTab === 'Presentations' && <SchedulesTab   team={team} />}
          {activeTab === 'Evaluations'   && <EvaluationsTab team={team} />}
        </div>
      </div>

      {/* PS Blueprint Modal */}
      {selectedPsForAnalysis && (
        <PsArchitecturePlanModal
          ps={selectedPsForAnalysis}
          onClose={() => setSelectedPsForAnalysis(null)}
        />
      )}
    </>
  );
};

export default DetailedTeamView;
