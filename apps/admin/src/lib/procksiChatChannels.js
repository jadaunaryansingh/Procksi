/**
 * procksiChatChannels.js
 *
 * Pure channel/recipient logic for the Procksi Chat conversations dashboard.
 * No React, no network, no imports — so it can be unit-tested directly.
 *
 * A conversation's channel is fixed at creation. Changing audience means
 * starting a new conversation, so a recipient added later can never read
 * messages they were not addressed in.
 */

export const CHANNELS = [
    { id: 'mentor_student', label: 'Mentors & Students', roles: ['mentor', 'student'] },
    { id: 'panel_team', label: 'Panels & Teams', roles: ['panel', 'student'] },
    { id: 'all', label: 'All Portals', roles: ['mentor', 'student', 'panel'] },
];

export function isValidChannel(id) {
    return CHANNELS.some((c) => c.id === id);
}

export function channelById(id) {
    return CHANNELS.find((c) => c.id === id) || CHANNELS[0];
}

const GROUPS_BY_CHANNEL = {
    mentor_student: ['mentors', 'students'],
    panel_team: ['panels', 'teams'],
    all: ['mentors', 'students', 'panels', 'teams'],
};

export function resolveRecipients(channelId, sources = {}) {
    const channel = channelById(channelId);
    const wanted = GROUPS_BY_CHANNEL[channel.id];
    const pick = (key) => (wanted.includes(key) && Array.isArray(sources[key]) ? sources[key] : []);

    const resolved = {
        mentors: pick('mentors'),
        students: pick('students'),
        panels: pick('panels'),
        teams: pick('teams'),
    };
    resolved.total = resolved.mentors.length + resolved.students.length
        + resolved.panels.length + resolved.teams.length;
    return resolved;
}

const LABELS = [
    ['mentors', 'mentor'],
    ['students', 'student'],
    ['panels', 'panel'],
    ['teams', 'team'],
];

export function describeRecipients(resolved) {
    const parts = LABELS
        .filter(([key]) => resolved[key].length > 0)
        .map(([key, noun]) => {
            const n = resolved[key].length;
            return `${n} ${noun}${n === 1 ? '' : 's'}`;
        });
    return parts.length ? parts.join(', ') : 'no recipients';
}
