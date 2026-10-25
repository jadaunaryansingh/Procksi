/**
 * memberCommits.js
 *
 * Attributes repository commits to individual team members.
 *
 * The external analyser reports commits per GIT IDENTITY, not per student, and
 * one student routinely appears under several identities — a display name from
 * their git config plus their GitHub login, e.g.:
 *
 *   { contributorName: 'Aryan Singh Jadaun', commits: 76 }
 *   { contributorName: 'jadaunaryansingh',   commits: 1  }
 *
 * Both are the same person. Attribution therefore matches on several signals
 * and SUMS every identity that resolves to the same student, rather than
 * picking one.
 *
 * Pure module: no React, no network, no imports.
 */

export function normalizeName(value) {
    return String(value ?? '')
        .toLowerCase()
        .replace(/[._-]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

/** "jadaunaryansingh" -> "jadaunaryansingh"; "Aryan Singh" -> "aryansingh" */
export function compactName(value) {
    return normalizeName(value).replace(/\s/g, '');
}

/**
 * Does this git identity belong to this member?
 * Ordered strongest signal first — an explicit github_username always wins.
 */
export function identityMatchesMember(contributorName, member) {
    const identity = String(contributorName ?? '').trim();
    if (!identity) return false;

    const handle = member?.github_username || member?.github;
    if (handle && normalizeName(handle) === normalizeName(identity)) return true;

    const name = member?.name;
    if (!name) return false;

    // Exact display-name match, then whitespace-insensitive (covers logins
    // written as a squashed full name).
    if (normalizeName(name) === normalizeName(identity)) return true;
    if (compactName(name) === compactName(identity)) return true;

    return false;
}

/**
 * @returns {{
 *   byMember: Map<string, {commits:number, percentage:number, identities:string[]}>,
 *   unattributed: Array<{contributorName:string, commits:number}>,
 *   totalCommits: number,
 *   attributedCommits: number
 * }}
 * Keyed by each member's id (falling back to roll, then name).
 */
export function attributeCommits(contributors, members) {
    const list = Array.isArray(contributors) ? contributors : [];
    const people = Array.isArray(members) ? members : [];

    const keyOf = (m) => String(m?.id ?? m?.roll ?? m?.name ?? '');
    const byMember = new Map(people.map(m => [keyOf(m), { commits: 0, percentage: 0, identities: [] }]));
    const unattributed = [];

    let totalCommits = 0;
    let attributedCommits = 0;

    for (const c of list) {
        const identity = c?.contributorName ?? c?.name ?? '';
        const commits = Number(c?.commits) || 0;
        totalCommits += commits;

        const owner = people.find(m => identityMatchesMember(identity, m));
        if (!owner) {
            unattributed.push({ contributorName: String(identity), commits });
            continue;
        }
        const entry = byMember.get(keyOf(owner));
        entry.commits += commits;
        entry.identities.push(String(identity));
        attributedCommits += commits;
    }

    // Percentages are of the repository total, so they stay comparable even
    // when some commits could not be attributed to anyone.
    if (totalCommits > 0) {
        for (const entry of byMember.values()) {
            entry.percentage = Math.round((entry.commits / totalCommits) * 1000) / 10;
        }
    }

    return { byMember, unattributed, totalCommits, attributedCommits };
}

/**
 * Pulls the contributor array out of an analyser report, tolerating both
 * schema shapes the analyser has produced.
 */
export function extractContributors(rawReport) {
    let report = rawReport;
    if (typeof report === 'string') {
        try { report = JSON.parse(report); } catch { return []; }
    }
    const commits = report?.commits;
    if (!commits || typeof commits !== 'object') return [];
    const list = commits.contributors || commits.contributionDistribution || [];
    return Array.isArray(list) ? list : [];
}
