import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Sparkles, CheckCircle, XCircle, Clock, RefreshCw,
  Loader2, AlertCircle, Search, Filter, Trophy,
  Eye, ExternalLink, Calendar, User, FileText, Download, X
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { apiFetchTable, apiPatchRow } from '../lib/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { safeFrameUrl, safeLinkUrl } from '../lib/safeUrl';

const STATUS_STYLES = {
  'Pending Review': 'bg-amber-500/10 text-amber-500 border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20',
  approved:        'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20',
  rejected:        'bg-rose-500/10 text-rose-500 border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/20',
};

const STATUS_ICON = {
  'Pending Review': <Clock className="w-3.5 h-3.5" />,
  approved:        <CheckCircle className="w-3.5 h-3.5" />,
  rejected:        <XCircle className="w-3.5 h-3.5" />,
};

export default function ExtraActivities() {
  const { filterRows } = useGlobalFilters();
  const [activities, setActivities] = useState([]);
  const [students, setStudents] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState({}); // { [id]: true }
  const [pointsInput, setPointsInput] = useState({}); // { [id]: string }
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedActivity, setSelectedActivity] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch students list to resolve names/emails/roll numbers
      let studentRows = [];
      try {
        studentRows = await apiFetchTable('students');
      } catch (studentErr) {
        console.error('Failed to load students, continuing with ID fallback', studentErr);
      }
      const studentMap = {};
      for (const s of studentRows) {
        studentMap[s.id] = s;
      }
      setStudents(studentMap);

      // 2. Fetch extra activities — apiFetchTable attaches auth headers (and
      // retries once on token refresh); a bare fetch() here 401s.
      const rows = await apiFetchTable('extra_activities', { orderBy: 'created_at', ascending: false });
      setActivities(rows);

      // Pre-populate points inputs
      const pts = {};
      for (const r of rows) pts[r.id] = String(r.points ?? 0);
      setPointsInput(pts);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAction = async (row, newStatus) => {
    const pts = parseInt(pointsInput[row.id] ?? '0', 10);
    if (isNaN(pts) || pts < 0 || pts > 100) {
      alert('Points must be a number between 0 and 100.');
      return;
    }
    setSaving((s) => ({ ...s, [row.id]: true }));
    try {
      await apiPatchRow('extra_activities', row.id, { status: newStatus, points: pts });
      setActivities((prev) =>
        prev.map((a) => (a.id === row.id ? { ...a, status: newStatus, points: pts } : a))
      );
      // Update selected activity if it is currently open in modal
      if (selectedActivity && selectedActivity.id === row.id) {
        setSelectedActivity(prev => ({ ...prev, status: newStatus, points: pts }));
      }
    } catch (e) {
      alert(`Failed to update: ${e.message}`);
    } finally {
      setSaving((s) => ({ ...s, [row.id]: false }));
    }
  };

  const filtered = useMemo(() => {
    const contextList = activities.map(a => {
      const student = students[a.student_id] || {};
      return {
        ...a,
        semester_id: student.semester_id || student.semesterId || '',
        branch: student.branch || '',
        year: student.year || student.academic_year || student.academic_level || ''
      };
    });

    return filterRows(contextList).filter((a) => {
      const student = students[a.student_id] || {};
      const sName = student.name || '';
      const sRoll = student.student_id || student.id || '';
      const matchSearch =
        !search ||
        (a.student_id || '').toLowerCase().includes(search.toLowerCase()) ||
        (a.title || '').toLowerCase().includes(search.toLowerCase()) ||
        (a.description || '').toLowerCase().includes(search.toLowerCase()) ||
        sName.toLowerCase().includes(search.toLowerCase()) ||
        sRoll.toLowerCase().includes(search.toLowerCase());
      const matchStatus = !statusFilter || (a.status || '').toLowerCase() === statusFilter.toLowerCase();
      return matchSearch && matchStatus;
    });
  }, [activities, students, search, statusFilter, filterRows]);

  const pendingCount = activities.filter((a) => (a.status || '').toLowerCase() === 'pending review').length;
  const approvedCount = activities.filter((a) => (a.status || '').toLowerCase() === 'approved' || (a.status || '').toLowerCase() === 'verified').length;
  const totalPointsAwarded = activities.reduce((sum, a) => sum + (a.points || 0), 0);

  const getProofFileType = (url) => {
    // Only classify URLs that are safe to embed. The suffix checks below are
    // trivially satisfied by "javascript:...//x.pdf", so they must never be the
    // only thing standing between a stored string and an iframe src.
    if (!safeFrameUrl(url)) return 'none';
    const cleanUrl = url.toLowerCase().split('?')[0];
    if (cleanUrl.endsWith('.pdf')) return 'pdf';
    if (cleanUrl.match(/\.(jpg|jpeg|png|webp|gif|svg)$/)) return 'image';
    return 'unknown';
  };

  return (
    <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-6 border-b border-slate-200/50 dark:border-slate-700/50"
      >
        <div>
          <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-1 tracking-tight flex items-center gap-3">
            <Sparkles className="w-7 h-7 text-indigo-500" /> Extra-Curricular Review
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
            Inspect proof documents, award score points, and approve student achievements.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold transition-all shadow-sm active:scale-95"
        >
          <RefreshCw className="w-4 h-4 text-white" /> Refresh Dashboard
        </button>
      </motion.div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 p-6 flex items-center space-x-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center shrink-0">
            <Clock className="w-7 h-7" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-0.5">Pending Review</p>
            <h3 className="text-3xl font-black text-slate-800 dark:text-white">{pendingCount}</h3>
          </div>
        </div>

        <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 p-6 flex items-center space-x-4 shadow-sm hover:shadow-md transition-shadow relative overflow-hidden group">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
            <CheckCircle className="w-7 h-7" />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-0.5">Approved Submissions</p>
            <h3 className="text-3xl font-black text-slate-800 dark:text-white">{approvedCount}</h3>
          </div>
        </div>

        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 rounded-3xl p-6 flex items-center space-x-4 shadow-md text-white relative overflow-hidden group">
          <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center shrink-0">
            <Trophy className="w-7 h-7 text-white animate-bounce" />
          </div>
          <div className="relative z-10">
            <p className="text-sm font-bold text-indigo-100 uppercase tracking-wider mb-0.5">Total Points Awarded</p>
            <h3 className="text-3xl font-black">{totalPointsAwarded}</h3>
          </div>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by student name, roll number, or activity title…"
            className="w-full pl-9 pr-4 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm transition-all"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400 shrink-0" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-4 py-2.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm"
          >
            <option value="">All Statuses</option>
            <option value="Pending Review">Pending Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {/* Main Grid table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden"
      >
        {loading ? (
          <div className="flex items-center justify-center h-56">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-56 gap-3 text-rose-500">
            <AlertCircle className="w-7 h-7" />
            <p className="text-sm font-semibold">{error}</p>
            <button onClick={load} className="text-xs underline text-slate-500">Retry</button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3 text-slate-400 dark:text-slate-500">
            <Sparkles className="w-10 h-10 opacity-30 text-indigo-500" />
            <p className="font-bold text-sm">No submissions match criteria.</p>
            <p className="text-xs">Select other filters or search keywords.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-50/80 dark:bg-slate-900/30 border-b border-slate-200 dark:border-slate-700 sticky top-0 z-10 backdrop-blur-md">
                <tr>
                  {['Student Name', 'Activity Title', 'Date', 'Proof Attachment', 'Status', 'Points', 'Actions'].map((h) => (
                    <th key={h} className="px-5 py-4 text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                <AnimatePresence>
                  {filtered.map((row) => {
                    const normalizedStatus = (row.status || 'Pending Review');
                    const isBusy = saving[row.id];
                    const studentInfo = students[row.student_id] || {};
                    const sName = studentInfo.name || 'Unknown';
                    const sRoll = studentInfo.student_id || row.student_id || '—';
                    return (
                      <motion.tr
                        key={row.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="hover:bg-slate-50/80 dark:hover:bg-slate-700/30 transition-colors group"
                      >
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2.5">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-500/20 text-indigo-500 flex items-center justify-center font-bold text-xs shrink-0 shadow-inner">
                              {sName.charAt(0).toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-slate-800 dark:text-slate-200 truncate">{sName}</p>
                              <p className="text-[10px] font-mono text-slate-400 mt-0.5">{sRoll}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-sm font-bold text-slate-700 dark:text-slate-300 max-w-[200px] truncate" title={row.title}>
                          {row.title}
                        </td>
                        <td className="px-5 py-4 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                          {row.date ? new Date(row.date).toLocaleDateString() : '—'}
                        </td>
                        <td className="px-5 py-4">
                          {row.proof_url ? (
                            <a
                              href={row.proof_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200/50 dark:border-indigo-800 rounded-lg text-xs font-bold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 transition-colors"
                            >
                              <FileText className="w-3.5 h-3.5" /> View Certificate
                            </a>
                          ) : (
                            <span className="text-xs text-slate-400 italic">No proof attached</span>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black border uppercase tracking-wider whitespace-nowrap ${STATUS_STYLES[normalizedStatus] || STATUS_STYLES['Pending Review']}`}>
                            {STATUS_ICON[normalizedStatus] || STATUS_ICON['Pending Review']}
                            {normalizedStatus}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-1.5">
                            <Trophy className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                            <input
                              type="number"
                              min="0"
                              max="100"
                              value={pointsInput[row.id] ?? String(row.points ?? 0)}
                              onChange={(e) => setPointsInput((p) => ({ ...p, [row.id]: e.target.value }))}
                              className="w-16 px-2 py-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-bold text-slate-700 dark:text-slate-300 outline-none focus:ring-2 focus:ring-indigo-500 text-center"
                            />
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => setSelectedActivity(row)}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-300 rounded-lg text-xs font-bold transition-all active:scale-95 whitespace-nowrap"
                            >
                              <Eye className="w-3.5 h-3.5" /> Review
                            </button>
                            <button
                              onClick={() => handleAction(row, 'approved')}
                              disabled={isBusy || normalizedStatus === 'approved'}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white rounded-lg text-xs font-bold transition-all active:scale-95 shadow-sm whitespace-nowrap"
                            >
                              {isBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                              Approve
                            </button>
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        )}
      </motion.div>
      {/* Review Modal */}
      <AnimatePresence>
        {selectedActivity && (() => {
          const sInfo = students[selectedActivity.student_id] || {};
          const sName = sInfo.name || 'Unknown Student';
          const sRoll = sInfo.student_id || selectedActivity.student_id || '—';
          const sEmail = sInfo.email || '—';
          const sBranch = sInfo.branch || '—';
          const normalizedStatus = (selectedActivity.status || 'Pending Review');
          const isBusy = saving[selectedActivity.id];
          const fileType = getProofFileType(selectedActivity.proof_url);

          return (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setSelectedActivity(null)}
                className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm"
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="relative w-full max-w-4xl bg-white dark:bg-slate-800 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden z-10 flex flex-col max-h-[90vh]"
              >
                {/* Header */}
                <div className="p-6 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-50 dark:bg-indigo-550/10 text-indigo-500 rounded-xl">
                      <Sparkles className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-lg font-black text-slate-800 dark:text-white">Review Activity Submission</h3>
                      <p className="text-xs text-slate-400 mt-0.5">ID: {selectedActivity.id}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedActivity(null)}
                    className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Content */}
                <div className="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 min-h-0">
                  {/* Left Column: Details */}
                  <div className="space-y-5 flex flex-col justify-between">
                    <div className="space-y-4">
                      {/* Student Info Card */}
                      <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700">
                        <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2.5 flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5" /> Student Profile
                        </h4>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                           <div>
                            <p className="text-slate-400">Name</p>
                            <p className="font-bold text-slate-700 dark:text-slate-200 mt-0.5">{sName}</p>
                          </div>
                          <div>
                            <p className="text-slate-400">Roll Number</p>
                            <p className="font-bold text-slate-700 dark:text-slate-200 mt-0.5 font-mono">{sRoll}</p>
                          </div>
                          <div className="col-span-2 border-t border-slate-200/50 dark:border-slate-700/50 pt-2 mt-1">
                            <p className="text-slate-400">Email & Branch</p>
                            <p className="font-bold text-slate-700 dark:text-slate-200 mt-0.5 truncate">{sEmail} · {sBranch}</p>
                          </div>
                        </div>
                      </div>

                      {/* Achievement Details */}
                      <div className="space-y-3">
                        <div>
                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                            <FileText className="w-3.5 h-3.5" /> Activity Title
                          </h4>
                          <p className="text-base font-extrabold text-slate-800 dark:text-slate-100 leading-tight">
                            {selectedActivity.title}
                          </p>
                        </div>
                        <div>
                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                            <Calendar className="w-3.5 h-3.5" /> Achievement Date
                          </h4>
                          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                            {selectedActivity.date ? new Date(selectedActivity.date).toLocaleDateString() : '—'}
                          </p>
                        </div>
                        <div>
                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Description / Rationale</h4>
                          <div className="p-4 bg-indigo-50/30 dark:bg-indigo-950/10 border-l-4 border-indigo-500 rounded-r-xl text-sm leading-relaxed text-slate-600 dark:text-slate-300 font-medium whitespace-pre-wrap max-h-48 overflow-y-auto">
                            {selectedActivity.description || 'No description provided.'}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Points Input & Status */}
                    <div className="pt-4 border-t border-slate-100 dark:border-slate-700 flex flex-col gap-4">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Status</h4>
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black border uppercase tracking-wider ${STATUS_STYLES[normalizedStatus] || STATUS_STYLES['Pending Review']}`}>
                            {STATUS_ICON[normalizedStatus] || STATUS_ICON['Pending Review']}
                            {normalizedStatus}
                          </span>
                        </div>
                        <div>
                          <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1 flex items-center gap-1">
                            <Trophy className="w-3 h-3 text-amber-400" /> Award Points
                          </h4>
                          <input
                            type="number"
                            min="0"
                            max="100"
                            value={pointsInput[selectedActivity.id] ?? String(selectedActivity.points ?? 0)}
                            onChange={(e) => setPointsInput((p) => ({ ...p, [selectedActivity.id]: e.target.value }))}
                            className="w-24 px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-black text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 text-center"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Embedded Preview */}
                  <div className="border border-slate-200 dark:border-slate-700 rounded-2xl p-4 bg-slate-50 dark:bg-slate-900/50 flex flex-col min-h-80">
                    <h4 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3 flex items-center justify-between">
                      <span>Proof Document Preview</span>
                      {selectedActivity.proof_url && (
                        <a
                          href={safeLinkUrl(selectedActivity.proof_url) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-500 hover:text-indigo-600 flex items-center gap-0.5 normal-case font-bold"
                        >
                          <ExternalLink className="w-3 h-3" /> Full Screen
                        </a>
                      )}
                    </h4>
                    
                    <div className="flex-1 flex items-center justify-center min-h-0 bg-slate-100 dark:bg-slate-950 rounded-xl overflow-hidden relative border border-slate-200 dark:border-slate-800">
                      {fileType === 'pdf' ? (
                        <iframe
                          src={safeFrameUrl(selectedActivity.proof_url)}
                          referrerPolicy="no-referrer"
                          title="Proof Document Preview"
                          className="w-full h-full border-none"
                        />
                      ) : fileType === 'image' ? (
                        <img
                          src={selectedActivity.proof_url}
                          alt="Proof Document"
                          className="max-w-full max-h-full object-contain"
                        />
                      ) : selectedActivity.proof_url ? (
                        <div className="text-center p-6 space-y-3">
                          <FileText className="w-12 h-12 text-slate-400 mx-auto" />
                          <p className="text-xs text-slate-500">Document preview not supported for this file type.</p>
                          <a
                            href={safeLinkUrl(selectedActivity.proof_url) || undefined}
                            download
                            className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-bold shadow-sm"
                          >
                            <Download className="w-3.5 h-3.5" /> Download File
                          </a>
                        </div>
                      ) : (
                        <div className="text-center text-slate-400 p-6">
                          <AlertCircle className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                          <p className="text-xs italic">No certificate proof uploaded for this activity.</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Footer Actions */}
                <div className="p-6 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex gap-3 justify-end shrink-0">
                  <button
                    disabled={isBusy}
                    onClick={() => setSelectedActivity(null)}
                    className="px-5 py-2.5 rounded-xl text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                  >
                    Close
                  </button>
                  <button
                    disabled={isBusy || normalizedStatus === 'rejected'}
                    onClick={() => handleAction(selectedActivity, 'rejected')}
                    className="px-5 py-2.5 bg-rose-50 hover:bg-rose-100 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400 dark:hover:bg-rose-500/20 disabled:opacity-40 rounded-xl text-sm font-bold transition-all active:scale-95 flex items-center gap-1.5"
                  >
                    <XCircle className="w-4 h-4" /> Reject Submission
                  </button>
                  <button
                    disabled={isBusy || normalizedStatus === 'approved'}
                    onClick={() => handleAction(selectedActivity, 'approved')}
                    className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white rounded-xl text-sm font-bold transition-all active:scale-95 shadow-sm flex items-center gap-1.5"
                  >
                    {isBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                    Approve & Award Points
                  </button>
                </div>
              </motion.div>
            </div>
          );
        })()}
      </AnimatePresence>
    </div>
  );
}
