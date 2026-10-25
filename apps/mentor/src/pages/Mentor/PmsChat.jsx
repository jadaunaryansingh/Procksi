import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatTime, groupByDay, senderName, deliveryState, DELIVERY, mergeTimeline } from '../../lib/messageMeta';
import {
    Send, MessageSquare, MessagesSquare, Megaphone, Users, RefreshCcw, UserCircle, Plus, Search,
    Clock, Check, CheckCheck, Maximize2, Minimize2, X, Loader2,
} from 'lucide-react';
import { api, chatAPI } from '../../services/api';
import { publishChatUnread, refreshChatUnread } from '../../hooks/useChatUnread';
import ChatReportCard, { ChatReportMessage } from '../../components/ChatReportCard';
import { subscribeChatEvents } from '../../lib/chatRealtime';

/**
 * PMS-Chat for the mentor portal.
 *
 * A mentor sees three groups, all derived server-side from their allocations:
 *   coordinator  their own direct thread with the project coordinator
 *   team         the mentor and coordinator threads of every team they supervise
 *   broadcast    announcements, which are read-only
 *
 * A supervised team with no mentor thread yet is listed under "Start a thread".
 * The row is created by the backend on the first message, so browsing writes
 * nothing. The team id sent there comes from /teams, which is built from the
 * same allocation query the backend re-checks the POST against.
 */

// What each standing group reaches. Membership is derived from role on the
// server, so these are descriptions rather than counts this portal could
// compute — it only ever sees its own side of the directory.
const GROUP_BLURB = {
    mentors: 'Every mentor',
    panels: 'Every panel',
    teams: 'Every team',
    everyone: 'Every student, mentor and panel',
};

const GROUPS = [
    { key: 'coordinator', label: 'Coordinator', icon: UserCircle },
    { key: 'team', label: 'My teams', icon: Users },
    { key: 'broadcast', label: 'Announcements', icon: Megaphone },
    // The standing groups this mentor belongs to: All Mentors and Everyone.
    // Membership follows from the role, so it needs no upkeep.
    { key: 'group', label: 'Groups', icon: MessagesSquare },
];

// Fallback refresh. Realtime pings drive the live updates; this catches the
// case where the websocket never connected or has dropped.
const POLL_MS = 20000;

// Slash commands. Picking one runs it: the server does the work and returns a
// result the thread renders. These are actions, not message templates.
const SLASH_COMMANDS = [
    { id: 'report', label: '/report', hint: 'Team analysis for the open thread' },
];

