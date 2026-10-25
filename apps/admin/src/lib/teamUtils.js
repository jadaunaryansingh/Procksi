/**
 * teamUtils.js
 * Shared helpers for displaying team data consistently across all admin portal pages.
 */
import { teamDisplayLabel, resolveTeamNumber, cleanUUIDsFromText } from './globalFilters.js';
import { teamUidOf } from './teamUid.js';
export { cleanUUIDsFromText };

/**
 * Extracts a human-readable label from a team DB id.
 * Examples:
 *   "mca-2026-T3"          → "Team 3"
 *   "2026-2027-odd-yr4-T9" → "Team 9"
 *   "TEAM-3"               → "Team 3"
 *   3                      → "Team 3"
 *   "Some Custom Name"     → "Some Custom Name"
 *
 * @param {string|number} teamId
 * @param {object|null} row
 * @param {object} semesterMap
 * @returns {string}
 */
export function teamLabel(teamId, row = null, semesterMap = {}) {
    return teamDisplayLabel(teamId, row, semesterMap);
}

/**
 * Extracts the numeric team number from a team DB id.
 * Returns null if not parseable.
 *
 * @param {string|number} teamId
 * @returns {number|null}
 */
export function teamNumber(teamId, row = null) {
    return resolveTeamNumber(teamId, row);
}

/**
 * Sort comparator for team IDs or team row objects by team number.
 * Accepts optional direction: 'asc' (1 -> N) or 'desc' (N -> 1).
 */
export function sortByTeamNumber(a, b, direction = 'asc') {
    const rowA = (a && typeof a === 'object') ? a : null;
    const rowB = (b && typeof b === 'object') ? b : null;
    const idA = rowA ? (rowA.id || rowA.uuid || rowA.teamId || a) : a;
    const idB = rowB ? (rowB.id || rowB.uuid || rowB.teamId || b) : b;

    const na = teamDisplayLabel ? resolveTeamNumber(idA, rowA) : teamNumber(idA);
    const nb = teamDisplayLabel ? resolveTeamNumber(idB, rowB) : teamNumber(idB);

    if (na === null && nb === null) return 0;
    if (na === null) return 1;
    if (nb === null) return -1;

    return direction === 'desc' ? nb - na : na - nb;
}

/**
 * Resolves the correct team object for a given proposal object from a list of teams.
 * Avoids cross-batch/cross-semester false matches by enforcing strict matching priorities:
 * 1. Exact ID match (t.id === proposal.teamId)
 * 2. Case-insensitive exact ID match
 * 3. Prefix/Suffix match within the same semester or structure
 * 4. Proposal leader/member name match
 * 5. Semester-scoped numeric team number match
 * 6. Unique global numeric match (only if single team matches across all data)
 *
 * @param {object} proposal - The proposal object
 * @param {Array} teamsData - List of team objects
 * @param {object} semesterMap - Map of semester configs (optional)
 * @returns {object|null} Matched team object or null
 */
export function findMatchingTeam(proposal, teamsData = [], _semesterMap = {}) {
    if (!proposal || !Array.isArray(teamsData) || teamsData.length === 0) return null;

    // Canonical path: exact team_uid. A uuid is stable and globally unique, so
    // when the proposal carries one this is authoritative and the fuzzy cascade
    // below is skipped entirely. This is the match that stops one team's
    // proposal being attached to another team that shares a number.
    const propUid = teamUidOf(proposal);
    if (propUid) {
        const byUid = teamsData.find((t) => teamUidOf(t) === propUid);
        if (byUid) return byUid;
    }

    const teamId = String(proposal.team_id || proposal.teamId || '').trim();
    const propSemId = String(proposal.semester_id || proposal.semesterId || '').trim();

    // 1. Direct exact ID match
    if (teamId) {
        let found = teamsData.find(t => String(t.id).trim() === teamId);
        if (found) return found;

        // 2. Case-insensitive exact ID match
        found = teamsData.find(t => String(t.id).trim().toLowerCase() === teamId.toLowerCase());
        if (found) return found;

        // 3. Match by team ID suffix/prefix (e.g., proposal teamId="T-4" or "TEAM-4", team id="2025-2026-even-yr3-T4")
        const cleanTeamId = teamId.replace(/^TEAM-/i, '').replace(/^T-?/i, '');
        if (cleanTeamId) {
            found = teamsData.find(t => {
                const tId = String(t.id || '');
                const tSemId = String(t.semester_id || '');
                if (propSemId && tSemId && tSemId !== propSemId) return false;
                return tId.endsWith(`-T${cleanTeamId}`) || 
                       tId.endsWith(`-TEAM-${cleanTeamId}`) || 
                       tId.endsWith(`_T${cleanTeamId}`) || 
                       tId.endsWith(`_TEAM_${cleanTeamId}`) ||
                       tId.endsWith(`-${cleanTeamId}`) ||
                       (tId.toLowerCase().includes(teamId.toLowerCase()) && (!propSemId || tSemId === propSemId));
            });
            if (found) return found;
        }
    }

    // 4. Leader or member name matching if proposal contains leader/author info
    const proposalLeader = String(proposal.leader || proposal.submitted_by || proposal.author || proposal.student_name || '').trim().toLowerCase();
    if (proposalLeader) {
        let found = teamsData.find(t => {
            const tSemId = String(t.semester_id || '');
            if (propSemId && tSemId && tSemId !== propSemId) return false;
            const leaderName = String(t.leader || '').trim().toLowerCase();
            if (leaderName && (leaderName.includes(proposalLeader) || proposalLeader.includes(leaderName))) return true;
            
            const members = Array.isArray(t.members) ? t.members : [];
            return members.some(m => {
                const mName = typeof m === 'string' ? m : (m.name || m.student?.name || '');
                return String(mName).trim().toLowerCase().includes(proposalLeader);
            });
        });
        if (found) return found;
    }

    // 5. Semester-scoped numeric team number match (STRICT: only within the same semester!)
    if (propSemId && teamId) {
        const candidateTeams = teamsData.filter(t => String(t.semester_id || '') === propSemId);
        const propTeamNum = resolveTeamNumber(teamId, proposal);
        if (propTeamNum !== null && candidateTeams.length > 0) {
            let found = candidateTeams.find(t => resolveTeamNumber(t.id, t) === propTeamNum);
            if (found) return found;
        }
    }

    // 6. Global numeric match ONLY if no semester conflict exists (i.e. unique match across entire dataset)
    if (teamId) {
        const propTeamNum = resolveTeamNumber(teamId, proposal);
        if (propTeamNum !== null) {
            const matches = teamsData.filter(t => resolveTeamNumber(t.id, t) === propTeamNum);
            if (matches.length === 1) {
                return matches[0];
            }
        }
    }

    return null;
}

