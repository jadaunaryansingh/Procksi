import { supabase } from './supabase';

/**
 * Realtime signal for PMS-Chat.
 *
 * The chat tables are locked to the backends' service-role key and are NOT
 * published to realtime — they hold message bodies. What is published is
 * `chat_events`, a content-free ping written by a trigger on every insert:
 * a conversation id and a timestamp, nothing else.
 *
 * So this module never delivers a message. It says "conversation N changed",
 * and the caller refetches through the portal's own authenticated API, where
 * the backend re-checks that this student may see that thread at all.
 *
 * One channel per tab, shared by every subscriber, so having the sidebar badge
 * and the chat page both listening does not open two websockets.
 */
let channel = null;
const handlers = new Set();

function open() {
    if (channel || !supabase) return;
    channel = supabase
        .channel('pms-chat-events')
        .on(
            'postgres_changes',
            { event: 'INSERT', schema: 'public', table: 'chat_events' },
            (payload) => {
                const conversationId = payload?.new?.conversation_id ?? null;
                // One bad handler must not stop the others from running.
                handlers.forEach((fn) => { try { fn(conversationId); } catch { /* ignore */ } });
            },
        )
        .subscribe();
}

function close() {
    if (!channel) return;
    supabase.removeChannel(channel);
    channel = null;
}

/**
 * @param {(conversationId: number|null) => void} handler
 * @returns {() => void} unsubscribe
 */
export function subscribeChatEvents(handler) {
    handlers.add(handler);
    open();
    return () => {
        handlers.delete(handler);
        if (handlers.size === 0) close();
    };
}
