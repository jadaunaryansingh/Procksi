import test from 'node:test';
import assert from 'node:assert/strict';
import {
    normalizeName,
    compactName,
    identityMatchesMember,
    attributeCommits,
    extractContributors,
} from '../src/lib/memberCommits.js';

// Shapes taken from a real analyser report (team T117).
const CONTRIBUTORS = [
    { contributorName: 'Aryan Singh Jadaun', commits: 76, percentage: 98.7 },
    { contributorName: 'jadaunaryansingh', commits: 1, percentage: 1.3 },
];

const MEMBERS = [
    { id: '2415500130', name: 'Aryan Singh Jadaun', roll: '2415500130', github_username: 'jadaunaryansingh' },
    { id: '2415500158', name: 'Samarth Verma', roll: '2415500158' },
];

test('normalizeName lowercases and collapses separators', () => {
    assert.equal(normalizeName('  Aryan_Singh-Jadaun '), 'aryan singh jadaun');
    assert.equal(normalizeName(null), '');
});

test('compactName strips whitespace so squashed logins can match', () => {
    assert.equal(compactName('Aryan Singh'), 'aryansingh');
});

test('an explicit github_username matches its identity', () => {
    assert.equal(identityMatchesMember('jadaunaryansingh', MEMBERS[0]), true);
});

test('a display name matches the member name', () => {
    assert.equal(identityMatchesMember('Aryan Singh Jadaun', MEMBERS[0]), true);
});

test('a squashed login matches a spaced name', () => {
    assert.equal(identityMatchesMember('samarthverma', MEMBERS[1]), true);
});

test('an unrelated identity matches nobody, and blanks never match', () => {
    assert.equal(identityMatchesMember('someoneelse', MEMBERS[0]), false);
    assert.equal(identityMatchesMember('', MEMBERS[0]), false);
    assert.equal(identityMatchesMember('x', { name: null }), false);
});

test('both identities of one student are summed onto that student', () => {
    const { byMember, totalCommits, attributedCommits } = attributeCommits(CONTRIBUTORS, MEMBERS);
    const aryan = byMember.get('2415500130');
    assert.equal(aryan.commits, 77);
    assert.deepEqual(aryan.identities, ['Aryan Singh Jadaun', 'jadaunaryansingh']);
    assert.equal(totalCommits, 77);
    assert.equal(attributedCommits, 77);
});

test('a member with no commits reports zero rather than being absent', () => {
    const { byMember } = attributeCommits(CONTRIBUTORS, MEMBERS);
    assert.equal(byMember.get('2415500158').commits, 0);
    assert.equal(byMember.get('2415500158').percentage, 0);
});

test('percentages are of the repository total', () => {
    const { byMember } = attributeCommits(
        [{ contributorName: 'Aryan Singh Jadaun', commits: 3 }, { contributorName: 'Samarth Verma', commits: 1 }],
        MEMBERS,
    );
    assert.equal(byMember.get('2415500130').percentage, 75);
    assert.equal(byMember.get('2415500158').percentage, 25);
});

test('identities matching nobody are reported separately, not silently dropped', () => {
    const { unattributed, totalCommits, attributedCommits } = attributeCommits(
        [{ contributorName: 'dependabot[bot]', commits: 9 }, { contributorName: 'Samarth Verma', commits: 1 }],
        MEMBERS,
    );
    assert.deepEqual(unattributed, [{ contributorName: 'dependabot[bot]', commits: 9 }]);
    assert.equal(totalCommits, 10);
    assert.equal(attributedCommits, 1);
});

test('attributeCommits tolerates missing or malformed input', () => {
    const empty = attributeCommits(null, MEMBERS);
    assert.equal(empty.totalCommits, 0);
    assert.equal(empty.byMember.get('2415500130').commits, 0);
    assert.deepEqual(attributeCommits(CONTRIBUTORS, null).unattributed.length, 2);
});

test('extractContributors reads both schema shapes and survives junk', () => {
    assert.equal(extractContributors({ commits: { contributors: CONTRIBUTORS } }).length, 2);
    assert.equal(extractContributors({ commits: { contributionDistribution: CONTRIBUTORS } }).length, 2);
    assert.equal(extractContributors(JSON.stringify({ commits: { contributors: CONTRIBUTORS } })).length, 2);
    assert.deepEqual(extractContributors('not json'), []);
    assert.deepEqual(extractContributors(null), []);
    assert.deepEqual(extractContributors({ commits: 5 }), []);
});
