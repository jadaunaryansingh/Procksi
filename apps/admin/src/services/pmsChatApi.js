/**
 * pmsChatApi.js
 *
 * Supabase access for the PMS-Chat conversations dashboard.
 *
 * `conversations` carries semester_id and is filtered by the global semester
 * selector automatically. `conversation_messages` has no semester_id and is
 * excluded from that filtering in lib/api.js — do not add one.
 *
 * NOTE: the `conversations` / `conversation_messages` tables are created by
 * supabase/migrations/202608140001_delegate_conversations.sql. That migration
 * IS applied on the current Supabase project and both tables are in the
 * backend's DATA_TABLE_WHITELIST, so these calls succeed. It may still be
 * unapplied on a fresh project, so `isMissingTablesError` is kept: it lets
 * the page tell that specific, expected failure apart from a real fault and
 * show a setup notice instead of an error state.
 */
import { apiFetchTable, apiUpsertTable, apiPatchRow, getAuthHeaders } from '../lib/api';
import { getApiBaseUrl } from '../lib/apiBase';
import { channelById } from '../lib/pmsChatChannels';

// Matches the three real shapes the backend produces for a missing
// conversations/conversation_messages table:
//   1. 400 "Table '<name>' is not allowed." — server whitelist gate.
//   2. 500 containing "PGRST205" or "Could not find the table" — PostgREST
//      error text surfaced verbatim by the write (upsert) path.
//   3. 503 "Data service temporarily unavailable for '<table>'. Please
//      retry." — the read path's catch-all, which swallows the real
//      PostgREST error before it reaches the browser.
// Case 3 is a GENERIC 503 that the backend also raises for real transient
// outages on these tables (e.g. DB briefly unreachable). There is no way to
// tell "table doesn't exist yet" apart from "temporary outage" from this
// message alone, so a genuine outage will be misreported as "tables not
// created yet" here. This is a known, accepted ambiguity, not a bug to
// paper over: the backend does not give the frontend enough information to
// distinguish the two cases, and probing further would be scope creep.
export function isMissingTablesError(error) {
    const message = String(error?.message || '');
    if (!/conversation/i.test(message)) return false;
    return (
        /not allowed/i.test(message) ||
        /PGRST205/i.test(message) ||
        /could not find the table/i.test(message) ||
        /temporarily unavailable/i.test(message)
    );
}

/**
 * Latest repository analysis for a team. Returns null when the team has never
 * been analysed — which is the normal state until the weekly analysis runs.
 */
export async function fetchTeamAnalysis(teamRef) {
    if (!teamRef) return null;
    const rows = await apiFetchTable('github_agent_analysis', {
        orderBy: 'created_at', ascending: false,
    });
    const ref = String(teamRef);
    const mine = (rows || []).filter(r =>
        String(r.team_ref) === ref || String(r.team_uid) === ref || String(r.team_id) === ref);
    return mine.find(r => r.raw_report) || mine[0] || null;
}

export async function fetchConversations() {
    return apiFetchTable('conversations', { orderBy: 'updated_at', ascending: false });
}

export async function fetchMessages() {
    return apiFetchTable('conversation_messages', { orderBy: 'created_at', ascending: true });
}

// Fans a new message out to the existing notifications table, one row per
// recipient role, so every portal's existing notification bell surfaces it
// without waiting on the Phase 2 inbox UI.
export async function notifyChannel({ channel, subject, body }) {
    const rows = channelById(channel).roles.map((role) => ({
        recipient_email: null,
        recipient_role: role,
        audience: 'all',
        title: `New message: ${subject}`,
        message: String(body).slice(0, 200),
        type: 'conversation',
        read: false,
    }));
    await apiUpsertTable('notifications', rows);
}

