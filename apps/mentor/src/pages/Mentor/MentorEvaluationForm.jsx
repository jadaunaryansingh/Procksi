import React, { useState, useEffect, useMemo } from 'react';
import { Send, CheckCircle2, AlertCircle, FileText, Loader2, ExternalLink, Users } from 'lucide-react';
import { api } from '../../services/api';
import MemberProfileChip from '../../components/MemberProfileChip';
import { useGlobalFilters } from '../../context/useGlobalFilters';

const MentorEvaluationForm = () => {
  const { filterRows, filters } = useGlobalFilters();
  // Legacy State
  
  // Shared State
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [teams, setTeams] = useState([]);
  const [selectedTeamId, setSelectedTeamId] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  
  // Cycles State
  const [cycles, setCycles] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [selectedCycleId, setSelectedCycleId] = useState('');
  const [cycleScore, setCycleScore] = useState('');
  
  // Student Evaluation State
  const [teamMembers, setTeamMembers] = useState([]);
  const [studentScores, setStudentScores] = useState({});
  const [remarksText, setRemarksText] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Try fetching cycles first
        const cyclesRes = await api.get('/presentation-cycles');
        const data = cyclesRes.data || {};
        
        if (data.cycles && data.cycles.length > 0) {
            setCycles(data.cycles);
            setTeams(data.teams || []);
            setSubmissions(data.submissions || []);
            setEvaluations(data.evaluations || []);
            setSelectedCycleId(data.cycles[0].id);
            // Default to empty so the user must select a team
            setSelectedTeamId('');
        } else {
            // Fallback to legacy teams
            const response = await api.get('/teams');
            const tData = Array.isArray(response.data) ? response.data : response.data.teams || response.data.data || [];
            setTeams(tData);
            setSelectedTeamId(''); // Default to empty
        }
      } catch (err) {
        // silent fallback
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    // Re-run when the global filter is applied: `filters` is what Apply
    // commits, and the team list it feeds is scoped by semester/year/branch.
  }, [filters]);

  // Teams the current global filter admits. Kept separate from `teams` so the
  // raw fetch result stays intact for lookups elsewhere.
  const visibleTeams = useMemo(() => filterRows(teams) || [], [teams, filterRows]);

  // A team that the filter has just excluded must not stay selected, or the
  // form would go on grading a team no longer offered in the dropdown.
  useEffect(() => {
    if (!selectedTeamId) return;
    const stillVisible = visibleTeams.some(
      (t) => String(t.id || t.team_id) === String(selectedTeamId)
    );
    if (!stillVisible) {
      setSelectedTeamId('');
      setTeamMembers([]);
      setStudentScores({});
    }
  }, [visibleTeams, selectedTeamId]);

  // Fetch Team Members when Team changes
  useEffect(() => {
    if (selectedTeamId) {
      const fetchTeamDetails = async () => {
        try {
            const res = await api.get(`/teams/${selectedTeamId}`);
            const data = res.data?.data || res.data;
            // The API flattens team members to plain name strings (see
            // parse_members in mentor_portal.py), so `member.name`/`.roll`/`.id`
            // are all undefined on the raw list. Normalise to objects here:
            // every member needs a name to display and a distinct, stable key,
            // because `id` is what studentScores is keyed by and what gets
            // persisted inside the evaluation remarks. Falling back to the name
            // keeps saved scores attached to the right student across reloads —
            // an array index would silently remap them if the roster changes.
            if (Array.isArray(data?.members)) {
                setTeamMembers(data.members.map((m) => {
                    if (m && typeof m === 'object') {
                        const name = m.name || m.studentName || '';
                        return { ...m, name, id: m.id || m.roll || name };
                    }
                    const name = String(m ?? '').trim();
                    return { id: name, name, roll: '' };
                }).filter((m) => m.id));
            } else {
                setTeamMembers([]);
            }
        } catch(e) {
            console.error("Failed to fetch team members");
            setTeamMembers([]);
        }
      };
      fetchTeamDetails();
    }
  }, [selectedTeamId]);

  // Update form if evaluation already exists
  useEffect(() => {
      if (cycles.length > 0 && selectedCycleId && selectedTeamId) {
          const existingEval = evaluations.find(e => e.cycle_id === selectedCycleId && e.team_id === selectedTeamId);
          if (existingEval) {
              setCycleScore(existingEval.total_score || '');
              
              let text = existingEval.remarks || '';
              let sScores = {};
              try {
                  const parsed = JSON.parse(text);
                  if (parsed.text !== undefined) {
                      text = parsed.text;
                      sScores = parsed.studentScores || {};
                  }
              } catch {
                  // Older evaluations stored plain text in `remarks` rather than the
                  // packed {text, studentScores} JSON — use it verbatim.
              }
              
              setRemarksText(text);
              setStudentScores(sScores);
              setIsSubmitted(true);
          } else {
              setCycleScore('');
              setRemarksText('');
              setStudentScores({});
              setIsSubmitted(false);
          }
      }
  }, [selectedCycleId, selectedTeamId, cycles, evaluations]);

  const calculateStudentTotal = (studentId) => {
      if (!studentScores[studentId]) return 0;
      return Object.values(studentScores[studentId]).reduce((sum, curr) => sum + (parseInt(curr) || 0), 0);
  };

  useEffect(() => {
      if (teamMembers.length > 0 && Object.keys(studentScores).length > 0) {
          let totalSum = 0;
          teamMembers.forEach(m => {
              totalSum += calculateStudentTotal(m.id || m.roll);
          });
          const avg = Math.round(totalSum / teamMembers.length);
          setCycleScore(avg);
      }
  }, [studentScores, teamMembers]);

  const handleStudentScoreChange = (studentId, paramId, value, maxMarks) => {
      const numericVal = parseInt(value) || 0;
      if (value === '' || (numericVal >= 0 && numericVal <= maxMarks)) {
          setStudentScores(prev => ({
              ...prev,
              [studentId]: {
                  ...(prev[studentId] || {}),
                  [paramId]: value === '' ? '' : numericVal
              }
          }));
      }
  };



  const handleSubmit = async (e) => {
    e.preventDefault();
    if (confirm("Confirm submission of marks?")) {
      setSubmitting(true);
      setSubmitError(null);
      try {
        if (cycles.length > 0) {
            const packedRemarks = JSON.stringify({
                text: remarksText,
                studentScores: studentScores
            });
            await api.post(`/presentation-cycles/${selectedCycleId}/evaluate`, {
              team_id: selectedTeamId,
              total_score: parseInt(cycleScore) || 0,
              remarks: packedRemarks,
              scores: {} // Empty criterion scores for legacy payload structure
            });
            // Update local eval state
            setEvaluations(prev => [...prev.filter(e => !(e.cycle_id === selectedCycleId && e.team_id === selectedTeamId)), {
                cycle_id: selectedCycleId, team_id: selectedTeamId, total_score: parseInt(cycleScore) || 0, remarks: packedRemarks, scores: {}
            }]);
            setIsSubmitted(true);
        } else {
            const packedRemarks = JSON.stringify({
                text: remarksText,
                studentScores: studentScores
            });
            await api.post('/evaluate', {
              teamId: selectedTeamId,
              scores: studentScores,
              remarks: packedRemarks,
              total: parseInt(cycleScore) || 0,
            });
            setIsSubmitted(true);
        }
      } catch (err) {
        setSubmitError(err.response?.data?.detail || err.message || 'Submission failed');
      } finally {
        setSubmitting(false);
      }
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center min-h-[400px]"><Loader2 className="w-10 h-10 animate-spin text-indigo-500" /></div>;
  }

  const legacyParameters = [
    { id: 'finalScore', title: 'Final Student Score', desc: 'Overall evaluation score based on performance', max: 30 }
  ];

  const currentSubmission = submissions.find(s => s.cycle_id === selectedCycleId && s.team_id === selectedTeamId);
  const currentCycle = cycles.find(c => c.id === selectedCycleId);
  const isClosed = currentCycle && (currentCycle.status === 'closed' || currentCycle.status === 'frozen');
  const evaluationParams = currentCycle?.evaluation_parameters || [];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 flex items-center gap-3">
            <FileText className="text-indigo-600 dark:text-indigo-400" /> Mentor Assessment
          </h2>
          <p className="text-slate-500 font-medium mt-1">Submit marks prior to panel presentation.</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {cycles.length > 0 && (
              <select
                value={selectedCycleId}
                onChange={(e) => setSelectedCycleId(e.target.value)}
                className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-4 py-2 text-sm font-bold text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {cycles.map(c => <option key={c.id} value={c.id}>{c.title} ({c.status})</option>)}
              </select>
          )}
          {teams.length > 0 && (
            <select
              value={selectedTeamId}
              onChange={(e) => setSelectedTeamId(e.target.value)}
              className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-4 py-2 text-sm font-bold text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="" disabled>-- Select a Team --</option>
              {visibleTeams.map(t => <option key={t.id || t.team_id} value={t.id || t.team_id}>{t.name}</option>)}
            </select>
          )}
        </div>
      </div>

      {!selectedTeamId ? (
          <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-16 text-center shadow-sm">
              <Users className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
              <h3 className="text-xl font-bold text-slate-700 dark:text-slate-200 mb-2">No Team Selected</h3>
              <p className="text-slate-500 max-w-md mx-auto">Please select a team from the dropdown menu in the top right to view their members and begin the evaluation process.</p>
          </div>
      ) : (
          <>

      {submitError && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm animate-in fade-in">
          <AlertCircle className="w-5 h-5 mr-3 shrink-0" />
          {submitError}
        </div>
      )}

      {cycles.length > 0 && currentSubmission && (
          <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm">
              <h3 className="font-bold text-slate-800 dark:text-slate-200 mb-4">Student Submission Details</h3>
              <div className="flex gap-4">
                  {currentSubmission.github_url && (
                      <a href={currentSubmission.github_url} target="_blank" rel="noreferrer" className="flex items-center text-sm text-indigo-600 bg-indigo-50 px-4 py-2 rounded-lg font-bold hover:bg-indigo-100">
                          <ExternalLink className="w-4 h-4 mr-2"/> GitHub Link
                      </a>
                  )}
                  {currentSubmission.file_url && (
                      <a href={currentSubmission.file_url} target="_blank" rel="noreferrer" className="flex items-center text-sm text-emerald-600 bg-emerald-50 px-4 py-2 rounded-lg font-bold hover:bg-emerald-100">
                          <ExternalLink className="w-4 h-4 mr-2"/> Document / Drive Link
                      </a>
                  )}
                  {!currentSubmission.github_url && !currentSubmission.file_url && (
                      <span className="text-sm text-slate-500 font-medium">No links provided.</span>
                  )}
              </div>
              {currentSubmission.notes && (
                  <div className="mt-4 p-4 bg-slate-50 dark:bg-slate-900 rounded-lg text-sm text-slate-600 dark:text-slate-400">
                      <strong>Notes:</strong> {currentSubmission.notes}
                  </div>
              )}
          </div>
      )}

      {cycles.length > 0 && !currentSubmission && !isClosed && (
          <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl flex items-center text-amber-700 text-sm font-bold">
              <AlertCircle className="w-5 h-5 mr-3 shrink-0" />
              Team has not submitted any work for this cycle yet. You can still evaluate them if required.
          </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 overflow-hidden shadow-sm relative">
        <div className="p-8">
          <div className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700/50 rounded-xl p-5 mb-8 flex items-start gap-4">
            <AlertCircle className="text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold text-slate-800 dark:text-slate-200 text-sm">Grading Protocol Active</h4>
              <p className="text-sm font-medium text-slate-500">Ensure extreme fairness. These scores contribute heavily to the final semester grade.</p>
            </div>
          </div>

          <div className="space-y-6">
            {cycles.length > 0 ? (
                evaluationParams.length > 0 ? (
                    <div className="space-y-8">
                        <div className="border-b border-slate-100 dark:border-slate-700/50 pb-2">
                            <h4 className="font-bold text-slate-800 dark:text-slate-200 text-lg">Student Evaluations</h4>
                            <p className="text-xs text-slate-500">Provide marks for each team member. The team total is averaged automatically.</p>
                        </div>
                        
                        {teamMembers.length > 0 ? teamMembers.map(member => (
                            <div key={member.id || member.roll} className="bg-slate-50/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-2xl p-6 relative overflow-hidden group">
                                <div className="absolute top-0 left-0 w-1.5 h-full bg-indigo-500"></div>
                                <div className="flex justify-between items-center mb-6 pl-2">
                                    <MemberProfileChip teamId={selectedTeamId} member={member} />
                                    <div className="text-right">
                                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Total</p>
                                        <p className="text-2xl font-black text-indigo-600 dark:text-indigo-400">
                                            {calculateStudentTotal(member.id || member.roll)}
                                        </p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                    {evaluationParams.map(param => (
                                        <div key={param.id} className="flex justify-between items-center bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 p-4 rounded-xl shadow-sm">
                                            <span className="font-bold text-sm text-slate-700 dark:text-slate-300 truncate pr-4">{param.criterion}</span>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <input
                                                    type="number"
                                                    max={param.max_marks}
                                                    min="0"
                                                    required
                                                    disabled={isClosed}
                                                    value={studentScores[member.id || member.roll]?.[param.id] ?? ''}
                                                    onChange={(e) => handleStudentScoreChange(member.id || member.roll, param.id, e.target.value, param.max_marks)}
                                                    className="w-20 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 text-lg font-bold text-center text-indigo-600 dark:text-indigo-400 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                                />
                                                <span className="text-xs font-bold text-slate-400">/ {param.max_marks}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )) : (
                            <div className="p-12 text-center flex flex-col items-center border border-dashed border-slate-200 dark:border-slate-700 rounded-2xl">
                                <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-4" />
                                <p className="text-slate-500 font-bold">Loading team members...</p>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-xl border border-slate-200 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group">
                        <div>
                        <h4 className="font-bold text-slate-800 dark:text-slate-200 text-lg mb-1">Cycle Evaluation Score</h4>
                        <p className="text-sm font-medium text-slate-500">Score out of 100 based on the presentation and submission.</p>
                        </div>
                        <div className="flex items-center gap-3">
                        <input
                            type="number"
                            max="100"
                            min="0"
                            required
                            disabled={isClosed}
                            value={cycleScore}
                            onChange={(e) => setCycleScore(e.target.value)}
                            className="w-24 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-lg px-4 py-3 text-xl font-black text-indigo-600 dark:text-indigo-400 text-center focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm disabled:opacity-50"
                        />
                        <span className="text-slate-400 font-bold">/ 100</span>
                        </div>
                    </div>
                )
            ) : (
                <div className="space-y-8">
                    <div className="border-b border-slate-100 dark:border-slate-700/50 pb-2">
                        <h4 className="font-bold text-slate-800 dark:text-slate-200 text-lg">Student Evaluations (General)</h4>
                        <p className="text-xs text-slate-500">Provide marks for each team member. The team total is averaged automatically.</p>
                    </div>
                    
                    {teamMembers.length > 0 ? teamMembers.map(member => (
                        <div key={member.id || member.roll} className="bg-slate-50/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-2xl p-6 relative overflow-hidden group">
                            <div className="absolute top-0 left-0 w-1.5 h-full bg-indigo-500"></div>
                            <div className="flex justify-between items-center mb-6 pl-2">
                                <MemberProfileChip teamId={selectedTeamId} member={member} />
                                <div className="text-right">
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Total</p>
                                    <p className="text-2xl font-black text-indigo-600 dark:text-indigo-400">
                                        {calculateStudentTotal(member.id || member.roll)}
                                    </p>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 gap-4">
                                {legacyParameters.map(param => (
                                    <div key={param.id} className="flex justify-between items-center bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700 p-4 rounded-xl shadow-sm">
                                        <div className="overflow-hidden pr-2">
                                            <span className="font-bold text-sm text-slate-700 dark:text-slate-300 block truncate">{param.title}</span>
                                            <span className="text-xs text-slate-500 truncate hidden sm:block">{param.desc}</span>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            <input
                                                type="number"
                                                max={param.max || 10}
                                                min="0"
                                                required
                                                disabled={isSubmitted}
                                                value={studentScores[member.id || member.roll]?.[param.id] ?? ''}
                                                onChange={(e) => handleStudentScoreChange(member.id || member.roll, param.id, e.target.value, param.max || 10)}
                                                className="w-20 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 text-lg font-bold text-center text-indigo-600 dark:text-indigo-400 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                                            />
                                            <span className="text-xs font-bold text-slate-400">/ {param.max || 10}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )) : (
                        <div className="p-12 text-center flex flex-col items-center border border-dashed border-slate-200 dark:border-slate-700 rounded-2xl">
                            <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-4" />
                            <p className="text-slate-500 font-bold">Loading team members...</p>
                        </div>
                    )}
                </div>
            )}
          </div>

          <div className="mt-10">
            <h4 className="font-bold text-slate-800 dark:text-slate-200 text-lg mb-3">Remarks</h4>
            <textarea
              required
              disabled={isClosed && cycles.length > 0 ? true : cycles.length === 0 ? isSubmitted : false}
              value={remarksText}
              onChange={(e) => setRemarksText(e.target.value)}
              placeholder="Provide a detailed assessment of the team's dynamics and overall performance..."
              rows={5}
              className="w-full bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-xl p-5 text-slate-700 dark:text-slate-300 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm resize-none disabled:opacity-50"
            />
          </div>
        </div>

        <div className="bg-slate-50 dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800 p-6 flex flex-col sm:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-6 text-slate-500 text-sm font-medium">
            <span>Minimum passing: {cycles.length > 0 ? '50/100' : '15/30'}</span>
            <div className="h-6 w-px bg-slate-300 dark:bg-slate-700"></div>
            <span>Auto-saves drafts</span>
          </div>
          
          <div className="flex items-center gap-6 w-full sm:w-auto">
            <div className="text-right">
              <p className="text-xs uppercase tracking-wider text-slate-500 font-bold mb-1">Total Score</p>
              <p className="text-3xl font-black tracking-tight text-slate-800 dark:text-slate-100">
                {cycleScore || 0} <span className="text-lg text-slate-400">/ {cycles.length > 0 ? '100' : '30'}</span>
              </p>
            </div>
            <button
              type="submit"
              disabled={submitting || (cycles.length > 0 ? isClosed : isSubmitted)}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-4 rounded-xl font-bold transition-all shadow-lg active:scale-95 disabled:opacity-50 disabled:active:scale-100"
            >
              {submitting ? <><Loader2 size={18} className="animate-spin" /> Submitting...</> : <><Send size={18} /> Submit Formal Marks</>}
            </button>
          </div>
        </div>
      </form>
      </>
      )}
    </div>
  );
};

export default MentorEvaluationForm;
