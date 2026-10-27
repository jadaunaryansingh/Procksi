import test from 'node:test';
import assert from 'node:assert/strict';

import {
    formatTime, dayKey, formatDayLabel, groupByDay,
    humanizeSenderId, buildPeopleIndex, senderName,
    deliveryState, DELIVERY, mergeTimeline,
} from '../src/lib/messageMeta.js';

// Dates are built from local components throughout, so these assertions hold
// in any timezone the test runner happens to be in.
const at = (y, m, d, hh = 0, mm = 0) => new Date(y, m - 1, d, hh, mm);

test('formatTime renders a 12-hour clock with a padded minute', () => {
    assert.equal(formatTime(at(2026, 8, 15, 14, 45)), '2:45 PM');
    assert.equal(formatTime(at(2026, 8, 15, 9, 5)), '9:05 AM');
});

test('formatTime renders both midnight and noon as 12', () => {
    assert.equal(formatTime(at(2026, 8, 15, 0, 30)), '12:30 AM');
    assert.equal(formatTime(at(2026, 8, 15, 12, 0)), '12:00 PM');
});

test('formatTime returns empty string for missing or unparseable dates', () => {
    assert.equal(formatTime(null), '');
    assert.equal(formatTime(undefined), '');
    assert.equal(formatTime('not a date'), '');
});

test('dayKey uses the local calendar day, not the UTC one', () => {
    // 11:30pm local must stay on the 15th even for readers behind UTC, where
    // toISOString() would report the 16th.
    assert.equal(dayKey(at(2026, 8, 15, 23, 30)), '2026-08-15');
    assert.equal(dayKey(at(2026, 1, 5, 0, 15)), '2026-01-05');
});

test('formatDayLabel names today and yesterday', () => {
    const now = at(2026, 8, 15, 10, 0);
    assert.equal(formatDayLabel(at(2026, 8, 15, 8, 0), now), 'Today');
    assert.equal(formatDayLabel(at(2026, 8, 14, 23, 0), now), 'Yesterday');
});

test('formatDayLabel crossing a month boundary still reads as Yesterday', () => {
    const now = at(2026, 9, 1, 9, 0);
    assert.equal(formatDayLabel(at(2026, 8, 31, 20, 0), now), 'Yesterday');
});

test('formatDayLabel spells out older dates', () => {
    const now = at(2026, 8, 15, 10, 0);
    assert.equal(formatDayLabel(at(2026, 8, 12, 10, 0), now), '12 August 2026');
});

test('groupByDay splits consecutive runs and labels each', () => {
    const now = at(2026, 8, 15, 12, 0);
    const groups = groupByDay([
        { id: 1, created_at: at(2026, 8, 13, 9, 0) },
        { id: 2, created_at: at(2026, 8, 13, 18, 0) },
        { id: 3, created_at: at(2026, 8, 15, 8, 0) },
    ], now);

    assert.equal(groups.length, 2);
    assert.deepEqual(groups.map(g => g.label), ['13 August 2026', 'Today']);
    assert.deepEqual(groups[0].items.map(m => m.id), [1, 2]);
    assert.deepEqual(groups[1].items.map(m => m.id), [3]);
});

test('groupByDay keeps an undated message beside the one before it', () => {
    const now = at(2026, 8, 15, 12, 0);
    const groups = groupByDay([
        { id: 1, created_at: at(2026, 8, 15, 8, 0) },
        { id: 2, created_at: null },
    ], now);

    assert.equal(groups.length, 1);
    assert.deepEqual(groups[0].items.map(m => m.id), [1, 2]);
});

test('groupByDay files a leading undated message under today', () => {
    const now = at(2026, 8, 15, 12, 0);
    const groups = groupByDay([{ id: 1, created_at: null }], now);
    assert.equal(groups.length, 1);
    assert.equal(groups[0].label, 'Today');
});

test('groupByDay tolerates empty and missing input', () => {
    assert.deepEqual(groupByDay([]), []);
    assert.deepEqual(groupByDay(null), []);
});

