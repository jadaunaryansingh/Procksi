// Client-side aggregation for the Analysis dashboard.
// Takes the raw rows from /api/admin/analysis/data plus the global-filter
// `filterRows` fn, applies the SAME filtering the rest of the admin app uses,
// then computes every number the Analysis page charts. Output shape matches
// what Analysis.jsx renders, so changing the top Filter Bar just re-runs this.

const num = (v) => {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
};

const mentorNames = (v) => {
    if (!v) return [];
    if (Array.isArray(v)) return v.map((x) => String(x).trim()).filter(Boolean);
    const s = String(v).trim();
    if (s.startsWith('[')) {
        try { return JSON.parse(s).map((x) => String(x).trim()).filter(Boolean); } catch { /* fall through */ }
    }
    return s ? [s] : [];
};

const avg = (arr) => {
    const v = arr.filter((x) => x !== null && x !== undefined);
    return v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 10) / 10 : null;
};

const groupCount = (rows, key, top = 8) => {
    const m = new Map();
    rows.forEach((r) => {
        const k = String(r[key] || 'Unspecified');
        m.set(k, (m.get(k) || 0) + 1);
    });
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, top).map(([label, count]) => ({ label, count }));
};

const groupAvg = (rows, key, scoreKey, top = 8) => {
    const m = new Map();
    rows.forEach((r) => {
        const s = num(r[scoreKey]);
        if (s === null) return;
        const k = String(r[key] || 'Unspecified');
        if (!m.has(k)) m.set(k, []);
        m.get(k).push(s);
    });
    return [...m.entries()]
        .map(([label, vals]) => ({ label, avg: avg(vals), count: vals.length }))
        .sort((a, b) => (b.avg || 0) - (a.avg || 0))
        .slice(0, top);
};

export function aggregateAnalysis(raw, filterRows) {
    const f = typeof filterRows === 'function' ? filterRows : (x) => x;
    const teams = f(raw.teams || []);
    const results = f(raw.results || []);
    const proposals = f(raw.proposals || []);
    const absents = f(raw.absents || []);
    const students = f(raw.students || []);
    const mentors = raw.mentors || []; // global, not semester-scoped

    // ---- KPIs ----
    const validated = teams.filter((t) => t.validationStatus === 'Valid').length;
    const incomplete = teams.filter((t) => (t.memberCount || 0) < 3).length;
    const withoutMentor = teams.filter((t) => !t.mentor).length;
    const scored = results.map((r) => num(r.totalScore)).filter((x) => x !== null);

    const kpis = {
        total_students: students.length,
        total_teams: teams.length,
        validated_teams: validated,
        incomplete_teams: incomplete,
        teams_without_mentor: withoutMentor,
        total_mentors: mentors.length,
        pending_proposals: proposals.filter((p) => p.status === 'Pending').length,
        avg_total_score: avg(scored),
        teams_evaluated: scored.length,
        teams_evaluated_pct: teams.length ? Math.round((100 * scored.length) / teams.length) : 0,
    };

    // ---- Leaderboard: top 3 scoring teams ----
    const leaderboard = results
        .filter((r) => num(r.totalScore) !== null)
        .sort((a, b) => num(b.totalScore) - num(a.totalScore))
        .slice(0, 3)
        .map((r, i) => ({
            rank: i + 1,
            team: r.team || '',
            title: r.title || '',
            score: num(r.totalScore),
            domain: r.domain || 'Unspecified',
            mentor: mentorNames(r.mentor).join(', ') || 'Unassigned',
        }));

    // ---- Performance ----
    const bands = [[0, 40], [40, 50], [50, 60], [60, 70], [70, 80], [80, 90], [90, 101]];
    const score_distribution = scored.length ? bands.map(([lo, hi]) => ({
        band: `${lo}-${Math.min(hi, 100)}`,
        label: lo === 0 ? `<${hi}` : (hi > 100 ? `${lo}+` : `${lo}-${hi}`),
        count: scored.filter((s) => s >= lo && s < hi).length,
    })) : [];

    const performance = {
        evaluated: scored.length,
        score_distribution,
        avg_by_stage: [
            { stage: 'Proposal', avg: avg(results.map((r) => num(r.proposalMarks))) },
            { stage: 'Mid', avg: avg(results.map((r) => num(r.midMarks))) },
            { stage: 'Final', avg: avg(results.map((r) => num(r.finalMarks))) },
        ],
        by_domain: groupAvg(results, 'domain', 'totalScore'),
    };

    // ---- Team health ----
    const sizeMap = new Map();
    teams.forEach((t) => { const s = t.memberCount || 0; sizeMap.set(s, (sizeMap.get(s) || 0) + 1); });
    const team_health = {
        validation_status: groupCount(teams, 'validationStatus'),
        team_size: [...sizeMap.entries()].sort((a, b) => a[0] - b[0]).map(([label, count]) => ({ label: String(label), count })),
        by_domain: groupCount(teams, 'domain'),
        incomplete_teams: incomplete,
        teams_without_mentor: withoutMentor,
    };

    // ---- Mentor load ----
    const assigned = new Map();
    teams.forEach((t) => mentorNames(t.mentor).forEach((n) => assigned.set(n, (assigned.get(n) || 0) + 1)));
    const load = mentors.map((m) => ({
        name: m.name || 'Unknown',
        assigned: assigned.get(m.name) || 0,
        capacity: Number(m.max_teams || m.maxLoad || 0) || 0,
    })).sort((a, b) => b.assigned - a.assigned);

    // ---- Proposals ----
    const decided = proposals.filter((p) => p.status === 'Approved' || p.status === 'Rejected').length;
    const approved = proposals.filter((p) => p.status === 'Approved').length;
    const proposalsBlock = {
        status: groupCount(proposals, 'status'),
        total: proposals.length,
        approval_rate: decided ? Math.round((100 * approved) / decided) : null,
        avg_ai_score: avg(proposals.map((p) => num(p.aiScore !== null && p.aiScore !== undefined ? p.aiScore : p.ai_score))),
    };

    // ---- Attendance ----
    const attendance = {
        absent_total: absents.length,
        by_reason: groupCount(absents, 'reason', 6),
    };

    return {
        kpis,
        leaderboard,
        performance,
        team_health,
        mentors: { load, unallocated_teams: withoutMentor },
        proposals: proposalsBlock,
        attendance,
    };
}
