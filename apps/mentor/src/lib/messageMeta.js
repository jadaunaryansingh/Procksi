/**
 * Display rules for chat message lists: timestamps, day grouping and sender
 * names.
 *
 * Pure by design — no imports, no DOM, no network — because these rules are
 * easy to get subtly wrong (midnight boundaries, missing dates, a sender whose
 * name is not on file) and are worth testing directly.
 */

const ROLE_LABELS = {
    bot: 'PMSbot',
    admin: 'Coordinator',
    mentor: 'Mentor',
    panel: 'Panel',
    student: 'Student',
};

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

// Always returns a fresh Date. Returning the caller's own object would let
// formatDayLabel's "yesterday" arithmetic mutate the `now` it was handed, so
// every later call in the same pass would compare against a shifted clock.
function toDate(value) {
    if (value instanceof Date) {
        return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
    }
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
}

/** "2:45 PM", in the reader's own timezone. Empty string if there is no date. */
export function formatTime(value) {
    const d = toDate(value);
    if (!d) return '';
    const hours = d.getHours();
    const period = hours >= 12 ? 'PM' : 'AM';
    const hour12 = hours % 12 === 0 ? 12 : hours % 12;
    return `${hour12}:${String(d.getMinutes()).padStart(2, '0')} ${period}`;
}

/**
 * Local-calendar-day identity, e.g. "2026-08-15". Deliberately built from local
 * getters rather than toISOString(), which would roll a late-evening message
 * into the next day for readers behind UTC.
 */
export function dayKey(value) {
    const d = toDate(value);
    if (!d) return null;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** "Today" / "Yesterday" / "15 August 2026". */
export function formatDayLabel(value, now = new Date()) {
    const key = dayKey(value);
    if (!key) return '';
    if (key === dayKey(now)) return 'Today';

    const yesterday = toDate(now);
    if (yesterday) {
        yesterday.setDate(yesterday.getDate() - 1);
        if (key === dayKey(yesterday)) return 'Yesterday';
    }

    const d = toDate(value);
    return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/**
 * Splits an ascending message list into consecutive same-day runs:
 *   [{ key, label, items }, ...]
 *
 * Messages with no usable date join the run in progress rather than forming a
 * group of their own — an unsent message has not been stamped by the server
 * yet, and it belongs beside the message the writer just sent.
 */
export function groupByDay(messages, now = new Date()) {
    const groups = [];
    for (const message of messages || []) {
        const key = dayKey(message?.created_at);
        const current = groups[groups.length - 1];

        if (key === null) {
            if (current) { current.items.push(message); continue; }
            groups.push({ key: dayKey(now), label: 'Today', items: [message] });
            continue;
        }
        if (current && current.key === key) { current.items.push(message); continue; }
        groups.push({ key, label: formatDayLabel(message.created_at, now), items: [message] });
    }
    return groups;
}

/**
 * Best-effort name from a login id. College addresses append a course and year
 * after an underscore (kushagra.kulshrestha_cs.aiml24@gla.ac.in), which is not
 * part of anyone's name.
 */
export function humanizeSenderId(senderId) {
    const raw = String(senderId ?? '').trim();
    if (!raw) return '';
    const local = raw.includes('@') ? raw.slice(0, raw.indexOf('@')) : raw;
    const words = local.split('_')[0].split(/[.\-+]+/).filter(Boolean);
    if (!words.length) return raw;
    // A roll number is not a name; leave it as-is rather than title-casing it.
    if (words.every(w => /^\d+$/.test(w))) return raw;
    return words.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

/**
 * Index of every identifier a message might be signed with, so a sender can be
 * named exactly rather than guessed at. Keys are lowercased; both email and
 * roll number are indexed because the portals sign with whichever they have.
 */
export function buildPeopleIndex(rows = []) {
    const index = new Map();
    for (const row of rows) {
        const name = String(row?.name ?? '').trim();
        if (!name) continue;
        for (const key of [row?.email, row?.id, row?.roll]) {
            const k = String(key ?? '').trim().toLowerCase();
            if (k) index.set(k, name);
        }
    }
    return index;
}

/**
 * Who to show above a message. Staff are shown by role — a student should see
 * "Coordinator", not an administrator's personal address — while students are
 * named, because in a team thread the role alone does not say who is speaking.
 */
/**
 * Builds the render list: confirmed messages, then anything still in flight,
 * each with a unique key.
 *
 * `keyMap` maps a confirmed message id to the temporary id its optimistic
 * bubble used, so the bubble keeps its React key through the handover. That
 * makes the handover invisible, but it also means a pending message that was
 * confirmed WITHOUT being removed from the outbox would render twice under one
 * key — React then warns about duplicate keys and may drop or duplicate rows.
 * Dropping any pending row whose key a confirmed message has already claimed
 * makes that impossible regardless of how the outbox is reconciled.
 */
export function mergeTimeline(confirmed = [], pending = [], keyMap = new Map()) {
    const rows = [];
    const claimed = new Set();

    for (const message of confirmed) {
        const key = keyMap?.get?.(message?.id) ?? `m-${message?.id}`;
        claimed.add(key);
        rows.push({ ...message, status: DELIVERY.SENT, rowKey: key });
    }
    for (const message of pending) {
        if (claimed.has(message?.id)) continue;
        rows.push({ ...message, rowKey: message?.id });
    }
    return rows;
}

/** Delivery states a message can be shown in, in the order they progress. */
export const DELIVERY = {
    SENDING: 'sending',
    FAILED: 'failed',
    SENT: 'sent',
    READ: 'read',
};

/**
 * How far a message has got: still in flight, rejected, stored, or seen by
 * somebody else.
 *
 * `read_by` always contains the sender — it is seeded with their own id at
 * insert — so the sender's presence in it means nothing. Only another party
 * appearing there counts as having been read.
 */
export function deliveryState(message) {
    if (message?.status === DELIVERY.SENDING) return DELIVERY.SENDING;
    if (message?.status === DELIVERY.FAILED) return DELIVERY.FAILED;

    const sender = String(message?.sender_id ?? '').trim().toLowerCase();
    const readers = Array.isArray(message?.read_by) ? message.read_by : [];
    const others = readers
        .map(r => String(r ?? '').trim().toLowerCase())
        .filter(r => r && r !== sender);

    return others.length > 0 ? DELIVERY.READ : DELIVERY.SENT;
}

export function senderName(message, people) {
    const role = String(message?.sender_role ?? '').trim().toLowerCase();
    if (role && role !== 'student') {
        return ROLE_LABELS[role] || role.charAt(0).toUpperCase() + role.slice(1);
    }

    // A backend that can resolve the name itself wins over any guess made here.
    const supplied = String(message?.sender_name ?? '').trim();
    if (supplied) return supplied;

    const id = String(message?.sender_id ?? '').trim();
    const known = people?.get?.(id.toLowerCase());
    if (known) return known;
    return humanizeSenderId(id) || ROLE_LABELS.student;
}
