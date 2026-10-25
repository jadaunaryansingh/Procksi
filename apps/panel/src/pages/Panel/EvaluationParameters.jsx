import React, { useState, useEffect } from 'react';
import { BookOpen, CheckCircle, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { evaluationAPI } from '../../services/api';

const EvaluationParameters = () => {
  const [parameters, setParameters] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSems, setExpandedSems] = useState({});

  useEffect(() => {
    const fetchParameters = async () => {
      try {
        const data = await evaluationAPI.getParameters();
        console.log("FETCHED EVAL PARAMETERS:", data);
        setParameters(data);
        if (data?.semesters) {
          const initial = {};
          data.semesters.forEach(sem => {
            initial[sem.id] = true; // Expanded by default
          });
          setExpandedSems(initial);
        }
      } catch (err) {
        console.error('Failed to fetch evaluation parameters:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchParameters();
  }, []);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          Failed to load evaluation parameters: {error}
        </div>
      </div>
    );
  }

  // Render multiple semesters if available
  if (parameters?.semesters && parameters.semesters.length > 0) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
              Evaluation Parameters
            </h2>
            <p className="text-slate-500 font-medium">Official evaluation rubrics configured across academic semesters.</p>
          </div>
          <div className="px-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-400 text-sm font-bold flex items-center gap-2">
            <BookOpen size={16} /> Locked Guidelines
          </div>
        </div>

        {parameters.semesters.map((sem) => {
          const isOpen = expandedSems[sem.id] !== false;
          return (
            <div key={sem.id} className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden transition-all duration-300">
              {/* Semester Header Toggle */}
              <div 
                onClick={() => setExpandedSems(prev => ({ ...prev, [sem.id]: !isOpen }))}
                className="p-6 bg-slate-50/50 dark:bg-slate-900/20 border-b border-slate-100 dark:border-slate-800/50 flex justify-between items-center cursor-pointer select-none hover:bg-slate-50 dark:hover:bg-slate-900/40 transition-colors"
              >
                <div>
                  <h3 className="text-lg font-black text-slate-800 dark:text-slate-100 flex items-center gap-2 flex-wrap">
                    <span className="px-2 py-0.5 rounded bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-300 text-xs font-black">
                      {sem.branch}
                    </span>
                    {sem.academic_level} — {sem.semester_type}
                  </h3>
                  <p className="text-xs text-slate-400 font-bold mt-1 uppercase tracking-wider">Academic Year: {sem.academic_year}</p>
                </div>
                <div className="text-slate-400 shrink-0 ml-4">
                  {isOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                </div>
              </div>

              {/* Semester Content (Cycles & Rubrics) */}
              {isOpen && (
                <div data-tour="panel-params-list" className="p-6 space-y-8">
                  {sem.cycles?.length === 0 ? (
                    <div className="text-center py-6 text-sm text-slate-400 dark:text-slate-500">No evaluation cycles configured.</div>
                  ) : (
                    sem.cycles.map((cycle) => (
                      <div key={cycle.id} className="space-y-4">
                        {/* Cycle Info Bar */}
                        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                          <h4 className="font-extrabold text-slate-700 dark:text-slate-300 text-sm flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-emerald-500" />
                            {cycle.title}
                          </h4>
                          <span className="text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                            Weightage: {cycle.weightage}%
                          </span>
                        </div>

                        {/* Criteria Grid */}
                        <div className="grid gap-3 sm:grid-cols-1">
                          {cycle.rubrics?.map((section, idx) => (
                            <div key={idx} className="flex items-center justify-between p-4 bg-slate-50/50 dark:bg-slate-900/30 rounded-xl border border-slate-200 dark:border-slate-700/50 hover:border-emerald-200 dark:hover:border-emerald-500/30 transition-colors">
                              <div className="flex items-center gap-3 min-w-0">
                                <div className="w-7 h-7 bg-emerald-100 dark:bg-emerald-500/20 rounded-lg flex items-center justify-center shrink-0">
                                  <CheckCircle size={14} className="text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <p className="font-bold text-slate-800 dark:text-slate-200 text-sm truncate">{section.category}</p>
                              </div>
                              <div className="shrink-0 text-right ml-4">
                                <span className="font-mono font-black text-emerald-600 dark:text-emerald-400">{section.criteria?.[0]?.max_marks}</span>
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider ml-1">marks</span>
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Cycle Total */}
                        <div className="flex justify-end pr-4 text-xs font-bold text-slate-500 dark:text-slate-400">
                          Total Max Marks: <span className="text-emerald-600 dark:text-emerald-400 font-mono font-black ml-1">{cycle.total_maximum}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Fallback single semester render (Legacy / specific active evaluation context)
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
            Evaluation Parameters
          </h2>
          <p className="text-slate-500 font-medium">Official rubric for the evaluations. Maximum {parameters?.total_maximum || 100} marks.</p>
        </div>
        <div className="px-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-400 text-sm font-bold flex items-center gap-2">
          <BookOpen size={16} /> {parameters?.locked ? 'Locked' : 'Read-Only'} Guidelines
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-8 shadow-sm relative overflow-hidden">
        {/* Info Banner */}
        <div className="flex items-start gap-4 mb-8 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 p-4 rounded-xl text-emerald-800 dark:text-emerald-300 relative z-10">
          <div className="p-1 rounded bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
            <Info size={20} />
          </div>
          <p className="text-sm font-medium">
            These parameters are strictly enforced for all panels during this round. 
            Modifications to the criteria can only be made by the Chief Administrator. 
            Please review them thoroughly before starting any active evaluation slot.
          </p>
        </div>

        {/* Criteria List */}
        <div className="space-y-3 relative z-10">
          {parameters?.sections?.map((section, idx) => (
            <div key={idx} className="flex items-start justify-between p-4 bg-slate-50 dark:bg-slate-900/30 rounded-xl border border-slate-200 dark:border-slate-700/50 group hover:border-emerald-200 dark:hover:border-emerald-500/30 transition-colors">
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <div className="w-7 h-7 mt-0.5 bg-emerald-100 dark:bg-emerald-500/20 rounded-lg flex items-center justify-center shrink-0">
                  <CheckCircle size={14} className="text-emerald-600 dark:text-emerald-400" />
                </div>
                <div className="min-w-0">
                  <p className="font-bold text-slate-800 dark:text-slate-200 text-sm">{section.category}</p>
                  {section.criteria?.length === 1 && section.criteria[0].name === section.category ? null : (
                    <ul className="mt-1 space-y-0.5">
                      {section.criteria?.map((c, ci) => (
                        c.name !== section.category && (
                          <li key={ci} className="text-xs text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-600 shrink-0" />
                            {c.name}
                          </li>
                        )
                      ))}
                    </ul>
                  )}
                </div>
              </div>
              <div className="shrink-0 ml-4 text-right">
                <span className="font-mono font-black text-lg text-emerald-600 dark:text-emerald-400">
                  {section.criteria?.reduce((s, c) => s + (c.max_marks || 0), 0)}
                </span>
                <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">marks</p>
              </div>
            </div>
          ))}
        </div>
        
        {/* Total Summarizer */}
        <div className="mt-10 pt-6 border-t border-slate-200 dark:border-slate-700/50 flex justify-end">
          <div data-tour="panel-params-total" className="flex items-center gap-4 bg-slate-50 dark:bg-slate-900/50 px-6 py-4 rounded-xl border border-emerald-200 dark:border-emerald-500/20 shadow-sm shadow-emerald-500/5">
            <span className="text-slate-500 font-bold uppercase tracking-widest text-sm">Total Maximum</span>
            <span className="text-3xl font-black text-emerald-600 dark:text-emerald-400">{parameters?.total_maximum || 100}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EvaluationParameters;
