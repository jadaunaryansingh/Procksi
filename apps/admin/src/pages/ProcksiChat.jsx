import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Plus, MessageSquare, X, Database, RefreshCcw, Search, Maximize2, Minimize2 , Clock, Check, CheckCheck, Loader2, Users, Power } from 'lucide-react';
import { useProcksiChatToggles } from '../hooks/useProcksiChatToggles';
import ProcksiChatToggleModal from '../components/ProcksiChatToggleModal';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { getStoredSession, apiFetchTable } from '../lib/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { CHANNELS, channelById } from '../lib/procksiChatChannels';
import { summariseThreads } from '../lib/procksiChatThreads';
import {
    fetchConversations, fetchGroupConversations, fetchMessages, sendMessage, sendDirectMessage,
    markThreadRead, isMissingTablesError, fetchTeamAnalysis, runChatCommand,
} from '../services/procksiChatApi';
import { attributeCommits, extractContributors } from '../lib/memberCommits';
import ChatReportCard, { ChatReportMessage } from '../components/ChatReportCard';
import { refreshChatUnread } from '../hooks/useChatUnread';
import { subscribeChatEvents } from '../lib/chatRealtime';
import { formatTime, groupByDay, buildPeopleIndex, senderName, deliveryState, DELIVERY, mergeTimeline } from '../lib/messageMeta';

// Audience chips inside the conversations pane. `role` is matched against the
// channel's roles (see procksiChatChannels.js), so "Teams" covers any thread that
// reaches students and "Panel" any thread that reaches panel members.
const AUDIENCE_TABS = [
    { id: 'mentor', label: 'Mentor', role: 'mentor' },
    { id: 'team', label: 'Teams', role: 'student' },
    { id: 'panel', label: 'Panel', role: 'panel' },
    // Groups is the odd one out: the three above browse directories of people
    // you could start a conversation with, while this lists conversations that
    // already exist — the ones addressed to several named recipients at once.
    { id: 'group', label: 'Groups', role: null },
];

// Fallback refresh. Realtime pings drive the live updates; this catches the
// case where the websocket never connected or has dropped.
const POLL_MS = 20000;

// Slash commands. Picking one runs it: the server does the work and returns a
// result the thread renders. These are actions, not message templates.
const SLASH_COMMANDS = [
    { id: 'report', label: '/report', hint: 'Team analysis for the open thread' },
];

