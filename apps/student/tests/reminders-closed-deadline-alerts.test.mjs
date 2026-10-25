import test from 'node:test';
import assert from 'node:assert/strict';
import { buildReminders } from '../src/lib/reminders.js';

// The deadlines API only returns a deadline while it is inside its open
// window, so anything absent from `deadlines` has closed (or never applied to
// this student). A leftover "Upcoming Deadline: ..." notification must not keep
// alerting after that -- Problem Statement Selection stayed in the reminder
// window for days after it closed.

const psNotification = {
    id: 'n1',
    title: 'Upcoming Deadline: Problem Statement Selection',
    read: false,
    created_at: '2026-08-10T00:00:00Z',
};

test('a deadline notification goes quiet once its deadline is no longer returned', () => {
    const r = buildReminders([], [], 3, {}, [psNotification]);

    assert.equal(r.alertingNotifications.length, 0,
        'closed-deadline notification should not alert');
    assert.equal(r.hasAlert, false, 'nothing left to act on');
});

test('a deadline notification still alerts while its deadline is open and unmet', () => {
    const openDeadline = {
        id: 'deadline-problemStatementSelection',
        name: 'problemStatementSelection',
        deadline_date: '2026-12-01T23:59:00+05:30',
        days_remaining: 5,
        is_past: false,
    };

    const r = buildReminders([openDeadline], [], 3, {}, [psNotification]);

    assert.equal(r.alertingNotifications.length, 1,
        'an open, unmet deadline should still alert');
    assert.equal(r.hasAlert, true);
});

test('a deadline notification goes quiet once its deadline is met', () => {
    const openDeadline = {
        id: 'deadline-teamFormation',
        name: 'teamFormation',
        deadline_date: '2026-12-01T23:59:00+05:30',
        days_remaining: 5,
        is_past: false,
    };
    const teamNotification = {
        id: 'n2',
        title: 'Upcoming Deadline: Team Formation',
        read: false,
        created_at: '2026-08-10T00:00:00Z',
    };

    const r = buildReminders([openDeadline], [], 3, { teamFormation: true }, [teamNotification]);

    assert.equal(r.alertingNotifications.length, 0, 'met deadline should not alert');
});

test('non-deadline notifications still follow the ordinary unread rule', () => {
    const invite = { id: 'n3', title: 'Team invitation from Asha', read: false, created_at: '2026-08-10T00:00:00Z' };

    const r = buildReminders([], [], 3, {}, [invite]);

    assert.equal(r.alertingNotifications.length, 1,
        'an unread non-deadline notification is unaffected by deadline filtering');
});

// The bell dot in TopNav is driven by the same filtered set as the alert
// button, so a closed deadline must not keep it lit either.
test('the bell dot set excludes closed-deadline notifications but keeps real ones', () => {
    const closedPs = { id: 'n1', title: 'Deadline Updated: Problem Statement Selection', read: false, created_at: '2026-08-10T00:00:00Z' };
    const invite = { id: 'n2', title: 'Team invitation from Asha', read: false, created_at: '2026-08-12T00:00:00Z' };

    const onlyStale = buildReminders([], [], 3, {}, [closedPs], Number.MAX_SAFE_INTEGER);
    assert.equal(onlyStale.alertingNotifications.length, 0, 'dot should be grey');

    const withReal = buildReminders([], [], 3, {}, [closedPs, invite], Number.MAX_SAFE_INTEGER);
    assert.deepEqual(withReal.alertingNotifications.map((n) => n.id), ['n2'],
        'only the genuine unread notification should light the dot');
});

test('raising maxNotifications does not cap the set the dot is derived from', () => {
    const many = Array.from({ length: 6 }, (_, i) => ({
        id: `n${i}`, title: `Team invitation ${i}`, read: false,
        created_at: `2026-08-1${i}T00:00:00Z`,
    }));

    const capped = buildReminders([], [], 3, {}, many);
    const uncapped = buildReminders([], [], 3, {}, many, Number.MAX_SAFE_INTEGER);

    assert.equal(capped.alertingNotifications.length, 3, 'render cap still applies by default');
    assert.equal(uncapped.alertingNotifications.length, 6, 'the dot sees every alerting row');
});

// "New Evaluation Cycle" notifications carry their deadline inside the message
// body and never matched the deadline-reminder title prefix, so they alerted
// forever. 886 of the 946 unread rows in production had a deadline already in
// the past.
test('a notification whose embedded deadline has passed stops alerting', () => {
    const stale = {
        id: 'e1', read: false, created_at: '2026-08-19T20:29:45Z',
        title: 'New Evaluation Cycle',
        message: "A new evaluation cycle 'Mid-Term Presentation' has been scheduled. Deadline: 2026-08-19T20:29:45.749Z",
    };

    const r = buildReminders([], [], 3, {}, [stale], Number.MAX_SAFE_INTEGER);

    assert.equal(r.alertingNotifications.length, 0);
    assert.equal(r.hasAlert, false, 'alert button greys out');
    assert.equal(r.hasContent, false, 'window does not auto-open with nothing to show');
});

test('a notification whose embedded deadline is still ahead keeps alerting', () => {
    const live = {
        id: 'e2', read: false, created_at: '2026-08-19T00:00:00Z',
        title: 'New Evaluation Cycle',
        message: "A new evaluation cycle 'Final Evaluation' has been scheduled. Deadline: 2099-01-01T00:00:00.000Z",
    };

    const r = buildReminders([], [], 3, {}, [live], Number.MAX_SAFE_INTEGER);

    assert.equal(r.alertingNotifications.length, 1);
    assert.equal(r.hasAlert, true);
});

test('a notification with no parseable deadline is left alone', () => {
    // "cannot tell" must not silence a row -- these have no expiry to apply.
    const noDeadline = {
        id: 'e3', read: false, created_at: '2026-08-19T00:00:00Z',
        title: 'New Evaluation Cycle',
        message: "A new evaluation cycle 'Proposal Evaluation' has been scheduled.",
    };
    const tbd = {
        id: 'e4', read: false, created_at: '2026-08-19T00:00:00Z',
        title: 'New Evaluation Cycle',
        message: "A new evaluation cycle 'X' has been scheduled. Deadline: TBD",
    };

    const r = buildReminders([], [], 3, {}, [noDeadline, tbd], Number.MAX_SAFE_INTEGER);

    assert.equal(r.alertingNotifications.length, 2,
        'without a usable date the row keeps its ordinary unread behaviour');
});
