import { useEffect, useSyncExternalStore } from 'react';
import { chatAPI } from '../services/api';
import { subscribeChatEvents } from '../lib/chatRealtime';

// Fallback only. A realtime ping recounts the instant anyone writes a message,
// so this interval exists for the case where the websocket never connected or
// has dropped — not as the normal path. Reading a thread and refocusing the tab
// also recount immediately.
const POLL_MS = 30000;

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
 * Fetch the count now. Concurrent callers share one request, so a burst (poll
 * tick landing on a thread being opened) does not fan out.
 */
export async function refreshChatUnread() {
    if (inflight) return inflight;
    inflight = (async () => {
        try {
            const res = await chatAPI.getUnread();
            publish(res?.unread);
        } catch {
            // Keep whatever was last shown: the badge is decoration on someone
            // else's page, and the next tick corrects it.
        } finally {
            inflight = null;
        }
    })();
    return inflight;
}

/**
 * Publish a total the caller already has. The chat page polls unread counts
 * every 5s anyway, so handing that number over keeps the badge current without
 * a second request.
 */
export function publishChatUnread(total) {
    publish(total);
}

/** Unread Procksi Chat message count for the sidebar badge. */
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
