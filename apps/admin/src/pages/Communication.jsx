import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Send, Eye, Paperclip, Users, X, MessageSquare, Satellite, History, LayoutTemplate, Plus, Edit2, Trash2, Search, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { apiUpsertTable, apiDeleteRows, getAuthHeaders } from '../lib/api';
import { Loader2 } from 'lucide-react';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamDisplayLabel } from '../lib/globalFilters';
import { sortByTeamNumber } from '../lib/teamUtils';
import { getApiBaseUrl } from '../lib/apiBase';
import SelectMenu from '../components/SelectMenu';

function formatMarkdownText(text) {
    if (!text) return { __html: '' };
    let safe = String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    safe = safe.replace(/^[ \t]*[*+-][ \t]+/gm, '• ');
    safe = safe.replace(/\*\*(.*?)\*\*/gs, '<strong class="font-black text-slate-900 dark:text-slate-100">$1</strong>');
    safe = safe.replace(/__(.*?)__/gs, '<strong class="font-black text-slate-900 dark:text-slate-100">$1</strong>');
    safe = safe.replace(/(?<!\w|\*)\*([^\s*][^*]*?)\*(?!\w|\*)/g, '<em>$1</em>');
    safe = safe.replace(/(?<!\w|_)_([^\s_][^_]*?)_(?!\w|_)/g, '<em>$1</em>');
    safe = safe.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="text-indigo-600 underline font-bold">$1</a>');
    safe = safe.replace(/\n/g, '<br />');

    return { __html: safe };
}

// Mirrors FIXED_GREETINGS in communication_agent.py: faculty and panel mail is
// institutional, so it greets the role, not the person.
const FIXED_GREETINGS = { mentors: 'Mentor', panel_members: 'Panel' };

// Mirrors the server: a leading "Dear ...," is lifted out of the body into the
// greeting slot, so the line is not rendered twice in the preview.
const LEADING_GREETING = /^[ \t]*(Dear|Hello|Greetings)[ \t]*[^,\n]{0,60},[ \t]*\r?\n?/i;

