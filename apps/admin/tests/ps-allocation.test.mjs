import test from 'node:test';
import assert from 'node:assert/strict';
import {
    PS_TEAM_CAPACITY,
    normalizePsTitle,
    buildAllocationsByTitle,
    isPsAvailableForTeam,
    computeBulkAllocations,
} from '../src/lib/psAllocation.js';

test('PS_TEAM_CAPACITY is 2', () => {
    assert.equal(PS_TEAM_CAPACITY, 2);
});

test('normalizePsTitle trims and lower-cases', () => {
    assert.equal(normalizePsTitle('  Smart Grid  '), 'smart grid');
    assert.equal(normalizePsTitle(null), '');
});

test('buildAllocationsByTitle groups allocated teams by normalized title and skips unallocated/placeholder ones', () => {
    const teams = [
        { id: 't1', title: 'Smart Grid' },
        { id: 't2', title: ' smart grid ' },
        { id: 't3', title: 'Team 12' },
        { id: 't4', title: '' },
    ];
    const getHasAllocated = (t) => t.id === 't1' || t.id === 't2';
    const map = buildAllocationsByTitle(teams, getHasAllocated);
    assert.deepEqual(map.get('smart grid').map(t => t.id), ['t1', 't2']);
    assert.equal(map.has('team 12'), false);
    assert.equal(map.has(''), false);
});

test('isPsAvailableForTeam allows a 2nd team, blocks a 3rd, and always allows the current holder', () => {
    const oneHolder = buildAllocationsByTitle([{ id: 't1', title: 'Smart Grid' }], () => true);
    assert.equal(isPsAvailableForTeam(oneHolder, 'Smart Grid', 't2'), true);

    const twoHolders = buildAllocationsByTitle(
        [{ id: 't1', title: 'Smart Grid' }, { id: 't2', title: 'Smart Grid' }],
        () => true,
    );
    assert.equal(isPsAvailableForTeam(twoHolders, 'Smart Grid', 't3'), false);
    assert.equal(isPsAvailableForTeam(twoHolders, 'Smart Grid', 't1'), true);
});

test('computeBulkAllocations spreads across distinct PS before doubling any of them up', () => {
    const problemStatements = [
        { title: 'PS A', year: 3 },
        { title: 'PS B', year: 3 },
    ];
    const teams = ['t1', 't2', 't3', 't4'].map(id => ({ id, prefRecord: null, teamYear: 3 }));
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });

    assert.equal(assignments.size, 4);
    const tally = new Map();
    for (const item of teams) {
        const title = assignments.get(item).title;
        tally.set(title, (tally.get(title) || 0) + 1);
    }
    assert.deepEqual([...tally.values()].sort(), [2, 2]);
});

test('computeBulkAllocations leaves teams unallocated once every PS is at capacity', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }];
    const teams = ['t1', 't2', 't3'].map(id => ({ id, prefRecord: null, teamYear: 3 }));
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });
    assert.equal(assignments.size, 2);
});

test('computeBulkAllocations honors a priority team preference before any random fallback', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }, { title: 'PS B', year: 3 }];
    const priorityItem = { id: 'p1', prefRecord: { preferences: [{ title: 'PS B' }], updated_at: null }, teamYear: 3 };
    const titleCounts = new Map();
    const assignments = computeBulkAllocations({ priorityTeams: [priorityItem], randomTeams: [], problemStatements, titleCounts });
    assert.equal(assignments.get(priorityItem).title, 'PS B');
});

test('computeBulkAllocations only assigns a 2nd team to a PS once no zero-count PS remains for that team', () => {
    const problemStatements = [{ title: 'PS A', year: 3 }];
    const titleCounts = new Map([['ps a', 1]]);
    const teams = [{ id: 't1', prefRecord: null, teamYear: 3 }];
    const assignments = computeBulkAllocations({ priorityTeams: [], randomTeams: teams, problemStatements, titleCounts });
    assert.equal(assignments.get(teams[0]).title, 'PS A');
    assert.equal(titleCounts.get('ps a'), 2);
});
test('priority team uses an empty PS before doubling its occupied preference', () => {
    const priorityItem = { teamYear: 3, prefRecord: { preferences: [{ title: 'PS A' }] } };
    const statements = [
        { title: 'PS A', year: 3 },
        { title: 'PS B', year: 3 },
    ];
    const counts = new Map([['ps a', 1]]);

    const assignments = computeBulkAllocations({
        priorityTeams: [priorityItem], randomTeams: [], problemStatements: statements, titleCounts: counts,
    });

    assert.equal(assignments.get(priorityItem).title, 'PS B');
});