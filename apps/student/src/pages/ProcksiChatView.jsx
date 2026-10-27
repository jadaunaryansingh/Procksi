import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { formatTime, groupByDay, senderName, deliveryState, DELIVERY, mergeTimeline } from '../lib/messageMeta';
import { Send, MessageSquare, MessagesSquare, Megaphone, Users, RefreshCcw, UserCircle, GraduationCap, ClipboardCheck , Clock, Check, CheckCheck, Maximize2, Minimize2, X, Loader2 } from 'lucide-react';
import { getChatConversations, getChatMessages, sendChatMessage, getChatUnread, getTeamMembers, getTeamGithub } from '../lib/api';
// Students do not run /report, but they do receive it: ProcksiBot posts a
// coordinator's or mentor's report into the thread, and this renders it.
import { ChatReportMessage } from '../components/ChatReportCard';
import { attributeCommits, extractContributors } from '../lib/memberCommits';
import { publishChatUnread, refreshChatUnread } from '../hooks/useChatUnread';
import { subscribeChatEvents } from '../lib/chatRealtime';

/**
 * Procksi Chat for the student portal.
 *
 * Deliberately much simpler than the coordinator's view: a student has exactly
 * four standing threads — coordinator, mentor, panel and their own team — plus
 * announcements. There is no directory, no audience picker and no broadcast
 * composer; who a student can talk to is fixed by their team.
 *
 * A thread with no `id` has no database row yet. It is shown anyway, and the row
 * is created on the first message, so browsing never writes.
 *
 * Announcements are read-only — a broadcast goes to every team, so a reply there
 * would be visible far wider than the student expects.
 */
// Fallback refresh. Realtime pings drive the live updates; this catches the
// case where the websocket never connected or has dropped.
const POLL_MS = 20000;

// Sections in the conversation list, and the chips that filter it. "Recent"
// (audience === null) shows all three at once.
// What each standing group reaches. Membership is derived from role on the
// server, so these are descriptions rather than counts this portal could
// compute — it only ever sees its own side of the directory.
const GROUP_BLURB = {
    mentors: 'Every mentor',
    panels: 'Every panel',
    teams: 'Every team',
    everyone: 'Every student, mentor and panel',
};

const SECTIONS = [
    { key: 'thread', label: 'Chats' },
    { key: 'broadcast', label: 'Announcements' },
    { key: 'group', label: 'Groups' },
];

// Students have no slash commands. `/report` is run by coordinators, mentors
// and panels; a student sees the result when ProcksiBot posts it into the thread,
// but does not run it themselves.

