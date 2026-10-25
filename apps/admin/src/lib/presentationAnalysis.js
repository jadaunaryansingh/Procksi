// Aggregations for the presentation-focused Analysis views (Ideation Round / Mid Term / End Term).
// Every number is derived from the RAW rows of /api/admin/analysis/data — no dummy
// data. Marks-based widgets read the mark column for the selected presentation
// (P1=proposalMarks, P2=midMarks, P3=finalMarks) and stay empty until real marks
// exist. Panel/GitHub widgets read the evaluations / github_agent_analysis rows.

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

// Sum the per-criterion marks stored in evaluations.scores_json (e.g. {"q1":8,...}).
const evalTotal = (scores) => {
    let obj = scores;
    if (typeof obj === 'string') { try { obj = JSON.parse(obj); } catch { return null; } }
    if (!obj || typeof obj !== 'object') return null;
    const vals = Object.values(obj).map(Number).filter(Number.isFinite);
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) * 10) / 10 : null;
};

// Composite GitHub score from the agent's five sub-scores (0-10 each -> /10 avg).
const ghComposite = (g) => {
    const keys = ['quality_score', 'security_score', 'originality_score', 'architecture_score', 'documentation_score'];
    const vals = keys.map((k) => num(g[k])).filter((v) => v !== null);
    return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10 : null;
};

export const MARKS_KEYS = ['proposalMarks', 'midMarks', 'finalMarks'];
export const PRESENTATION_LABELS = ['Ideation Round', 'Mid Term', 'End Term'];

const CRITICAL_RE = /gap|weak|concern|poor|missing|lack|risk|delay|incomplete|fail|behind|unclear/i;