// Loose name match between a roster entry and a contributor row. The analyser
// reports git identities, so casing and separators vary even when the person
// is the same.
const normName = (v) => String(v ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');

const SectionHeading = ({ icon: Icon, children }) => (
    <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 border-b border-slate-200/70 dark:border-slate-700/50 flex items-center gap-1.5">
        <Icon className="w-3 h-3" /> {children}
    </p>
);

const PmsChat = () => {
    const [conversations, setConversations] = useState([]);
    const [teams, setTeams] = useState([]);
    const [messages, setMessages] = useState([]);
    // Messages typed here but not yet confirmed by the server. They render
    // immediately so sending feels instant, and are dropped once the same
    // message comes back from the server.
    const [outbox, setOutbox] = useState([]);
    // An existing conversation is selected by id ("c:<id>"); a supervised team
    // with no thread yet is selected by team id ("t:<teamId>").
    const [selectedKey, setSelectedKey] = useState(null);
    const [reply, setReply] = useState('');
    const [busy, setBusy] = useState(false);
    const [loading, setLoading] = useState(true);
    const [messagesLoading, setMessagesLoading] = useState(false);
    const [error, setError] = useState(null);
    // Unread counts per conversation id, straight from /chat/unread. The same
    // figure the sidebar badge totals, broken out so a row can say which thread
    // the badge is actually about.
    const [unreadByConv, setUnreadByConv] = useState({});
    const [query, setQuery] = useState('');
    const [audience, setAudience] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [analysisLoading, setAnalysisLoading] = useState(false);
    const [openMember, setOpenMember] = useState(null);
    // Viewport-free coordinates for the open member card, measured against the
    // thread column at click time. The card cannot live inside the roster row:
    // that row scrolls sideways, and `overflow-x: auto` forces `overflow-y` to
    // `auto` as well, so the card would be clipped to the row's height.
    const [memberPos, setMemberPos] = useState(null);
    const [mentionIndex, setMentionIndex] = useState(0);
    const scrollRef = useRef(null);
    const threadColRef = useRef(null);
    const rosterRef = useRef(null);
    const memberCardRef = useRef(null);
    // Only auto-scroll when the reader is already at the bottom, so a refresh
    // never yanks them away from something they scrolled up to read.
    const atBottomRef = useRef(true);
    // Maps a confirmed server message id back to the temporary id its optimistic
    // bubble used, so the bubble settles in place instead of remounting.
    const keyMapRef = useRef(new Map());
    // Mirrors `outbox` so reconciliation can read it without a state updater.
    const outboxRef = useRef([]);
    // The only writer for the outbox, so state and ref never drift apart and
    // the updater runs exactly once.
    const updateOutbox = (updater) => {
        const next = updater(outboxRef.current);
        outboxRef.current = next;
        setOutbox(next);
    };

    // Full-screen view. The same card is repositioned rather than duplicated,
    // so scroll position, the open thread and the draft all survive the toggle.
    const [maximized, setMaximized] = useState(false);

    const cardRef = useRef(null);

    // Escape, or a click anywhere off the card, restores it. The dimmed
    // backdrop has its own onClick, but this covers every other surface —
    // sidebar, top bar, anything that paints above the backdrop — so "click
    // away to close" holds no matter what the click lands on.
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') setMaximized(false); };
        const onPointerDown = (e) => {
            if (!cardRef.current?.contains(e.target)) setMaximized(false);
        };
        document.addEventListener('keydown', onKey);
        if (maximized) document.addEventListener('pointerdown', onPointerDown);
        return () => {
            document.removeEventListener('keydown', onKey);
            document.removeEventListener('pointerdown', onPointerDown);
        };
    }, [maximized]);

    const load = useCallback(async ({ silent = false } = {}) => {
        try {
            const [convs, teamRows, unread] = await Promise.all([
                chatAPI.getConversations(),
                api.get('/teams').then(r => r.data).catch(() => []),
                // Per-row counts are decoration: a failed poll leaves the last
                // known badges in place rather than blanking the list.
                chatAPI.getUnread().catch(() => null),
            ]);
            setConversations(Array.isArray(convs) ? convs : []);
            setTeams(Array.isArray(teamRows) ? teamRows : []);
            if (unread) {
                setUnreadByConv(unread.by_conversation || {});
                // This page polls every 5s; the sidebar's own poll is slower.
                // Handing the total over keeps the badge current for free.
                publishChatUnread(unread.unread);
            }
            setError(null);
        } catch (err) {
            // A background poll must not raise a banner over a working page.
            if (!silent) setError(err?.response?.data?.detail || err?.message || 'Could not load conversations.');
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const q = query.trim().toLowerCase();
    const convTitle = (c) => c.subject || c.recipient_label || `Conversation ${c.id}`;
    const teamTitle = (t) => t.name || `Team ${t.tag || ''}`.trim();

    const grouped = useMemo(() => {
        const out = { coordinator: [], team: [], broadcast: [], group: [] };
        for (const c of conversations) {
            if (q && !convTitle(c).toLowerCase().includes(q)) continue;
            if (out[c.group]) out[c.group].push(c);
        }
        return out;
    }, [conversations, q]);

    // Chip filter over the sections below. null is "Recent", which shows every
    // section at once — the list as it was before the chips existed.
    const visibleSections = useMemo(
        () => (audience ? GROUPS.filter(g => g.key === audience) : GROUPS),
        [audience],
    );

    // Supervised teams that have no mentor thread yet.
    const startable = useMemo(() => {
        const withThread = new Set(
            conversations.filter(c => c.kind === 'mentor' && c.team_id).map(c => String(c.team_id))
        );
        return teams.filter(t => t?.id
            && !withThread.has(String(t.id))
            && (!q || teamTitle(t).toLowerCase().includes(q)));
    }, [teams, conversations, q]);

    const selected = useMemo(() => {
        if (!selectedKey) return null;
        if (selectedKey.startsWith('t:')) {
            const teamId = selectedKey.slice(2);
            const team = teams.find(t => String(t.id) === teamId);
            return team
                ? { pendingTeamId: team.id, subject: team.name || `Team ${team.tag || ''}`.trim(), group: 'team' }
                : null;
        }
        const id = selectedKey.slice(2);
        return conversations.find(c => String(c.id) === id) || null;
    }, [selectedKey, conversations, teams]);

    const loadMessages = useCallback(async (conversationId, { silent = false } = {}) => {
        if (!conversationId) { setMessages([]); setMessagesLoading(false); return; }
        // Only a foreground fetch spins. The 5s poll runs over messages already
        // on screen, and a spinner there would blink every five seconds.
        if (!silent) setMessagesLoading(true);
        try {
            const res = await chatAPI.getMessages(conversationId);
            const rows = Array.isArray(res) ? res : [];
            setMessages(rows);

            // Fetching a thread is what marks it read server-side, so this row's
            // badge is wrong the instant this resolves. Drop it now rather than
            // leaving a count on a thread the reader is looking at until the
            // next conversation poll repeats what we already know.
            setUnreadByConv(prev => {
                const key = String(conversationId);
                if (!prev[key]) return prev;
                const next = { ...prev };
                delete next[key];
                return next;
            });
            // Retire any optimistic bubble the server has now echoed back.
            // Computed against outboxRef, not inside a setOutbox updater: an
            // updater must be pure, and React may run it twice — on the second
            // run keyMapRef already held the mapping, so the `has(r.id)` guard
            // skipped the match and the bubble was never removed, leaving it on
            // screen beside the confirmed message under the SAME React key.
            const prev = outboxRef.current;
            if (prev.length) {
                const remaining = [];
                for (const p of prev) {
                    let matched = false;
                    for (let i = rows.length - 1; i >= 0; i -= 1) {
                        const r = rows[i];
                        if (keyMapRef.current.has(r.id)) continue;
                        if (r.sender_role === p.sender_role && String(r.body || '').trim() === p.body) {
                            keyMapRef.current.set(r.id, p.id);
                            matched = true;
                            break;
                        }
                    }
                    if (!matched) remaining.push(p);
                }
                if (remaining.length !== prev.length) {
                    outboxRef.current = remaining;
                    setOutbox(remaining);
                }
            }
        } catch (err) {
            if (!silent) {
                setMessages([]);
                setError(err?.response?.data?.detail || err?.message || 'Could not load messages.');
            }
        } finally {
            if (!silent) {
                setMessagesLoading(false);
                // Fetching a thread is what marks it read server-side, so the
                // badge is stale the instant this resolves. Recount now rather
                // than leaving the old number up until the next poll.
                refreshChatUnread();
            }
        }
    }, []);

    // Switching threads starts clean: another thread's unsent bubbles and key
    // mappings must never leak into this one.
    useEffect(() => {
        updateOutbox(() => []);
        keyMapRef.current = new Map();
        atBottomRef.current = true;
        loadMessages(selected?.id ?? null);
    }, [selected?.id, loadMessages]);

    // Realtime is the live path: a trigger pings `chat_events` on every insert
    // and the refetch below runs immediately. The interval is only a fallback
    // for a websocket that never connected or has dropped, which is why it is
    // far slower than the 5s poll it replaces. Both are skipped while the tab
    // is hidden, and a visible tab refetches at once on becoming visible so
    // returning shows current messages rather than stale ones.
    useEffect(() => {
        const tick = () => {
            if (document.hidden) return;
            load({ silent: true });
            if (selected?.id) loadMessages(selected.id, { silent: true });
        };
        const timer = setInterval(tick, POLL_MS);
        document.addEventListener('visibilitychange', tick);
        // The ping carries a conversation id and nothing else. The open thread
        // refetches only when the id matches; the list always refetches,
        // because a message in any thread changes its row's unread count.
        const stopRealtime = subscribeChatEvents((conversationId) => {
            if (document.hidden) return;
            load({ silent: true });
            if (selected?.id && String(selected.id) === String(conversationId)) {
                loadMessages(selected.id, { silent: true });
            }
        });
        return () => {
            clearInterval(timer);
            stopRealtime();
            document.removeEventListener('visibilitychange', tick);
        };
    }, [selected?.id, load, loadMessages]);

    useEffect(() => {
        if (!atBottomRef.current) return;
        const el = scrollRef.current;
        if (!el) return;
        // Wait a frame. Framer Motion has not run its layout pass for this
        // commit yet, so scrollHeight is still the pre-animation height and
        // scrolling to it leaves the newest message clipped by the composer.
        const frame = requestAnimationFrame(() => {
            el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
        });
        return () => cancelAnimationFrame(frame);
    }, [messages, outbox]);

    const handleScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };

    const readOnly = Boolean(selected && selected.group === 'broadcast');

    const settle = useCallback(async (item) => {
        try {
            const res = await chatAPI.sendMessage({
                conversationId: item.conversationId,
                teamId: item.teamId,
                body: item.body,
            });
            const newId = res?.conversation_id ?? item.conversationId;
            if (!item.conversationId && newId) setSelectedKey(`c:${newId}`);
            await loadMessages(newId, { silent: true });
            await load({ silent: true });
        } catch (err) {
            // The bubble stays on screen marked "Not sent" rather than vanishing
            // with an alert, so the text the mentor wrote is never lost.
            const detail = err?.response?.data?.detail || err?.message || 'Could not send.';
            updateOutbox(prev => prev.map(m => m.id === item.id
                ? { ...m, status: 'failed', error: detail } : m));
        }
    }, [loadMessages, load]);

    const handleSend = async (e) => {
        e.preventDefault();
        const text = reply.trim();
        if (!text || !selected || busy || readOnly) return;

        const item = {
            id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            body: text,
            sender_role: 'mentor',
            // Stamped locally so an unsent message shows a time and files under
            // the right day; the server's timestamp replaces it on confirm.
            created_at: new Date().toISOString(),
            conversationId: selected.id ?? null,
            teamId: selected.id ? null : (selected.pendingTeamId ?? null),
            status: 'sending',
        };
        setReply('');
        updateOutbox(prev => [...prev, item]);
        atBottomRef.current = true;
        setBusy(true);
        await settle(item);
        setBusy(false);
    };

    const retrySend = async (item) => {
        updateOutbox(prev => prev.map(m => m.id === item.id ? { ...m, status: 'sending' } : m));
        await settle(item);
    };

    const discardSend = (id) => updateOutbox(prev => prev.filter(m => m.id !== id));

    // Confirmed messages first, then anything still in flight. A confirmed
    // message reuses its optimistic bubble's key where one exists, so the
    // handover is invisible.
    const timeline = useMemo(
        () => mergeTimeline(messages, outbox, keyMapRef.current),
        [messages, outbox],
    );

    const days = groupByDay(timeline);

    // One placeholder for the whole thread pane, rendered as an overlay on the
    // column rather than inside the message list. Centred on the column, its
    // position no longer depends on which chrome happens to be on screen — a
    // header, a roster strip and a composer each shifted the old in-flow
    // version, so the icon sat at a different height in every state.
    const placeholder = !selected ? 'select'
        : messagesLoading ? 'loading'
        : timeline.length === 0 ? 'empty'
        : null;

    // The team behind the open thread, if any. A coordinator thread and an
    // announcement have no team, so they get no roster.
    const openTeamId = selected?.pendingTeamId ?? selected?.team_id ?? null;

    // /teams already carries each team's members, so the roster needs no extra
    // call. They arrive as plain names.
    const roster = useMemo(() => {
        if (!openTeamId) return [];
        const team = teams.find(t => String(t.id) === String(openTeamId));
        const list = Array.isArray(team?.members) ? team.members : [];
        return list
            .map(m => (typeof m === 'string' ? { id: m, name: m } : { id: m?.id || m?.name, name: m?.name || String(m) }))
            .filter(m => m.name);
    }, [openTeamId, teams]);

    // Switching threads drops the open card and the previous team's stats.
    useEffect(() => { setOpenMember(null); setAnalysis(null); }, [openTeamId]);

    // Repository analysis for the open team, fetched only when a chip is
    // actually clicked. /teams/{id}/github queues a fresh analysis run when the
    // stored one is stale, so it must not fire merely because a thread was
    // opened. The endpoint already attributes commits to members server-side,
    // so the response is read as-is rather than re-derived here.
    const loadAnalysis = useCallback(async () => {
        if (!openTeamId) return;
        setAnalysisLoading(true);
        try {
            const r = await api.get(`/teams/${encodeURIComponent(openTeamId)}/github`);
            setAnalysis(r.data);
        } catch {
            setAnalysis(null);
        } finally {
            setAnalysisLoading(false);
        }
    }, [openTeamId]);

    const contributors = Array.isArray(analysis?.contributors) ? analysis.contributors : [];
    const activeMember = openMember ? roster.find(m => String(m.id) === openMember) || null : null;
    const activeStat = activeMember
        ? contributors.find(c => normName(c.name) === normName(activeMember.name)) || null
        : null;

    // Anchors the card under its chip, in the thread column's coordinates, and
    // keeps it inside that column so a chip near the right edge cannot push the
    // card off-panel.
    const openMemberCard = (key, chipEl) => {
        const column = threadColRef.current;
        if (!column) return;
        const chip = chipEl.getBoundingClientRect();
        const col = column.getBoundingClientRect();
        const CARD_W = 256;   // w-64
        const GUTTER = 8;
        const maxLeft = Math.max(GUTTER, col.width - CARD_W - GUTTER);
        setMemberPos({
            left: Math.min(Math.max(chip.left - col.left, GUTTER), maxLeft),
            top: chip.bottom - col.top + GUTTER,
        });
        setOpenMember(key);
        if (!analysis && !analysisLoading) loadAnalysis();
    };

    // The card is positioned once, so anything that moves the chip out from
    // under it closes the card rather than letting it drift.
    useEffect(() => {
        if (!openMember) return undefined;
        const close = () => setOpenMember(null);
        const onPointerDown = (e) => {
            if (rosterRef.current?.contains(e.target)) return;
            if (memberCardRef.current?.contains(e.target)) return;
            close();
        };
        const rosterEl = rosterRef.current;
        rosterEl?.addEventListener('scroll', close, { passive: true });
        window.addEventListener('resize', close);
        document.addEventListener('pointerdown', onPointerDown);
        return () => {
            rosterEl?.removeEventListener('scroll', close);
            window.removeEventListener('resize', close);
            document.removeEventListener('pointerdown', onPointerDown);
        };
    }, [openMember]);

    // The /report affordance: the option picker, the "working" state, and any
    // failure. The report itself is not held here — PMSbot posts it into the
    // conversation, so it arrives through the normal message list and stays.
    const [command, setCommand] = useState(null);

    const runCommand = useCallback(async (id, option = null) => {
        const conversationId = selected?.id ?? null;
        if (option && !conversationId) {
            setCommand({ loading: false, data: null, error: 'Open a conversation first.' });
            return;
        }
        setCommand({ loading: true, error: null, data: null });
        try {
            const data = await chatAPI.runCommand({
                command: id, option, teamId: openTeamId, conversationId,
            });
            if (data?.step === 'posted') {
                // The result is now a message. Clear the affordance and pull it in.
                setCommand(null);
                await loadMessages(conversationId, { silent: true });
                return;
            }
            setCommand({ loading: false, error: null, data });
        } catch (err) {
            setCommand({ loading: false, data: null,
                error: err?.response?.data?.detail || err?.message || 'That command could not be run.' });
        }
    }, [openTeamId, selected, loadMessages]);

    // @-mention autocomplete. Triggers on a trailing "@word" so it only fires
    // while the caret is still inside the token being typed.
    const mentionToken = useMemo(() => {
        const m = reply.match(/@([\p{L}\p{N}._-]*)$/u);
        return m ? m[1] : null;
    }, [reply]);

    const mentionMatches = useMemo(() => {
        if (mentionToken === null || roster.length === 0) return [];
        const needle = mentionToken.toLowerCase();
        return roster.filter(m => !needle || String(m.name).toLowerCase().includes(needle));
    }, [mentionToken, roster]);

    const insertMention = (member) => {
        // Replace only the trailing @token, leaving the rest of the draft alone.
        setReply(prev => prev.replace(/@([\p{L}\p{N}._-]*)$/u, `@${String(member.name).trim()} `));
    };

    // Slash commands only trigger on a leading "/" — mid-sentence slashes (URLs,
    // dates) must never open the menu.
    const slashToken = useMemo(() => {
        const m = reply.match(/^\/([a-z]*)$/i);
        return m ? m[1].toLowerCase() : null;
    }, [reply]);

    const slashMatches = useMemo(() => {
        if (slashToken === null) return [];
        return SLASH_COMMANDS.filter(c => c.id.startsWith(slashToken));
    }, [slashToken]);

    useEffect(() => { setMentionIndex(0); }, [slashToken]);

    // Running a command clears the draft: the "/report" text was the gesture,
    // not something anyone should send to the thread by accident.
    const pickCommand = (cmd) => {
        setReply('');
        runCommand(cmd.id);
    };

    // One list is open at a time; whichever is active owns the arrow keys.
    const openList = slashMatches.length > 0 ? slashMatches : mentionMatches;
    const isSlash = slashMatches.length > 0;

    const handleReplyKeyDown = (e) => {
        if (openList.length === 0) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setMentionIndex(i => (i + 1) % openList.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setMentionIndex(i => (i - 1 + openList.length) % openList.length);
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            // Enter picks the highlighted entry instead of submitting the form.
            e.preventDefault();
            if (isSlash) pickCommand(openList[mentionIndex]);
            else insertMention(openList[mentionIndex]);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            setReply(prev => `${prev} `);
        }
    };

    const Row = ({ id, title, subtitle, icon: Icon, dim, unread = 0 }) => {
        const active = selectedKey === id;
        return (
            // Clicking the open row closes it. The open row collapses to its
            // identifier plus the hint, so the list always shows which thread
            // is on screen and how to dismiss it. min-height matches an
            // expanded row so collapsing never shifts the list.
            <button type="button" onClick={() => setSelectedKey(active ? null : id)}
                className={`w-full text-left px-4 min-h-[4rem] flex items-center gap-3 transition-colors ${active
                    ? 'bg-emerald-50 dark:bg-emerald-500/10'
                    : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'} ${dim ? 'opacity-70' : ''}`}>
                {active ? (
                    <span className="w-full flex items-center gap-2.5">
                        <span className="shrink-0 px-2 py-0.5 bg-emerald-600 text-white rounded-md text-[10px] font-black tracking-wider truncate max-w-[10rem]">
                            {title}
                        </span>
                        <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">Click to close</span>
                        <X className="w-3.5 h-3.5 text-emerald-500 ml-auto shrink-0" />
                    </span>
                ) : (
                    <>
                        <Icon className="w-4 h-4 shrink-0 text-slate-400" />
                        <span className="min-w-0 flex-1">
                            <span className="block font-bold text-sm text-slate-800 dark:text-white truncate">{title}</span>
                            <span className="block text-[11px] font-medium text-slate-400 truncate">{subtitle}</span>
                        </span>
                        {unread > 0 && (
                            <span className="shrink-0 px-2 py-0.5 bg-emerald-600 text-white rounded-full text-[10px] font-black tabular-nums">
                                {unread > 99 ? '99+' : unread}
                            </span>
                        )}
                    </>
                )}
            </button>
        );
    };

    const isEmpty = conversations.length === 0 && teams.length === 0;
    // What the list is actually showing after the search filter.
    const visibleCount = GROUPS.reduce((n, g) => n + grouped[g.key].length, 0) + startable.length;

    return (
        <div className="space-y-6">
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-emerald-600 via-emerald-700 to-teal-900 rounded-3xl p-8 text-white shadow-xl shadow-emerald-500/20 relative overflow-hidden border border-emerald-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10">
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">PMS-Chat</h1>
                    <p className="text-emerald-100/90 text-sm md:text-base max-w-lg font-medium">
                        Your coordinator and every team you supervise - all in one place.
                    </p>
                </div>
            </motion.div>

            {error && (
                <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 rounded-3xl p-5 flex items-start justify-between gap-4">
                    <div>
                        <p className="font-black text-sm text-rose-900 dark:text-rose-200">Could not load PMS-Chat</p>
                        <p className="text-xs font-medium text-rose-800/80 dark:text-rose-200/70 mt-1">{error}</p>
                    </div>
                    <button onClick={() => { setLoading(true); load(); }}
                        className="p-2 text-rose-500 hover:text-rose-700 rounded-lg shrink-0">
                        <RefreshCcw className="w-4 h-4" />
                    </button>
                </div>
            )}

            {/* Dim the page behind the maximized messenger. Clicking it restores. */}
            <AnimatePresence>
                {maximized && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ duration: 0.18 }}
                        onClick={() => setMaximized(false)}
                        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-[60]" />
                )}
            </AnimatePresence>

            {/* NOTE: `relative` must NOT be in the base classes — Tailwind emits
                .relative after .fixed, so it would win and the maximized card
                would never leave the flow. Position is set per-branch instead. */}
            <motion.div
                ref={cardRef}
                layout
                initial={false}
                // `layout` tweens the element's bounding box, so all four edges
                // travel outward at once rather than the box sliding from a
                // corner. transformOrigin keeps that growth centred.
                style={{ transformOrigin: 'center center' }}
                transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }}
                className={`bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 overflow-hidden grid grid-cols-1 lg:grid-cols-3 ${maximized
                ? 'fixed z-[70] shadow-2xl inset-4 sm:inset-8 lg:inset-y-10 lg:left-[10vw] lg:right-[10vw]'
                : 'relative shadow-sm lg:h-[calc(100vh-24rem)] lg:min-h-[26rem]'}`}>

                <button type="button" onClick={() => setMaximized(m => !m)}
                    title={maximized ? 'Restore down (Esc)' : 'Maximize chat'}
                    aria-label={maximized ? 'Restore chat' : 'Maximize chat'}
                    className="absolute top-3 right-3 z-40 p-2 rounded-xl bg-white/80 dark:bg-slate-800/80 backdrop-blur border border-slate-200/70 dark:border-slate-700/70 text-slate-400 hover:text-emerald-600 dark:hover:text-emerald-400 hover:border-emerald-300 transition-colors shadow-sm">
                    {maximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                {/* Conversation list */}
                <motion.div layout transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }}
                    className="flex flex-col min-h-0 border-b lg:border-b-0 lg:border-r border-slate-100 dark:border-slate-700/50">
                    <div className="h-16 shrink-0 px-4 pr-14 lg:pr-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <h2 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest">Messages</h2>
                        <button onClick={load} title="Refresh"
                            className="p-2 text-slate-400 hover:text-emerald-600 rounded-lg transition-colors">
                            <RefreshCcw className="w-4 h-4" />
                        </button>
                    </div>

                    {/* Section filter. Recent shows every section, exactly as the
                        list behaved before the chips existed. */}
                    <div className="h-14 shrink-0 px-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center gap-1.5 overflow-x-auto">
                        <button onClick={() => setAudience(null)}
                            className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === null
                                ? 'bg-emerald-600 text-white'
                                : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                            Recent
                        </button>
                        {GROUPS.map(g => (
                            <button key={g.key} onClick={() => setAudience(audience === g.key ? null : g.key)}
                                className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === g.key
                                    ? 'bg-emerald-600 text-white'
                                    : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                                {g.label}
                            </button>
                        ))}
                    </div>

                    {/* Search — filters the conversation list and the startable teams */}
                    <div className="h-16 shrink-0 px-4 flex items-center border-b border-slate-100 dark:border-slate-700/50">
                        <div className="relative w-full">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                            <input value={query} onChange={e => setQuery(e.target.value)}
                                placeholder="Search conversations..."
                                className="w-full pl-9 pr-8 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" />
                            {query && (
                                <button type="button" onClick={() => setQuery('')} title="Clear"
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-md">
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="divide-y divide-slate-100 dark:divide-slate-700/50 overflow-y-auto flex-1 min-h-0 max-h-[20rem] lg:max-h-none">
                        {loading && <p className="p-8 text-center text-sm font-medium text-slate-500">Loading...</p>}

                        {!loading && isEmpty && (
                            <p className="p-8 text-center text-sm font-medium text-slate-500">
                                No conversations yet. Threads appear here once the coordinator writes to you,
                                or once teams are allocated to you.
                            </p>
                        )}

                        {!loading && !isEmpty && visibleCount === 0 && (
                            <p className="p-8 text-center text-sm font-medium text-slate-500">Nothing matches that search.</p>
                        )}

                        {visibleSections.map(({ key, label, icon: Icon }) => (
                            grouped[key].length > 0 && (
                                <React.Fragment key={key}>
                                    <SectionHeading icon={Icon}>{label}</SectionHeading>
                                    {grouped[key].map(c => (
                                        <Row key={c.id} id={`c:${c.id}`} icon={Icon}
                                            unread={Number(unreadByConv[String(c.id)]) || 0}
                                            title={convTitle(c)}
                                            subtitle={key === 'team'
                                                ? (c.kind === 'coordinator' ? 'From the coordinator' : 'Mentor thread')
                                                : key === 'broadcast' ? 'Announcement - read only'
                                                : key === 'group'
                                                    ? (GROUP_BLURB[c.group_key] || 'Group thread')
                                                    : 'Direct thread'} />
                                    ))}
                                </React.Fragment>
                            )
                        ))}

                        {/* Startable teams belong to the teams list, so they are
                            hidden whenever a different chip is selected. */}
                        {(audience === null || audience === 'team') && startable.length > 0 && (
                            <>
                                <SectionHeading icon={Plus}>Start a thread</SectionHeading>
                                {startable.map(t => (
                                    <Row key={t.id} id={`t:${t.id}`} icon={Users} dim
                                        title={teamTitle(t)}
                                        subtitle={t.projectTitle || 'No messages yet'} />
                                ))}
                            </>
                        )}
                    </div>
                </motion.div>

                {/* Thread */}
                <motion.div ref={threadColRef} layout transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }} className="relative lg:col-span-2 flex flex-col min-h-0">
                    {!selected ? (
                        // Reserves the column's height on stacked layouts, where the
                        // card has no fixed height and an empty column would collapse.
                        // The placeholder itself is the overlay at the end of this column.
                        <div aria-hidden="true" className="flex-1 min-h-[18rem] lg:min-h-0" />
                    ) : (
                        <>
                            <div className="h-16 shrink-0 px-4 pr-14 flex flex-col justify-center">
                                <h2 className="font-black text-slate-800 dark:text-white truncate">{selected.subject}</h2>
                                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 mt-0.5">
                                    {readOnly ? 'Announcement - read only'
                                        : selected.pendingTeamId ? 'New thread' : (selected.kind || 'Direct')}
                                </p>
                            </div>

                            {/* Team roster — who this chat actually reaches */}
                            {roster.length > 0 && (
                                <div ref={rosterRef} className="h-14 shrink-0 px-4 flex items-center gap-1.5 overflow-x-auto bg-slate-50/50 dark:bg-slate-900/20">
                                    {roster.map(m => {
                                        const key = String(m.id);
                                        const isOpen = openMember === key;
                                        return (
                                            <button key={key} type="button"
                                                onClick={(e) => (isOpen ? setOpenMember(null) : openMemberCard(key, e.currentTarget))}
                                                className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-bold border transition-colors bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 ${isOpen ? 'ring-2 ring-emerald-400' : ''}`}>
                                                {m.name}
                                            </button>
                                        );
                                    })}
                                </div>
                            )}

                            {/* Member card. A sibling of the roster row, not a child of
                                it: the row is a horizontal scroller, and a scroller
                                clips its children on both axes regardless of which one
                                you asked to scroll. */}
                            <AnimatePresence>
                            {activeMember && memberPos && (
                                <motion.div ref={memberCardRef}
                                    initial={{ opacity: 0, y: -6, scale: 0.96 }}
                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                    exit={{ opacity: 0, y: -6, scale: 0.96 }}
                                    transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                                    style={{ transformOrigin: 'top left', left: memberPos.left, top: memberPos.top }}
                                    className="absolute w-64 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl p-3.5 z-40">
                                    <p className="font-black text-sm text-slate-800 dark:text-white truncate mb-3">
                                        {activeMember.name}
                                    </p>

                                    {analysisLoading ? (
                                        <p className="text-xs font-medium text-slate-400">Loading repository analysis…</p>
                                    ) : !analysis ? (
                                        <p className="text-xs font-medium text-slate-400">
                                            No repository analysis yet. Stats appear after the next analysis run.
                                        </p>
                                    ) : (
                                        <>
                                            <div className="grid grid-cols-2 gap-2">
                                                <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-2.5">
                                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Commits</p>
                                                    <p className="text-lg font-black text-slate-800 dark:text-white">{activeStat?.commits ?? 0}</p>
                                                </div>
                                                <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-2.5">
                                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Share</p>
                                                    <p className="text-lg font-black text-slate-800 dark:text-white">{activeStat?.contribution ?? 0}%</p>
                                                </div>
                                            </div>
                                            <p className="text-[10px] font-medium text-slate-400 mt-2.5">
                                                {analysis.commitCount || 0} commits in the repository
                                            </p>
                                            {activeStat?.lastCommit && activeStat.lastCommit !== 'Never' && (
                                                <p className="text-[10px] font-medium text-slate-400 mt-1">
                                                    Last commit: {activeStat.lastCommit}
                                                </p>
                                            )}
                                            {!activeStat?.commits && (
                                                <p className="text-[10px] font-medium text-amber-600 dark:text-amber-400 mt-1.5">
                                                    No commits matched this student. Commits made under a different
                                                    GitHub name are not counted here.
                                                </p>
                                            )}
                                        </>
                                    )}
                                </motion.div>
                            )}
                            </AnimatePresence>

                            <div ref={scrollRef} onScroll={handleScroll}
                                className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 max-h-[18rem] lg:max-h-none">
                                <AnimatePresence initial={false}>
                                    {days.map(day => (
                                        <React.Fragment key={day.key}>
                                            <motion.div layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                                transition={{ duration: 0.2 }}
                                                className="flex items-center justify-center py-1">
                                                <span className="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-700/60 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                                                    {day.label}
                                                </span>
                                            </motion.div>
                                            {day.items.map(m => {
                                                const status = deliveryState(m);
                                                const own = m.sender_role === 'mentor';

                                                // PMSbot's reports are stored messages like any
                                                // other, but they render as a card rather than a
                                                // bubble: a grid of figures does not fit inside
                                                // 75% of the column.
                                                if (m.sender_role === 'bot') return (
                                                    <motion.div key={m.rowKey} layout
                                                        initial={{ opacity: 0, y: 14 }}
                                                        animate={{ opacity: 1, y: 0 }}
                                                        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                                                        className="flex justify-start">
                                                        <div className="w-full max-w-[92%]">
                                                            <ChatReportMessage message={m}
                                                                timeLabel={formatTime(m.created_at)} />
                                                        </div>
                                                    </motion.div>
                                                );

                                                return (
                                                <motion.div key={m.rowKey} layout
                                                    initial={{ opacity: 0, y: 14, scale: 0.96 }}
                                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                                    exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.12 } }}
                                                    transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
                                                    className={`flex ${m.sender_role === 'mentor' ? 'justify-end' : 'justify-start'}`}>
                                                    <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 transition-opacity ${m.sender_role === 'mentor'
                                                        ? 'bg-emerald-600 text-white'
                                                        : 'bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100'
                                                        } ${m.status === 'sending' ? 'opacity-70' : ''
                                                        } ${m.status === 'failed' ? 'ring-2 ring-rose-400' : ''}`}>
                                                        <p className="text-[10px] font-black uppercase tracking-widest opacity-70 mb-1">
                                                            {senderName(m)}
                                                        </p>
                                                        <p className="text-sm font-medium whitespace-pre-wrap">{m.body}</p>
                                                        <div className="mt-1 flex items-center justify-end gap-2">
                                                            {own && status === DELIVERY.SENDING && (
                                                                <Clock className="w-3 h-3 opacity-70" aria-label="Sending" />
                                                            )}
                                                            {own && status === DELIVERY.SENT && (
                                                                <Check className="w-3.5 h-3.5 opacity-70" aria-label="Sent" />
                                                            )}
                                                            {own && status === DELIVERY.READ && (
                                                                <CheckCheck className="w-3.5 h-3.5 text-sky-300" aria-label="Read" />
                                                            )}
                                                            {m.status === 'failed' && (
                                                                <>
                                                                    <span className="text-[10px] font-bold uppercase tracking-widest mr-auto">Not sent</span>
                                                                    <button type="button" onClick={() => retrySend(m)}
                                                                        className="text-[10px] font-black uppercase tracking-widest underline underline-offset-2">
                                                                        Retry
                                                                    </button>
                                                                    <button type="button" onClick={() => discardSend(m.id)}
                                                                        className="text-[10px] font-black uppercase tracking-widest underline underline-offset-2 opacity-80">
                                                                        Discard
                                                                    </button>
                                                                </>
                                                            )}
                                                            {m.status !== 'failed' && (
                                                                <span className="text-[10px] font-semibold tabular-nums opacity-60">
                                                                    {formatTime(m.created_at)}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                </motion.div>
                                                );
                                            })}
                                        </React.Fragment>
                                    ))}
                                </AnimatePresence>

                                {/* Command output sits at the end of the thread, where
                                    the answer to "/report" belongs, but is not a message. */}
                                {command && (
                                    <ChatReportCard
                                        state={command}
                                        onChoose={(optionId) => runCommand('report', optionId)}
                                        onDismiss={() => setCommand(null)} />
                                )}
                            </div>

                            {readOnly ? (
                                <p className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 text-xs font-medium text-slate-400 text-center">
                                    Announcements are read only. Contact the coordinator directly to respond.
                                </p>
                            ) : (
                                <form onSubmit={handleSend} className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2 relative">
                                    <AnimatePresence>

                                    {/* Slash-command list. Picking one runs it. */}
                                    {slashMatches.length > 0 && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 8, scale: 0.97 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            exit={{ opacity: 0, y: 8, scale: 0.97 }}
                                            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                                            style={{ transformOrigin: 'bottom left' }}
                                            className="absolute bottom-full left-4 right-16 mb-2 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl overflow-hidden p-1.5 max-h-56 overflow-y-auto z-20">
                                            <p className="px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                                                Commands
                                            </p>
                                            {slashMatches.map((c, i) => (
                                                <button key={c.id} type="button"
                                                    onMouseDown={e => { e.preventDefault(); pickCommand(c); }}
                                                    onMouseEnter={() => setMentionIndex(i)}
                                                    className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-xl text-left transition-colors ${i === mentionIndex
                                                        ? 'bg-emerald-50 dark:bg-emerald-500/15'
                                                        : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                                    <span className="shrink-0 px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-md text-[11px] font-black font-mono">
                                                        {c.label}
                                                    </span>
                                                    <span className="text-xs font-medium text-slate-500 dark:text-slate-400 truncate">{c.hint}</span>
                                                </button>
                                            ))}
                                        </motion.div>
                                    )}

                                    {/* @-mention list — team members only */}
                                    {slashMatches.length === 0 && mentionMatches.length > 0 && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 8, scale: 0.97 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            exit={{ opacity: 0, y: 8, scale: 0.97 }}
                                            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                                            style={{ transformOrigin: 'bottom left' }}
                                            className="absolute bottom-full left-4 right-16 mb-2 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl overflow-hidden p-1.5 max-h-48 overflow-y-auto z-20">
                                            <p className="px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                                                Tag a member
                                            </p>
                                            {mentionMatches.map((m, i) => (
                                                <button key={String(m.id)} type="button"
                                                    onMouseDown={e => { e.preventDefault(); insertMention(m); }}
                                                    onMouseEnter={() => setMentionIndex(i)}
                                                    className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-xl text-left transition-colors ${i === mentionIndex
                                                        ? 'bg-emerald-50 dark:bg-emerald-500/15'
                                                        : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                                    <span className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center text-[10px] font-black shrink-0">
                                                        {String(m.name || '?').charAt(0).toUpperCase()}
                                                    </span>
                                                    <span className="block text-sm font-bold text-slate-800 dark:text-white truncate">{m.name}</span>
                                                </button>
                                            ))}
                                        </motion.div>
                                    )}
                                    </AnimatePresence>
                                    <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={handleReplyKeyDown}
                                        placeholder="Write a reply..."
                                        className="flex-1 px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" />
                                    <button type="submit" disabled={busy || !reply.trim()}
                                        className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl transition-colors">
                                        <Send className="w-4 h-4" />
                                    </button>
                                </form>
                            )}
                        </>
                    )}

                    {/* Placeholder overlay. Centred on the column, so it lands in
                        exactly the same spot whether the pane is empty, loading,
                        or showing a thread with a roster strip and a composer.
                        pointer-events-none keeps it from swallowing clicks. */}
                    {placeholder && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-400 gap-3 pointer-events-none">
                            {placeholder === 'loading'
                                ? <Loader2 className="w-10 h-10 animate-spin" aria-label="Loading messages" />
                                : <MessageSquare className="w-10 h-10" />}
                            <p className="text-sm font-bold">
                                {placeholder === 'loading' ? 'Loading messages'
                                    : placeholder === 'select' ? 'Select a conversation'
                                    : 'No messages yet'}
                            </p>
                        </div>
                    )}
                </motion.div>
            </motion.div>
        </div>
    );
};

export default PmsChat;
