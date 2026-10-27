import test from 'node:test';
import assert from 'node:assert/strict';
import {
    CHANNELS,
    channelById,
    isValidChannel,
    resolveRecipients,
    describeRecipients,
} from '../src/lib/procksiChatChannels.js';

const sources = {
    mentors: [{ id: 'M-1', name: 'Preshit' }, { id: 'M-2', name: 'Asha' }],
    students: [{ id: '2415500148', name: 'Devang' }],
    panels: [{ id: 'P-1', name: 'Anushka' }],
    teams: [{ id: 'T-1', title: 'AuthPulse' }, { id: 'T-2', title: 'Echo' }],
};

test('CHANNELS has exactly the three spec channels in order', () => {
    assert.deepEqual(CHANNELS.map(c => c.id), ['mentor_student', 'panel_team', 'all']);
});

test('isValidChannel accepts known ids and rejects anything else', () => {
    assert.equal(isValidChannel('panel_team'), true);
    assert.equal(isValidChannel('mentor'), false);
    assert.equal(isValidChannel(null), false);
});

test('channelById falls back to the first channel for unknown ids', () => {
    assert.equal(channelById('all').id, 'all');
    assert.equal(channelById('nope').id, 'mentor_student');
    assert.equal(channelById(undefined).id, 'mentor_student');
});

test('mentor_student resolves mentors and students only', () => {
    const r = resolveRecipients('mentor_student', sources);
    assert.equal(r.mentors.length, 2);
    assert.equal(r.students.length, 1);
    assert.equal(r.panels.length, 0);
    assert.equal(r.teams.length, 0);
    assert.equal(r.total, 3);
});

test('panel_team resolves panels and teams only', () => {
    const r = resolveRecipients('panel_team', sources);
    assert.equal(r.panels.length, 1);
    assert.equal(r.teams.length, 2);
    assert.equal(r.mentors.length, 0);
    assert.equal(r.students.length, 0);
    assert.equal(r.total, 3);
});

test('all resolves every source', () => {
    const r = resolveRecipients('all', sources);
    assert.equal(r.total, 6);
});

test('resolveRecipients tolerates missing and empty sources', () => {
    const r = resolveRecipients('all', {});
    assert.deepEqual(r.mentors, []);
    assert.equal(r.total, 0);
});

test('unknown channel resolves as the fallback channel, never throws', () => {
    const r = resolveRecipients('bogus', sources);
    assert.equal(r.total, 3);
});

test('describeRecipients lists non-empty groups only, in a stable order', () => {
    assert.equal(describeRecipients(resolveRecipients('panel_team', sources)), '1 panel, 2 teams');
    assert.equal(describeRecipients(resolveRecipients('mentor_student', sources)), '2 mentors, 1 student');
    assert.equal(describeRecipients(resolveRecipients('all', {})), 'no recipients');
});
