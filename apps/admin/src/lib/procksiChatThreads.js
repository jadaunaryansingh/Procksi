/**
 * procksiChatThreads.js
 *
 * Pure thread-summarising and unread logic for the Procksi Chat dashboard.
 * Unread state is derived from each message's `read_by` array rather than a
 * join table — see the spec's note on why this does not scale past a few
 * thousand recipients per message.
 */

export function isUnreadFor(message, viewerId) {
    if (!message) return false;
    if (message.sender_id === viewerId) return false;
    const readBy = Array.isArray(message.read_by) ? message.read_by : [];
    return !readBy.includes(viewerId);
}

export function unreadCount(messages, viewerId) {
    if (!Array.isArray(messages)) return 0;
    return messages.reduce((n, m) => n + (isUnreadFor(m, viewerId) ? 1 : 0), 0);
}

export function groupMessagesByConversation(messages) {
    const grouped = new Map();
    if (!Array.isArray(messages)) return grouped;
    for (const message of messages) {
        const key = message.conversation_id;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(message);
    }
    for (const list of grouped.values()) {
        list.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    }
    return grouped;
}

export function summariseThreads(conversations, messages, viewerId) {
    if (!Array.isArray(conversations)) return [];
    const grouped = groupMessagesByConversation(messages);

    return conversations
        .map((conversation) => {
            const thread = grouped.get(conversation.id) || [];
            const lastMessage = thread.length ? thread[thread.length - 1] : null;
            return {
                ...conversation,
                lastMessage,
                unread: unreadCount(thread, viewerId),
                preview: lastMessage ? lastMessage.body : 'No messages yet',
            };
        })
        .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
}
