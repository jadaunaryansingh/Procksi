import React, { useState, useEffect, useMemo } from 'react';
import { Search, Loader2, FileText, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const History = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [evaluations, setEvaluations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 6;

  useEffect(() => {
    api.get('/history')
      .then(r => {
        // API returns array directly after envelope unwrap
        const raw = r.data;
        if (Array.isArray(raw)) {
          setEvaluations(raw);
        } else if (Array.isArray(raw?.evaluations)) {
          setEvaluations(raw.evaluations);
        } else if (Array.isArray(raw?.data)) {
          setEvaluations(raw.data);
        } else {
          setEvaluations([]);
        }
      })
      .catch(err => setError(err.response?.data?.detail || err.message || 'Failed to load history'))
      .finally(() => setLoading(false));
  }, []);

  const { filterRows, semesterMap } = useGlobalFilters();

  const filtered = useMemo(() => {
    const globallyFiltered = filterRows(evaluations);
    return globallyFiltered.filter(e =>
      (e.team || e.teamName || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (e.project || e.projectName || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (e.feedback || e.remarks || '').toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [evaluations, searchTerm, filterRows]);


  const totalPages = Math.ceil(filtered.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const paginated = filtered.slice(start, start + itemsPerPage);

  if (loading) return (
    <div className="flex justify-center items-center min-h-[400px]">
      <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between mb-4 mt-2">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">Evaluation History</h2>
          <p className="text-sm font-medium text-slate-500">Review past team evaluations, scores, and feedback</p>
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm">
          <AlertCircle className="w-5 h-5 mr-3 shrink-0" /> {error}
        </div>
      )}

      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden flex flex-col min-h-[400px]">

        {/* Toolbar */}
        <div className="p-5 border-b border-slate-100 dark:border-slate-700/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-50/50 dark:bg-slate-800/80">
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <FileText size={18} className="text-emerald-500" />
            All Evaluations
            {evaluations.length > 0 && (
              <span className="text-xs font-black px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-500">
                {evaluations.length}
              </span>
            )}
          </h3>
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input
              type="text"
              placeholder="Search teams, projects, or feedback..."
              className="w-full pl-9 pr-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 text-sm font-medium text-slate-800 dark:text-slate-100 placeholder:text-slate-400"
              value={searchTerm}
              // Reset pagination here rather than in an effect on searchTerm:
              // an effect made every keystroke render twice.
              onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
            />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left border-collapse">
            <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700/50">
              <tr>
                <th className="py-4 px-6 text-xs font-bold text-slate-500 uppercase tracking-wider w-1/4">Team</th>
                <th className="py-4 px-6 text-xs font-bold text-slate-500 uppercase tracking-wider w-1/6">Date</th>
                <th className="py-4 px-6 text-xs font-bold text-slate-500 uppercase tracking-wider w-2/5">Feedback</th>
                <th className="py-4 px-6 text-xs font-bold text-slate-500 uppercase tracking-wider text-right w-1/6">Score</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
              {paginated.map((e, idx) => (
                <tr key={e.id || idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors group">
                  <td className="py-4 px-6 align-top">
                    <p className="font-bold text-slate-900 dark:text-slate-100">{teamDisplayLabel(e.team || e.teamName, e, semesterMap)}</p>
                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-0.5">{e.project || e.projectName || ''}</p>
                  </td>
                  <td className="py-4 px-6 text-sm font-semibold text-slate-600 dark:text-slate-300 align-top">
                    {e.date || e.evaluatedOn || '—'}
                  </td>
                  <td className="py-4 px-6 text-sm text-slate-600 dark:text-slate-300 align-top">
                    <p className="line-clamp-2 group-hover:line-clamp-none transition-all duration-300">
                      {e.feedback || e.remarks || 'No feedback provided.'}
                    </p>
                  </td>
                  <td className="py-4 px-6 text-right align-top">
                    {(e.score || e.totalScore) ? (
                      <span className="font-black text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-100 dark:border-emerald-500/20 shadow-sm inline-block">
                        {e.score ?? e.totalScore}
                      </span>
                    ) : (
                      <span className="text-slate-400 text-sm">—</span>
                    )}
                  </td>
                </tr>
              ))}

              {paginated.length === 0 && (
                <tr>
                  <td colSpan="4" className="py-16 text-center">
                    <div className="flex flex-col items-center justify-center text-slate-500">
                      <FileText className="w-12 h-12 mb-3 text-slate-300 dark:text-slate-600" />
                      <p className="text-lg font-medium text-slate-600 dark:text-slate-300">
                        {searchTerm ? 'No results found' : 'No evaluations yet'}
                      </p>
                      <p className="text-sm mt-1 text-slate-400">
                        {searchTerm ? 'Try a different search term.' : 'Evaluations will appear here once submitted.'}
                      </p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/80 flex items-center justify-between min-h-[64px]">
          <span className="text-sm font-medium text-slate-500">
            {filtered.length > 0
              ? `Showing ${start + 1}–${Math.min(start + itemsPerPage, filtered.length)} of ${filtered.length}`
              : 'No entries'}
          </span>
          <div className="flex items-center gap-2">
            <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1 || totalPages === 0}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors bg-white dark:bg-slate-800">
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm font-bold text-slate-700 dark:text-slate-300 px-3">
              {totalPages > 0 ? `${currentPage} / ${totalPages}` : '0 / 0'}
            </span>
            <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages || totalPages === 0}
              className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors bg-white dark:bg-slate-800">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default History;