export default function Communication() {
    const navigate = useNavigate();
    const { semesterMap } = useGlobalFilters();
    const [mailType, setMailType] = useState('Proposal Updates');
    const [recipients, setRecipients] = useState('');
    const [subject, setSubject] = useState('');
    const [body, setBody] = useState('');
    const [file, setFile] = useState(null);
    const [includePortalButton, setIncludePortalButton] = useState(true);

    // Which face of the Live Simulator is showing: the rendered email, or the
    // list of who it goes to.
    const [previewMode, setPreviewMode] = useState('email');
    // Steps of the send that did not complete (portal broadcasts, notification
    // write). Shown rather than only logged: these used to fail invisibly.
    const [fanoutIssues, setFanoutIssues] = useState([]);
    const [sendSummary, setSendSummary] = useState(null);
    const [sent, setSent] = useState(false);

    // New states
    const [showTemplateManager, setShowTemplateManager] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState(null);
    const [templateForm, setTemplateForm] = useState({ title: '', subject: '', body: '' });
    const [isSavingTemplate, setIsSavingTemplate] = useState(false);
    const [templateError, setTemplateError] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [sendError, setSendError] = useState('');
    
    // Communication History
    const { data: history, setData: setHistory } = useSupabaseTableState('communication_history', [], { orderBy: 'id', ascending: false });

    // Communication Templates
    const { data: templates, setData: setTemplates } = useSupabaseTableState('communication_templates', [], { orderBy: 'id' });

    // Teams for specific team targeting
    const { data: teams } = useSupabaseTableState('teams_validation', [], { orderBy: 'id' });
    const [specificTeam, setSpecificTeam] = useState('');
    const [teamSearch, setTeamSearch] = useState('');

    // Who the chosen segment actually resolves to. Shown before sending, so an
    // audience is not picked blind -- the panel used to show only its label.
    const [audience, setAudience] = useState({ loading: false, count: null, emails: [], label: '', isTeamSegment: false, teams: [], teamCount: 0, names: {} });
    // Rows the admin has unchecked in the audience preview. Tracked as an
    // exclusion set so a freshly loaded segment is fully selected by default --
    // the common case is "send to all of them".
    const [excluded, setExcluded] = useState(() => new Set());

    // The mail face only exists once a preview has been generated, so the
    // stored mode alone cannot decide which face shows.
    // The addresses the send will actually go to, after exclusions.
    const selectedEmails = useMemo(() => {
        if (audience.count === null) return [];
        if (audience.isTeamSegment) {
            return audience.teams
                .filter(t => !excluded.has(t.id))
                .flatMap(t => t.emails || []);
        }
        return audience.emails.filter(e => !excluded.has(e));
    }, [audience, excluded]);

    useEffect(() => {
        if (!recipients) { setAudience({ loading: false, count: null, emails: [], label: '', isTeamSegment: false, teams: [], teamCount: 0, names: {} }); return undefined; }
        if (recipients === 'specific_team' && !specificTeam) {
            setAudience({ loading: false, count: null, emails: [], label: '', isTeamSegment: false, teams: [], teamCount: 0, names: {} });
            return undefined;
        }

        let cancelled = false;
        setAudience(a => ({ ...a, loading: true }));

        const params = new URLSearchParams({ segment: recipients });
        if (recipients === 'specific_team') params.set('team_id', specificTeam);

        (async () => {
            try {
                const res = await fetch(`${getApiBaseUrl()}/api/admin/communication/recipients?${params}`, { headers: getAuthHeaders() });
                if (!res.ok) throw new Error(String(res.status));
                const json = await res.json();
                const d = json?.data || {};
                if (!cancelled) setExcluded(new Set());
                if (!cancelled) setAudience({
                    loading: false,
                    count: d.count ?? 0,
                    emails: d.emails || [],
                    label: d.label || '',
                    isTeamSegment: Boolean(d.is_team_segment),
                    teams: d.teams || [],
                    teamCount: d.team_count ?? 0,
                    names: d.names || {},
                });
            } catch {
                // Leave the count unknown rather than claiming zero recipients.
                if (!cancelled) setAudience({ loading: false, count: null, emails: [], label: '', isTeamSegment: false, teams: [], teamCount: 0, names: {} });
            }
        })();

        return () => { cancelled = true; };
    }, [recipients, specificTeam]);

    // Ordered by team number rather than id, because the ids sort lexically --
    // "Team 11" would otherwise sit between 109 and 110. Matches on the visible
    // label and the project title, so either gets you there.
    const filteredTeams = useMemo(() => {
        const q = teamSearch.trim().toLowerCase();
        // Pass the rows, not bare ids: the comparator resolves the number from
        // the row when the id alone does not carry it.
        const ordered = [...teams].sort((a, b) => sortByTeamNumber(a, b));
        if (!q) return ordered;
        return ordered.filter(t => {
            const label = teamDisplayLabel(t.id, t, semesterMap) || '';
            return label.toLowerCase().includes(q)
                || String(t.projectTitle || '').toLowerCase().includes(q);
        });
    }, [teams, teamSearch, semesterMap]);

    // Hardcoded as the fallback only. The live list is fetched from
    // GET /segments below -- the backend has served that endpoint all along and
    // the page never called it, so the two lists agreed only by coincidence.
    // Keeping a fallback means a settings outage degrades rather than leaving
    // the form with no audience to choose.
    const [segments, setSegments] = useState([
        { key: 'all_students', label: 'All Enrolled Students', requires_team: false },
        { key: 'valid_teams', label: 'Valid Teams', requires_team: false },
        { key: 'invalid_teams', label: 'Invalid Teams', requires_team: false },
        { key: 'team_leaders', label: 'Team Leaders Only', requires_team: false },
        { key: 'unassigned_students', label: 'Unallocated Students (no team)', requires_team: false },
        { key: 'incomplete_teams', label: 'Incomplete Teams (< 3 members)', requires_team: false },
        { key: 'teams_without_mentors', label: 'Teams without a Mentor', requires_team: false },
        { key: 'mentors', label: 'All Faculty Mentors', requires_team: false },
        { key: 'panel_members', label: 'All Panel Members', requires_team: false },
        { key: 'specific_team', label: 'A Specific Team', requires_team: true }
    ]);

    const activeSemesterId = sessionStorage.getItem('activeSemesterId') || '';

    useEffect(() => {
        let cancelled = false;
        (async () => {
            try {
                // Scoped to the semester: which segments are usable depends on
                // whether this batch has teams, mentors and panels yet.
                const qs = activeSemesterId ? `?semester_id=${encodeURIComponent(activeSemesterId)}` : '';
                const res = await fetch(`${getApiBaseUrl()}/api/admin/communication/segments${qs}`, { headers: getAuthHeaders() });
                if (!res.ok) return;
                const json = await res.json();
                const list = json?.data || json;
                if (!cancelled && Array.isArray(list) && list.length > 0) setSegments(list);
            } catch {
                // Keep the fallback list -- see the note above.
            }
        })();
        return () => { cancelled = true; };
    }, [activeSemesterId]);

    useEffect(() => {
        if (!recipients) return;
        const chosen = segments.find(s2 => s2.key === recipients);
        if (chosen && chosen.available === false) {
            setRecipients('');
            setSpecificTeam('');
        }
    }, [segments, recipients]);

    // The raw id is a UUID with a -T34 suffix, which is unreadable in the
    // preview and in the history row this string is logged to.
    const specificTeamLabel = () => teamDisplayLabel(
        specificTeam, teams.find(t => t.id === specificTeam), semesterMap,
    ) || specificTeam;

    const audienceLabel = recipients === 'specific_team'
        ? (specificTeam ? specificTeamLabel() : 'No team chosen')
        : (audience.label || segments.find(s => s.key === recipients)?.label || 'Resolving...');

    const bodyWithoutGreeting = (body || '').replace(LEADING_GREETING, '');

    // The name the preview greets. Student segments follow the first selected
    // recipient; mentors and panel members are greeted by role, so every one of
    // them sees the same line and there is no sample to disclaim.
    const fixedGreeting = FIXED_GREETINGS[recipients] || null;
    const greetingName = useMemo(() => {
        if (fixedGreeting) return fixedGreeting;
        const first = selectedEmails[0];
        return (first && audience.names?.[String(first).trim().toLowerCase()]) || 'Student';
    }, [fixedGreeting, selectedEmails, audience.names]);

    // Derived from the form rather than snapshotted on submit, so the viewport
    // tracks every keystroke. handleSend already read the live state, so this
    // also removes the chance of sending something the preview never showed.
    const previewContent = useMemo(
        () => ({ mailType, recipients: audienceLabel, subject, body: bodyWithoutGreeting, file, includePortalButton }),
        [mailType, audienceLabel, subject, bodyWithoutGreeting, file, includePortalButton],
    );

    const handleSend = async () => {
        setIsSending(true);
        setSendError('');
        const effectiveRecipients = recipients === 'specific_team'
            ? (specificTeam ? specificTeamLabel() : 'All Students')
            : (segments.find(s => s.key === recipients)?.label || recipients || 'All Students');
        
        try {
            const API_BASE_URL = getApiBaseUrl();
            const response = await fetch(`${API_BASE_URL}/api/admin/communication/send`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    segment: recipients,
                    template_code: mailType,
                    subject: subject,
                    body: body,
                    team_id: recipients === 'specific_team' ? specificTeam : null,
                    semester_id: sessionStorage.getItem('activeSemesterId') || null,
                    include_portal_button: includePortalButton,
                    // Only sent when something has actually been unchecked, so a
                    // normal send stays a plain segment send. The server
                    // intersects this with the segment it resolves.
                    only_emails: excluded.size > 0 ? selectedEmails : null,
                }),
            });
            
            const json = await response.json();
            if (!response.ok) {
                throw new Error(json.detail || 'Failed to dispatch email.');
            }

            const newRow = {
                id: Date.now(),
                type: mailType,
                recipients: effectiveRecipients,
                subject: subject,
                body: body,
                date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
                time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
                status: json.data?.delivered ? 'Delivered' : 'Logged',
            };

            // Refresh history from backend logs
            try {
                const histRes = await fetch(`${API_BASE_URL}/api/admin/communication/history?limit=50`, { headers: getAuthHeaders() });
                const histJson = await histRes.json();
                if (histJson && histJson.data) {
                    setHistory(histJson.data);
                } else {
                    setHistory((prev) => [newRow, ...prev]);
                }
            } catch (histErr) {
                console.warn('Failed to refresh history:', histErr);
                setHistory((prev) => [newRow, ...prev]);
            }

            // The notification write and the portal broadcasts now happen
            // inside /send. They used to run here as three further requests,
            // each swallowed into console.warn("non-critical") -- so a failed
            // step was invisible, and closing the tab abandoned whatever had
            // not run yet. The server reports each step in json.data.fanout.
            const fanout = json?.data?.fanout || [];
            const failedSteps = fanout.filter(f => !f.ok);
            if (failedSteps.length > 0) {
                console.warn('Some delivery steps did not complete:', failedSteps);
            }
            setFanoutIssues(failedSteps);
            setSendSummary(json?.data || null);

            setSent(true);
            // Clearing the form clears the preview too, now that it derives.
            setSubject('');
            setBody('');
            setRecipients('');
            setSpecificTeam('');
            setTimeout(() => setSent(false), 3000);
            AuditLogger.logUserAction(getCurrentUser(), `Sent communication "${subject}" to ${effectiveRecipients}`);
        } catch (err) {
            setSendError(err.message || 'Failed to send.');
        } finally {
            setIsSending(false);
        }
    };

    const openNewTemplate = () => {
        setEditingTemplate('new');
        setTemplateForm({ title: '', subject: '', body: '' });
        setTemplateError('');
    };

    const openEditTemplate = (t) => {
        setEditingTemplate(t.id);
        setTemplateForm({ title: t.title, subject: t.subject, body: t.body });
        setTemplateError('');
    };

    const handleSaveTemplate = async () => {
        if (!templateForm.title || !templateForm.subject || !templateForm.body) {
            setTemplateError('All fields are required.');
            return;
        }
        setIsSavingTemplate(true);
        setTemplateError('');
        try {
            if (editingTemplate === 'new') {
                const result = await apiUpsertTable('communication_templates', [templateForm]);
                const saved = result?.data?.[0];
                if (saved) setTemplates((prev) => [...prev, saved]);
            } else {
                await apiUpsertTable('communication_templates', [{ id: editingTemplate, ...templateForm }], 'id');
                setTemplates((prev) => prev.map((t) => t.id === editingTemplate ? { ...t, ...templateForm } : t));
            }
            AuditLogger.logAdminAction(getCurrentUser(), editingTemplate === 'new' ? `Created new communication template "${templateForm.title}"` : `Updated communication template "${templateForm.title}"`);
            setEditingTemplate(null);
        } catch (err) {
            setTemplateError(err.message || 'Save failed.');
        } finally {
            setIsSavingTemplate(false);
        }
    };

    const handleDeleteTemplate = async (id) => {
        if (!window.confirm('Delete this template?')) return;
        try {
            await apiDeleteRows('communication_templates', { id });
            setTemplates((prev) => prev.filter((t) => t.id !== id));
            AuditLogger.logAdminAction(getCurrentUser(), `Deleted communication template`);
        } catch (err) {
            alert('Delete failed: ' + err.message);
        }
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header Title Space */}
             <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50">
                <div className="flex items-center space-x-4">
                    <div className="p-3 bg-gradient-to-br from-indigo-500 to-blue-600 shadow-lg shadow-indigo-500/20 rounded-2xl text-white">
                         <Satellite className="w-6 h-6" />
                    </div>
                    <div>
                        <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-1 tracking-tight">Mass Comms Array</h1>
                        <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Broadcast alerts and scheduled digests across the platform hierarchy.</p>
                    </div>
                </div>
                <button onClick={() => navigate('/admin/communication/per-team')} className="flex items-center px-5 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-black uppercase tracking-widest hover:border-indigo-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors shadow-sm shrink-0">
                    <Users className="w-4 h-4 mr-2" /> Per-Team Personalized Send
                </button>
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 xl:gap-8">
                <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }} className="lg:col-span-3 space-y-6">
                    <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl p-6 xl:p-8 rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50">
                        <h2 className="text-xl font-black text-slate-800 dark:text-white flex items-center mb-8 pb-4 border-b border-slate-100 dark:border-slate-700/50">
                            <MessageSquare className="w-5 h-5 mr-3 text-indigo-500" /> Dispatch Console
                        </h2>

                        <form onSubmit={e => e.preventDefault()} className="space-y-6">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                <div>
                                    <div className="flex justify-between items-center mb-2">
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Templated Protocol</label>
                                        <button type="button" onClick={() => setShowTemplateManager(true)} className="text-[10px] font-black uppercase tracking-widest text-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 flex items-center transition-colors">
                                            <LayoutTemplate className="w-3 h-3 mr-1" /> Manager
                                        </button>
                                    </div>
                                    <SelectMenu
                                        ariaLabel="Templated protocol"
                                        value={mailType}
                                        onChange={(v) => {
                                            setMailType(v);
                                            const tmpl = templates.find(t => t.title === v);
                                            if (tmpl) { setSubject(tmpl.subject); setBody(tmpl.body); }
                                        }}
                                        options={[
                                            ...templates.map(t => ({ value: t.title, label: t.title })),
                                            { value: 'Custom General Alert', label: 'Custom General Alert' },
                                        ]}
                                    />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Recipient Filter Group</label>
                                    <div className="relative">
                                        {/* Disabled rather than removed: an admin looking
                                            for "All Faculty Mentors" should see why it
                                            cannot be picked, not wonder where it went. */}
                                        <SelectMenu
                                            ariaLabel="Recipient filter group"
                                            value={recipients}
                                            onChange={(v) => { setRecipients(v); if (v !== 'specific_team') setSpecificTeam(''); }}
                                            placeholder="-- Target Segments --"
                                            leftIcon={<Users className="w-5 h-5" />}
                                            options={segments.map(seg => {
                                                const off = seg.available === false;
                                                return {
                                                    value: seg.key,
                                                    label: seg.label,
                                                    disabled: off,
                                                    title: off ? seg.unavailable_reason : undefined,
                                                    suffix: off ? 'not ready' : undefined,
                                                };
                                            })}
                                        />
                                        {/* Sits over the chevron while a segment resolves,
                                            so feedback appears where the click did. */}
                                        {audience.loading && (
                                            <div className="absolute inset-y-0 right-0 flex items-center px-4 pointer-events-none bg-slate-50 dark:bg-slate-900 rounded-r-2xl">
                                                <Loader2 className="w-5 h-5 animate-spin text-indigo-500" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div>
                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Subject Header</label>
                                <input type="text" value={subject} onChange={e => setSubject(e.target.value)} required placeholder="e.g. Action Required: Finalize Project Domains" 
                                    className="w-full px-5 py-3.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none font-bold shadow-inner transition-shadow focus:shadow-md" />
                            </div>

                            {/* Portal Redirect Button Toggle */}
                            <div className="flex items-center justify-between p-4 bg-indigo-50/60 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-2xl">
                                <div>
                                    <label className="text-xs font-bold text-slate-800 dark:text-slate-200 block">Include Portal Redirect Button</label>
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Appends a button in outgoing email linking to the <b>Procksi student portal</b></p>
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
                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Body Payload (Markdown Supported)</label>
                                <textarea value={body} onChange={e => setBody(e.target.value)} required rows={8} placeholder="Draft the communication payload..." 
                                    className="w-full px-5 py-4 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-2xl text-sm focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none whitespace-pre-wrap font-medium leading-loose shadow-inner transition-shadow focus:shadow-md resize-none"></textarea>
                            </div>

                            <div className="flex flex-col sm:flex-row items-center justify-between pt-6 border-t border-slate-100 dark:border-slate-700/50 gap-4">
                                <div className="flex items-center w-full sm:w-auto">
                                    <label className="flex items-center w-full sm:w-auto justify-center text-xs font-black uppercase tracking-widest text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 cursor-pointer bg-indigo-50 dark:bg-indigo-500/10 px-6 py-3 rounded-xl transition-colors border border-indigo-100 dark:border-indigo-500/20 shadow-sm hover:shadow-md">
                                        <Paperclip className="w-4 h-4 mr-2" />
                                        {file ? <span className="truncate max-w-[150px]">{file.name}</span> : 'Attach Context'}
                                        <input type="file" onChange={e => setFile(e.target.files[0])} className="hidden" />
                                    </label>
                                    {file && <button type="button" onClick={() => setFile(null)} className="ml-3 text-red-500 p-2 bg-red-50 dark:bg-red-500/10 rounded-xl hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"><X className="w-4 h-4" /></button>}
                                </div>
                            </div>
                        </form>
                    </div>
                </motion.div>

                {/* Preview Sidebar */}
                <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }} className="lg:col-span-2 relative h-[680px] flex flex-col">
                    <AnimatePresence mode="wait">
                        {!sent && !audience.loading && audience.count === null && (
                            <motion.div key="empty" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }} className="flex-1 bg-slate-900/5 dark:bg-slate-900/50 backdrop-blur-3xl rounded-3xl border border-dashed border-slate-300/50 dark:border-slate-700/50 flex flex-col items-center justify-center p-12 text-center min-h-0">
                                <div className="p-6 bg-slate-200/50 dark:bg-slate-800/50 rounded-full mb-6 text-slate-400 dark:text-slate-600">
                                    <Mail className="w-12 h-12" />
                                </div>
                                <h3 className="text-xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Render Standby</h3>
                                <p className="text-sm font-medium text-slate-500 dark:text-slate-400 max-w-xs leading-relaxed">Construct a payload and trigger the renderer to compile a mobile-responsive preview structure.</p>

                            </motion.div>
                        )}

                        {/* Team picker. Lives in this panel rather than the
                            Dispatch Console: at 197 teams it needs the room, and
                            it is the audience-choosing step, which is what this
                            panel is for. */}
                        {!sent && recipients === 'specific_team' && !specificTeam && (
                            <motion.div key="team-picker" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                                className="absolute inset-0 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl rounded-3xl border border-indigo-200 dark:border-indigo-500/30 flex flex-col overflow-hidden shadow-xl">
                                <div className="px-6 py-5 border-b border-indigo-100 dark:border-indigo-500/20 bg-gradient-to-r from-indigo-50 to-white dark:from-slate-800 dark:to-slate-800">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-indigo-400 mb-1">Choose a team</p>
                                    <h3 className="text-lg font-black text-slate-800 dark:text-white">Which team is this for?</h3>
                                </div>

                                <div className="px-6 pt-4 pb-3">
                                    <div className="relative">
                                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-indigo-400 pointer-events-none" />
                                        <input
                                            type="text"
                                            value={teamSearch}
                                            onChange={e => setTeamSearch(e.target.value)}
                                            placeholder="Search by team number or project title..."
                                            className="w-full pl-11 pr-4 py-3 bg-indigo-50 dark:bg-indigo-500/10 border-2 border-indigo-200 dark:border-indigo-500/30 rounded-2xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-all placeholder:font-medium placeholder:text-indigo-400/70"
                                        />
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto px-6 pb-6">
                                    <div className="rounded-2xl border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden">
                                        {filteredTeams.length === 0 ? (
                                            <p className="p-6 text-xs font-bold text-slate-400 text-center">No team matches that search.</p>
                                        ) : filteredTeams.map((t, i) => (
                                            <button type="button" key={t.id}
                                                onClick={() => setSpecificTeam(t.id)}
                                                className="w-full text-left flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-slate-900/40 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 cursor-pointer transition-colors">
                                                <span className="w-6 shrink-0 text-[10px] font-black text-slate-300 dark:text-slate-600 tabular-nums">{i + 1}</span>
                                                <span className="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                                                    {teamDisplayLabel(t.id, t, semesterMap)}{t.projectTitle ? ` \u2013 ${t.projectTitle}` : ''}
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/30">
                                    <p className="text-[11px] font-bold text-slate-400">{filteredTeams.length} of {teams.length} teams</p>
                                </div>
                            </motion.div>
                        )}

                        {(audience.loading || audience.count !== null) && !sent && (
                            <motion.div key="preview" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }} className="bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl rounded-3xl shadow-2xl border border-indigo-200 dark:border-indigo-500/30 overflow-hidden flex flex-col flex-1 min-h-0 ring-4 ring-indigo-500/10">
                                <div className="p-5 bg-gradient-to-r from-indigo-50 to-white dark:from-slate-800 dark:to-slate-800 border-b border-indigo-100 dark:border-indigo-500/20 flex justify-between items-center relative overflow-hidden">
                                    <div className="absolute right-0 top-0 opacity-10">
                                        <Satellite className="w-32 h-32 transform translate-x-12 -translate-y-8" />
                                    </div>
                                    {/* Plain heading. Recalibrate is the way out of the
                                        preview; the eye is decoration only. */}
                                    <h3 className="font-black text-indigo-900 dark:text-indigo-300 flex items-center tracking-tight relative z-10 min-w-0">
                                        <Eye className="w-4 h-4 mr-2 shrink-0" />
                                        <span className="truncate">{previewMode === 'email' ? 'Live Simulator' : 'Target Audience'}</span>
                                    </h3>
                                    {/* Swaps the panel body between the rendered mail and
                                        the recipient list. Labelled with the view it
                                        switches to, so the click is predictable. With no
                                        preview yet it renders one, which is the only way
                                        the mail face can exist. */}
                                    <button type="button"
                                        onClick={() => setPreviewMode(m => (m === 'email' ? 'recipients' : 'email'))}
                                        title={previewMode === 'email' ? 'Show who this goes to' : 'Show the rendered email'}
                                        className="relative z-10 shrink-0 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-md cursor-pointer hover:bg-indigo-200 dark:hover:bg-indigo-500/30 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/60">
                                        {previewMode === 'email' ? 'Recipients' : 'Mobile Viewport'}
                                    </button>
                                </div>
                                
                                {/* Pinned: only the recipient list scrolls. */}
                                <div className="shrink-0 px-6 pt-6 pb-0 bg-slate-50/30 dark:bg-slate-900/30">
                                    {/* gap-3 and min-w-0 rather than justify-between:
                                        a long audience label used to wrap under the
                                        type badge and collide with it. */}
                                    <div className="bg-white dark:bg-slate-800 p-4 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-700/50 flex items-start gap-3">
                                        <div className="min-w-0 flex-1">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Audience Segment</p>
                                            <p className="text-sm font-bold text-indigo-600 dark:text-indigo-400 flex w-full items-center bg-indigo-50 dark:bg-indigo-500/10 px-2.5 py-1 rounded-md">
                                                {audience.loading
                                                    ? <Loader2 className="w-3 h-3 mr-1.5 shrink-0 animate-spin" />
                                                    : <Users className="w-3 h-3 mr-1.5 shrink-0" />}
                                                <span className="truncate" title={audienceLabel}>
                                                    {audience.loading ? 'Resolving...' : audienceLabel}
                                                </span>
                                            </p>
                                        </div>
                                        <span className="shrink-0 text-[10px] font-black uppercase tracking-wider px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-600">
                                            {mailType || "Custom Mail"}
                                        </span>
                                    </div>
                                </div>

                                {/* The scroll region. min-h-0 lets it shrink inside the
                                    fixed-height panel instead of forcing it taller. */}
                                <div className="flex-1 min-h-0 flex flex-col px-6 pb-6 pt-5 bg-slate-50/30 dark:bg-slate-900/30">
                                    {previewMode !== 'email' ? (
                                        /* Same rows and the same `excluded` set as the
                                           audience overlay, so unchecking here changes
                                           what Execute sends. */
                                        <div className="flex-1 min-h-0 flex flex-col">
                                            {/* Checked before count: while a segment is
                                                resolving the count is still null, so this
                                                branch used to show "no audience resolved
                                                yet" for the whole request. */}
                                            {audience.loading ? (
                                                <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400">
                                                    <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
                                                    <p className="text-[11px] font-black uppercase tracking-widest">Resolving recipients</p>
                                                </div>
                                            ) : audience.count === null ? (
                                                <p className="text-sm font-bold text-slate-400 text-center p-6">No audience resolved yet.</p>
                                            ) : audience.count === 0 ? (
                                                <p className="text-sm font-bold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-2xl p-5 text-center">
                                                    This group has no one in it. Sending would deliver nothing.
                                                </p>
                                            ) : (() => {
                                                const rows = audience.isTeamSegment ? audience.teams.map(t => t.id) : audience.emails;
                                                const allOn = rows.every(k => !excluded.has(k));
                                                return (
                                                    <>
                                                        <div className="shrink-0 flex items-center justify-between gap-3 mb-3">
                                                            <button type="button"
                                                                onClick={() => setExcluded(allOn ? new Set(rows) : new Set())}
                                                                className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 cursor-pointer transition-colors">
                                                                <span className={`w-4 h-4 rounded flex items-center justify-center border-2 transition-colors ${
                                                                    allOn ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-300 dark:border-slate-600'}`}>
                                                                    {allOn && <Check className="w-3 h-3" />}
                                                                </span>
                                                                {allOn ? 'Deselect all' : 'Select all'}
                                                            </button>
                                                            <p className="text-[11px] font-bold text-slate-400">
                                                                {selectedEmails.length} of {audience.count} will receive this
                                                            </p>
                                                        </div>
                                                        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar rounded-2xl border border-slate-200 dark:border-slate-700 divide-y divide-slate-100 dark:divide-slate-800">
                                                            {(audience.isTeamSegment ? audience.teams : audience.emails).map((row, i) => {
                                                                const key = audience.isTeamSegment ? row.id : row;
                                                                const on = !excluded.has(key);
                                                                const label = audience.isTeamSegment
                                                                    ? (row.number != null ? `Team ${row.number}` : row.id)
                                                                    : row;
                                                                return (
                                                                    <button type="button" key={key}
                                                                        onClick={() => setExcluded(prev => {
                                                                            const next = new Set(prev);
                                                                            if (on) next.add(key); else next.delete(key);
                                                                            return next;
                                                                        })}
                                                                        className="w-full text-left flex items-center gap-3 px-4 py-2.5 bg-white dark:bg-slate-900/40 hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer transition-colors">
                                                                        <span className={`w-4 h-4 shrink-0 rounded flex items-center justify-center border-2 transition-colors ${
                                                                            on ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-slate-300 dark:border-slate-600'}`}>
                                                                            {on && <Check className="w-3 h-3" />}
                                                                        </span>
                                                                        <span className="w-6 shrink-0 text-[10px] font-black text-slate-300 dark:text-slate-600 tabular-nums">{i + 1}</span>
                                                                        <span className={`truncate ${audience.isTeamSegment ? 'text-sm font-bold text-slate-700 dark:text-slate-200' : 'text-xs font-medium text-slate-600 dark:text-slate-300'} ${on ? '' : 'line-through opacity-40'}`}>
                                                                            {label}
                                                                        </span>
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    </>
                                                );
                                            })()}
                                        </div>
                                    ) : (
                                    <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar space-y-5">
                                    {/* Live Email Template Card Preview */}
                                    <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700/70 shadow-lg bg-white text-slate-900">
                                        {/* Dark Navy Header Card */}
                                        <div className="bg-[#0f172a] text-white p-6 border-b-4 border-indigo-500 relative">
                                            <span className="inline-block px-3 py-1 bg-indigo-500/20 border border-indigo-400/40 text-indigo-300 text-[10px] font-black uppercase tracking-widest rounded-md mb-2">
                                                {(previewContent.mailType || "PROCKSI NOTIFICATION").toUpperCase()}
                                            </span>
                                            <h2 className="text-xl font-extrabold text-white leading-tight">
                                                {previewContent.subject || "Email Subject"}
                                            </h2>
                                            <p className="text-xs text-slate-400 font-medium mt-1">
                                                Procksi • Project Management Platform
                                            </p>
                                        </div>
                                        {/* White Card Body */}
                                        <div className="p-6 bg-white space-y-4">
                                            {/* The body's own "Dear X," wins, matching the
                                                server, which rewrites that line per
                                                recipient before sending. */}
                                            <p className="text-sm font-bold text-slate-900 flex items-baseline gap-2">
                                                <span>Dear {greetingName},</span>
                                                {!fixedGreeting && selectedEmails.length > 1 && (
                                                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
                                                        sample of {selectedEmails.length}
                                                    </span>
                                                )}
                                            </p>
                                            <div 
                                                className="text-sm text-slate-700 leading-relaxed font-sans"
                                                dangerouslySetInnerHTML={formatMarkdownText(previewContent.body)}
                                            />
                                            {previewContent.includePortalButton && (
                                                <div className="pt-4 text-center">
                                                    <a href={import.meta.env.VITE_STUDENT_PORTAL_URL || 'https://student.procksi.in'} target="_blank" rel="noreferrer" className="inline-block bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-bold text-xs px-6 py-3 rounded-xl shadow-md hover:shadow-lg transition-all">
                                                        Open Procksi
                                                    </a>
                                                </div>
                                            )}
                                            <div className="pt-6 border-t border-slate-100 text-xs text-slate-500 space-y-1">
                                                <p className="font-semibold text-slate-700">Best Regards,</p>
                                                <p className="font-bold text-slate-900">Mr. Preshit Desai & Ms. Anushka Shukla</p>
                                                <p className="text-[11px] font-bold text-indigo-600 uppercase tracking-wider">Project Coordinators – AIML</p>
                                            </div>
                                        </div>
                                        {/* Official Footer */}
                                        <div className="bg-slate-100 p-4 text-center border-t border-slate-200">
                                            <p className="text-[11px] font-semibold text-slate-600 margin-0">Official Automated Communication • Procksi</p>
                                            <p className="text-[10px] text-slate-400 margin-0">If you have questions regarding this notification, please contact your department coordinator.</p>
                                        </div>
                                    </div>

                                    {previewContent.file && (
                                        <div className="bg-indigo-50 dark:bg-indigo-500/10 p-4 rounded-xl border border-indigo-100 dark:border-indigo-500/20 flex items-center">
                                            <div className="p-2 bg-white dark:bg-slate-800 rounded-lg mr-3 shadow-sm"><Paperclip className="w-4 h-4 text-indigo-500" /></div>
                                            <span className="text-xs font-bold text-indigo-800 dark:text-indigo-300 truncate">{previewContent.file.name}</span>
                                        </div>
                                    )}
                                    </div>
                                    )}
                                </div>
                                
                                <div className="shrink-0 p-5 bg-white dark:bg-slate-800 border-t border-slate-200/50 dark:border-slate-700/50 flex space-x-3">
                                    {/* There is no snapshot to discard now, so this clears
                                        the draft itself. Confirmed because the body can be
                                        long and this is not otherwise undoable. */}
                                    <button onClick={() => {
                                        if (!subject && !body && !file) return;
                                        if (!window.confirm('Clear the subject, body and attachment?')) return;
                                        setSubject(''); setBody(''); setFile(null);
                                    }} className="flex-1 px-4 py-3 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 border border-transparent rounded-xl hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors shadow-sm">Recalibrate</button>
                                    {/* The form's required attributes no longer gate the
                                        send, since there is no submit step left. */}
                                    <button onClick={handleSend} disabled={isSending || !subject.trim() || !body.trim() || !selectedEmails.length}
                                        title={!subject.trim() || !body.trim() ? 'Add a subject and body first' : (!selectedEmails.length ? 'No recipients selected' : undefined)}
                                        className="flex-1 flex items-center justify-center px-4 py-3 text-xs font-black uppercase tracking-widest text-white bg-gradient-to-tr from-emerald-600 to-emerald-500 hover:from-emerald-700 hover:to-emerald-600 rounded-xl transition-all shadow-lg shadow-emerald-500/30 active:scale-95 group disabled:opacity-60 disabled:cursor-not-allowed">
                                        {isSending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending...</> : <>Execute <Send className="w-4 h-4 ml-2 group-hover:translate-x-1 group-hover:-translate-y-1 transition-transform" /></>}
                                    </button>
                                </div>
                                {sendError && <p className="px-5 pb-4 text-xs font-bold text-red-500 text-center">{sendError}</p>}
                            </motion.div>
                        )}

                        {sent && (
                            <motion.div key="success" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="flex-1 bg-gradient-to-b from-emerald-50 to-white dark:from-slate-800 dark:to-slate-900 rounded-3xl border border-emerald-200 dark:border-emerald-500/30 flex flex-col items-center justify-center p-12 text-center min-h-0 relative overflow-hidden shadow-2xl shadow-emerald-500/10">
                                <div className="absolute inset-0 bg-emerald-500/5 dark:bg-emerald-500/10 pointer-events-none blur-2xl rounded-full scale-150"></div>
                                <motion.div initial={{ scale: 0, rotate: -180 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 200, damping: 15 }} className="w-24 h-24 bg-gradient-to-tr from-emerald-400 to-emerald-600 shadow-xl shadow-emerald-500/40 rounded-full flex items-center justify-center mb-8 relative z-10">
                                    <Send className="w-10 h-10 text-white translate-x-1 -translate-y-1" />
                                </motion.div>
                                <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }} className="relative z-10">
                                    <h3 className="text-3xl font-black text-emerald-900 dark:text-emerald-400 tracking-tight mb-2">Payload Dispatched</h3>
                                    <p className="text-sm font-bold text-emerald-600/80 dark:text-emerald-500/80 uppercase tracking-widest">
                                        {sendSummary?.failed_count
                                            ? `${sendSummary.delivered_count} sent, ${sendSummary.failed_count} failed`
                                            : sendSummary?.delivered_count
                                                ? `${sendSummary.delivered_count} recipient(s) accepted by the mail server`
                                                : 'Recorded — see history for delivery status.'}
                                    </p>
                                    {/* Steps that did not complete. Previously these
                                        failed silently in the browser. */}
                                    {fanoutIssues.length > 0 && (
                                        <div className="mt-6 text-left bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-2xl p-4 max-w-sm">
                                            <p className="text-xs font-black text-amber-800 dark:text-amber-300 uppercase tracking-widest mb-2">Incomplete steps</p>
                                            <ul className="space-y-1">
                                                {fanoutIssues.map(f => (
                                                    <li key={f.step} className="text-[11px] font-medium text-amber-800/90 dark:text-amber-200/90 leading-relaxed">
                                                        <span className="font-bold">{f.step}</span>: {f.error}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </motion.div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </motion.div>
            </div>

            {/* Outgoing Email History */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col">
                <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 flex justify-between items-center">
                    <div className="flex items-center">
                        <div className="p-2.5 bg-slate-100 dark:bg-slate-700 rounded-xl text-slate-500 dark:text-slate-400 mr-3"><History className="w-5 h-5" /></div>
                        <h2 className="text-xl font-black text-slate-800 dark:text-white">Outgoing Comm History</h2>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse min-w-[800px]">
                        <thead className="bg-slate-50/80 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700">
                            <tr>
                                <th className="p-5 pl-6 text-[10px] font-black text-slate-400 uppercase tracking-widest">Date / Time</th>
                                <th className="p-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Protocol</th>
                                <th className="p-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Recipients</th>
                                <th className="p-5 text-[10px] font-black text-slate-400 uppercase tracking-widest">Subject</th>
                                <th className="p-5 pr-6 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Status</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {history.map((log) => (
                                <tr key={log.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-700/30 transition-colors group">
                                    <td className="p-5 pl-6">
                                        <div className="text-sm font-bold text-slate-800 dark:text-slate-200">{log.date}</div>
                                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">{log.time}</div>
                                    </td>
                                    <td className="p-5">
                                        <span className="text-xs font-bold bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-600">{log.type}</span>
                                    </td>
                                    <td className="p-5">
                                        <div className="text-sm font-bold text-indigo-600 dark:text-indigo-400 flex items-center">
                                            <Users className="w-3 h-3 mr-1.5" />
                                            {log.recipients}
                                        </div>
                                    </td>
                                    <td className="p-5 text-sm font-medium text-slate-700 dark:text-slate-300 max-w-sm truncate" title={log.subject}>
                                        {log.subject}
                                    </td>
                                    <td className="p-5 pr-6 text-right">
                                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border shadow-sm ${log.status === 'Delivered' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30' : 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/30'}`}>
                                            {log.status === 'Delivered' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>}
                                            {log.status}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                            {history.length === 0 && (
                                <tr>
                                    <td colSpan="5" className="p-12 text-center">
                                        <div className="flex flex-col items-center justify-center">
                                            <History className="w-10 h-10 text-slate-300 dark:text-slate-600 mb-3" />
                                            <p className="text-sm font-bold text-slate-500 dark:text-slate-400">No communications dispatched yet.</p>
                                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Sent messages will appear here.</p>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </motion.div>

            {/* Template Manager Modal */}
            <AnimatePresence>
                {showTemplateManager && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-3xl border border-slate-200 dark:border-slate-700 overflow-hidden flex flex-col max-h-[80vh]">
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center shrink-0">
                                <div className="flex items-center text-white">
                                    <LayoutTemplate className="w-6 h-6 mr-3" />
                                    <h3 className="font-black text-xl">Template Library</h3>
                                </div>
                                <button onClick={() => setShowTemplateManager(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-5 h-5"/></button>
                            </div>
                            
                            <div className="p-6 flex-1 overflow-y-auto bg-slate-50/50 dark:bg-slate-900/50">
                                <div className="flex justify-end mb-6">
                                    <button onClick={openNewTemplate} className="flex items-center px-4 py-2 bg-indigo-600 text-white text-xs font-black uppercase tracking-widest rounded-xl hover:bg-indigo-700 transition-colors shadow-sm">
                                        <Plus className="w-4 h-4 mr-2" /> New Template
                                    </button>
                                </div>

                                {editingTemplate && (
                                    <div className="bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 rounded-2xl p-5 mb-4 space-y-3">
                                        <h4 className="text-sm font-black text-indigo-900 dark:text-indigo-300">{editingTemplate === 'new' ? 'New Template' : 'Edit Template'}</h4>
                                        <input value={templateForm.title} onChange={e => setTemplateForm(f => ({...f, title: e.target.value}))} placeholder="Template title" className="w-full px-4 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" />
                                        <input value={templateForm.subject} onChange={e => setTemplateForm(f => ({...f, subject: e.target.value}))} placeholder="Email subject" className="w-full px-4 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" />
                                        <textarea value={templateForm.body} onChange={e => setTemplateForm(f => ({...f, body: e.target.value}))} placeholder="Email body..." rows={4} className="w-full px-4 py-2.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
                                        {templateError && <p className="text-xs font-bold text-red-500">{templateError}</p>}
                                        <div className="flex gap-3">
                                            <button onClick={() => setEditingTemplate(null)} className="px-4 py-2 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors">Cancel</button>
                                            <button onClick={handleSaveTemplate} disabled={isSavingTemplate} className="flex items-center px-4 py-2 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors disabled:opacity-60">{isSavingTemplate ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Saving...</> : 'Save Template'}</button>
                                        </div>
                                    </div>
                                )}

                                <div className="space-y-4">
                                    {templates.map(t => (
                                        <div key={t.id} className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-md transition-shadow group">
                                            <div className="flex justify-between items-start mb-3">
                                                <h4 className="font-black text-slate-800 dark:text-white text-lg">{t.title}</h4>
                                                <div className="flex space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button onClick={() => openEditTemplate(t)} className="p-1.5 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 bg-slate-100 dark:bg-slate-700 rounded-lg"><Edit2 className="w-4 h-4" /></button>
                                                    <button onClick={() => handleDeleteTemplate(t.id)} className="p-1.5 text-slate-400 hover:text-red-600 dark:hover:text-red-400 bg-slate-100 dark:bg-slate-700 rounded-lg"><Trash2 className="w-4 h-4" /></button>
                                                </div>
                                            </div>
                                            <div className="space-y-2">
                                                <p className="text-sm font-bold text-slate-600 dark:text-slate-300"><span className="text-[10px] p-1 uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 rounded inline-block mr-2">Subj</span> {t.subject}</p>
                                                <p className="text-sm text-slate-500 dark:text-slate-400 truncate"><span className="text-[10px] p-1 uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 rounded inline-block mr-2">Body</span> {t.body}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