const ProcksiChatView = () => {
    const [threads, setThreads] = useState([]);
    const [broadcasts, setBroadcasts] = useState([]);
    const [groups, setGroups] = useState([]);
    const [messages, setMessages] = useState([]);
    // Messages typed here but not yet confirmed by the server. They render
    // immediately so sending feels instant, and are dropped once the same
    // message comes back from the server.
    const [outbox, setOutbox] = useState([]);
    // A thread with no row yet is selected by kind; an existing one by id.
    const [selectedKey, setSelectedKey] = useState(null);
    const [audience, setAudience] = useState(null);
    const [reply, setReply] = useState('');
    const [busy, setBusy] = useState(false);
    const [loading, setLoading] = useState(true);
    const [messagesLoading, setMessagesLoading] = useState(false);
    const [error, setError] = useState(null);
    // Unread counts per conversation id, straight from /chat/unread. The same
    // figure the sidebar badge totals, broken out so a row can say which thread
    // the badge is actually about.
    const [unreadByConv, setUnreadByConv] = useState({});
    // The student's own team. Fetched once — a roster does not change mid-chat.
    const [teamMembers, setTeamMembers] = useState([]);
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
    // bubble used. Reusing that key keeps React from unmounting and remounting
    // the bubble, so it settles in place instead of replaying its entry.
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

    const loadConversations = useCallback(async ({ silent = false } = {}) => {
        try {
            // apiRequest already returns the envelope's `data` field, so this
            // is `{threads, broadcasts}` — not `{data: {...}}`.
            const [res, unread] = await Promise.all([
                getChatConversations(),
                // Per-row counts are decoration: a failed poll leaves the last
                // known badges in place rather than blanking the list.
                getChatUnread().catch(() => null),
            ]);
            setThreads(res?.threads || []);
            setBroadcasts(res?.broadcasts || []);
            // `kind` is stamped locally: the server sends group rows without one,
            // and the composer reads a kind-less selection as a read-only broadcast.
            setGroups((res?.groups || []).map(g => ({ ...g, kind: 'group' })));
            if (unread) {
                setUnreadByConv(unread.by_conversation || {});
                // This page polls every 5s; the sidebar's own poll is slower.
                // Handing the total over keeps the badge current for free.
                publishChatUnread(unread.unread);
            }
            setError(null);
        } catch (err) {
            // A background poll must not raise a banner over a working page;
            // the next tick will retry anyway.
            if (!silent) setError(err?.message || 'Could not load conversations.');
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => { loadConversations(); }, [loadConversations]);

    const loadMessages = useCallback(async (conversationId, { silent = false } = {}) => {
        if (!conversationId) { setMessages([]); setMessagesLoading(false); return; }
        // Only a foreground fetch spins. The 5s poll runs over messages already
        // on screen, and a spinner there would blink every five seconds.
        if (!silent) setMessagesLoading(true);
        try {
            const res = await getChatMessages(conversationId);
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
                setError(err?.message || 'Could not load messages.');
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

    const selected = useMemo(() => {
        if (!selectedKey) return null;
        if (selectedKey.startsWith('k:')) {
            return threads.find(t => t.kind === selectedKey.slice(2)) || null;
        }
        const id = selectedKey.slice(2);
        return broadcasts.find(b => String(b.id) === id)
            || groups.find(g => String(g.id) === id)
            || threads.find(t => String(t.id) === id)
            || null;
    }, [selectedKey, threads, broadcasts, groups]);

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
            loadConversations({ silent: true });
            if (selected?.id) loadMessages(selected.id, { silent: true });
        };
        const timer = setInterval(tick, POLL_MS);
        document.addEventListener('visibilitychange', tick);
        // The ping carries a conversation id and nothing else. The open thread
        // refetches only when the id matches; the list always refetches,
        // because a message in any thread changes its row's unread count.
        const stopRealtime = subscribeChatEvents((conversationId) => {
            if (document.hidden) return;
            loadConversations({ silent: true });
            if (selected?.id && String(selected.id) === String(conversationId)) {
                loadMessages(selected.id, { silent: true });
            }
        });
        return () => {
            clearInterval(timer);
            stopRealtime();
            document.removeEventListener('visibilitychange', tick);
        };
    }, [selected?.id, loadConversations, loadMessages]);

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

    const deliver = useCallback(async (item) => {
        const res = await sendChatMessage({
            conversationId: item.conversationId,
            kind: item.kind,
            body: item.body,
        });
        return res?.conversation_id ?? item.conversationId;
    }, []);

    const settle = useCallback(async (item) => {
        try {
            const newId = await deliver(item);
            if (!item.conversationId && newId) setSelectedKey(`i:${newId}`);
            await loadMessages(newId, { silent: true });
            await loadConversations({ silent: true });
        } catch (err) {
            // The bubble stays on screen marked "Not sent" rather than vanishing
            // with an alert, so the text the student wrote is never lost.
            updateOutbox(prev => prev.map(m => m.id === item.id
                ? { ...m, status: 'failed', error: err?.message || 'Could not send.' }
                : m));
        }
    }, [deliver, loadMessages, loadConversations]);

    const handleSend = async (e) => {
        e.preventDefault();
        const text = reply.trim();
        const isBroadcast = Boolean(selected && !selected.kind);
        if (!text || !selected || busy || isBroadcast
            || selected.available === false || selected.can_post === false) return;

        const item = {
            id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            body: text,
            sender_role: 'student',
            // Stamped locally so an unsent message shows a time and files under
            // the right day; the server's timestamp replaces it on confirm.
            created_at: new Date().toISOString(),
            conversationId: selected.id ?? null,
            kind: selected.id ? null : selected.kind,
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

    // The roster belongs to the team thread only. The coordinator, mentor and
    // panel threads reach one person each, so listing teammates under them
    // would misstate who is reading.
    const isTeamThread = selected?.kind === 'team';

    useEffect(() => {
        let cancelled = false;
        getTeamMembers()
            .then(rows => {
                if (cancelled) return;
                const list = Array.isArray(rows) ? rows : [];
                // The endpoint spells it roll_number; the rest of the chat code
                // (and the commit attributor) expects `roll`.
                setTeamMembers(list.map(m => ({ ...m, roll: m.roll_number || m.roll || '' })));
            })
            .catch(() => { if (!cancelled) setTeamMembers([]); });
        return () => { cancelled = true; };
    }, []);

    // Leaving the team thread drops the open card and its stats.
    useEffect(() => { setOpenMember(null); setAnalysis(null); }, [isTeamThread]);

    // Repository analysis, fetched only when a roster chip is actually clicked.
    // /team/github queues a fresh analysis run when the stored one is stale, so
    // it must not fire merely because a thread was opened.
    const loadAnalysis = useCallback(async () => {
        setAnalysisLoading(true);
        try {
            setAnalysis(await getTeamGithub());
        } catch {
            setAnalysis(null);
        } finally {
            setAnalysisLoading(false);
        }
    }, []);

    const roster = isTeamThread ? teamMembers : [];

    const commitStats = useMemo(
        // The student endpoint returns the analyser payload under
        // `analysisResults`; extractContributors reads the contributor array
        // out of whichever schema version it holds.
        () => attributeCommits(extractContributors(analysis?.analysisResults), roster),
        [analysis, roster],
    );

    const memberKey = (m) => String(m?.id ?? m?.roll ?? m?.name ?? '');
    const activeMember = openMember
        ? roster.find(m => memberKey(m) === openMember) || null
        : null;
    const activeStat = (openMember && commitStats.byMember.get(openMember))
        || { commits: 0, percentage: 0, identities: [] };

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

    // @-mention autocomplete. Triggers on a trailing "@word" so it only fires
    // while the caret is still inside the token being typed.
    const mentionToken = useMemo(() => {
        const m = reply.match(/@([\p{L}\p{N}._-]*)$/u);
        return m ? m[1] : null;
    }, [reply]);

    const mentionMatches = useMemo(() => {
        if (mentionToken === null || roster.length === 0) return [];
        const needle = mentionToken.toLowerCase();
        return roster.filter(m =>
            !needle ||
            String(m.name || '').toLowerCase().includes(needle) ||
            String(m.roll || '').toLowerCase().includes(needle));
    }, [mentionToken, roster]);

    useEffect(() => { setMentionIndex(0); }, [mentionToken]);

    const insertMention = (member) => {
        const name = String(member.name || member.roll || '').trim();
        // Replace only the trailing @token, leaving the rest of the draft alone.
        setReply(prev => prev.replace(/@([\p{L}\p{N}._-]*)$/u, `@${name} `));
    };

    const handleReplyKeyDown = (e) => {
        if (mentionMatches.length === 0) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setMentionIndex(i => (i + 1) % mentionMatches.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setMentionIndex(i => (i - 1 + mentionMatches.length) % mentionMatches.length);
        } else if (e.key === 'Enter' || e.key === 'Tab') {
            // Enter picks the highlighted entry instead of submitting the form.
            e.preventDefault();
            insertMention(mentionMatches[mentionIndex]);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            setReply(prev => `${prev} `);
        }
    };

    const KIND_ICON ={ coordinator: UserCircle, mentor: GraduationCap, panel: ClipboardCheck, team: Users };

    const ThreadRow = ({ t }) => {
        const Icon = KIND_ICON[t.kind] || MessageSquare;
        const key = t.id ? `i:${t.id}` : `k:${t.kind}`;
        const active = selectedKey === key || (t.id && selectedKey === `i:${t.id}`);
        // A thread with no row yet cannot have unread messages.
        const unread = t.id ? Number(unreadByConv[String(t.id)]) || 0 : 0;
        return (
            // Clicking the open row closes it. The open row collapses to its
            // identifier plus the hint, so the list always shows which thread
            // is on screen and how to dismiss it. min-height matches an
            // expanded row so collapsing never shifts the list.
            <button type="button" onClick={() => setSelectedKey(active ? null : key)}
                className={`w-full text-left px-4 min-h-[4rem] flex items-center gap-3 transition-colors ${active
                    ? 'bg-indigo-50 dark:bg-indigo-500/10'
                    : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'} ${t.available === false ? 'opacity-60' : ''}`}>
                {active ? (
                    <span className="w-full flex items-center gap-2.5">
                        <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-md text-[10px] font-black tracking-wider truncate max-w-[10rem]">
                            {t.subject}
                        </span>
                        <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Click to close</span>
                        <X className="w-3.5 h-3.5 text-indigo-500 ml-auto shrink-0" />
                    </span>
                ) : (
                    <>
                        <Icon className="w-4 h-4 shrink-0 text-slate-400" />
                        <span className="min-w-0 flex-1">
                            <span className="block font-bold text-sm text-slate-800 dark:text-white truncate">{t.subject}</span>
                            <span className="block text-[11px] font-medium text-slate-400 truncate">
                                {t.note || (t.id ? 'Open' : 'No messages yet')}
                            </span>
                        </span>
                        {unread > 0 && (
                            <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-full text-[10px] font-black tabular-nums">
                                {unread > 99 ? '99+' : unread}
                            </span>
                        )}
                    </>
                )}
            </button>
        );
    };

    return (
        <div className="space-y-6">
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-900 rounded-3xl p-8 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden border border-indigo-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10">
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Procksi Chat</h1>
                    <p className="text-indigo-100/90 text-sm md:text-base max-w-lg font-medium">
                        Your coordinator, mentor, evaluation panel and team - all in one place.
                    </p>
                </div>
            </motion.div>

            {error && (
                <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 rounded-3xl p-5 flex items-start justify-between gap-4">
                    <div>
                        <p className="font-black text-sm text-rose-900 dark:text-rose-200">Could not load Procksi Chat</p>
                        <p className="text-xs font-medium text-rose-800/80 dark:text-rose-200/70 mt-1">{error}</p>
                    </div>
                    <button onClick={() => { setLoading(true); loadConversations(); }}
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
                    className="absolute top-3 right-3 z-40 p-2 rounded-xl bg-white/80 dark:bg-slate-800/80 backdrop-blur border border-slate-200/70 dark:border-slate-700/70 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-300 transition-colors shadow-sm">
                    {maximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                {/* Conversation list */}
                <motion.div layout transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }}
                    className="flex flex-col min-h-0 border-b lg:border-b-0 lg:border-r border-slate-100 dark:border-slate-700/50">
                    <div className="h-16 shrink-0 px-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center">
                        <h2 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest">Messages</h2>
                    </div>

                    {/* Section filter. Recent shows every section at once. */}
                    <div className="h-14 shrink-0 px-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center gap-1.5 overflow-x-auto">
                        <button onClick={() => setAudience(null)}
                            className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === null
                                ? 'bg-indigo-600 text-white'
                                : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                            Recent
                        </button>
                        {SECTIONS.map(sec => (
                            <button key={sec.key} onClick={() => setAudience(audience === sec.key ? null : sec.key)}
                                className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === sec.key
                                    ? 'bg-indigo-600 text-white'
                                    : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                                {sec.label}
                            </button>
                        ))}
                    </div>

                    <div className="divide-y divide-slate-100 dark:divide-slate-700/50 overflow-y-auto flex-1 min-h-0 max-h-[20rem] lg:max-h-none">
                        {loading && <p className="p-8 text-center text-sm font-medium text-slate-500">Loading…</p>}

                        {!loading && threads.length === 0 && broadcasts.length === 0 && groups.length === 0 && (
                            <p className="p-8 text-center text-sm font-medium text-slate-500">
                                You are not on a team yet, so there are no conversations.
                            </p>
                        )}

                        {(audience === null || audience === 'thread') && threads.length > 0 && (
                            <>
                                <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 border-b border-slate-200/70 dark:border-slate-700/50 flex items-center gap-1.5">
                                    <Users className="w-3 h-3" /> My conversations
                                </p>
                                {threads.map(t => <ThreadRow key={t.kind} t={t} />)}
                            </>
                        )}

                        {(audience === null || audience === 'group') && groups.length > 0 && (
                            <>
                                <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 border-b border-slate-200/70 dark:border-slate-700/50 flex items-center gap-1.5">
                                    <MessagesSquare className="w-3 h-3" /> Groups
                                </p>
                                {groups.map(g => {
                                    const open = selectedKey === `i:${g.id}`;
                                    const unread = Number(unreadByConv[String(g.id)]) || 0;
                                    return (
                                        <button key={g.id} type="button" onClick={() => setSelectedKey(open ? null : `i:${g.id}`)}
                                            className={`w-full text-left px-4 min-h-[4rem] flex flex-col justify-center transition-colors ${open
                                                ? 'bg-indigo-50 dark:bg-indigo-500/10'
                                                : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                            {open ? (
                                                <span className="w-full flex items-center gap-2.5">
                                                    <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-md text-[10px] font-black tracking-wider truncate max-w-[10rem]">
                                                        {g.subject}
                                                    </span>
                                                    <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Click to close</span>
                                                    <X className="w-3.5 h-3.5 text-indigo-500 ml-auto shrink-0" />
                                                </span>
                                            ) : (
                                                <>
                                                    <span className="flex items-center gap-2">
                                                        <span className="font-bold text-sm text-slate-800 dark:text-white truncate flex-1">{g.subject}</span>
                                                        {unread > 0 && (
                                                            <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-full text-[10px] font-black tabular-nums">
                                                                {unread > 99 ? '99+' : unread}
                                                            </span>
                                                        )}
                                                    </span>
                                                    <span className="text-[11px] font-medium text-slate-400 mt-0.5">
                                                        {GROUP_BLURB[g.group_key] || 'Group thread'}
                                                    </span>
                                                </>
                                            )}
                                        </button>
                                    );
                                })}
                            </>
                        )}

                        {(audience === null || audience === 'broadcast') && broadcasts.length > 0 && (
                            <>
                                <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 border-b border-slate-200/70 dark:border-slate-700/50 flex items-center gap-1.5">
                                    <Megaphone className="w-3 h-3" /> Announcements
                                </p>
                                {broadcasts.map(b => {
                                    const open = selectedKey === `i:${b.id}`;
                                    const unread = Number(unreadByConv[String(b.id)]) || 0;
                                    return (
                                    <button key={b.id} type="button" onClick={() => setSelectedKey(open ? null : `i:${b.id}`)}
                                        className={`w-full text-left px-4 min-h-[4rem] flex flex-col justify-center transition-colors ${open
                                            ? 'bg-indigo-50 dark:bg-indigo-500/10'
                                            : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                        {open ? (
                                            <span className="w-full flex items-center gap-2.5">
                                                <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-md text-[10px] font-black tracking-wider truncate max-w-[10rem]">
                                                    {b.subject}
                                                </span>
                                                <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400">Click to close</span>
                                                <X className="w-3.5 h-3.5 text-indigo-500 ml-auto shrink-0" />
                                            </span>
                                        ) : (
                                            <>
                                                <span className="flex items-center gap-2">
                                                    <span className="font-bold text-sm text-slate-800 dark:text-white truncate flex-1">{b.subject}</span>
                                                    {unread > 0 && (
                                                        <span className="shrink-0 px-2 py-0.5 bg-indigo-600 text-white rounded-full text-[10px] font-black tabular-nums">
                                                            {unread > 99 ? '99+' : unread}
                                                        </span>
                                                    )}
                                                </span>
                                                <span className="text-[11px] font-medium text-slate-400 mt-0.5">Announcement</span>
                                            </>
                                        )}
                                    </button>
                                    );
                                })}
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
                                <p className="text-[10px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400 mt-0.5">
                                    {!selected.kind ? 'Announcement - read only' : selected.kind}
                                </p>
                            </div>

                            {/* Team roster — who this chat actually reaches */}
                            {roster.length > 0 && (
                                <div ref={rosterRef} className="h-14 shrink-0 px-4 flex items-center gap-1.5 overflow-x-auto bg-slate-50/50 dark:bg-slate-900/20">
                                    {roster.map(m => {
                                        const key = memberKey(m);
                                        const isOpen = openMember === key;
                                        return (
                                            <button key={key} type="button"
                                                onClick={(e) => (isOpen ? setOpenMember(null) : openMemberCard(key, e.currentTarget))}
                                                className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-bold border transition-colors bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 ${isOpen ? 'ring-2 ring-indigo-400' : ''}`}>
                                                {m.name || m.roll}
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
                                    <p className="font-black text-sm text-slate-800 dark:text-white truncate">
                                        {activeMember.name || activeMember.roll}
                                    </p>
                                    <p className="text-[10px] font-mono text-slate-400 mb-3">
                                        {[activeMember.roll, activeMember.branch].filter(Boolean).join(' · ')}
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
                                                    <p className="text-lg font-black text-slate-800 dark:text-white">{activeStat.commits}</p>
                                                </div>
                                                <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-2.5">
                                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Share</p>
                                                    <p className="text-lg font-black text-slate-800 dark:text-white">{activeStat.percentage}%</p>
                                                </div>
                                            </div>
                                            <p className="text-[10px] font-medium text-slate-400 mt-2.5">
                                                {commitStats.totalCommits} commits in the repository
                                            </p>
                                            {activeStat.identities.length > 0 && (
                                                <p className="text-[10px] font-medium text-slate-400 mt-1 truncate"
                                                    title={activeStat.identities.join(', ')}>
                                                    Matched: {activeStat.identities.join(', ')}
                                                </p>
                                            )}
                                            {activeStat.commits === 0 && (
                                                <p className="text-[10px] font-medium text-amber-600 dark:text-amber-400 mt-1.5">
                                                    No commits matched this member. Commits made under a different
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
                                                const own = m.sender_role === 'student';

                                                // ProcksiBot's reports are stored messages like any
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
                                                    className={`flex ${m.sender_role === 'student' ? 'justify-end' : 'justify-start'}`}>
                                                    <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 transition-opacity ${m.sender_role === 'student'
                                                        ? 'bg-indigo-600 text-white'
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
                            </div>

                            {!selected.kind ? (
                                <p className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 text-xs font-medium text-slate-400 text-center">
                                    Announcements are read only. Contact your coordinator directly to respond.
                                </p>
                            ) : selected.can_post === false ? (
                                // All Teams is addressed by team, not by person: one voice
                                // per team, and it is the leader's. The server enforces this
                                // too — this only avoids typing a message that would bounce.
                                <p className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 text-xs font-medium text-slate-400 text-center">
                                    Only your team leader can post in {selected.subject}. You can read everything here.
                                </p>
                            ) : selected.available === false ? (
                                <p className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 text-xs font-medium text-slate-400 text-center">
                                    {selected.note}
                                </p>
                            ) : (
                                <form onSubmit={handleSend} className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2 relative">
                                    <AnimatePresence>
                                    {/* @-mention list — teammates only */}
                                    {mentionMatches.length > 0 && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 8, scale: 0.97 }}
                                            animate={{ opacity: 1, y: 0, scale: 1 }}
                                            exit={{ opacity: 0, y: 8, scale: 0.97 }}
                                            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                                            style={{ transformOrigin: 'bottom left' }}
                                            className="absolute bottom-full left-4 right-16 mb-2 bg-white/95 dark:bg-slate-800/95 backdrop-blur-xl border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl overflow-hidden p-1.5 max-h-48 overflow-y-auto z-20">
                                            <p className="px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                                                Tag a teammate
                                            </p>
                                            {mentionMatches.map((m, i) => (
                                                <button key={memberKey(m)} type="button"
                                                    onMouseDown={e => { e.preventDefault(); insertMention(m); }}
                                                    onMouseEnter={() => setMentionIndex(i)}
                                                    className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-xl text-left transition-colors ${i === mentionIndex
                                                        ? 'bg-indigo-50 dark:bg-indigo-500/15'
                                                        : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                                    <span className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center text-[10px] font-black shrink-0">
                                                        {String(m.name || m.roll || '?').charAt(0).toUpperCase()}
                                                    </span>
                                                    <span className="min-w-0 flex-1">
                                                        <span className="block text-sm font-bold text-slate-800 dark:text-white truncate">{m.name || m.roll}</span>
                                                        {m.roll && <span className="block text-[10px] font-mono text-slate-400 truncate">{m.roll}</span>}
                                                    </span>
                                                </button>
                                            ))}
                                        </motion.div>
                                    )}
                                    </AnimatePresence>
                                    <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={handleReplyKeyDown}
                                        placeholder="Write a reply..."
                                        className="flex-1 px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" />
                                    <button type="submit" disabled={busy || !reply.trim()}
                                        className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl transition-colors">
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
                                    : placeholder === 'select' ? 'Select a message'
                                    : 'No messages yet'}
                            </p>
                        </div>
                    )}
                </motion.div>
            </motion.div>
        </div>
    );
};

export default ProcksiChatView;
