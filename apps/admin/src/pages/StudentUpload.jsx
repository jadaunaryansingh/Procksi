import React, { useState, useEffect } from 'react';
import Papa from 'papaparse';
import { UploadCloud, FileType, CheckCircle, AlertTriangle, XCircle, Save, Database, ArrowRight, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { apiUpsertTable } from '../lib/api';
import { api } from '../services/api';

// The "master data" schema for the bulk student upload.
//
// This is the single list that drives everything on this page — the required-
// columns hint, the validation, and the preview table columns all read from it.
// To add or change a column, edit here only.
//
// Each entry has:
//   key      — internal name we store the cleaned value under (row._v[key])
//   label    — how the column is shown to the admin (and expected in the sheet)
//   aliases  — accepted header spellings; we take the first one found in the row,
//              so "E-mail", "Email" or "Email ID" all map to the same field
//   validate — returns true if the value is OK, or a short reason string if not
const FIELDS = [
    {
        key: 'name', label: 'Name', aliases: ['Name', 'Full Name', 'Student Name', 'Candidate Name'],
        // Letters plus spaces / . ' - (so "O'Brien" or "A. Kumar" pass); no digits.
        validate: (v) => /^[A-Za-z][A-Za-z .'-]+$/.test(v) || 'Name has invalid characters',
    },
    {
        key: 'roll', label: 'University Roll No.',
        aliases: ['University Roll No.', 'University Roll No', 'University Roll Number', 'Roll No.', 'Roll No', 'Roll Number', 'Student ID', 'Roll'],
        // Letters and numbers only, no spaces or symbols (e.g. "21SCSE1010001").
        validate: (v) => /^[A-Za-z0-9]+$/.test(v) || 'Roll no. must be alphanumeric',
    },
    {
        key: 'section', label: 'Section', aliases: ['Section', 'Sec', 'Sec.'],
        // Letters/numbers and an optional hyphen (e.g. "A", "CS-A").
        validate: (v) => /^[A-Za-z0-9-]+$/.test(v) || 'Invalid section',
    },
    {
        key: 'email', label: 'E-mail', aliases: ['E-mail', 'E-Mail', 'Email', 'Email ID', 'Email Address', 'Mail'],
        // Basic email shape: something@something.something.
        validate: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Invalid e-mail format',
    },
    {
        key: 'contact', label: 'Contact No. (Team Leader)',
        aliases: ['Contact No.(Team Leader)', 'Contact No. (Team Leader)', 'Contact No.', 'Contact Number', 'Contact', 'Phone', 'Phone No.', 'Mobile', 'Mobile No.'],
        // Exactly 10 digits after removing spaces/hyphens (no country code).
        validate: (v) => /^\d{10}$/.test(v.replace(/[\s-]/g, '')) || 'Contact must be 10 digits',
    },
    {
        key: 'branch', label: 'Branch', aliases: ['Branch', 'Branch Name', 'Branch Code', 'Department', 'Dept', 'Dept.', 'Course'],
        // Words with spaces, digits and & . / - (e.g. "CSE", "B.Tech CSE", "Computer Science & Engg.").
        validate: (v) => /^[A-Za-z0-9][A-Za-z0-9 &./-]*$/.test(v) || 'Invalid branch',
    },
    {
        key: 'year', label: 'Year', aliases: ['Year', 'Academic Year', 'Yr'],
        // A whole number from 1 to 4 (college year).
        validate: (v) => (/^\d+$/.test(v) && +v >= 1 && +v <= 4) || 'Year must be 1–4',
    },
    {
        key: 'semester', label: 'Semester', aliases: ['Semester', 'Sem', 'Sem.'],
        // A whole number from 1 to 8 (two semesters per year).
        validate: (v) => (/^\d+$/.test(v) && +v >= 1 && +v <= 8) || 'Semester must be 1–8',
    },
];

export default function StudentUpload() {
    const [file, setFile] = useState(null);
    const [parsedData, setParsedData] = useState([]);
    const [summary, setSummary] = useState(null);
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [dragActive, setDragActive] = useState(false);
    // Which semester the rows are written to. The sheet's Year/Semester columns
    // are validated but cannot select this: the DB keys students by semester_id,
    // a uuid the sheet has no way to express.
    const [semesters, setSemesters] = useState([]);
    const [semesterId, setSemesterId] = useState('');
    const [saveError, setSaveError] = useState('');
    const [savedCount, setSavedCount] = useState(0);

    useEffect(() => {
        let cancelled = false;
        api.getSemesterConfig()
            .then(res => {
                const list = Array.isArray(res?.data) ? res.data : [];
                if (cancelled) return;
                setSemesters(list);
                // Default to the active semester rather than the first row, so a
                // stray inactive semester is never the silent default.
                const active = list.find(s2 => s2.is_active);
                setSemesterId((active || list[0])?.id || '');
            })
            .catch(err => console.error('Could not load semesters', err));
        return () => { cancelled = true; };
    }, []);

    const handleFileUpload = (uploadedFile) => {
        if (!uploadedFile) return;
        setFile(uploadedFile);
        
        // Papa Parse reads the CSV/XLSX. `header: true` means each row comes back
        // as an object keyed by the column headers (e.g. row['Name']).
        Papa.parse(uploadedFile, {
            header: true,
            skipEmptyLines: true,
            complete: (results) => {
                const data = results.data;
                // Running tallies for the KPI cards at the top.
                let valid = 0, invalid = 0, duplicate = 0;
                // Remember roll numbers / e-mails we've already accepted, so a
                // second row with the same one can be flagged as a duplicate.
                const seenEmail = new Set();
                const seenRoll = new Set();

                // Check every row and tag it Valid / Duplicate / Invalid.
                const processedData = data.map((row, index) => {
                    const values = {};   // cleaned value per field, keyed by field.key
                    const errors = [];   // reasons this row failed (empty = all good)
                    const rowKeys = Object.keys(row);

                    // Step 1: for each required column, read its value and check it.
                    for (const f of FIELDS) {
                        // Find the value using the first header alias present in the row (case-insensitive).
                        let raw = '';
                        for (const a of f.aliases) {
                            const matchedKey = rowKeys.find(k => k.trim().toLowerCase() === a.trim().toLowerCase());
                            if (matchedKey !== undefined) { raw = row[matchedKey]; break; }
                        }
                        const val = String(raw ?? '').trim();
                        values[f.key] = val;
                        // Missing value → required error; otherwise run the field's rule.
                        if (!val) { errors.push(`${f.label} is required`); continue; }
                        const res = f.validate(val);
                        if (res !== true) errors.push(res);   // res is the reason string
                    }

                    // Step 2: decide the row's status.
                    let status;
                    if (errors.length) {
                        // Something failed a check → Invalid.
                        status = 'Invalid'; invalid++;
                    } else {
                        // All fields valid — now make sure this student isn't already
                        // in the file (same roll no. or e-mail seen earlier).
                        const em = values.email.toLowerCase();
                        const rl = values.roll.toLowerCase();
                        if (seenEmail.has(em) || seenRoll.has(rl)) {
                            status = 'Duplicate'; duplicate++;
                            errors.push('Duplicate roll no. / e-mail in file');
                        } else {
                            status = 'Valid'; valid++;
                            seenEmail.add(em); seenRoll.add(rl);   // remember for later rows
                        }
                    }

                    // Keep the original row plus our results: _v (cleaned values),
                    // status, and reason (shown in the preview's Reason column).
                    return { ...row, _v: values, status, reason: errors.join('; '), id: index };
                });

                setParsedData(processedData);
                setSummary({ valid, duplicate, invalid, total: processedData.length });
                setSaveSuccess(false);
            }
        });
    };

    // Maps a validated row onto the students table. The column names are not the
    // sheet's: the roll number is the primary key `id`, contact lands in `phone`,
    // and there is no `semester` column -- the semester is the semester_id uuid.
    const toStudentRow = (v) => ({
        id: v.roll,
        student_id: v.roll,
        name: v.name,
        email: v.email,
        section: v.section,
        branch: v.branch,
        year: Number(v.year),
        phone: v.contact,
        status: 'Active',
        semester_id: semesterId,
    });

    const handleSave = async () => {
        if (!semesterId) { setSaveError('Choose a semester before importing.'); return; }
        const rows = parsedData.filter(r => r.status === 'Valid').map(r => toStudentRow(r._v));
        if (!rows.length) { setSaveError('No valid rows to import.'); return; }

        setIsSaving(true);
        setSaveError('');
        try {
            // Chunked: 456 rows in one request is large enough to risk a timeout,
            // and a partial failure is easier to reason about in blocks.
            const CHUNK = 100;
            let written = 0;
            for (let i = 0; i < rows.length; i += CHUNK) {
                const chunk = rows.slice(i, i + CHUNK);
                // on_conflict id: re-importing a corrected sheet updates the
                // existing students rather than erroring on the primary key.
                await apiUpsertTable('students', chunk, 'id');
                written += chunk.length;
            }
            setSavedCount(written);
            setSaveSuccess(true);
            setParsedData([]);
            setSummary(null);
            setFile(null);
        } catch (err) {
            // Surfaced, not swallowed: this page previously reported success
            // unconditionally, which is why nothing was ever imported.
            console.error('Student import failed', err);
            setSaveError(err?.message || 'Import failed. Nothing was saved.');
        } finally {
            setIsSaving(false);
        }
    };

    const onDragOver = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(true); };
    const onDragLeave = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false); };
    const onDrop = (e) => { e.preventDefault(); e.stopPropagation(); setDragActive(false); if (e.dataTransfer.files && e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]); };

    return (
        <div className="space-y-8 relative z-10 w-full min-h-[calc(100vh-8rem)]">
            {/* Ambient Background Graphic */}
            <div className="absolute top-0 right-0 w-max h-max pointer-events-none z-[-1] opacity-50 dark:opacity-30 mix-blend-multiply dark:mix-blend-screen text-indigo-100 dark:text-indigo-900/50 -translate-y-12 translate-x-12">
                <svg width="400" height="400" viewBox="0 0 100 100" fill="currentColor">
                    <circle cx="50" cy="50" r="40" opacity="0.5" />
                    <path d="M50 10 L90 50 L50 90 L10 50 Z" opacity="0.8" />
                </svg>
            </div>

            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row justify-between items-start sm:items-center bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 sm:p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
                <div className="flex items-center">
                    <div className="w-12 h-12 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-2xl flex items-center justify-center mr-4 border border-indigo-100 dark:border-indigo-500/20 shadow-sm">
                        <Database className="w-6 h-6" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">Bulk Import Portal</h1>
                        <p className="text-slate-500 dark:text-slate-400 text-sm mt-1 font-medium">Ingest massive student records safely via intelligent CSV/XLSX parsing mechanisms.</p>
                    </div>
                </div>
            </motion.div>

            {/* Upload Area */}
            <AnimatePresence mode="wait">
                {!file && !saveSuccess && (
                    <motion.div key="upload-zone" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
                        onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
                        className={`bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-12 sm:p-20 rounded-[2.5rem] shadow-sm border-2 border-dashed transition-all duration-300 text-center flex flex-col items-center justify-center relative overflow-hidden ${dragActive ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-900/20 scale-[1.02]' : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
                        {/* Decorative background dashed ring */}
                        <div className="absolute inset-0 z-0 flex items-center justify-center pointer-events-none opacity-20 dark:opacity-10">
                            <svg className={`w-96 h-96 text-indigo-500 ${dragActive ? 'animate-spin-slow' : ''}`} viewBox="0 0 100 100">
                                <circle cx="50" cy="50" r="48" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="4 4" />
                                <circle cx="50" cy="50" r="40" fill="none" stroke="currentColor" strokeWidth="0.5" strokeDasharray="2 6" />
                            </svg>
                        </div>
                        
                        <div className="relative z-10">
                            <motion.div animate={{ y: [0, -10, 0] }} transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }} className="w-20 h-20 bg-gradient-to-tr from-indigo-500 to-purple-500 text-white rounded-3xl flex items-center justify-center mx-auto mb-6 shadow-xl shadow-indigo-500/30">
                                <UploadCloud className="w-10 h-10" />
                            </motion.div>
                            <h3 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">Drop your data payload here</h3>
                            <p className="text-sm font-medium text-slate-500 dark:text-slate-400 mt-3 max-w-sm mx-auto">Upload robust spreadsheets formatted as .CSV or .XLSX arrays up to exactly 10 Megabytes.</p>
                            <p className="text-[11px] font-semibold text-slate-400 dark:text-slate-500 mt-3 mb-8 max-w-lg mx-auto leading-relaxed">
                                <span className="uppercase tracking-widest text-slate-400/80">Required columns:</span>{' '}
                                {FIELDS.map((f) => f.label).join(' · ')}
                            </p>
                            <label className="bg-slate-900 border border-slate-700 dark:bg-indigo-600 dark:border-indigo-500/50 hover:bg-slate-800 dark:hover:bg-indigo-700 text-white px-8 py-3.5 rounded-xl cursor-pointer transition-all shadow-xl shadow-slate-900/20 dark:shadow-indigo-500/30 text-sm font-bold uppercase tracking-widest inline-flex items-center group">
                                Select File <ArrowRight className="w-4 h-4 ml-3 opacity-70 group-hover:translate-x-1 group-hover:opacity-100 transition-all" />
                                <input type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => handleFileUpload(e.target.files[0])} />
                            </label>
                        </div>
                    </motion.div>
                )}

                {/* Success Message */}
                {saveSuccess && (
                    <motion.div key="success" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                        className="bg-gradient-to-br from-emerald-500 to-teal-700 p-1 rounded-[2.5rem] shadow-2xl relative overflow-hidden">
                        <div className="absolute right-0 top-0 w-64 h-64 bg-white/10 rounded-full blur-3xl pointer-events-none"></div>
                        <div className="bg-white dark:bg-slate-900 rounded-[2.3rem] p-12 text-center h-full w-full relative z-10 flex flex-col items-center">
                            <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', bounce: 0.5, delay: 0.2 }} className="w-20 h-20 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6 shadow-indigo-500/10 shadow-xl border-4 border-emerald-100 dark:border-emerald-500/30">
                                <CheckCircle className="w-10 h-10" />
                            </motion.div>
                            <h3 className="text-3xl font-black text-slate-800 dark:text-white mb-3">Upload Successful!</h3>
                            {/* The real count from the write, not a fixed sentence:
                                this screen used to claim success unconditionally. */}
                            <p className="text-slate-500 dark:text-slate-400 text-sm mb-8 font-medium max-w-md mx-auto">
                                <span className="font-black text-slate-700 dark:text-slate-200">{savedCount}</span> student records written to{' '}
                                <span className="font-black text-slate-700 dark:text-slate-200">
                                    {(() => { const sm = semesters.find(x => x.id === semesterId);
                                        return sm ? `${sm.year} - Yr ${sm.academic_level}` : 'the selected semester'; })()}
                                </span>. Open the Students page to confirm.
                            </p>
                            <button onClick={() => setSaveSuccess(false)} className="bg-emerald-600 hover:bg-emerald-700 border border-emerald-500/50 text-white px-8 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase transition-colors shadow-lg shadow-emerald-500/30">
                                Transmit Another Payload
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Preview & Summary Area */}
            {file && summary && !saveSuccess && (
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center space-x-5 shadow-sm hover:-translate-y-1 transition-transform">
                            <div className="p-4 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 rounded-2xl border border-indigo-100 dark:border-indigo-500/20"><FileType className="w-6 h-6" /></div>
                            <div><p className="text-xs uppercase tracking-widest font-bold text-slate-400 mb-1">Total Payload</p><p className="text-3xl font-black text-slate-800 dark:text-white">{summary.total}</p></div>
                        </div>
                        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center space-x-5 shadow-sm hover:-translate-y-1 transition-transform">
                            <div className="p-4 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-2xl border border-emerald-100 dark:border-emerald-500/20"><CheckCircle className="w-6 h-6" /></div>
                            <div><p className="text-xs uppercase tracking-widest font-bold text-slate-400 mb-1">Integrity Valid</p><p className="text-3xl font-black text-slate-800 dark:text-white">{summary.valid}</p></div>
                        </div>
                        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center space-x-5 shadow-sm hover:-translate-y-1 transition-transform">
                            <div className="p-4 bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-2xl border border-amber-100 dark:border-amber-500/20"><AlertTriangle className="w-6 h-6" /></div>
                            <div><p className="text-xs uppercase tracking-widest font-bold text-slate-400 mb-1">Duplications</p><p className="text-3xl font-black text-slate-800 dark:text-white">{summary.duplicate}</p></div>
                        </div>
                        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-md p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center space-x-5 shadow-sm hover:-translate-y-1 transition-transform">
                            <div className="p-4 bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 rounded-2xl border border-red-100 dark:border-red-500/20"><XCircle className="w-6 h-6" /></div>
                            <div><p className="text-xs uppercase tracking-widest font-bold text-slate-400 mb-1">Corrupted</p><p className="text-3xl font-black text-slate-800 dark:text-white">{summary.invalid}</p></div>
                        </div>
                    </div>

                    <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col">
                        <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 flex justify-between items-center bg-slate-50/50 dark:bg-slate-900/20">
                            <h3 className="font-bold text-slate-800 dark:text-white flex items-center tracking-tight">
                                <Database className="w-5 h-5 mr-2 text-indigo-500" /> Data Preview Matrix
                            </h3>
                            <button className="text-sm font-bold text-slate-500 hover:text-red-500 dark:text-slate-400 dark:hover:text-red-400 transition-colors uppercase tracking-wider" onClick={() => { setFile(null); setParsedData([]); }}>Abort Upload</button>
                        </div>
                        <div className="overflow-x-auto max-h-[500px]">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-50 dark:bg-slate-800/80 sticky top-0 z-10 shadow-sm backdrop-blur-md">
                                    <tr>
                                        <th className="p-4 font-bold text-xs text-slate-400 dark:text-slate-500 uppercase tracking-widest border-b border-slate-200 dark:border-slate-700 pl-6 whitespace-nowrap">Validation</th>
                                        {FIELDS.map((f) => (
                                            <th key={f.key} className="p-4 font-bold text-xs text-slate-400 dark:text-slate-500 uppercase tracking-widest border-b border-slate-200 dark:border-slate-700 whitespace-nowrap">{f.label}</th>
                                        ))}
                                        <th className="p-4 font-bold text-xs text-slate-400 dark:text-slate-500 uppercase tracking-widest border-b border-slate-200 dark:border-slate-700 pr-6 whitespace-nowrap">Reason</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                                    {parsedData.slice(0, 50).map((row) => (
                                        <tr key={row.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-700/30 transition-colors">
                                            <td className="p-4 pl-6">
                                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border shadow-sm ${
                                                    row.status === 'Valid' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:border-emerald-500/30 dark:text-emerald-400' :
                                                    row.status === 'Duplicate' ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-400' :
                                                    'bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-400'
                                                }`}>
                                                    {row.status}
                                                </span>
                                            </td>
                                            {FIELDS.map((f) => (
                                                <td key={f.key} className="p-4 text-sm font-medium text-slate-600 dark:text-slate-300 whitespace-nowrap">
                                                    {row._v?.[f.key] || <span className="text-red-400 dark:text-red-500">—</span>}
                                                </td>
                                            ))}
                                            <td className="p-4 text-xs font-semibold text-red-500 dark:text-red-400 pr-6 min-w-[220px]">{row.status !== 'Valid' ? row.reason : ''}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {parsedData.length > 50 && (
                                <div className="p-4 text-center text-xs font-bold text-slate-500 uppercase tracking-widest bg-slate-50 dark:bg-slate-800/80 border-t border-slate-100 dark:border-slate-700">
                                    Displaying 50 vector rows. Total matrix: {parsedData.length}
                                </div>
                            )}
                        </div>
                        <div className="p-6 bg-slate-50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-700 flex flex-col sm:flex-row justify-between items-stretch sm:items-center gap-4">
                            {/* The target semester. Nothing in the sheet can express
                                this, so it is an explicit choice rather than a guess. */}
                            <label className="flex items-center gap-3 min-w-0">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 shrink-0">Import into</span>
                                <select value={semesterId} onChange={e => { setSemesterId(e.target.value); setSaveError(''); }}
                                    className="min-w-0 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-sm font-bold rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                                    {semesters.length === 0 && <option value="">No semesters found</option>}
                                    {semesters.map(sem => (
                                        <option key={sem.id} value={sem.id}>
                                            {sem.year} - Yr {sem.academic_level}{sem.branch ? ` - ${sem.branch}` : ''}{sem.is_active ? ' (Active)' : ''}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <div className="flex items-center gap-4">
                                {saveError && <p className="text-xs font-bold text-red-500 max-w-xs">{saveError}</p>}
                                <button onClick={handleSave} disabled={isSaving || summary.valid === 0 || !semesterId}
                                    title={!semesterId ? 'Choose a semester first' : undefined}
                                    className={`flex items-center px-8 py-3.5 rounded-xl text-sm font-black uppercase tracking-widest shadow-xl transition-all ${
                                        isSaving ? 'bg-indigo-400/50 text-white cursor-wait' :
                                        (summary.valid === 0 || !semesterId) ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed' :
                                        'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-500/30 border border-indigo-500/50 active:scale-[0.98]'
                                    }`}>
                                    {isSaving ? <><Loader2 className="w-5 h-5 mr-3 animate-spin" /> Importing {summary.valid} rows</> : <><Save className="w-5 h-5 mr-3" /> Import {summary.valid} Students</>}
                                </button>
                            </div>
                        </div>
                    </div>
                </motion.div>
            )}
        </div>
    );
}
