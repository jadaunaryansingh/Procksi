export const PS_TEAM_CAPACITY = 2;

export function normalizePsTitle(title) {
    return (title || '').trim().toLowerCase();
}

export function buildAllocationsByTitle(teams, getHasAllocated) {
    const map = new Map();
    for (const team of teams) {
        if (!team.title || !getHasAllocated(team)) continue;
        const key = normalizePsTitle(team.title);
        if (key === '' || key === 'custom team') continue;
        const existing = map.get(key);
        if (existing) existing.push(team);
        else map.set(key, [team]);
    }
    return map;
}

export function isPsAvailableForTeam(allocationsByTitle, psTitle, teamId, capacity = PS_TEAM_CAPACITY) {
    const holders = allocationsByTitle.get(normalizePsTitle(psTitle)) || [];
    if (holders.some(t => t.id === teamId)) return true;
    return holders.length < capacity;
}

export function computeBulkAllocations({ priorityTeams, randomTeams, problemStatements, titleCounts, capacity = PS_TEAM_CAPACITY }) {
    const assignments = new Map();

    const availableForYear = (year, ceiling) => problemStatements.filter(ps => {
        const matchesYear = (ps.year === null || ps.year === undefined || Number(ps.year) === Number(year));
        if (!matchesYear) return false;
        const count = titleCounts.get(normalizePsTitle(ps.title)) || 0;
        return count < ceiling;
    });

    const hasPreferences = (item) => item.prefRecord && Array.isArray(item.prefRecord.preferences) && item.prefRecord.preferences.length > 0;

    const tryAssignFromPreferences = (item, ceiling) => {
        for (const pref of item.prefRecord.preferences) {
            const prefTitle = normalizePsTitle(pref.title);
            const count = titleCounts.get(prefTitle) || 0;
            if (count >= ceiling) continue;
            const matchedPS = problemStatements.find(ps => normalizePsTitle(ps.title) === prefTitle);
            const matchesYear = !matchedPS || matchedPS.year === null || matchedPS.year === undefined || Number(matchedPS.year) === Number(item.teamYear);
            if (!matchesYear) continue;
            titleCounts.set(prefTitle, count + 1);
            assignments.set(item, { title: pref.title, description: pref.description || '', domain: pref.domain || 'General' });
            return true;
        }
        return false;
    };

    const tryAssignRandom = (item, ceiling) => {
        const pool = availableForYear(item.teamYear, ceiling);
        if (pool.length === 0) return false;
        const chosenPS = pool[Math.floor(Math.random() * pool.length)];
        const title = normalizePsTitle(chosenPS.title);
        titleCounts.set(title, (titleCounts.get(title) || 0) + 1);
        assignments.set(item, { title: chosenPS.title, description: chosenPS.description || '', domain: chosenPS.domain || 'General' });
        return true;
    };

    // Pass 1: only PS with zero current teams (ceiling 1 => count must be < 1).
    const unresolved = [];
    for (const item of priorityTeams) {
        if (tryAssignFromPreferences(item, 1)) continue;
        if (!tryAssignRandom(item, 1)) unresolved.push(item);
    }
    for (const item of randomTeams) {
        if (!tryAssignRandom(item, 1)) unresolved.push(item);
    }

    // Pass 2: PS with one existing team may now take a second.
    for (const item of unresolved) {
        if (hasPreferences(item) && tryAssignFromPreferences(item, capacity)) continue;
        tryAssignRandom(item, capacity);
    }

    return assignments;
}