export async function createConversation({ channel, subject, body, createdBy, semesterId }) {
    // The row must land in the semester the admin currently has selected —
    // otherwise apiUpsertTable's own semester_id injection (lib/api.js) picks
    // the first ACTIVE semester, which can silently differ from what the
    // admin is viewing and make the new conversation vanish from reload().
    // Omit semester_id (and let that injection apply as before) when nothing
    // specific is selected, rather than inventing a value.
    const semesterFields = (semesterId && semesterId !== 'all') ? { semester_id: semesterId } : {};
    const inserted = await apiUpsertTable('conversations', [{
        channel,
        subject,
        created_by: createdBy,
        status: 'open',
        updated_at: new Date().toISOString(),
        ...semesterFields,
    }]);

    // apiUpsertTable resolves to { data, count } (see lib/api.js), never a
    // bare array. Read the inserted row from that real shape. There is no
    // safe fallback here: re-fetching and guessing which conversation was
    // just created can attach this message to an unrelated one when the
    // list is filtered by a different semester than the row was inserted
    // into, so if the row doesn't come back we fail loudly instead.
    const conversation = inserted?.data?.[0] ?? null;
    if (!conversation?.id) {
        throw new Error('Conversation was created but could not be read back.');
    }

    await apiUpsertTable('conversation_messages', [{
        conversation_id: conversation.id,
        sender_role: 'admin',
        sender_id: createdBy,
        body,
        read_by: [createdBy],
    }]);

    // The conversation and its first message are the real work and have
    // already committed at this point. The notification fan-out is a
    // convenience side effect only; failing the whole call after the real
    // work succeeded would leave the UI showing an error and inviting a
    // retry that creates a duplicate conversation/message.
    try {
        await notifyChannel({ channel, subject, body });
    } catch (err) {
        console.warn('notifyChannel failed after conversation was created:', err);
    }

    return conversation;
}

/**
 * The four standing groups, seeded by migration 202608160003 and never created
 * from the UI.
 *
 * They are fetched separately from fetchConversations because they carry no
 * semester_id — they are institution-wide and must survive a semester rollover,
 * so the semester filter that every other conversation needs would hide them.
 */
export async function fetchGroupConversations() {
    const rows = await apiFetchTable('conversations', {
        orderBy: 'id', ascending: true, semesterOverride: 'all',
    });
    return (rows || []).filter(c => c.kind === 'group');
}

// Channel is NOT NULL with a CHECK constraint, so a direct thread still has to
// carry one. It is the closest matching broadcast channel, and is unused for
// routing on direct threads — recipient_type/recipient_id are what matter.
const CHANNEL_FOR_RECIPIENT = { mentor: 'mentor_student', team: 'panel_team', panel: 'panel_team' };

/**
 * The student and mentor portals do NOT read recipient_type/recipient_id for
 * team threads — they look a thread up by (team_id, kind), the columns added in
 * migration 202608150001. That migration backfilled the rows existing at the
 * time, but nothing taught this insert to keep writing them, so every admin
 * to team thread created afterwards landed with team_id and kind NULL and was
 * invisible to the very students it was addressed to.
 *
 * An admin to team thread is the "coordinator" thread from the student's side.
 * Mentor and panel recipients are matched by recipient_id instead and carry no
 * team, so they get nothing here.
 */
function teamThreadFields(recipientType, recipientId) {
    if (recipientType !== 'team') return {};
    return { kind: 'coordinator', team_id: String(recipientId) };
}

/**
 * Sends a direct message to one mentor/team/panel, creating the 1:1 thread on
 * first send (so clicking a name opens an empty chat without writing a row).
 * Returns the conversation the message landed in.
 */