test('humanizeSenderId drops the course-and-year suffix', () => {
    assert.equal(humanizeSenderId('kushagra.kulshrestha_cs.aiml24@example.edu'), 'Kushagra Kulshrestha');
    assert.equal(humanizeSenderId('yashi.x_cs.aiml24@example.edu'), 'Yashi X');
});

test('humanizeSenderId leaves a roll number alone', () => {
    assert.equal(humanizeSenderId('2415500262'), '2415500262');
});

test('humanizeSenderId returns empty string for nothing', () => {
    assert.equal(humanizeSenderId(''), '');
    assert.equal(humanizeSenderId(null), '');
});

test('buildPeopleIndex indexes email, id and roll, all lowercased', () => {
    const index = buildPeopleIndex([
        { id: '2415500262', name: 'Kushagra Kulshrestha', email: 'Kushagra.Kulshrestha_cs.aiml24@example.edu' },
        { roll: '2415500128', name: 'Bharti Singh' },
    ]);
    assert.equal(index.get('kushagra.kulshrestha_cs.aiml24@example.edu'), 'Kushagra Kulshrestha');
    assert.equal(index.get('2415500262'), 'Kushagra Kulshrestha');
    assert.equal(index.get('2415500128'), 'Bharti Singh');
});

test('buildPeopleIndex skips rows with no name', () => {
    const index = buildPeopleIndex([{ id: '1', email: 'x@y.z' }, null, undefined]);
    assert.equal(index.size, 0);
});

test('senderName shows staff by role, never by personal address', () => {
    const people = buildPeopleIndex([]);
    assert.equal(senderName({ sender_role: 'admin', sender_id: 'coordinator@example.edu' }, people), 'Coordinator');
    assert.equal(senderName({ sender_role: 'mentor', sender_id: 'm@example.edu' }, people), 'Mentor');
    assert.equal(senderName({ sender_role: 'panel', sender_id: 'p@example.edu' }, people), 'Panel');
});

test('senderName names a student from the index', () => {
    const people = buildPeopleIndex([
        { id: '2415500262', name: 'Kushagra Kulshrestha', email: 'kushagra.kulshrestha_cs.aiml24@example.edu' },
    ]);
    assert.equal(
        senderName({ sender_role: 'student', sender_id: 'kushagra.kulshrestha_cs.aiml24@example.edu' }, people),
        'Kushagra Kulshrestha',
    );
});

test('senderName matches a student regardless of address casing', () => {
    const people = buildPeopleIndex([{ id: '1', name: 'Bharti Singh', email: 'bharti@example.edu' }]);
    assert.equal(senderName({ sender_role: 'student', sender_id: 'Bharti@example.edu' }, people), 'Bharti Singh');
});

test('senderName falls back to the address when the student is unknown', () => {
    const people = buildPeopleIndex([]);
    assert.equal(
        senderName({ sender_role: 'student', sender_id: 'venu.gopal_cs.aiml24@example.edu' }, people),
        'Venu Gopal',
    );
});

test('senderName prefers a name the backend resolved over any local guess', () => {
    const people = buildPeopleIndex([{ id: '1', name: 'Stale Name', email: 'a@b.c' }]);
    assert.equal(
        senderName({ sender_role: 'student', sender_id: 'a@b.c', sender_name: 'Yashi' }, people),
        'Yashi',
    );
});

test('senderName ignores a blank supplied name and falls back', () => {
    const people = buildPeopleIndex([{ id: '1', name: 'Bharti Singh', email: 'a@b.c' }]);
    assert.equal(
        senderName({ sender_role: 'student', sender_id: 'a@b.c', sender_name: '   ' }, people),
        'Bharti Singh',
    );
});

test('senderName degrades to a role label rather than showing nothing', () => {
    assert.equal(senderName({ sender_role: 'student', sender_id: '' }, new Map()), 'Student');
    assert.equal(senderName({}, new Map()), 'Student');
});

