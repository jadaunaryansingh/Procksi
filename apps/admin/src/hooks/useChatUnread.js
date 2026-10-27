import { useEffect, useSyncExternalStore } from 'react';
import { getStoredSession } from '../lib/api';
import { fetchConversations, fetchMessages } from '../services/procksiChatApi';
import { unreadCount } from '../lib/procksiChatThreads';
import { subscribeChatEvents } from '../lib/chatRealtime';

// Fallback only. A realtime ping recounts the instant anyone writes a message,
// so this interval exists for the case where the websocket never connected or
// has dropped — not as the normal path. Reading a thread and refocusing the tab
// also recount immediately.
//
// Slower still than the other three portals. They ask a dedicated endpoint that
// returns a number; this one pulls the whole message table and counts
// client-side, so it is the most expensive request in the portal and the
// sidebar runs it on every page.
const POLL_MS = 60000;

// The count lives outside React so every sidebar instance shows the same
// number, a page change does not reset the badge to 0 while the first poll is
// in flight, and the chat page can correct it the moment it knows better.
let current = 0;
const listeners = new Set();
let inflight = null;

const publish = (n) => {
    const next = Number(n) || 0;
    if (next === current) return;
    current = next;
    listeners.forEach(fn => fn(next));
};

/**
 * Recount now. Concurrent callers share one pass, so a poll tick landing on a
 * thread being marked read does not fan out into two table reads.
 *
 * Unlike the other three portals the admin has no dedicated chat backend to
 * ask — it reads the tables directly — so the count is derived here from the
 * same `read_by` arrays the page uses. Messages are scoped to conversations the
 * admin can actually see, so a thread outside the selected semester never
 * inflates the badge.
 */
export async function refreshChatUnread() {
    if (inflight) return inflight;
    const viewerId = getStoredSession()?.user?.email || '';
    if (!viewerId) return undefined;

    inflight = (async () => {
        try {
            const [conversations, messages] = await Promise.all([
                fetchConversations(),
                fetchMessages(),
            ]);
            const visible = new Set((conversations || []).map(c => c.id));
            const mine = (messages || []).filter(m => visible.has(m.conversation_id));
            publish(unreadCount(mine, viewerId));
        } catch {
            // Keep whatever was last shown: the badge is decoration on someone
            // else's page, and the next tick corrects it.
        } finally {
            inflight = null;
        }
    })();
    return inflight;
}

/** Publish a total the caller already has, without a second round trip. */
export function publishChatUnread(total) {
    publish(total);
}

/** Unread Procksi Chat count for the sidebar badge. */
export function useChatUnread() {
    // The count already lives outside React, so this is what
    // useSyncExternalStore is for: subscribe and read in one step. The previous
    // version mirrored the store into local state and re-seeded it from an
    // effect — a render with a stale count followed by a second render to
    // correct it, which is the cascading render the compiler flags.
    const unread = useSyncExternalStore(
        (onStoreChange) => {
            listeners.add(onStoreChange);
            return () => listeners.delete(onStoreChange);
        },
        () => current,
        () => current,
    );

    useEffect(() => {
        const tick = () => { if (!document.hidden) refreshChatUnread(); };
        tick();
        const timer = setInterval(tick, POLL_MS);
        // Any message anywhere may change this viewer's count, and the ping
        // carries no way to tell — the server decides what they can see. So
        // every ping recounts; the request is cheap and shared.
        const stopRealtime = subscribeChatEvents(() => { if (!document.hidden) refreshChatUnread(); });
        // visibilitychange covers tab switches; focus covers coming back to the
        // browser from another application, which does not fire it.
        document.addEventListener('visibilitychange', tick);
        window.addEventListener('focus', tick);
        return () => {
            stopRealtime();
            clearInterval(timer);
            document.removeEventListener('visibilitychange', tick);
            window.removeEventListener('focus', tick);
        };
    }, []);

    return unread;
}
