import React, { useState, useEffect, useMemo, useRef } from 'react';
import Papa from 'papaparse';
import { motion, AnimatePresence } from 'framer-motion';
import {
    UploadCloud, Search, Plus, Edit2, Trash2, X, Save,
    CheckCircle, AlertTriangle, XCircle, ChevronLeft, ChevronRight,
} from 'lucide-react';
import { apiFetchTable, apiUpsertTable, apiDeleteRows } from '../lib/api';

/**
 * Mentor Master Data.
 *
 * Mentors are roster-gated the same way students are: a mentor can only sign up
 * if the coordinator has already uploaded them here. Signup then *claims* that
 * row by setting its password — it never creates one. So a row on this page with
 * no password yet is an invitation that has not been taken up.
 *
 * Two flags describe a mentor's state, and they are independent:
 *   claimed   password_hash is set — the person has completed signup
 *   active    is_active is true — the coordinator has approved them to log in
 */

// Column rules for the bulk upload. `aliases` are the header spellings accepted
// from a sheet; `validate` returns true or a short reason shown in the preview.
const FIELDS = [
    {
        key: 'name', label: 'Name', required: true,
        aliases: ['Name', 'Full Name', 'Mentor Name', 'Faculty Name'],
        validate: (v) => /^[A-Za-z][A-Za-z .'-]+$/.test(v) || 'Name has invalid characters',
    },
    {
        key: 'email', label: 'E-mail', required: true,
        aliases: ['E-mail', 'E-Mail', 'Email', 'Email ID', 'Email Address', 'Mail'],
        // The portal only admits @gla.ac.in, so reject anything else at upload
        // rather than letting it fail confusingly at signup.
        validate: (v) => /^[^\s@]+@gla\.ac\.in$/i.test(v) || 'Must be a @gla.ac.in address',
    },
    {
        key: 'phone', label: 'Phone', required: false,
        aliases: ['Phone', 'Phone No.', 'Contact', 'Contact No.', 'Mobile', 'Mobile No.'],
        validate: (v) => /^\d{10}$/.test(v.replace(/[\s-]/g, '')) || 'Phone must be 10 digits',
    },
    {
        key: 'domain', label: 'Domain', required: false,
        aliases: ['Domain', 'Domains', 'Expertise', 'Specialization', 'Area'],
        validate: () => true,
    },
    {
        key: 'max_teams', label: 'Max Teams', required: false,
        aliases: ['Max Teams', 'MaxTeams', 'Capacity', 'Max Load', 'Load'],
        validate: (v) => (/^\d+$/.test(v) && +v >= 1 && +v <= 20) || 'Max teams must be 1-20',
    },
];

const BLANK = { id: '', name: '', email: '', phone: '', domain: '', max_teams: '3' };

export default function MentorMasterData() {
    const [mentors, setMentors] = useState([]);
    const [loading, setLoading] = useState(true);
    const [query, setQuery] = useState('');
    const [statusFilter, setStatusFilter] = useState('all');
    const [page, setPage] = useState(1);
    const perPage = 10;

    const [addOpen, setAddOpen] = useState(false);
    const [form, setForm] = useState(BLANK);
    const [editing, setEditing] = useState(null);
    const [busy, setBusy] = useState(false);

    const [uploadOpen, setUploadOpen] = useState(false);
    const [parsed, setParsed] = useState([]);
    const [summary, setSummary] = useState(null);
    const [dragActive, setDragActive] = useState(false);
    const fileRef = useRef(null);

    const load = async () => {
        setLoading(true);
        try {
            const rows = await apiFetchTable('mentors', { orderBy: 'id', ascending: true });
            setMentors(Array.isArray(rows) ? rows : []);
        } catch (err) {
            console.error('Could not load mentors', err);
            setMentors([]);
        } finally {
            setLoading(false);
        }
    };
    useEffect(() => { load(); }, []);

    const claimed = (m) => Boolean(m.password_hash);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        return mentors.filter(m => {
            if (statusFilter === 'pending' && (m.is_active || !claimed(m))) return false;
            if (statusFilter === 'active' && !m.is_active) return false;
            if (statusFilter === 'unclaimed' && claimed(m)) return false;
            if (!q) return true;
            return [m.id, m.name, m.email, m.domain]
                .some(v => String(v || '').toLowerCase().includes(q));
        });
    }, [mentors, query, statusFilter]);

    const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
    const shown = filtered.slice((page - 1) * perPage, page * perPage);
    useEffect(() => { setPage(1); }, [query, statusFilter]);

    // Mentor ids are sequential (M-001, M-002...). Allocating them in one pass
    // matters for bulk upload: asking for "the next id" per row would hand the
    // same number to every row in the batch.
    const nextIds = (count) => {
        let max = 0;
        for (const m of mentors) {
            const match = /^M-(\d+)$/.exec(String(m.id || ''));
            if (match) max = Math.max(max, parseInt(match[1], 10));
        }
        return Array.from({ length: count }, (_, i) => `M-${String(max + 1 + i).padStart(3, '0')}`);
    };

    const rowFor = (values, id) => ({
        id,
        name: values.name.trim(),
        email: values.email.trim().toLowerCase(),
        phone: values.phone ? values.phone.replace(/[\s-]/g, '') : null,
        domain: values.domain || null,
        domains: [],
        skills: [],
        experience_years: 0,
        max_teams: parseInt(values.max_teams, 10) || 3,
        current_teams: 0,
        // Uploaded, not yet claimed and not yet approved. Signup sets the
        // password; the coordinator flips is_active.
        is_active: false,
    });

    const saveOne = async (e) => {
        e.preventDefault();
        if (busy) return;
        const email = form.email.trim().toLowerCase();
        if (!/^[^\s@]+@gla\.ac\.in$/i.test(email)) {
            alert('E-mail must be a @gla.ac.in address.');
            return;
        }
        const clash = mentors.find(m => String(m.email).toLowerCase() === email && m.id !== editing?.id);
        if (clash) {
            alert(`That e-mail is already on the roster as ${clash.id}.`);
            return;
        }
        setBusy(true);
        try {
            if (editing) {
                // Never write password_hash or is_active from this form: those
                // belong to the mentor and the approval action respectively.
                await apiUpsertTable('mentors', [{
                    ...editing,
                    name: form.name.trim(),
                    email,
                    phone: form.phone ? form.phone.replace(/[\s-]/g, '') : null,
                    domain: form.domain || null,
                    max_teams: parseInt(form.max_teams, 10) || 3,
                }], 'id');
            } else {
                await apiUpsertTable('mentors', [rowFor({ ...form, email }, nextIds(1)[0])], 'id');
            }
            setAddOpen(false); setEditing(null); setForm(BLANK);
            await load();
        } catch (err) {
            alert(`Could not save mentor: ${err.message}`);
        } finally {
            setBusy(false);
        }
    };

    const setActive = async (mentor, active) => {
        try {
            await apiUpsertTable('mentors', [{ ...mentor, is_active: active }], 'id');
            await load();
        } catch (err) {
            alert(`Could not update approval: ${err.message}`);
        }
    };

    const remove = async (mentor) => {
        if (!confirm(`Remove ${mentor.name} (${mentor.email}) from the mentor roster?\n\nIf they have already signed up, their account stops working.`)) return;
        try {
            await apiDeleteRows('mentors', { id: mentor.id });
            await load();
        } catch (err) {
            alert(`Could not delete mentor: ${err.message}`);
        }
    };

    const parseFile = (file) => {
        if (!file) return;
        Papa.parse(file, {
            header: true, skipEmptyLines: true,
            complete: ({ data }) => {
                const existing = new Set(mentors.map(m => String(m.email).toLowerCase()));
                const seen = new Set();
                let valid = 0, invalid = 0, duplicate = 0;

                const rows = data.map((raw, index) => {
                    const keys = Object.keys(raw);
                    const values = {}; const errors = [];

                    for (const f of FIELDS) {
                        let cell = '';
                        for (const alias of f.aliases) {
                            const k = keys.find(x => x.trim().toLowerCase() === alias.trim().toLowerCase());
                            if (k !== undefined) { cell = raw[k]; break; }
                        }
                        const val = String(cell ?? '').trim();
                        values[f.key] = val;
                        if (!val) { if (f.required) errors.push(`${f.label} is required`); continue; }
                        const res = f.validate(val);
                        if (res !== true) errors.push(res);
                    }

                    let status;
                    if (errors.length) { status = 'Invalid'; invalid++; }
                    else {
                        const em = values.email.toLowerCase();
                        if (seen.has(em)) { status = 'Duplicate'; duplicate++; errors.push('Duplicate e-mail in file'); }
                        else if (existing.has(em)) { status = 'Duplicate'; duplicate++; errors.push('Already on the roster'); }
                        else { status = 'Valid'; valid++; seen.add(em); }
                    }
                    return { _v: values, status, reason: errors.join('; '), key: index };
                });

                setParsed(rows);
                setSummary({ valid, duplicate, invalid, total: rows.length });
            },
        });
    };

    const commitUpload = async () => {
        const good = parsed.filter(r => r.status === 'Valid');
        if (!good.length || busy) return;
        setBusy(true);
        try {
            const ids = nextIds(good.length);
            await apiUpsertTable('mentors', good.map((r, i) => rowFor(r._v, ids[i])), 'id');
            setParsed([]); setSummary(null); setUploadOpen(false);
            await load();
            alert(`Added ${good.length} mentor${good.length === 1 ? '' : 's'} to the roster. They can now sign up.`);
        } catch (err) {
            alert(`Upload failed: ${err.message}`);
        } finally {
            setBusy(false);
        }
    };

    const counts = useMemo(() => ({
        total: mentors.length,
        active: mentors.filter(m => m.is_active).length,
        pending: mentors.filter(m => claimed(m) && !m.is_active).length,
        unclaimed: mentors.filter(m => !claimed(m)).length,
    }), [mentors]);

    const Chip = ({ id, label, n }) => (
        <button onClick={() => setStatusFilter(id)}
            className={`px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${statusFilter === id
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
            {label}{typeof n === 'number' ? ` ${n}` : ''}
        </button>
    );

    return (
        <div className="space-y-6">
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-slate-900 rounded-3xl p-8 text-white shadow-xl shadow-indigo-500/20 border border-indigo-500/30">
                <h1 className="text-3xl sm:text-4xl font-black mb-3">Mentor Master Data</h1>
                <p className="text-indigo-100/90 text-sm md:text-base max-w-2xl font-medium">
                    The mentor roster. Only mentors listed here can sign up on the mentor portal,
                    and each still needs your approval before they can log in.
                </p>
            </motion.div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: 'On roster', value: counts.total, tone: 'text-slate-800 dark:text-white' },
                    { label: 'Approved', value: counts.active, tone: 'text-emerald-600 dark:text-emerald-400' },
                    { label: 'Awaiting approval', value: counts.pending, tone: 'text-amber-600 dark:text-amber-400' },
                    { label: 'Not signed up yet', value: counts.unclaimed, tone: 'text-slate-500' },
                ].map(c => (
                    <div key={c.label} className="bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200/60 dark:border-slate-700/50 shadow-sm">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{c.label}</p>
                        <p className={`text-3xl font-black mt-1 ${c.tone}`}>{c.value}</p>
                    </div>
                ))}
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/60 dark:border-slate-700/50 shadow-sm overflow-hidden">
                <div className="p-5 flex flex-col lg:flex-row gap-3 lg:items-center justify-between border-b border-slate-100 dark:border-slate-700/50">
                    <div className="relative flex-1 max-w-md">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                        <input value={query} onChange={e => setQuery(e.target.value)}
                            placeholder="Search name, e-mail or ID..."
                            className="w-full pl-9 pr-3 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" />
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => { setEditing(null); setForm(BLANK); setAddOpen(true); }}
                            className="flex items-center px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md shadow-indigo-500/20 transition-all">
                            <Plus className="w-4 h-4 mr-1.5" /> Add Mentor
                        </button>
                        <button onClick={() => setUploadOpen(true)}
                            className="flex items-center px-4 py-2.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-sm font-bold hover:bg-slate-200 dark:hover:bg-slate-600 transition-all">
                            <UploadCloud className="w-4 h-4 mr-1.5" /> Bulk Upload
                        </button>
                    </div>
                </div>

                <div className="px-5 py-3 flex items-center gap-1.5 border-b border-slate-100 dark:border-slate-700/50 overflow-x-auto">
                    <Chip id="all" label="All" n={counts.total} />
                    <Chip id="pending" label="Awaiting approval" n={counts.pending} />
                    <Chip id="active" label="Approved" n={counts.active} />
                    <Chip id="unclaimed" label="Not signed up" n={counts.unclaimed} />
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900/50 text-[10px] font-black uppercase tracking-widest text-slate-400">
                            <tr>
                                <th className="text-left px-5 py-3">Mentor</th>
                                <th className="text-left px-5 py-3">ID</th>
                                <th className="text-left px-5 py-3">Domain</th>
                                <th className="text-left px-5 py-3">State</th>
                                <th className="text-right px-5 py-3">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {loading && (
                                <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-400 font-medium">Loading...</td></tr>
                            )}
                            {!loading && shown.length === 0 && (
                                <tr><td colSpan={5} className="px-5 py-10 text-center text-slate-400 font-medium">
                                    {mentors.length === 0 ? 'No mentors on the roster yet. Add one or upload a sheet.' : 'Nothing matches that filter.'}
                                </td></tr>
                            )}
                            {!loading && shown.map(m => (
                                <tr key={m.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/20">
                                    <td className="px-5 py-3">
                                        <p className="font-bold text-slate-800 dark:text-white">{m.name}</p>
                                        <p className="text-xs text-slate-400">{m.email}</p>
                                    </td>
                                    <td className="px-5 py-3 font-mono text-xs text-slate-500">{m.id}</td>
                                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">{m.domain || '—'}</td>
                                    <td className="px-5 py-3">
                                        {m.is_active ? (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                                                <CheckCircle className="w-3 h-3" /> Approved
                                            </span>
                                        ) : claimed(m) ? (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300">
                                                <AlertTriangle className="w-3 h-3" /> Awaiting approval
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300">
                                                Not signed up
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-5 py-3">
                                        <div className="flex items-center justify-end gap-1.5">
                                            {claimed(m) && !m.is_active && (
                                                <button onClick={() => setActive(m, true)} title="Approve"
                                                    className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-black uppercase tracking-wider">
                                                    Approve
                                                </button>
                                            )}
                                            {m.is_active && (
                                                <button onClick={() => setActive(m, false)} title="Revoke access"
                                                    className="px-2.5 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-[11px] font-black uppercase tracking-wider hover:bg-slate-200 dark:hover:bg-slate-600">
                                                    Revoke
                                                </button>
                                            )}
                                            <button onClick={() => {
                                                setEditing(m);
                                                setForm({
                                                    id: m.id, name: m.name || '', email: m.email || '',
                                                    phone: m.phone || '', domain: m.domain || '',
                                                    max_teams: String(m.max_teams ?? 3),
                                                });
                                                setAddOpen(true);
                                            }} title="Edit"
                                                className="p-2 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10">
                                                <Edit2 className="w-4 h-4" />
                                            </button>
                                            <button onClick={() => remove(m)} title="Remove from roster"
                                                className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10">
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {!loading && filtered.length > perPage && (
                    <div className="p-4 flex items-center justify-between border-t border-slate-100 dark:border-slate-700/50">
                        <p className="text-xs font-semibold text-slate-400">
                            {(page - 1) * perPage + 1}-{Math.min(page * perPage, filtered.length)} of {filtered.length}
                        </p>
                        <div className="flex gap-2">
                            <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                                className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-40 text-slate-500">
                                <ChevronLeft className="w-4 h-4" />
                            </button>
                            <button disabled={page === totalPages} onClick={() => setPage(p => p + 1)}
                                className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-40 text-slate-500">
                                <ChevronRight className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                )}
            </div>

            <AnimatePresence>
                {addOpen && (
                    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" onClick={() => setAddOpen(false)}>
                        <motion.form initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }}
                            onClick={e => e.stopPropagation()} onSubmit={saveOne}
                            className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden">
                            <div className="p-5 bg-indigo-600 text-white flex items-center justify-between">
                                <h2 className="text-lg font-black">{editing ? 'Edit mentor' : 'Add mentor to roster'}</h2>
                                <button type="button" onClick={() => setAddOpen(false)} className="p-2 hover:bg-black/20 rounded-full"><X className="w-5 h-5" /></button>
                            </div>
                            <div className="p-5 space-y-4">
                                {!editing && (
                                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3">
                                        This adds the mentor to the roster so they can sign up. They set their own
                                        password, and you approve them once they have.
                                    </p>
                                )}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">Name</label>
                                    <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Preshit Desai" />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">E-mail (@gla.ac.in)</label>
                                    <input required type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. name@gla.ac.in" />
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">Phone</label>
                                        <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
                                            className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="10 digits" />
                                    </div>
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">Max teams</label>
                                        <input type="number" min="1" max="20" value={form.max_teams} onChange={e => setForm(f => ({ ...f, max_teams: e.target.value }))}
                                            className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" />
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1.5">Domain</label>
                                    <input value={form.domain} onChange={e => setForm(f => ({ ...f, domain: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Artificial Intelligence" />
                                </div>
                                <button type="submit" disabled={busy}
                                    className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors flex items-center justify-center gap-2">
                                    <Save className="w-4 h-4" /> {busy ? 'Saving...' : editing ? 'Save changes' : 'Add to roster'}
                                </button>
                            </div>
                        </motion.form>
                    </div>
                )}
            </AnimatePresence>

            <AnimatePresence>
                {uploadOpen && (
                    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" onClick={() => setUploadOpen(false)}>
                        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.97 }}
                            onClick={e => e.stopPropagation()}
                            className="w-full max-w-3xl bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
                            <div className="p-5 bg-indigo-600 text-white flex items-center justify-between shrink-0">
                                <h2 className="text-lg font-black">Bulk upload mentors</h2>
                                <button type="button" onClick={() => { setUploadOpen(false); setParsed([]); setSummary(null); }} className="p-2 hover:bg-black/20 rounded-full"><X className="w-5 h-5" /></button>
                            </div>
                            <div className="p-5 space-y-4 overflow-y-auto">
                                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                                    Expected columns: <span className="font-bold">{FIELDS.map(f => f.label).join(', ')}</span>.
                                    Only Name and E-mail are required.
                                </p>

                                <div onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                                    onDragLeave={e => { e.preventDefault(); setDragActive(false); }}
                                    onDrop={e => { e.preventDefault(); setDragActive(false); parseFile(e.dataTransfer.files?.[0]); }}
                                    onClick={() => fileRef.current?.click()}
                                    className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-colors ${dragActive ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10' : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'}`}>
                                    <UploadCloud className="w-8 h-8 mx-auto text-slate-400 mb-2" />
                                    <p className="text-sm font-bold text-slate-600 dark:text-slate-300">Drop a CSV here, or click to choose</p>
                                    <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden"
                                        onChange={e => parseFile(e.target.files?.[0])} />
                                </div>

                                {summary && (
                                    <div className="grid grid-cols-3 gap-3">
                                        {[
                                            { label: 'Valid', value: summary.valid, icon: CheckCircle, tone: 'text-emerald-600' },
                                            { label: 'Duplicate', value: summary.duplicate, icon: AlertTriangle, tone: 'text-amber-600' },
                                            { label: 'Invalid', value: summary.invalid, icon: XCircle, tone: 'text-rose-600' },
                                        ].map(s => (
                                            <div key={s.label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3">
                                                <p className={`flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest ${s.tone}`}>
                                                    <s.icon className="w-3 h-3" /> {s.label}
                                                </p>
                                                <p className="text-2xl font-black text-slate-800 dark:text-white">{s.value}</p>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {parsed.length > 0 && (
                                    <div className="max-h-64 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700">
                                        <table className="w-full text-xs">
                                            <thead className="bg-slate-50 dark:bg-slate-900/50 sticky top-0">
                                                <tr className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                                                    <th className="text-left px-3 py-2">Name</th>
                                                    <th className="text-left px-3 py-2">E-mail</th>
                                                    <th className="text-left px-3 py-2">Status</th>
                                                    <th className="text-left px-3 py-2">Reason</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                                                {parsed.map(r => (
                                                    <tr key={r.key}>
                                                        <td className="px-3 py-2 font-semibold text-slate-700 dark:text-slate-200">{r._v.name || '—'}</td>
                                                        <td className="px-3 py-2 text-slate-500">{r._v.email || '—'}</td>
                                                        <td className={`px-3 py-2 font-black ${r.status === 'Valid' ? 'text-emerald-600' : r.status === 'Duplicate' ? 'text-amber-600' : 'text-rose-600'}`}>{r.status}</td>
                                                        <td className="px-3 py-2 text-slate-400">{r.reason || '—'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}

                                {summary && summary.valid > 0 && (
                                    <button onClick={commitUpload} disabled={busy}
                                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors">
                                        {busy ? 'Adding...' : `Add ${summary.valid} mentor${summary.valid === 1 ? '' : 's'} to roster`}
                                    </button>
                                )}
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
}