export async function sendDirectMessage({
    recipientType, recipientId, recipientLabel, existingConversationId,
    body, senderId, semesterId,
}) {
    let conversationId = existingConversationId;

    if (!conversationId) {
        const semesterFields = (semesterId && semesterId !== 'all') ? { semester_id: semesterId } : {};
        const inserted = await apiUpsertTable('conversations', [{
            channel: CHANNEL_FOR_RECIPIENT[recipientType] || 'all',
            subject: recipientLabel,
            created_by: senderId,
            status: 'open',
            recipient_type: recipientType,
            recipient_id: String(recipientId),
            recipient_label: recipientLabel,
            updated_at: new Date().toISOString(),
            ...teamThreadFields(recipientType, recipientId),
            ...semesterFields,
        }]);
        const conversation = inserted?.data?.[0] ?? null;
        if (!conversation?.id) {
            throw new Error('Conversation was created but could not be read back.');
        }
        conversationId = conversation.id;
    }

    await apiUpsertTable('conversation_messages', [{
        conversation_id: conversationId,
        sender_role: 'admin',
        sender_id: senderId,
        body,
        read_by: [senderId],
    }]);

    try {
        await apiPatchRow('conversations', conversationId, { updated_at: new Date().toISOString() });
    } catch (err) {
        console.warn('Could not bump conversation timestamp:', err);
    }

    return conversationId;
}

export async function sendMessage({ conversationId, channel, subject, body, senderId }) {
    await apiUpsertTable('conversation_messages', [{
        conversation_id: conversationId,
        sender_role: 'admin',
        sender_id: senderId,
        body,
        read_by: [senderId],
    }]);

    // The message insert above is the real work and has already committed.
    // The conversations.updated_at patch is a display-only convenience (it
    // only affects thread ordering/recency), so a failure here (transient
    // 500, or 403 if the semester is frozen) must not fail the whole call —
    // doing so would alert "Could not send" while the message already
    // landed, and the admin would retry and create a duplicate message row.
    try {
        await apiPatchRow('conversations', conversationId, { updated_at: new Date().toISOString() });
    } catch (err) {
        console.warn('conversations.updated_at patch failed after message was sent:', err);
    }

    // Same rationale as in createConversation: the message insert and the
    // conversation timestamp patch are the real work and have already
    // committed. Do not fail the whole call over the notification fan-out,
    // which would otherwise invite a duplicate-creating retry.
    try {
        await notifyChannel({ channel, subject, body });
    } catch (err) {
        console.warn('notifyChannel failed after message was sent:', err);
    }
}

// Marks every message in a thread that the viewer has not yet read as read,
// by appending viewerId to each message's read_by array. Called when the
// admin opens a thread so its unread badge can clear — read_by is otherwise
// only ever written at insert time (see pmsChatThreads.js's isUnreadFor),
// so without this an unread badge could never clear once a reply existed.
// Returns true if at least one message was successfully marked read, false
// if there was nothing to mark (falsy viewerId, empty/non-array messages,
// or nothing unread) or if every patch attempt failed.
export async function markThreadRead({ messages, viewerId }) {
    if (!viewerId || !Array.isArray(messages) || messages.length === 0) return false;

    const unread = messages.filter((m) => (
        m.sender_id !== viewerId && !(Array.isArray(m.read_by) && m.read_by.includes(viewerId))
    ));
    if (unread.length === 0) return false;

    // Failing to mark a thread read must never break opening it, so every
    // patch is best-effort: log and move on rather than reject.
    const results = await Promise.all(unread.map(async (message) => {
        try {
            await apiPatchRow('conversation_messages', message.id, {
                read_by: [...(Array.isArray(message.read_by) ? message.read_by : []), viewerId],
            });
            return true;
        } catch (err) {
            console.warn('markThreadRead failed for message', message.id, err);
            return false;
        }
    }));

    // Return true if at least one patch succeeded
    return results.some(result => result);
}


// Slash commands. These execute server-side and return a result to render;
// nothing is posted into the conversation. Uses the same base URL and auth
// headers as the table helpers above rather than a client of its own.
export async function runChatCommand({ command, option = null, teamId = null, conversationId = null }) {
    const response = await fetch(`${getApiBaseUrl()}/api/admin/chat/command`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ command, option, team_id: teamId, conversation_id: conversationId }),
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || 'That command could not be run.');
    }
    return response.json();
}