const ProcksiChat = () => {
    const viewerId = getStoredSession()?.user?.email || '';
    const { filters } = useGlobalFilters();
    const selectedSemesterId = filters.semesterId;

    const { data: mentors } = useSupabaseTableState('mentors', [], { orderBy: 'id' });
    const { data: panels } = useSupabaseTableState('panels', [], { orderBy: 'id' });

    const [conversations, setConversations] = useState([]);
    const [messages, setMessages] = useState([]);
    // Recipient counts for students/teams are fetched directly with
    // apiFetchTable (below) rather than useSupabaseTableState, because
    // students and teams_validation are both in filterableTables — the
    // global search/year/branch filters would otherwise shrink these counts
    // to whatever the admin currently has typed into the search box, even
    // though the real broadcast fan-out is role-wide.
    const [studentRows, setStudentRows] = useState([]);
    const [teamRows, setTeamRows] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [togglesOpen, setTogglesOpen] = useState(false);
    const procksiChatToggles = useProcksiChatToggles();
    const [reply, setReply] = useState('');
    const [busy, setBusy] = useState(false);
    const [loadError, setLoadError] = useState(null);
    const [audience, setAudience] = useState(null);
    const [query, setQuery] = useState('');
    const [recipient, setRecipient] = useState(null);
    const [mentionIndex, setMentionIndex] = useState(0);
    const [openMember, setOpenMember] = useState(null);
    // Viewport-free coordinates for the open member card, measured against the
    // thread column at click time. The card cannot live inside the roster row:
    // that row scrolls sideways, and `overflow-x: auto` forces `overflow-y` to
    // `auto` as well, so the card was being clipped to the row's 3.5rem height.
    const [memberPos, setMemberPos] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [analysisLoading, setAnalysisLoading] = useState(false);
    const [maximized, setMaximized] = useState(false);
    // True until the first fetch settles. The admin view loads every message at
    // once and filters per thread client-side, so after that a thread switch is
    // instant and needs no spinner.
    const [messagesLoading, setMessagesLoading] = useState(true);
    // Messages typed here but not yet confirmed by the server. They render
    // immediately so sending feels instant, and are dropped once the same
    // message comes back from the server.
    const [outbox, setOutbox] = useState([]);

    const rosterRef = useRef(null);
    const composerBarRef = useRef(null);
    const threadColRef = useRef(null);
    const memberCardRef = useRef(null);
    const panelRef = useRef(null);

    const scrollRef = useRef(null);
    // Only auto-scroll when the reader is already at the bottom, so a refresh
    // never yanks them away from something they scrolled up to read.
    const atBottomRef = useRef(true);
    // Maps a confirmed server message id back to the temporary id its optimistic
    // bubble used, so the bubble settles in place instead of remounting.
    const keyMapRef = useRef(new Map());
    // Mirrors `outbox` so reconciliation can read it without a state updater.
    const outboxRef = useRef([]);
    // The only writer for the outbox. Keeping the ref in lockstep with state
    // means reconciliation always sees the current list, and the updater it
    // takes is run exactly once — never twice, as React may do to a setState
    // updater.
    const updateOutbox = (updater) => {
        const next = updater(outboxRef.current);
        outboxRef.current = next;
        setOutbox(next);
    };

    // Tap/click anywhere outside a popup dismisses it. Escape does the same,
    // so the popups behave the way every other menu in the portal does.
    useEffect(() => {
        const onPointerDown = (e) => {
            const inComposer = composerBarRef.current?.contains(e.target);
            // The card is rendered outside the roster row (see memberPos), so it
            // has to be excluded by name — otherwise clicking the card's own text
            // would count as clicking away from it.
            const inCard = memberCardRef.current?.contains(e.target);
            // Clicking into the message box must NOT close an open member card —
            // reading someone's stats while writing to them is the normal flow.
            if (rosterRef.current && !rosterRef.current.contains(e.target) && !inCard && !inComposer) {
                setOpenMember(null);
            }
            if (composerBarRef.current && !inComposer) {
                // The @/slash menus are driven by the draft text, so closing
                // them means ending the token rather than hiding a flag.
                setReply(prev => (/(^\/[a-z]*$)|(@[\p{L}\p{N}._-]*$)/iu.test(prev) ? `${prev} ` : prev));
            }
        };
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            // Escape closes the member card first; a second press un-maximizes.
            setOpenMember(prev => { if (prev) return null; setMaximized(false); return prev; });
        };

        document.addEventListener('pointerdown', onPointerDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('pointerdown', onPointerDown);
            document.removeEventListener('keydown', onKey);
        };
    }, []);

    // Clicking anywhere off the card restores it. The dimmed backdrop has its
    // own onClick; this covers every other surface that paints above it. The
    useEffect(() => {
        if (!maximized) return undefined;
        const onPointerDown = (e) => {
            if (!panelRef.current?.contains(e.target)) setMaximized(false);
        };
        document.addEventListener('pointerdown', onPointerDown);
        return () => document.removeEventListener('pointerdown', onPointerDown);
    }, [maximized]);

    // A conversation opened from Recent must present exactly like one opened
    // from a directory — same header, roster and member stats. Direct threads
    // carry recipient_type/recipient_id, so rebuild that context from the row;
    // broadcasts have neither and stay broadcasts.
    const recipientFromConversation = (conversation) => {
        if (!conversation?.recipient_type || !conversation?.recipient_id) return null;
        const team = conversation.recipient_type === 'team'
            ? teamRows.find(t => String(t.id) === String(conversation.recipient_id))
            : null;
        return {
            type: conversation.recipient_type,
            id: conversation.recipient_id,
            label: conversation.recipient_label || conversation.subject,
            num: team?.team_number != null ? String(team.team_number) : null,
        };
    };

    // Drops any optimistic bubble the server has now echoed back, recording the
    // temporary id against the confirmed one so the bubble keeps its React key
    // through the handover and settles in place instead of remounting.
    // Computed against outboxRef rather than inside a setOutbox updater. An
    // updater must be pure: React may invoke it more than once, and on the
    // second run keyMapRef already held the mapping, so the `has(r.id)` guard
    // skipped the match and the item was never removed — leaving a confirmed
    // message and its optimistic bubble on screen under the SAME React key.
    const reconcileOutbox = (rows) => {
        const prev = outboxRef.current;
        if (!prev.length) return;

        const remaining = [];
        for (const p of prev) {
            let matched = false;
            for (let i = rows.length - 1; i >= 0; i -= 1) {
                const r = rows[i];
                if (keyMapRef.current.has(r.id)) continue;
                // A message sent into a thread that did not exist yet has no
                // conversation id to match on, so only check it when known.
                const sameThread = p.conversationId == null || r.conversation_id === p.conversationId;
                if (sameThread && r.sender_role === p.sender_role
                    && String(r.body || '').trim() === p.body) {
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
    };

    // `light` skips the students/teams lookups, which the 5s poll does not need.
    // `silent` keeps whatever is on screen when a background refresh fails, so a
    // momentary blip never blanks a working page.
    const reload = async ({ silent = false, light = false } = {}) => {
        try {
            const [c, g, m, s, t] = await Promise.all([
                fetchConversations(),
                // The standing groups carry no semester_id, so the semester
                // filter on fetchConversations would drop them.
                fetchGroupConversations(),
                fetchMessages(),
                // name/email are needed to show who wrote each message; a
                // student signs with their address, not their roll.
                light ? Promise.resolve(null) : apiFetchTable('students', { select: 'id,name,email' }),
                light ? Promise.resolve(null)
                    : apiFetchTable('teams_validation', { select: 'id,title,leader,team_number,validationStatus,members' }),
            ]);
            // One list from here on: a group is a conversation like any other
            // once it is loaded, and `selected` looks it up in the same place.
            setConversations([...(c || []), ...(g || [])]);
            setMessages(m);
            reconcileOutbox(m);
            if (s) setStudentRows(s);
            if (t) setTeamRows(t);
            setLoadError(null);
            return m;
        } catch (err) {
            if (silent) return null;
            setConversations([]);
            setMessages([]);
            setStudentRows([]);
            setTeamRows([]);
            setLoadError(err);
            return null;
        } finally {
            // Only the first load spins. Every later fetch is a background poll
            // over messages already on screen, and a spinner there would blink
            // every five seconds.
            setMessagesLoading(false);
        }
    };

    // filters.semesterId participates so switching the top-nav semester
    // filter refetches conversations/messages for the newly selected
    // semester instead of leaving the previous semester's rows on screen
    // (see useSupabaseTableState.js:69 for the same reasoning).
    useEffect(() => { reload(); }, [selectedSemesterId]);

    // Auto-refresh. Realtime is the live path — a trigger pings `chat_events`
    // on every insert and this reloads at once. The interval behind it is only
    // a fallback for a websocket that never connected or has dropped.
    //
    // Both call through a ref so they always run the current render's reload
    // without being torn down and rebuilt on every state change.
    const pollRef = useRef(null);
    useEffect(() => { pollRef.current = () => reload({ silent: true, light: true }); });
    useEffect(() => {
        const tick = () => { if (!document.hidden) pollRef.current?.(); };
        const timer = setInterval(tick, POLL_MS);
        document.addEventListener('visibilitychange', tick);
        // The admin holds every conversation in memory and filters per thread
        // client-side, so any ping is worth a reload no matter which
        // conversation it names.
        const stopRealtime = subscribeChatEvents(tick);
        return () => {
            clearInterval(timer);
            stopRealtime();
            document.removeEventListener('visibilitychange', tick);
        };
    }, []);

    // Keyed on `messages`/`outbox` rather than the derived thread array, which
    // is rebuilt on every render and would fire this on every render.
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

    // No channel filter here any more — the audience chips below are the only
    // list filter, so every conversation is reachable from one screen.
    const allThreads = useMemo(
        () => summariseThreads(conversations, messages, viewerId),
        [conversations, messages, viewerId],
    );

    // One search box serves whichever list the active chip is showing.
    const q = query.trim().toLowerCase();

    const threads = useMemo(() => {
        if (!q) return allThreads;
        return allThreads.filter(t =>
            String(t.subject || '').toLowerCase().includes(q) ||
            String(t.preview || '').toLowerCase().includes(q));
    }, [allThreads, q]);

    // Group threads are conversations, not directory entries, so they are
    // filtered out of Recent — otherwise every group would appear under two
    // chips at once.
    const groupThreads = useMemo(
        () => threads.filter(t => t.kind === 'group'),
        [threads],
    );

    // How far each standing group reaches, counted from the same directories the
    // other chips browse. `everyone` deduplicates by email: a person who is both
    // a mentor and a panel is one participant, not two.
    const groupReach = useMemo(() => {
        const emailOf = (r) => String(r?.email || r?.id || '').trim().toLowerCase();
        const mentorCount = (mentors || []).length;
        const panelCount = (panels || []).length;
        const teamCount = (teamRows || []).length;
        const studentCount = (studentRows || []).length;
        const staff = new Set([
            ...(mentors || []).map(emailOf),
            ...(panels || []).map(emailOf),
        ].filter(Boolean));

        const n = (count, noun) => `${count} ${noun}${count === 1 ? '' : 's'}`;
        return {
            mentors: n(mentorCount, 'mentor'),
            panels: n(panelCount, 'panel'),
            teams: n(teamCount, 'team'),
            everyone: `${n(studentCount, 'student')}, ${n(staff.size, 'staff member')}`,
        };
    }, [mentors, panels, teamRows, studentRows]);
    const recentThreads = useMemo(
        () => threads.filter(t => t.kind !== 'group'),
        [threads],
    );

    // ALL shows conversations; the other chips show the live directory of
    // recipients pulled straight from the database, so the admin can see who
    // exists before starting a conversation.
    const directory = useMemo(() => {
        const mentorItems = () => (mentors || []).map(m => ({
            key: `m-${m.id}`, type: 'mentor', rid: m.id,
            primary: m.name || m.email || m.id,
            secondary: m.email || m.domain || '',
            badge: null, status: null,
            search: [m.name, m.email, m.domain, m.id].filter(Boolean).join(' ').toLowerCase(),
        }));
        const panelItems = () => (panels || []).map(p => ({
            key: `p-${p.id}`, type: 'panel', rid: p.id,
            primary: p.name || p.id,
            secondary: p.description || '',
            badge: null, status: null,
            search: [p.name, p.description, p.id].filter(Boolean).join(' ').toLowerCase(),
        }));
        // Every team is browsable, including Pending ones — an admin often
        // needs to message a team precisely because its validation is stuck.
        // The broadcast recipient count still counts validated teams only.
        const teamItems = () => teamRows.map(t => {
            const num = t.team_number ?? null;
            return {
                key: `t-${t.id}`, type: 'team', rid: t.id,
                primary: t.title || (num != null ? `Team ${num}` : t.id),
                secondary: t.leader ? `Leader: ${t.leader}` : '',
                badge: num != null ? `T${num}` : null,
                status: t.validationStatus && t.validationStatus !== 'Valid' ? t.validationStatus : null,
                // Members are searchable too — an admin often knows the student's
                // name or roll number but not which team they are on.
                search: [
                    t.title, t.leader, num,
                    num != null ? `t${num}` : null,
                    num != null ? `team ${num}` : null,
                    t.validationStatus,
                    ...(Array.isArray(t.members)
                        ? t.members.flatMap(mem => [mem?.name, mem?.roll, mem?.branch])
                        : []),
                ]
                    .filter(v => v !== null && v !== undefined && v !== '')
                    .join(' ').toLowerCase(),
            };
        });

        // Recent shows conversations only — the directories live behind their
        // own chips, so the two never mix in one list.
        if (audience === null) return null;
        if (audience === 'mentor') return [{ label: 'Mentors', items: mentorItems() }];
        if (audience === 'team') return [{ label: 'Teams', items: teamItems() }];
        if (audience === 'panel') return [{ label: 'Panels', items: panelItems() }];
        // Groups lists conversations, handled separately below.
        return null;
    }, [audience, mentors, teamRows, panels]);


    // Search applies inside each section; empty sections are dropped so a
    // query never leaves a bare header behind.
    const visibleDirectory = useMemo(() => {
        if (!directory) return null;
        if (!q) return directory;
        // A short bare number ("12") means a team number, so it matches the
        // badge exactly rather than any stray digits in a title. A long one is
        // a roll number, so it falls through to the full-text search where
        // member rolls live. Team numbers here are at most 3 digits; rolls are 10.
        const isTeamNumberQuery = /^\d{1,3}$/.test(q);
        const match = (d) => (isTeamNumberQuery && d.badge
            ? d.badge.toLowerCase() === `t${q}` || String(d.badge).replace(/\D/g, '') === q
            : (d.search || '').includes(q));
        return directory
            .map(g => ({ ...g, items: g.items.filter(match) }))
            .filter(g => g.items.length > 0);
    }, [directory, q]);

    const directoryCount = useMemo(
        () => (visibleDirectory || []).reduce((n, g) => n + g.items.length, 0),
        [visibleDirectory],
    );

    // Switching chips changes which list you are browsing, so any chat opened
    // from the previous list is no longer in context — close it and fall back
    // to the placeholder rather than leaving an unrelated thread on screen.
    useEffect(() => {
        setRecipient(null);
        setSelectedId(null);
        setReply('');
    }, [audience]);

    // read_by is only ever written at insert time, so a thread's unread
    // badge can never clear on its own. Mark it read as soon as the admin
    // opens it, then refresh so the badge reflects that.
    useEffect(() => {
        if (!selectedId) return;
        const threadMessages = messages.filter(m => m.conversation_id === selectedId);
        if (threadMessages.length === 0) return;
        (async () => {
            const wasMarked = await markThreadRead({ messages: threadMessages, viewerId });
            if (wasMarked) {
                await reload();
                // The sidebar keeps its own count on a slower poll, so without
                // this the badge stays up for seconds after the thread is read.
                refreshChatUnread();
            }
        })();
        // Intentionally depends only on selectedId: re-running this whenever
        // `messages` changes (which reload() itself causes) would loop.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedId]);

    // A direct chat reuses the existing 1:1 conversation for that recipient if
    // one exists; otherwise the pane opens empty and the row is created on the
    // first send (so browsing names never writes to the database).
    const directConversation = useMemo(() => {
        if (!recipient) return null;
        const byRecipient = conversations.find(c =>
            c.recipient_type === recipient.type &&
            String(c.recipient_id) === String(recipient.id));
        if (byRecipient) return byRecipient;
        // The same coordinator-to-team thread can be opened from the student
        // portal, which writes (team_id, kind) and leaves recipient_type and
        // recipient_id null. The unique index conversations_team_kind_idx makes
        // (team_id, kind) the real identity of a team thread, so matching only
        // on recipient_* misses that row — and the insert that follows then
        // collides with it and fails the send with a 500.
        if (recipient.type !== 'team') return null;
        return conversations.find(c =>
            c.kind === 'coordinator' && String(c.team_id) === String(recipient.id)) || null;
    }, [conversations, recipient]);

    // Members of the team currently open in the chat header. Leader first, so
    // the chip row reads the way the roster does elsewhere in the portal.
    const recipientMembers = useMemo(() => {
        if (recipient?.type !== 'team') return [];
        const team = teamRows.find(t => String(t.id) === String(recipient.id));
        const list = Array.isArray(team?.members) ? team.members : [];
        return [...list].sort((a, b) => (b.role === 'LEADER' ? 1 : 0) - (a.role === 'LEADER' ? 1 : 0));
    }, [recipient, teamRows]);

    // @-mention autocomplete. Triggers on a trailing "@word" so it only fires
    // while the caret is still inside the token being typed.
    const mentionToken = useMemo(() => {
        const m = reply.match(/@([\p{L}\p{N}._-]*)$/u);
        return m ? m[1] : null;
    }, [reply]);

    const mentionMatches = useMemo(() => {
        if (mentionToken === null || recipientMembers.length === 0) return [];
        const needle = mentionToken.toLowerCase();
        return recipientMembers.filter(m =>
            !needle ||
            String(m.name || '').toLowerCase().includes(needle) ||
            String(m.roll || '').toLowerCase().includes(needle));
    }, [mentionToken, recipientMembers]);

    useEffect(() => { setMentionIndex(0); }, [mentionToken]);

    const insertMention = (member) => {
        const name = String(member.name || member.roll || '').trim();
        // Replace only the trailing @token, leaving the rest of the draft alone.
        setReply(prev => prev.replace(/@([\p{L}\p{N}._-]*)$/u, `@${name} `));
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

    // Repository analysis for the open team, used for per-member commit stats.
    useEffect(() => {
        setOpenMember(null);
        if (recipient?.type !== 'team') { setAnalysis(null); return; }
        let cancelled = false;
        setAnalysisLoading(true);
        fetchTeamAnalysis(recipient.id)
            .then(row => { if (!cancelled) setAnalysis(row); })
            .catch(() => { if (!cancelled) setAnalysis(null); })
            .finally(() => { if (!cancelled) setAnalysisLoading(false); });
        return () => { cancelled = true; };
    }, [recipient]);

    const commitStats = useMemo(
        () => attributeCommits(extractContributors(analysis?.raw_report), recipientMembers),
        [analysis, recipientMembers],
    );

    const memberKey = (m) => String(m?.id ?? m?.roll ?? m?.name ?? '');
    const activeMember = openMember
        ? recipientMembers.find(m => memberKey(m) === openMember) || null
        : null;
    const activeStat = (openMember && commitStats.byMember.get(openMember))
        || { commits: 0, percentage: 0, identities: [] };

    // Anchors the card under its chip, in the thread column's coordinates, and
    // keeps it inside that column so a chip near the right edge doesn't push the
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
    };

    // The card is positioned once, so anything that moves the chip out from
    // under it closes it rather than letting it drift.
    useEffect(() => {
        if (!openMember) return undefined;
        const close = () => setOpenMember(null);
        const roster = rosterRef.current;
        roster?.addEventListener('scroll', close, { passive: true });
        window.addEventListener('resize', close);
        return () => {
            roster?.removeEventListener('scroll', close);
            window.removeEventListener('resize', close);
        };
    }, [openMember]);

    const activeConversationId = recipient ? (directConversation?.id ?? null) : selectedId;
    const selected = threads.find(t => t.id === selectedId) || null;

    // The /report affordance: the option picker, the "working" state, and any
    // failure. The report itself is not held here — ProcksiBot posts it into the
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
            const data = await runChatCommand({
                command: id, option,
                teamId: recipient?.type === 'team' ? recipient.id : null,
                conversationId,
            });
            if (data?.step === 'posted') {
                // The result is now a message. Clear the affordance and pull it in.
                setCommand(null);
                await pollRef.current?.();
                return;
            }
            setCommand({ loading: false, error: null, data });
        } catch (err) {
            setCommand({ loading: false, data: null,
                error: err?.response?.data?.detail || err?.message || 'That command could not be run.' });
        }
    }, [recipient, selected]);

    const thread = activeConversationId
        ? messages
            .filter(m => m.conversation_id === activeConversationId)
            .sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
        : [];

    const setupNeeded = loadError && isMissingTablesError(loadError);



    // Identifies which view an unsent message belongs to. A direct thread that
    // has no row yet has no conversation id, so it is keyed by its recipient.
    const threadKey = activeConversationId != null
        ? `c:${activeConversationId}`
        : (recipient ? `r:${recipient.type}:${recipient.id}` : null);

    const settle = async (item) => {
        try {
            if (item.recipient) {
                await sendDirectMessage({
                    recipientType: item.recipient.type, recipientId: item.recipient.id,
                    recipientLabel: item.recipient.label, existingConversationId: item.conversationId,
                    body: item.body, senderId: viewerId, semesterId: selectedSemesterId,
                });
            } else {
                await sendMessage({
                    conversationId: item.conversationId, channel: item.channel,
                    subject: item.subject, body: item.body, senderId: viewerId,
                });
            }
            // reconcileOutbox inside reload retires the optimistic bubble.
            await reload({ silent: true, light: true });
        } catch (err) {
            // The bubble stays on screen marked "Not sent" rather than vanishing
            // with an alert, so the text that was written is never lost.
            updateOutbox(prev => prev.map(m => m.id === item.id
                ? { ...m, status: 'failed', error: err.message } : m));
        }
    };

    const handleReply = async (e) => {
        e.preventDefault();
        const text = reply.trim();
        if (!text || busy || (!selected && !recipient)) return;

        const item = {
            id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            body: text,
            sender_role: 'admin',
            // Stamped locally so an unsent message shows a time and files under
            // the right day; the server's own timestamp replaces it on confirm.
            created_at: new Date().toISOString(),
            threadKey,
            conversationId: recipient ? (directConversation?.id ?? null) : selected.id,
            recipient: recipient || null,
            channel: recipient ? null : selected.channel,
            subject: recipient ? null : selected.subject,
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

    // Opening a different thread starts scrolled to the newest message.
    // Unsent bubbles are kept, not cleared: they are filtered by threadKey, so a
    // failed message stays waiting in the thread it was written for.
    useEffect(() => { atBottomRef.current = true; }, [threadKey]);

    // Confirmed messages first, then anything still in flight for THIS view.
    const timeline = mergeTimeline(
        thread,
        outbox.filter(o => o.threadKey === threadKey),
        keyMapRef.current,
    );

    // The open team's roster is indexed alongside the full student list: a
    // roster carries names for members whose student row the semester filter
    // may have excluded.
    const people = useMemo(
        () => buildPeopleIndex([...studentRows, ...recipientMembers]),
        [studentRows, recipientMembers],
    );
    const days = groupByDay(timeline);

    // One placeholder for the whole thread pane, rendered as an overlay on the
    // column rather than inside the message list. Centred on the column, its
    // position no longer depends on which chrome happens to be on screen — a
    // header, a roster strip and a composer each shifted the old in-flow
    // version, so the icon sat at a different height in every state.
    const placeholder = (!selected && !recipient) ? 'select'
        : messagesLoading ? 'loading'
        : timeline.length === 0 ? 'empty'
        : null;

    return (
        <div className="space-y-6">
            {/* Hero */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-sky-600 via-sky-700 to-indigo-900 rounded-3xl p-8 text-white shadow-xl shadow-sky-500/20 relative overflow-hidden border border-sky-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10">
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Procksi Chat</h1>
                    <p className="text-sky-100/90 text-sm md:text-base max-w-lg font-medium">
Conversations with mentors, teams and panels — all in one place.
                    </p>
                </div>
            </motion.div>

            {/* Setup notice — only for a project where the migration has not been applied */}
            {setupNeeded && (
                <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-3xl p-5 flex items-start gap-4">
                    <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center shrink-0">
                        <Database className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                    </div>
                    <div className="flex-1">
                        <p className="font-black text-sm text-amber-900 dark:text-amber-200">Conversation tables not created yet</p>
                        <p className="text-xs font-medium text-amber-800/80 dark:text-amber-200/70 mt-1 leading-relaxed">
                            The dashboard below is live, but has nothing to read. Apply
                            <code className="mx-1 px-1.5 py-0.5 bg-amber-100 dark:bg-amber-500/20 rounded font-mono text-[11px]">supabase/migrations/202608140001_delegate_conversations.sql</code>
                            to your Supabase project, then reload.
                        </p>
                    </div>
                    <button onClick={reload} title="Retry"
                        className="p-2 text-amber-600 hover:text-amber-800 dark:text-amber-400 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors shrink-0">
                        <RefreshCcw className="w-4 h-4" />
                    </button>
                </div>
            )}

            {loadError && !setupNeeded && (
                <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 rounded-3xl p-5">
                    <p className="font-black text-sm text-rose-900 dark:text-rose-200">Could not load conversations</p>
                    <p className="text-xs font-medium text-rose-800/80 dark:text-rose-200/70 mt-1">{String(loadError.message)}</p>
                </div>
            )}

            {/* One card, split internally: thread list | thread view */}
            {/* Both panes scroll internally so the reply box stays pinned to the
                bottom regardless of list length. Maximized lifts the same card
                out to fill the screen — no duplicate markup, so all state,
                scroll position and open popups survive the toggle. */}
            {/* Dim the page behind the maximized messenger */}
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
                ref={panelRef}
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
                    className="absolute top-3 right-3 z-40 p-2 rounded-xl bg-white/80 dark:bg-slate-800/80 backdrop-blur border border-slate-200/70 dark:border-slate-700/70 text-slate-400 hover:text-sky-600 dark:hover:text-sky-400 hover:border-sky-300 transition-colors shadow-sm">
                    {maximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>

                {/* Thread list */}
                <motion.div layout transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }} className="flex flex-col min-h-0 border-b lg:border-b-0 lg:border-r border-slate-100 dark:border-slate-700/50">
                    <div className="h-16 shrink-0 px-4 pr-14 lg:pr-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <h2 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest">Conversations</h2>
                        {/* Procksi Chat availability. Opens the per-portal window; the
                            label reflects whether ANY portal currently has chat on. */}
                        <button onClick={() => setTogglesOpen(true)}
                            title="Turn Procksi Chat on or off per portal"
                            aria-label="Procksi Chat availability"
                            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg ${
                                procksiChatToggles.anyOn
                                    ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-500/30'
                                    : 'bg-slate-400 hover:bg-slate-500 dark:bg-slate-600 dark:hover:bg-slate-500 text-white shadow-slate-500/20'}`}>
                            <Power className="w-4 h-4" />
                            {procksiChatToggles.anyOn ? 'On' : 'Off'}
                        </button>
                    </div>
                    {/* Audience filter */}
                    <div className="h-14 shrink-0 px-4 border-b border-slate-100 dark:border-slate-700/50 flex items-center gap-1.5">
                        <button onClick={() => setAudience(null)}
                            className={`px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === null
                                ? 'bg-sky-600 text-white'
                                : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                            Recent
                        </button>
                        {AUDIENCE_TABS.map(a => (
                            <button key={a.id} onClick={() => setAudience(audience === a.id ? null : a.id)}
                                className={`px-3 py-1.5 rounded-full text-[11px] font-black uppercase tracking-wider transition-colors ${audience === a.id
                                    ? 'bg-sky-600 text-white'
                                    : 'bg-slate-100 dark:bg-slate-700/50 text-slate-500 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
                                {a.label}
                            </button>
                        ))}
                    </div>

                    {/* Search — filters whichever list the active chip is showing */}
                    <div className="h-16 shrink-0 px-4 flex items-center border-b border-slate-100 dark:border-slate-700/50">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
                            <input
                                value={query}
                                onChange={e => setQuery(e.target.value)}
                                placeholder={audience
                                    ? `Search ${AUDIENCE_TABS.find(a => a.id === audience).label.toLowerCase()}...`
                                    : 'Search conversations...'}
                                className="w-full pl-9 pr-8 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-sky-500" />
                            {query && (
                                <button type="button" onClick={() => setQuery('')} title="Clear"
                                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-md">
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="divide-y divide-slate-100 dark:divide-slate-700/50 overflow-y-auto flex-1 min-h-0 max-h-[20rem] lg:max-h-none">
                        {/* The four standing groups. There is no way to create one:
                            membership is derived from role, so the set is fixed. */}
                        {audience === 'group' && groupThreads.map(t => (
                            <button key={t.id}
                                onClick={() => {
                                    if (t.id === selectedId) { setSelectedId(null); setRecipient(null); return; }
                                    setSelectedId(t.id);
                                    setRecipient(null);
                                }}
                                className={`w-full text-left px-4 min-h-[4.75rem] flex flex-col justify-center transition-colors ${t.id === selectedId ? 'bg-sky-50 dark:bg-sky-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                <span className="flex items-center gap-2">
                                    <Users className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                                    <span className="text-sm font-black text-slate-800 dark:text-white truncate">{t.subject}</span>
                                    {t.unread > 0 && (
                                        <span className="ml-auto shrink-0 min-w-[1.25rem] px-1.5 py-0.5 bg-sky-600 text-white rounded-full text-[10px] font-black text-center">
                                            {t.unread}
                                        </span>
                                    )}
                                </span>
                                <span className="text-[11px] font-medium text-slate-400 truncate mt-0.5">
                                    {groupReach[t.group_key] ?? '—'}{' · '}{t.preview}
                                </span>
                            </button>
                        ))}

                        {/* Conversations belong to Recent only */}
                        {audience === null && recentThreads.length > 0 && (
                            <>
                                <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 border-b border-slate-200/70 dark:border-slate-700/50">
                                    {recentThreads.length} conversation{recentThreads.length === 1 ? '' : 's'}
                                </p>
                                {recentThreads.map(t => (
                                    <button key={t.id}
                                        onClick={() => {
                                            // Same toggle as the directory rows: clicking the
                                            // open conversation closes it.
                                            if (t.id === selectedId) { setSelectedId(null); setRecipient(null); return; }
                                            setSelectedId(t.id);
                                            setRecipient(recipientFromConversation(t));
                                        }}
                                        className={`w-full text-left px-4 min-h-[4.75rem] flex flex-col justify-center transition-colors ${t.id === selectedId ? 'bg-sky-50 dark:bg-sky-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                        {t.id === selectedId ? (
                                            <span className="flex items-center gap-2.5">
                                                <span className="shrink-0 px-2 py-0.5 bg-sky-600 text-white rounded-md text-[10px] font-black tracking-wider truncate max-w-[10rem]">
                                                    {t.subject}
                                                </span>
                                                <span className="text-xs font-bold text-sky-600 dark:text-sky-400">Click to close</span>
                                                <X className="w-3.5 h-3.5 text-sky-500 ml-auto shrink-0" />
                                            </span>
                                        ) : (
                                            <>
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className="font-bold text-sm text-slate-800 dark:text-white truncate">{t.subject}</span>
                                                    {t.unread > 0 && (
                                                        <span className="shrink-0 px-2 py-0.5 bg-sky-600 text-white rounded-full text-[10px] font-black">{t.unread}</span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-1">{t.preview}</p>
                                            </>
                                        )}
                                    </button>
                                ))}
                            </>
                        )}

                        {/* Directory view — live rows from the database */}
                        {visibleDirectory && (
                            <>
                                {directoryCount === 0 && threads.length === 0 && (
                                    <p className="p-8 text-center text-sm font-medium text-slate-500">{q ? 'Nothing matches that search.' : 'None found in this semester.'}</p>
                                )}
                                {visibleDirectory.map(group => (
                                    <React.Fragment key={group.label}>
                                        <p className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 bg-slate-100 dark:bg-slate-900 sticky top-0 z-10 border-b border-slate-200/70 dark:border-slate-700/50">
                                            {group.items.length} {group.label}
                                        </p>
                                        {group.items.map(d => {
                                            // The open row collapses to just its identifier plus a hint,
                                            // so the list makes clear which chat is showing and how to close it.
                                            const isOpenChat = Boolean(recipient
                                                && recipient.type === d.type
                                                && String(recipient.id) === String(d.rid));
                                            return (
                                            <button key={d.key} type="button"
                                                onClick={() => {
                                                    setRecipient(isOpenChat ? null : {
                                                        type: d.type, id: d.rid, label: d.primary,
                                                        // "T189" -> "189", used to build the Direct-Team189 subtitle
                                                        num: d.badge ? String(d.badge).replace(/\D/g, '') : null,
                                                    });
                                                    setSelectedId(null);
                                                }}
                                                // min-height matches an expanded row so collapsing to
                                                // "Click to close" never shrinks the row or shifts the list.
                                                className={`w-full text-left px-4 min-h-[4.75rem] flex items-center gap-2.5 transition-colors ${isOpenChat
                                                    ? 'bg-sky-50 dark:bg-sky-500/10'
                                                    : 'hover:bg-slate-50 dark:hover:bg-slate-700/20'}`}>
                                                {isOpenChat ? (
                                                    <span className="w-full flex items-center gap-2.5">
                                                        <span className="shrink-0 px-2 py-0.5 bg-sky-600 text-white rounded-md text-[10px] font-black font-mono tracking-wider">
                                                            {d.badge || d.primary}
                                                        </span>
                                                        <span className="text-xs font-bold text-sky-600 dark:text-sky-400">Click to close</span>
                                                        <X className="w-3.5 h-3.5 text-sky-500 ml-auto shrink-0" />
                                                    </span>
                                                ) : (
                                                <>
                                                {d.badge && (
                                                    <span className="shrink-0 px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 rounded-md text-[10px] font-black font-mono tracking-wider">
                                                        {d.badge}
                                                    </span>
                                                )}
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex items-center gap-2">
                                                        <p className="font-bold text-sm text-slate-800 dark:text-white truncate">{d.primary}</p>
                                                        {d.status && (
                                                            <span className="shrink-0 px-1.5 py-0.5 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 rounded text-[9px] font-black uppercase tracking-wider">
                                                                {d.status}
                                                            </span>
                                                        )}
                                                    </div>
                                                    {d.secondary && (
                                                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">{d.secondary}</p>
                                                    )}
                                                </div>
                                                </>
                                                )}
                                            </button>
                                            );
                                        })}
                                    </React.Fragment>
                                ))}
                            </>
                        )}

                    </div>
                </motion.div>

                {/* Thread view */}
                <motion.div ref={threadColRef} layout transition={{ layout: { duration: 0.34, ease: [0.22, 1, 0.36, 1] } }} className="relative lg:col-span-2 flex flex-col min-h-0">
                    {!selected && !recipient ? (
                        // Reserves the column's height on stacked layouts, where the
                        // card has no fixed height and an empty column would collapse.
                        // The placeholder itself is the overlay at the end of this column.
                        <div aria-hidden="true" className="flex-1 min-h-[18rem] lg:min-h-0" />
                    ) : (
                        <>
                            <div className="h-16 shrink-0 px-4 pr-14 flex items-center justify-between gap-3">
                                <div className="min-w-0">
                                    <h2 className="font-black text-slate-800 dark:text-white truncate">
                                        {recipient ? recipient.label : selected.subject}
                                    </h2>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-sky-600 dark:text-sky-400 mt-0.5">
                                        {recipient
                                            ? `Direct-${recipient.type}${recipient.num ? recipient.num : ''}`
                                            : channelById(selected.channel).label}
                                    </p>
                                </div>
                            </div>

                            {/* Team roster — who this chat actually reaches */}
                            {recipientMembers.length > 0 && (
                                <div ref={rosterRef} className="h-14 shrink-0 px-4 flex items-center gap-1.5 overflow-x-auto bg-slate-50/50 dark:bg-slate-900/20">
                                    {recipientMembers.map(m => {
                                        const key = memberKey(m);
                                        const isOpen = openMember === key;
                                        return (
                                            <button key={key} type="button"
                                                onClick={(e) => (isOpen ? setOpenMember(null) : openMemberCard(key, e.currentTarget))}
                                                className={`shrink-0 px-2.5 py-1 rounded-full text-[11px] font-bold border transition-colors ${m.role === 'LEADER'
                                                    ? 'bg-sky-50 dark:bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-500/30'
                                                    : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700'} ${isOpen ? 'ring-2 ring-sky-400' : ''}`}>
                                                {m.name || m.roll}
                                                {m.role === 'LEADER' && <span className="ml-1 opacity-60">· lead</span>}
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
                                                    No commits matched this student. If they commit under a different
                                                    GitHub name, set their username on the student record.
                                                </p>
                                            )}
                                        </>
                                    )}
                                </motion.div>
                            )}
                            </AnimatePresence>

                            {/* Aligns the top of the message area with the top of the
                                conversation list. The left toolbar stack is
                                title(4rem) + chips(3.5rem) + search(4rem) = 11.5rem;
                                the right is title(4rem), plus the roster(3.5rem) only
                                when a team is open — so the gap to make up is 4rem
                                with a roster and 7.5rem without. Carries no border and
                                no background: a ruled empty band here renders as a
                                second, broken header rather than as alignment. */}
                            <div aria-hidden="true"
                                className={`hidden lg:block shrink-0 ${recipientMembers.length > 0 ? 'h-16' : 'h-[7.5rem]'}`} />

                            <div ref={scrollRef} onScroll={handleScroll}
                                className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3 max-h-[18rem] lg:max-h-none">
                                <AnimatePresence initial={false}>
                                    {days.map(day => (
                                        <React.Fragment key={day.key}>
                                            <motion.div layout key={`day-${day.key}`}
                                                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                                transition={{ duration: 0.2 }}
                                                className="flex items-center justify-center py-1">
                                                <span className="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-700/60 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                                                    {day.label}
                                                </span>
                                            </motion.div>
                                            {day.items.map(m => {
                                                const status = deliveryState(m);
                                                const own = m.sender_role === 'admin';

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
                                                    className={`flex ${m.sender_role === 'admin' ? 'justify-end' : 'justify-start'}`}>
                                                    <div className={`max-w-[75%] rounded-2xl px-4 py-2.5 transition-opacity ${m.sender_role === 'admin' ? 'bg-sky-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-800 dark:text-slate-100'
                                                        } ${m.status === 'sending' ? 'opacity-70' : ''
                                                        } ${m.status === 'failed' ? 'ring-2 ring-rose-400' : ''}`}>
                                                        <p className="text-[10px] font-black uppercase tracking-widest opacity-70 mb-1">
                                                            {senderName(m, people)}
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
                            <form ref={composerBarRef} onSubmit={handleReply} className="shrink-0 p-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2 relative">
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
                                                    ? 'bg-sky-50 dark:bg-sky-500/15'
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
                                            <button key={m.id || m.roll} type="button"
                                                onMouseDown={e => { e.preventDefault(); insertMention(m); }}
                                                onMouseEnter={() => setMentionIndex(i)}
                                                className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-xl text-left transition-colors ${i === mentionIndex
                                                    ? 'bg-sky-50 dark:bg-sky-500/15'
                                                    : 'hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                                <span className="w-6 h-6 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 flex items-center justify-center text-[10px] font-black shrink-0">
                                                    {String(m.name || m.roll || '?').charAt(0).toUpperCase()}
                                                </span>
                                                <span className="min-w-0 flex-1">
                                                    <span className="block text-sm font-bold text-slate-800 dark:text-white truncate">{m.name || m.roll}</span>
                                                    {m.roll && <span className="block text-[10px] font-mono text-slate-400 truncate">{m.roll}</span>}
                                                </span>
                                                {m.role === 'LEADER' && (
                                                    <span className="shrink-0 text-[9px] font-black uppercase tracking-wider text-sky-600 dark:text-sky-400">lead</span>
                                                )}
                                            </button>
                                        ))}
                                    </motion.div>
                                )}
                                </AnimatePresence>
                                <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={handleReplyKeyDown}
                                    placeholder="Write a reply..."
                                    className="flex-1 px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium dark:text-white outline-none focus:ring-2 focus:ring-sky-500" />
                                <button type="submit" disabled={busy || !reply.trim()}
                                    className="px-4 py-2.5 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white rounded-xl transition-colors">
                                    <Send className="w-4 h-4" />
                                </button>
                            </form>
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

            {/* Composer */}

            <ProcksiChatToggleModal
                open={togglesOpen}
                onClose={() => setTogglesOpen(false)}
                toggles={procksiChatToggles}
            />
        </div>
    );
};

export default ProcksiChat;