test('deliveryState reports an in-flight message as sending', () => {
    assert.equal(deliveryState({ status: 'sending' }), DELIVERY.SENDING);
});

test('deliveryState reports a rejected message as failed', () => {
    assert.equal(deliveryState({ status: 'failed' }), DELIVERY.FAILED);
});

test('deliveryState treats the sender in read_by as not yet read', () => {
    // read_by is seeded with the sender's own id at insert, so their presence
    // there must never count as somebody having read the message.
    const message = { sender_id: 'me@example.edu', read_by: ['me@example.edu'] };
    assert.equal(deliveryState(message), DELIVERY.SENT);
});

test('deliveryState reports read once another party appears in read_by', () => {
    const message = { sender_id: 'me@example.edu', read_by: ['me@example.edu', 'them@example.edu'] };
    assert.equal(deliveryState(message), DELIVERY.READ);
});

test('deliveryState ignores casing and padding when comparing readers', () => {
    const message = { sender_id: 'Me@example.edu', read_by: ['  me@example.edu  '] };
    assert.equal(deliveryState(message), DELIVERY.SENT);
});

test('deliveryState treats a missing or malformed read_by as unread', () => {
    assert.equal(deliveryState({ sender_id: 'a@b.c' }), DELIVERY.SENT);
    assert.equal(deliveryState({ sender_id: 'a@b.c', read_by: null }), DELIVERY.SENT);
    assert.equal(deliveryState({ sender_id: 'a@b.c', read_by: 'nonsense' }), DELIVERY.SENT);
});

test('deliveryState ignores blank entries in read_by', () => {
    const message = { sender_id: 'a@b.c', read_by: ['', '   ', null] };
    assert.equal(deliveryState(message), DELIVERY.SENT);
});

test('mergeTimeline puts confirmed messages before pending ones', () => {
    const rows = mergeTimeline(
        [{ id: 7, body: 'first' }],
        [{ id: 'tmp-1', body: 'second', status: 'sending' }],
    );
    assert.deepEqual(rows.map(r => r.body), ['first', 'second']);
    assert.deepEqual(rows.map(r => r.rowKey), ['m-7', 'tmp-1']);
});

test('mergeTimeline reuses the optimistic key so the bubble does not remount', () => {
    const keyMap = new Map([[7, 'tmp-1']]);
    const rows = mergeTimeline([{ id: 7, body: 'hi' }], [], keyMap);
    assert.equal(rows[0].rowKey, 'tmp-1');
});

test('mergeTimeline drops a pending message whose key a confirmed one claimed', () => {
    // The exact production failure: the outbox still held tmp-1 after the
    // server echoed it back, so both rendered under the key tmp-1.
    const keyMap = new Map([[7, 'tmp-1']]);
    const rows = mergeTimeline(
        [{ id: 7, body: 'hi' }],
        [{ id: 'tmp-1', body: 'hi', status: 'sending' }],
        keyMap,
    );
    assert.equal(rows.length, 1);
    assert.equal(rows[0].status, DELIVERY.SENT);
});

test('mergeTimeline never emits a duplicate key', () => {
    const keyMap = new Map([[1, 'tmp-a'], [2, 'tmp-b']]);
    const rows = mergeTimeline(
        [{ id: 1 }, { id: 2 }],
        [{ id: 'tmp-a' }, { id: 'tmp-b' }, { id: 'tmp-c' }],
        keyMap,
    );
    const keys = rows.map(r => r.rowKey);
    assert.equal(new Set(keys).size, keys.length);
    assert.deepEqual(keys, ['tmp-a', 'tmp-b', 'tmp-c']);
});

test('mergeTimeline keeps a pending message its own status', () => {
    const rows = mergeTimeline([], [{ id: 'tmp-1', status: 'failed' }]);
    assert.equal(rows[0].status, 'failed');
});

test('mergeTimeline tolerates empty and missing input', () => {
    assert.deepEqual(mergeTimeline(), []);
    assert.deepEqual(mergeTimeline([], []), []);
});
