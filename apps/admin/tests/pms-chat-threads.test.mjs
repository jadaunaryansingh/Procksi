import test from 'node:test';
import assert from 'node:assert/strict';
import {
    isUnreadFor,
    unreadCount,
    groupMessagesByConversation,
    summariseThreads,
} from '../src/lib/pmsChatThreads.js';

const ADMIN = 'aiml_project_coordinator@gla.ac.in';

const messages = [
    { id: 1, conversation_id: 10, sender_role: 'admin', sender_id: ADMIN, body: 'Kickoff', read_by: [], created_at: '2026-08-01T10:00:00Z' },
    { id: 2, conversation_id: 10, sender_role: 'mentor', sender_id: 'M-1', body: 'Acknowledged', read_by: [], created_at: '2026-08-02T10:00:00Z' },
    { id: 3, conversation_id: 11, sender_role: 'panel', sender_id: 'P-1', body: 'Slot clash', read_by: [ADMIN], created_at: '2026-08-03T10:00:00Z' },
];

const conversations = [
    { id: 10, channel: 'mentor_student', subject: 'Kickoff', updated_at: '2026-08-02T10:00:00Z' },
    { id: 11, channel: 'panel_team', subject: 'Scheduling', updated_at: '2026-08-03T10:00:00Z' },
    { id: 12, channel: 'all', subject: 'Empty thread', updated_at: '2026-08-04T10:00:00Z' },
];

test('a message the viewer sent is never unread to them', () => {
    assert.equal(isUnreadFor(messages[0], ADMIN), false);
});

test('a message from someone else with an empty read_by is unread', () => {
    assert.equal(isUnreadFor(messages[1], ADMIN), true);
});

test('a message already in read_by is not unread', () => {
    assert.equal(isUnreadFor(messages[2], ADMIN), false);
});

test('a missing read_by is treated as empty, not a crash', () => {
    assert.equal(isUnreadFor({ sender_id: 'M-9', body: 'hi' }, ADMIN), true);
});

test('unreadCount counts only other peoples unread messages', () => {
    assert.equal(unreadCount(messages, ADMIN), 1);
    assert.equal(unreadCount([], ADMIN), 0);
});

test('groupMessagesByConversation buckets by conversation_id', () => {
    const grouped = groupMessagesByConversation(messages);
    assert.equal(grouped.get(10).length, 2);
    assert.equal(grouped.get(11).length, 1);
    assert.equal(grouped.has(12), false);
});

test('summariseThreads sorts newest first and attaches preview and unread', () => {
    const threads = summariseThreads(conversations, messages, ADMIN);
    assert.deepEqual(threads.map(t => t.id), [12, 11, 10]);

    const kickoff = threads.find(t => t.id === 10);
    assert.equal(kickoff.unread, 1);
    assert.equal(kickoff.preview, 'Acknowledged');
    assert.equal(kickoff.lastMessage.id, 2);
});

test('a conversation with no messages summarises safely', () => {
    const empty = summariseThreads(conversations, messages, ADMIN).find(t => t.id === 12);
    assert.equal(empty.unread, 0);
    assert.equal(empty.preview, 'No messages yet');
    assert.equal(empty.lastMessage, null);
});