export function aggregatePresentation(raw, filterRows, presIndex = 0, search = '') {
    const f = typeof filterRows === 'function' ? filterRows : (x) => x;
    const marksKey = MARKS_KEYS[presIndex] ?? MARKS_KEYS[0];
    const q = String(search || '').trim().toLowerCase();
    const match = (...vals) => !q || vals.some((v) => String(v ?? '').toLowerCase().includes(q));

    const teams = f(raw.teams || []);
    const results = f(raw.results || []);
    const students = f(raw.students || []);
    const absents = f(raw.absents || []);
    const evaluations = raw.evaluations || []; // unscoped (may carry null semester_id)
    const panels = raw.panels || [];
    const github = raw.github || [];

    // team identity -> section (best-effort: match results to teams by title / team / leader)
    const sectionOf = new Map();
    teams.forEach((t) => {
        if (!t.section) return;
        [t.title, t.id, t.leader].forEach((key) => { if (key) sectionOf.set(String(key).toLowerCase(), t.section); });
    });
    const resultSection = (r) =>
        sectionOf.get(String(r.title || '').toLowerCase()) ||
        sectionOf.get(String(r.team || '').toLowerCase()) ||
        r.section || 'Unspecified';

    // Results carrying a real mark for the selected presentation.
    const scored = results.map((r) => ({ ...r, _m: num(r[marksKey]) })).filter((r) => r._m !== null);

    // 1. Marks distribution (range-wise histogram) — five 20-point bands.
    // Split into a team histogram (one count per scored team result) and a
    // student histogram (students inherit their team's score — built further
    // below once the student expansion exists).
    const bands = [[0, 20], [21, 40], [41, 60], [61, 80], [81, 100]];
    // Each band carries its members ({ name, meta, score }) so a bar click can
    // drill into who scored in that range.
    const buildBands = (entities) => bands.map(([lo, hi]) => {
        const items = entities.filter((e) => e.score >= lo && e.score <= hi);
        return { label: `${lo}–${hi}`, count: items.length, items };
    });
    const teamEntities = scored.map((r) => ({ name: r.title || r.team || '—', meta: resultSection(r), score: r._m }));
    const marks_distribution_teams = scored.length ? buildBands(teamEntities) : [];

    // 2. Top performers — TEAMS (top 10 by the selected presentation's marks)
    const top_performers = [...scored]
        .sort((a, b) => b._m - a._m)
        .slice(0, 10)
        .map((r, i) => ({
            rank: i + 1, team: r.team || '', title: r.title || '', marks: r._m,
            domain: r.domain || '—', section: resultSection(r),
            mentor: mentorNames(r.mentor).join(', ') || 'Unassigned',
        }))
        .filter((r) => match(r.team, r.title, r.mentor, r.section, r.domain));

    // 2b. Top performers — STUDENTS. No per-student marks exist, so each student
    // inherits their team's score (real data, not fabricated) via the team's
    // member list. Empty until teams are scored AND their members resolve to
    // student records.
    const studentLookup = new Map();
    students.forEach((s) => {
        [s.id, s.student_id, s.name].forEach((key) => { if (key) studentLookup.set(String(key).toLowerCase(), s); });
    });
    const scoreByTitle = new Map(scored.map((r) => [String(r.title || '').toLowerCase(), r._m]));
    const top_students = [];
    teams.forEach((t) => {
        const score = scoreByTitle.get(String(t.title || '').toLowerCase());
        if (score == null) return;
        let members = t.members;
        if (typeof members === 'string') { try { members = JSON.parse(members); } catch { members = []; } }
        if (!Array.isArray(members)) return;
        members.forEach((m) => {
            const key = (m && typeof m === 'object') ? (m.id || m.student_id || m.name) : m;
            const stu = key ? studentLookup.get(String(key).toLowerCase()) : null;
            const name = stu?.name || (m && typeof m === 'object' ? m.name : String(m || '')) || '—';
            top_students.push({
                name,
                section: stu?.section || t.section || '—',
                studentId: stu?.student_id || stu?.id || (m && typeof m === 'object' ? m.id : '') || '—',
                team: t.title || t.id || '—',
                score,
            });
        });
    });
    // Student marks distribution — every expanded student bucketed by inherited score.
    const studentEntities = top_students.map((s) => ({ name: s.name, meta: s.team, score: s.score }));
    const marks_distribution_students = top_students.length ? buildBands(studentEntities) : [];
    top_students.sort((a, b) => b.score - a.score);
    const top_students_ranked = top_students
        .filter((s) => match(s.name, s.section, String(s.studentId), s.team))
        .slice(0, 10)
        .map((s, i) => ({ rank: i + 1, ...s }));

    // 3. Absent students details
    const absent_details = absents
        .map((a) => ({ name: a.name || '—', roll: a.roll || '—', team: a.team || '—', reason: a.reason || '—', status: a.status || '—' }))
        .filter((a) => match(a.name, a.roll, a.team, a.reason));

    // 4. Total students (absent + present)
    const student_totals = {
        total: students.length,
        absent: absents.length,
        present: Math.max(0, students.length - absents.length),
    };

    // 5. Critical observations by panel (from panel evaluation remarks)
    const panelName = new Map(panels.map((p) => [String(p.id), p.name || String(p.id)]));
    const teamTitleById = new Map(teams.map((t) => [String(t.id), t.title]));
    const critical_observations = evaluations
        .map((e) => {
            const score = evalTotal(e.scores_json);
            return {
                team: teamTitleById.get(String(e.team_id)) || `Team ${e.team_id}`,
                panel: panelName.get(String(e.panel_id)) || e.panel_id || '—',
                remark: e.remarks || '',
                score,
                critical: (e.remarks && CRITICAL_RE.test(e.remarks)) || (score !== null && score < 20),
            };
        })
        .filter((o) => o.remark)
        .filter((o) => match(o.team, o.panel, o.remark))
        .sort((a, b) => (Number(b.critical) - Number(a.critical)) || ((a.score ?? 999) - (b.score ?? 999)));

    // 6. Average marks of the selected presentation
    const average_marks = avg(scored.map((r) => r._m));

    // 7. Section-wise performance
    const secMap = new Map();
    scored.forEach((r) => { const s = resultSection(r); if (!secMap.has(s)) secMap.set(s, []); secMap.get(s).push(r._m); });
    const section_performance = [...secMap.entries()]
        .map(([label, vals]) => ({ label, avg: avg(vals), count: vals.length }))
        .sort((a, b) => (b.avg || 0) - (a.avg || 0))
        .filter((s) => match(s.label));

    // 7b. Section competency profile — panel evaluation criteria (scores_json)
    // averaged per criterion, grouped by the section of each evaluated team
    // (falls back to the team's branch when no section is set). Radar axes are
    // the criteria keys. Empty until teams carry a section/branch that maps to
    // an evaluation. No fabricated data.
    const teamById = new Map();
    teams.forEach((t) => { if (t.id != null) teamById.set(String(t.id), t); });
    const compBucket = new Map(); // section -> Map(criterionKey -> number[])
    evaluations.forEach((e) => {
        const team = teamById.get(String(e.team_id));
        const section = team ? (team.section || team.branch) : null;
        if (!section) return;
        let obj = e.scores_json;
        if (typeof obj === 'string') { try { obj = JSON.parse(obj); } catch { return; } }
        if (!obj || typeof obj !== 'object') return;
        if (!compBucket.has(section)) compBucket.set(section, new Map());
        const crit = compBucket.get(section);
        Object.entries(obj).forEach(([k, v]) => {
            const nv = num(v); if (nv === null) return;
            if (!crit.has(k)) crit.set(k, []);
            crit.get(k).push(nv);
        });
    });
    const compAxisSet = new Set();
    compBucket.forEach((crit) => crit.forEach((_, k) => compAxisSet.add(k)));
    const compAxes = [...compAxisSet].sort();
    const section_competencies = {
        axes: compAxes,
        sections: [...compBucket.entries()]
            .map(([label, crit]) => ({
                label,
                values: compAxes.map((k) => avg(crit.get(k) || []) ?? 0),
                avg: avg(compAxes.flatMap((k) => crit.get(k) || [])),
                n: [...crit.values()].reduce((m, a) => Math.max(m, a.length), 0),
            }))
            .filter((s) => match(s.label))
            .sort((a, b) => (b.avg || 0) - (a.avg || 0)),
    };

    // 8. Panel-wise average marks (each panel carries the teams it evaluated,
    // so a bar click can drill into them).
    const panelMap = new Map();
    const panelTeams = new Map();
    evaluations.forEach((e) => {
        const s = evalTotal(e.scores_json); if (s === null) return;
        const key = String(e.panel_id);
        if (!panelMap.has(key)) { panelMap.set(key, []); panelTeams.set(key, []); }
        panelMap.get(key).push(s);
        panelTeams.get(key).push({ name: teamTitleById.get(String(e.team_id)) || `Team ${e.team_id}`, meta: '', score: Math.round(s * 10) / 10 });
    });
    const panel_averages = [...panelMap.entries()]
        .map(([id, vals]) => ({ label: panelName.get(id) || id, avg: avg(vals), count: vals.length, teams: panelTeams.get(id) || [] }))
        .sort((a, b) => (b.avg || 0) - (a.avg || 0))
        .filter((p) => match(p.label));

    // 9. Mentor-wise analysis (each mentor carries their scored teams).
    const mentorMap = new Map();
    const mentorTeams = new Map();
    scored.forEach((r) => mentorNames(r.mentor).forEach((n) => {
        if (!mentorMap.has(n)) { mentorMap.set(n, []); mentorTeams.set(n, []); }
        mentorMap.get(n).push(r._m);
        mentorTeams.get(n).push({ name: r.title || r.team || '—', meta: resultSection(r), score: r._m });
    }));
    const mentor_analysis = [...mentorMap.entries()]
        .map(([label, vals]) => ({ label, avg: avg(vals), count: vals.length, teams: mentorTeams.get(label) || [] }))
        .sort((a, b) => (b.avg || 0) - (a.avg || 0))
        .filter((m) => match(m.label));

    // 10. GitHub score (tracking agent) vs presentation score
    const marksByTitle = new Map(results.map((r) => [String(r.title || '').toLowerCase(), num(r[marksKey])]));
    const github_vs_presentation = github
        .map((g) => {
            const team = teams.find((t) => String(t.id) === String(g.team_id));
            const title = team ? team.title : null;
            const pres = title ? marksByTitle.get(String(title).toLowerCase()) : null;
            // Weekly commit history (agent contract: `weekly_commits` = number[],
            // oldest→newest). Absent today → null; the demo fill supplies it.
            const weeks = Array.isArray(g.weekly_commits)
                ? g.weekly_commits.map((v) => num(v)).filter((v) => v !== null)
                : null;
            return {
                team: title || `Team ${g.team_id}`,
                github: ghComposite(g),
                presentation: pres,
                commits30d: num(g.commit_count_30d),
                weeks: weeks && weeks.length ? weeks : null,
                repo: g.repository_url || null,
            };
        })
        .filter((x) => x.github !== null)
        .filter((x) => match(x.team))
        .sort((a, b) => (b.github || 0) - (a.github || 0));

    return {
        presentation: { index: presIndex, label: PRESENTATION_LABELS[presIndex] || PRESENTATION_LABELS[0], marksKey },
        marks_distribution: { students: marks_distribution_students, teams: marks_distribution_teams },
        top_performers,
        top_students: top_students_ranked,
        absent_details,
        student_totals,
        critical_observations,
        average_marks,
        section_performance,
        section_competencies,
        panel_averages,
        mentor_analysis,
        github_vs_presentation,
        counts: { scored: scored.length, teams: teams.length, evaluations: evaluations.length, github: github.length },
    };
}
