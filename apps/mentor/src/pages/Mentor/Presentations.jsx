import React, { useState, useEffect } from 'react';
import { Calendar, MapPin, CheckCircle2, Clock, AlertCircle, Loader2, Presentation as PresentationIcon } from 'lucide-react';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const Presentations = () => {
  const [activeTab, setActiveTab] = useState('Upcoming');
  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get('/presentations')
      .then(r => {
        const payload = r.data?.data !== undefined ? r.data.data : r.data;
        setPresentations(payload || []);
      })
      .catch(err => setError(err.response?.data?.detail || err.message || 'Failed to load presentations'))
      .finally(() => setLoading(false));
  }, []);

  const tabs = ['Upcoming', 'Completed'];
  const { filterRows, semesterMap } = useGlobalFilters();
  const filteredPresentations = filterRows(presentations);
  const filtered = filteredPresentations.filter(p => (p.status || '').toLowerCase() === activeTab.toLowerCase());

  const formatDate = (iso) => {
    if (!iso) return 'TBA';
    try {
      return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
    } catch { return iso; }
  };

  if (loading) return (
    <div className="flex justify-center items-center min-h-[400px]">
      <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center p-12 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
      <AlertCircle className="w-10 h-10 text-rose-500 mb-4" />
      <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Failed to load presentations</h3>
      <p className="text-slate-500 font-medium">{error}</p>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="mb-4 mt-2">
        <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100">Presentations</h2>
        <p className="text-sm font-medium text-slate-500">Scheduling &amp; Evaluations</p>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-2 gap-4">
        {tabs.map(tab => {
          const count = presentations.filter(p => (p.status || '').toLowerCase() === tab.toLowerCase()).length;
          return (
            <div key={tab} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl p-4 border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300 text-center">
              <h3 className={`text-3xl font-black mb-1 ${tab === 'Upcoming' ? 'text-indigo-500' : 'text-emerald-500'}`}>{count}</h3>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">{tab}</p>
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-4 border-b border-slate-200 dark:border-slate-700 pb-2">
        {tabs.map(tab => (
          <button key={tab}
            onClick={() => setActiveTab(tab)}
            className={`font-bold text-sm pb-2 border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-indigo-500 text-slate-900 dark:text-slate-100'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
            }`}>
            {tab}
            <span className={`ml-2 text-[10px] font-black px-1.5 py-0.5 rounded-full
              ${activeTab === tab
                ? 'bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400'
                : 'bg-slate-100 dark:bg-slate-700 text-slate-500'}`}>
              {presentations.filter(p => (p.status || '').toLowerCase() === tab.toLowerCase()).length}
            </span>
          </button>
        ))}
      </div>

      {/* Cards */}
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] transition-all duration-300 text-center">
          <div className="w-16 h-16 bg-slate-100 dark:bg-slate-700 rounded-full flex items-center justify-center mb-4">
            <PresentationIcon className="w-8 h-8 text-slate-400" />
          </div>
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">
            No {activeTab.toLowerCase()} presentations
          </h3>
          <p className="text-slate-500 dark:text-slate-400 font-medium">
            {activeTab === 'Upcoming'
              ? 'Presentation slots will appear here once scheduled by the admin.'
              : 'Completed presentations will be listed here.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map(item => (
            <div key={item.id} className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-2xl rounded-3xl border border-white/50 dark:border-slate-700/50 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.1)] hover:shadow-[0_8px_30px_rgb(0,0,0,0.08)] transition-all duration-300 flex flex-col overflow-hidden">
              <div className="p-5 flex-1">

                {/* Team + status badge */}
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{teamDisplayLabel(item.team || item.teamName, item, semesterMap)}</h3>
                    {item.projectTitle && (
                      <p className="text-xs font-medium text-slate-500 mt-0.5 line-clamp-2">{item.projectTitle}</p>
                    )}
                  </div>
                  <span className={`text-xs font-black px-2.5 py-1 rounded-full border ml-2 shrink-0
                    ${(item.status || '').toLowerCase() === 'completed'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20'
                      : 'bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/20'
                    }`}>
                    {item.status}
                  </span>
                </div>

                {/* Date + venue */}
                <div className="space-y-2 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                  <div className="flex items-center gap-2.5 text-sm font-medium text-slate-600 dark:text-slate-400">
                    <div className="p-1.5 rounded-md bg-slate-100 dark:bg-slate-700/50">
                      <Calendar size={14} className="text-slate-500" />
                    </div>
                    {formatDate(item.date || item.presentationDate)}
                  </div>
                  {item.time && (
                    <div className="flex items-center gap-2.5 text-sm font-medium text-slate-600 dark:text-slate-400">
                      <div className="p-1.5 rounded-md bg-slate-100 dark:bg-slate-700/50">
                        <Clock size={14} className="text-slate-500" />
                      </div>
                      {item.time}
                    </div>
                  )}
                  <div className="flex items-center gap-2.5 text-sm font-medium text-slate-600 dark:text-slate-400">
                    <div className="p-1.5 rounded-md bg-slate-100 dark:bg-slate-700/50">
                      <MapPin size={14} className="text-slate-500" />
                    </div>
                    {item.venue || item.location || 'TBA'}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Presentations;
