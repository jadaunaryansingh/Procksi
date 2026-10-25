import React, { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, Mail, Paperclip, X, Eye, Send, Loader2, Users, FileText, AlertCircle, CheckCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';

const DEFAULT_BODY = `<h2 style="margin:0 0 12px">Weekly Update</h2>
<p>Dear <b>{team_name}</b> ({project_title}),</p>
<p>Your mentor <b>{mentor_name}</b> has shared the attached report. Team leader: {leader_name}.</p>
<p>Members: {members}</p>
<p>Best regards,<br/>PMS Admin</p>`;

const SEGMENTS = [
    { key: '', label: 'All Teams (no filter)' },
    { key: 'all_students', label: 'All Enrolled Students' },
    { key: 'team_leaders', label: 'Team Leaders Only' },
    { key: 'unassigned_students', label: 'Unallocated Students (no team)' },
    { key: 'incomplete_teams', label: 'Incomplete Teams (< 3 members)' },
    { key: 'teams_without_mentors', label: 'Teams without a Mentor' },
    { key: 'mentors', label: 'All Faculty Mentors' },
    { key: 'specific_team', label: 'A Specific Team' },
];

// Preserve lookups across route changes so re-opening the page is instant.
let _teamsCache = null;
let _fieldsCache = null;
const SEGMENT_KEY = 'perTeamMail.segment';
const MAX_PREVIEW_CARDS = 80; // cap DOM nodes; totals still come from the header/count

export default function PerTeamMail() {
    const navigate = useNavigate();
    const [fields, setFields] = useState(_fieldsCache || []);
    const [subject, setSubject] = useState('Update: {project_title} - {team_name}');
    const [body, setBody] = useState(DEFAULT_BODY);
    const [isHtml, setIsHtml] = useState(true);
    const [teamIds, setTeamIds] = useState('');
    const [files, setFiles] = useState([]);
    const [result, setResult] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [segment, setSegment] = useState(() => localStorage.getItem(SEGMENT_KEY) || '');
    const [filterTeamId, setFilterTeamId] = useState('');
    const [includePortalButton, setIncludePortalButton] = useState(true);
    const [teams, setTeams] = useState(_teamsCache || []);
    const [count, setCount] = useState(null);
    const [countBusy, setCountBusy] = useState(false);
    const { data: templates } = useSupabaseTableState('communication_templates', [], { orderBy: 'id' });

    useEffect(() => {
        if (_fieldsCache) return;
        api.getPerTeamFields().then((f) => { _fieldsCache = f; setFields(f); }).catch(() => {});
    }, []);
    useEffect(() => {
        if (_teamsCache) return;
        api.getTeams().then((t) => { const arr = Array.isArray(t) ? t : []; _teamsCache = arr; setTeams(arr); }).catch(() => {});
    }, []);

    // Persist the chosen recipient filter so it survives navigation/reloads.
    useEffect(() => { localStorage.setItem(SEGMENT_KEY, segment); }, [segment]);

    // Live audience size — debounced, cheap (no rendering), updates as the filter changes.
    useEffect(() => {
        if (segment === 'specific_team' && !filterTeamId) { setCount(null); return; }
        let cancelled = false;
        setCountBusy(true);
        const timer = setTimeout(() => {
            api.getPerTeamCount({ teamIds: teamIds.trim(), segment, filterTeamId })
                .then((c) => { if (!cancelled) setCount(c); })
                .catch(() => { if (!cancelled) setCount(null); })
                .finally(() => { if (!cancelled) setCountBusy(false); });
        }, 350);
        return () => { cancelled = true; clearTimeout(timer); setCountBusy(false); };
    }, [teamIds, segment, filterTeamId]);

    const applyTemplate = (title) => {
        const tmpl = templates.find((t) => t.title === title);
        if (tmpl) { setSubject(tmpl.subject); setBody(tmpl.body); }
    };

    const addFiles = (list) => setFiles((prev) => [...prev, ...Array.from(list)]);
    const removeFile = (i) => setFiles((prev) => prev.filter((_, idx) => idx !== i));
    const insertField = (f) => setBody((b) => b + ' ' + f);

    const run = async (dryRun) => {
        setError(''); setBusy(true); setResult(null);
        try {
            const data = await api.sendPerTeam({ subject, body, isHtml, teamIds: teamIds.trim(), segment, filterTeamId, includePortalButton, dryRun, files });
            setResult({ ...data, mode: dryRun ? 'preview' : 'sent' });
        } catch (e) {
            setError(e.message || 'Failed');
        } finally { setBusy(false); }
    };

    const handleSend = () => {
        const n = result?.teams || '?';
        if (window.confirm(`Send personalized emails to ${n} team(s)? This will deliver/log one email per team.`)) run(false);
    };

    // Only offer templates that make sense for a personalized per-team send: ones that
    // use a per-team merge field and don't rely on broadcast-only fields ({date}/{time}/
    // {deadline}) that would render as literal placeholders per team.
    const perTeamTemplates = useMemo(() => {
        if (!templates.length) return [];
        const mergeFields = fields.length ? fields : ['{team_name}', '{project_title}', '{leader_name}', '{mentor_name}', '{members}', '{member_count}', '{domain}', '{semester}', '{team_id}'];
        const broadcastOnly = /\{(date|time|deadline)\}/i;
        return templates.filter((t) => {
            const blob = `${t.subject || ''} ${t.body || ''}`;
            return mergeFields.some((f) => blob.includes(f)) && !broadcastOnly.test(blob);
        });
    }, [templates, fields]);

    const countLabel = useMemo(() => {
        if (segment === 'specific_team' && !filterTeamId) return 'Pick a team';
        if (countBusy && !count) return 'Counting…';
        if (!count) return null;
        const t = count.teams ?? 0;
        const r = count.recipients ?? 0;
        const teamPart = `${t} team${t === 1 ? '' : 's'}`;
        const recipPart = `${r} recipient${r === 1 ? '' : 's'}`;
        return count.leftover_recipients
            ? `${teamPart} + 1 group · ${recipPart}`
            : `${teamPart} · ${recipPart}`;
    }, [count, countBusy, segment, filterTeamId]);

    const shownResults = result?.results ? result.results.slice(0, MAX_PREVIEW_CARDS) : [];
    const hiddenCount = result?.results ? result.results.length - shownResults.length : 0;

    const inputCls = 'w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500';
    const labelCls = 'block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2';

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
                <button onClick={() => navigate('/admin/communication')} title="Back to Communication" className="mr-3 p-2.5 rounded-xl text-slate-500 hover:text-indigo-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700/50 border border-slate-200 dark:border-slate-700 transition-colors">
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div className="p-3 bg-gradient-to-br from-indigo-500 to-blue-600 rounded-2xl text-white mr-4"><Mail className="w-6 h-6" /></div>
                <div className="flex-1">
                    <h1 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">Per-Team Personalized Send</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Mail-merge: one email per team, custom body plus each team's own attachments.</p>
                </div>
                {countLabel && (
                    <span className="hidden md:inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-black bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-500/20">
                        {countBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Users className="w-3.5 h-3.5" />}
                        {countLabel}
                    </span>
                )}
            </motion.div>

            {error && <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-400 px-5 py-3 rounded-2xl text-sm font-semibold flex items-center"><AlertCircle className="w-5 h-5 mr-2" />{error}</div>}

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 items-start">
                {/* Compose */}
                <div className="lg:col-span-3 bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                    <div className="p-6 space-y-5">
                        {/* Audience */}
                        <div className="space-y-4 pb-5 border-b border-slate-100 dark:border-slate-700/50">
                            <p className="text-[11px] font-black uppercase tracking-widest text-indigo-500">1 · Audience</p>
                            <div>
                                <label className={labelCls}>Target Teams</label>
                                <input value={teamIds} onChange={(e) => setTeamIds(e.target.value)} placeholder="e.g. TEAM-3, TEAM-68 — leave blank for ALL teams"
                                    className={`${inputCls} font-medium`} />
                            </div>
                            <div>
                                <label className={labelCls}>Recipient Filter Group</label>
                                <div className="relative">
                                    <Users className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                    <select value={segment} onChange={(e) => { setSegment(e.target.value); if (e.target.value !== 'specific_team') setFilterTeamId(''); }}
                                        className={`${inputCls} pl-11 font-bold cursor-pointer appearance-none`}>
                                        {SEGMENTS.map((s) => <option key={s.key || 'all'} value={s.key}>{s.label}</option>)}
                                    </select>
                                </div>
                                {segment === 'specific_team' && (
                                    <select value={filterTeamId} onChange={(e) => setFilterTeamId(e.target.value)}
                                        className="mt-2 w-full px-4 py-3 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 rounded-xl text-sm font-bold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer">
                                        <option value="">-- Select Team --</option>
                                        {teams.map((t) => <option key={t.id} value={t.id}>{t.id}{t.projectTitle ? ` – ${t.projectTitle}` : ''}</option>)}
                                    </select>
                                )}
                                {segment && (
                                    <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400 font-medium leading-relaxed">
                                        Filters each team's recipients to this group. Groups with no team (mentors, unassigned students) get one combined email.
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* Content */}
                        <div className="space-y-4 pb-5 border-b border-slate-100 dark:border-slate-700/50">
                            <p className="text-[11px] font-black uppercase tracking-widest text-indigo-500">2 · Content</p>
                            <div>
                                <label className={labelCls}>Start from a saved template</label>
                                <select onChange={(e) => applyTemplate(e.target.value)} defaultValue=""
                                    className={`${inputCls} font-bold cursor-pointer`}>
                                    <option value="">Load a personalized template ({perTeamTemplates.length})</option>
                                    {perTeamTemplates.map((t) => <option key={t.id} value={t.title}>{t.title}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className={labelCls}>Subject (supports merge fields)</label>
                                <input value={subject} onChange={(e) => setSubject(e.target.value)} className={`${inputCls} font-medium`} />
                            </div>
                            <div className="flex items-center justify-between p-3.5 bg-indigo-50/60 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-xl">
                                <div>
                                    <label className="text-xs font-bold text-slate-800 dark:text-slate-200 block">Include Portal Redirect Button</label>
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Appends redirect button (<b>glapms.in</b>) in outgoing emails</p>
                                </div>
                                <button 
                                    type="button" 
                                    onClick={() => setIncludePortalButton(!includePortalButton)}
                                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${includePortalButton ? 'bg-indigo-600' : 'bg-slate-300 dark:bg-slate-700'}`}
                                >
                                    <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${includePortalButton ? 'translate-x-5' : 'translate-x-0'}`} />
                                </button>
                            </div>
                            <div>
                                <div className="flex flex-wrap gap-1.5 mb-2">
                                    {fields.map((f) => (
                                        <button key={f} onClick={() => insertField(f)} className="text-[10px] font-bold px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-500/20 hover:bg-indigo-100 transition-colors font-mono">{f}</button>
                                    ))}
                                </div>
                                <label className="flex items-center justify-between text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                                    Body
                                    <span className="flex items-center gap-1.5 normal-case tracking-normal font-medium text-slate-500">
                                        <input type="checkbox" checked={isHtml} onChange={(e) => setIsHtml(e.target.checked)} className="accent-indigo-600" /> HTML
                                    </span>
                                </label>
                                <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={10}
                                    className={`${inputCls} font-mono leading-relaxed resize-none`} />
                            </div>
                        </div>

                        {/* Attachments */}
                        <div>
                            <p className="text-[11px] font-black uppercase tracking-widest text-indigo-500 mb-3">3 · Attachments <span className="text-slate-400 font-medium normal-case tracking-normal">(optional)</span></p>
                            <label className="block text-[11px] text-slate-500 dark:text-slate-400 font-medium mb-2 leading-relaxed">Name files with the team id (e.g. TEAM-3_report.pdf). Unmatched files go to every team.</label>
                            <label className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-dashed border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 text-sm font-bold cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/40 dark:hover:bg-indigo-500/5 transition-colors">
                                <Paperclip className="w-4 h-4" /> Add files
                                <input type="file" multiple className="hidden" onChange={(e) => addFiles(e.target.files)} />
                            </label>
                            {files.length > 0 && (
                                <div className="mt-3 space-y-1.5">
                                    {files.map((f, i) => (
                                        <div key={i} className="flex items-center justify-between bg-slate-50 dark:bg-slate-900/50 px-3 py-2 rounded-lg text-xs">
                                            <span className="flex items-center font-mono text-slate-600 dark:text-slate-300 truncate"><FileText className="w-3.5 h-3.5 mr-2 text-indigo-500 shrink-0" />{f.name}</span>
                                            <button onClick={() => removeFile(i)} className="text-slate-400 hover:text-red-500 ml-2"><X className="w-4 h-4" /></button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Sticky action bar */}
                    <div className="sticky bottom-0 flex items-center gap-3 px-6 py-4 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border-t border-slate-100 dark:border-slate-700/50 rounded-b-3xl">
                        <span className="hidden sm:flex items-center gap-1.5 text-[11px] font-bold text-slate-500 dark:text-slate-400 mr-auto">
                            {countBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Users className="w-3.5 h-3.5" />}
                            {countLabel || 'All teams'}
                        </span>
                        <button onClick={() => run(true)} disabled={busy} className="flex items-center justify-center px-5 py-3 rounded-xl text-xs font-black uppercase tracking-widest bg-slate-900 dark:bg-slate-700 text-white hover:bg-slate-800 disabled:opacity-60 transition-colors">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Eye className="w-4 h-4 mr-2" /> Preview</>}
                        </button>
                        <button onClick={handleSend} disabled={busy || !result || result.mode !== 'preview'} title={!result ? 'Preview first' : ''} className="flex items-center justify-center px-5 py-3 rounded-xl text-xs font-black uppercase tracking-widest bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                            <Send className="w-4 h-4 mr-2" /> Send to Teams
                        </button>
                    </div>
                </div>

                {/* Results */}
                <div className="lg:col-span-2 lg:sticky lg:top-6">
                    {!result && (
                        <div className="h-full min-h-[300px] bg-slate-900/5 dark:bg-slate-900/40 rounded-3xl border border-dashed border-slate-300/60 dark:border-slate-700/60 flex flex-col items-center justify-center p-10 text-center">
                            <Eye className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
                            <p className="text-sm font-bold text-slate-500 dark:text-slate-400">Hit <b>Preview</b> to see each team's rendered email before sending.</p>
                            {countLabel && <p className="mt-2 text-xs font-semibold text-indigo-500">Current audience: {countLabel}</p>}
                        </div>
                    )}
                    {result && (
                        <div className="space-y-3">
                            <div className={`p-4 rounded-2xl border text-sm font-bold flex items-center ${result.mode === 'sent' ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-400' : 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/30 text-indigo-700 dark:text-indigo-400'}`}>
                                {result.mode === 'sent' ? <CheckCircle className="w-5 h-5 mr-2" /> : <Eye className="w-5 h-5 mr-2" />}
                                {result.mode === 'sent'
                                    ? `Sent: ${result.sent} delivered, ${result.failed} failed across ${result.teams} teams`
                                    : `Preview — ${result.teams} teams${result.shared_files?.length ? `, ${result.shared_files.length} shared file(s)` : ''}`}
                            </div>
                            <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
                                {shownResults.map((t) => (
                                    <div key={t.team_id} className="bg-white/90 dark:bg-slate-800/90 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 overflow-hidden shadow-sm">
                                        <div className="px-4 py-2.5 bg-slate-50 dark:bg-slate-900/30 border-b border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                                            <span className="font-black text-xs text-slate-700 dark:text-slate-200 font-mono">{t.team_id}</span>
                                            <span className="flex items-center text-[10px] font-bold text-slate-500"><Users className="w-3 h-3 mr-1" />{t.recipient_count} · {t.status}</span>
                                        </div>
                                        <div className="p-4 space-y-2">
                                            <p className="text-xs font-bold text-slate-800 dark:text-slate-200">{t.subject}</p>
                                            {t.body_preview && (
                                                <div className="text-xs text-slate-600 dark:text-slate-300 border border-slate-100 dark:border-slate-700/50 rounded-lg p-3 bg-slate-50/50 dark:bg-slate-900/30 max-h-40 overflow-y-auto prose prose-sm dark:prose-invert" dangerouslySetInnerHTML={{ __html: t.body_preview }} />
                                            )}
                                            {t.attachments?.length > 0 && (
                                                <div className="flex flex-wrap gap-1.5">
                                                    {t.attachments.map((a) => (
                                                        <span key={a} className="inline-flex items-center text-[10px] font-mono bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 px-2 py-0.5 rounded border border-amber-200 dark:border-amber-500/30"><Paperclip className="w-3 h-3 mr-1" />{a}</span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {hiddenCount > 0 && (
                                    <p className="text-center text-xs font-bold text-slate-400 dark:text-slate-500 py-2">
                                        + {hiddenCount} more team{hiddenCount === 1 ? '' : 's'} not shown (all will be sent)
                                    </p>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
