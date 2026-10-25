/**
 * governanceExport.js
 * Builds and downloads the Governance "master sheet" workbook — ONE SHEET PER
 * BATCH / YEAR, one row per team, with members, mentors, project statement,
 * proposal status and the GitHub repository URL.
 *
 * Joins are done on the canonical team uid (teams_validation.uid):
 *   proposals.team_uid   -> teams_validation.uid
 *   github_data.team_uid  -> teams_validation.uid   (falls back to team_ref === team.id)
 *   teams_validation.problem_statement_id -> problem_statements.id
 *
 * DB shapes this has to survive (verified against the live schema):
 *   - teams_validation.mentor  : JSON string array, e.g. '["Preshit Desai"]'
 *   - teams_validation.members : jsonb array of { id, name, roll, role, year, branch }
 *   - teams_validation.title   : usually the placeholder "Team 12" — the real
 *                                project title lives on the proposal / PS.
 *   - team-level branch/year/academic_level are frequently NULL; fall back to
 *     the members and then the semester_config row.
 */
import * as XLSX from 'xlsx';
import { resolveRowSemesterId } from './globalFilters';

const COLUMNS = [
    'Team No', 'Batch', 'Branch', 'Study Year',
    'Leader', 'Members', 'Member Rolls', 'Member Count',
    'Mentor(s)', 'Project Title', 'Project Statement / Description', 'PS Code', 'Domain',
    'Validation Status', 'Repository URL',
    'Proposal Status', 'Proposal Submitted On', 'Proposal File', 'Proposal Remarks',
];

const parseJsonList = (raw) => {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
        const s = raw.trim();
        if (s.startsWith('[')) {
            try {
                const parsed = JSON.parse(s);
                return Array.isArray(parsed) ? parsed : [];
            } catch {
                return s ? [s] : [];
            }
        }
        return s ? [s] : [];
    }
    return [];
};

const memberName = (m) => (typeof m === 'string' ? m : (m?.name || m?.student_name || m?.roll || m?.id || ''));
const memberRoll = (m) => (typeof m === 'string' ? '' : (m?.roll || m?.student_id || m?.id || ''));
const isLeaderRole = (m) => m && typeof m === 'object' && String(m.role || '').toUpperCase() === 'LEADER';

const ordinal = (n) => {
    const num = Number(n);
    if (!Number.isFinite(num)) return String(n);
    const s = ['th', 'st', 'nd', 'rd'];
    const v = num % 100;
    return `${num}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

const teamNumFromId = (id) => {
    const m = /-T(\d+)$/i.exec(String(id || ''));
    return m ? Number(m[1]) : null;
};

const teamNo = (t) => Number(t.team_number ?? t.teamNo ?? teamNumFromId(t.id)) || null;

const fmtDate = (raw) => {
    if (!raw) return '';
    const d = new Date(raw);
    if (isNaN(d.getTime())) return String(raw);
    return d.toLocaleString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
};

// Excel sheet names: max 31 chars, none of  : \ / ? * [ ]  , must be unique.
const sanitizeSheetName = (name, used) => {
    const base = (String(name || 'Sheet').replace(/[:\\/?*[\]]/g, ' ').replace(/\s+/g, ' ').trim() || 'Sheet').slice(0, 31);
    let candidate = base;
    let i = 2;
    while (used.has(candidate.toLowerCase())) {
        const suffix = ` (${i})`;
        candidate = `${base.slice(0, 31 - suffix.length)}${suffix}`;
        i += 1;
    }
    used.add(candidate.toLowerCase());
    return candidate;
};

const shortBranch = (branch) => String(branch || '').replace(/^b\.?tech\s*/i, '').trim();

const semesterSheetName = (sem) => {
    if (!sem) return 'Unassigned';
    const yr = sem.academic_level ? `${ordinal(sem.academic_level)} Year` : (sem.year || 'Batch');
    const type = sem.semester_type ? sem.semester_type.charAt(0).toUpperCase() + sem.semester_type.slice(1) : '';
    const tail = [type, sem.year].filter(Boolean).join(' ');
    return [shortBranch(sem.branch), yr, tail && `(${tail})`].filter(Boolean).join(' ');
};

const semesterFullLabel = (sem) => {
    if (!sem) return 'Unassigned';
    const yr = sem.academic_level ? `${ordinal(sem.academic_level)} Year` : '';
    const tail = [sem.semester_type && sem.semester_type.toUpperCase(), sem.year].filter(Boolean).join(' ');
    return [sem.branch, yr, tail].filter(Boolean).join(' · ').replace(/\s+/g, ' ').trim();
};

/**
 * @returns {{ sheets: { sheetName: string, rows: object[] }[], stats: object }}
 *          one sheet entry per batch/year (ordered) plus join diagnostics.
 */
export function buildGovernanceSheets({ teams = [], proposals = [], github = [], problemStatements = [], semesterMap = {} }) {
    let reposMatched = 0;
    let proposalsMatched = 0;
    const propByUid = new Map();
    proposals.forEach((p) => {
        const u = p && p.team_uid ? String(p.team_uid).toLowerCase() : '';
        if (u && !propByUid.has(u)) propByUid.set(u, p);
    });

    const ghByUid = new Map();
    const ghByRef = new Map();
    github.forEach((g) => {
        if (!g || !g.repository_url) return;
        const u = g.team_uid ? String(g.team_uid).toLowerCase() : '';
        if (u && !ghByUid.has(u)) ghByUid.set(u, g);
        const r = g.team_ref ? String(g.team_ref) : '';
        if (r && !ghByRef.has(r)) ghByRef.set(r, g);
    });

    const psById = new Map();
    problemStatements.forEach((ps) => {
        if (ps && ps.id) psById.set(String(ps.id).toLowerCase(), ps);
    });

    // Group teams by their resolved semester (direct semester_id or the id prefix).
    const groups = new Map();
    teams.forEach((t) => {
        const semId = resolveRowSemesterId(t, semesterMap) || '__none__';
        if (!groups.has(semId)) groups.set(semId, []);
        groups.get(semId).push(t);
    });

    const orderedSemIds = [...groups.keys()].sort((a, b) => {
        if (a === '__none__') return 1;
        if (b === '__none__') return -1;
        const sa = semesterMap[a] || {};
        const sb = semesterMap[b] || {};
        return (sa.academic_level || 99) - (sb.academic_level || 99)
            || String(sa.year || '').localeCompare(String(sb.year || ''))
            || String(sa.branch || '').localeCompare(String(sb.branch || ''));
    });

    const usedNames = new Set();
    const sheetList = orderedSemIds.map((semId) => {
        const sem = semId === '__none__' ? null : semesterMap[semId];
        const sheetName = sanitizeSheetName(semesterSheetName(sem), usedNames);
        const batchLabel = semesterFullLabel(sem);

        const rows = groups.get(semId)
            .slice()
            .sort((a, b) => (teamNo(a) || 1e9) - (teamNo(b) || 1e9))
            .map((t) => {
                const uid = t.uid ? String(t.uid).toLowerCase() : '';
                const members = parseJsonList(t.members);
                const mentors = parseJsonList(t.mentor)
                    .map((m) => (typeof m === 'string' ? m : (m?.name || '')))
                    .filter(Boolean);

                const prop = uid ? propByUid.get(uid) : null;
                const gh = (uid && ghByUid.get(uid)) || (t.id && ghByRef.get(String(t.id))) || null;
                const ps = t.problem_statement_id ? psById.get(String(t.problem_statement_id).toLowerCase()) : null;

                if (prop) proposalsMatched += 1;
                if (gh && gh.repository_url) reposMatched += 1;

                const leaderMember = members.find(isLeaderRole);
                const leaderName = leaderMember
                    ? memberName(leaderMember)
                    : (typeof t.leader === 'string' ? t.leader : (t.leader?.name || ''));

                const memberBranches = [...new Set(members.map((m) => (typeof m === 'object' ? m.branch : '')).filter(Boolean))];
                const memberYears = [...new Set(members.map((m) => (typeof m === 'object' ? m.year : null)).filter((v) => v !== null && v !== ''))];

                const placeholderTitle = /^team\s*\d+$/i.test(String(t.title || '').trim());
                const projectTitle = (prop && prop.title)
                    || (ps && ps.title)
                    || (!placeholderTitle ? (t.title || '') : '');
                const statement = (ps && ps.description) || t.description || (prop && prop.description) || '';

                return {
                    'Team No': teamNo(t) || '',
                    'Batch': batchLabel,
                    'Branch': t.branch || memberBranches.join(', ') || (sem?.branch || ''),
                    'Study Year': t.academic_level || memberYears.join(', ') || (sem?.academic_level || ''),
                    'Leader': leaderName,
                    'Members': members.map(memberName).filter(Boolean).join(', '),
                    'Member Rolls': members.map(memberRoll).filter(Boolean).join(', '),
                    'Member Count': t.memberCount || members.length || 0,
                    'Mentor(s)': mentors.join(', '),
                    'Project Title': projectTitle,
                    'Project Statement / Description': statement,
                    'PS Code': t.problem_statement_id || '',
                    'Domain': t.domain || (ps && ps.domain) || '',
                    'Validation Status': t.validationStatus || t.validation_status || '',
                    'Repository URL': (gh && gh.repository_url) || '',
                    'Proposal Status': prop ? (prop.status || 'Submitted') : 'Not Submitted',
                    'Proposal Submitted On': prop ? fmtDate(prop.submitted_at || prop.submittedDate) : '',
                    'Proposal File': prop ? (prop.proposalFile || prop.document_url || '') : '',
                    'Proposal Remarks': (prop && (prop.remarks || prop.feedback)) || '',
                };
            });

        return { sheetName, rows };
    });

    const stats = {
        teams: teams.length,
        githubFetched: github.length,
        reposMatched,
        proposalsFetched: proposals.length,
        proposalsMatched,
        sheets: sheetList.length,
    };
    return { sheets: sheetList, stats };
}

/**
 * Builds the workbook (one sheet per batch/year) and triggers a browser download.
 * @returns {{ totalRows: number, sheetCount: number, stats: object }}
 */
export function downloadGovernanceExcel(args = {}) {
    const { sheets: allSheets, stats } = buildGovernanceSheets(args);
    const sheets = allSheets.filter((s) => s.rows.length > 0);
    const list = sheets.length ? sheets : [{ sheetName: 'Teams', rows: [] }];

    // Surfaced so the caller can warn when a join silently produced nothing.
    console.info('[governanceExport]', stats);

    const wb = XLSX.utils.book_new();
    let totalRows = 0;

    list.forEach(({ sheetName, rows }) => {
        totalRows += rows.length;
        const ws = XLSX.utils.json_to_sheet(rows, { header: COLUMNS });
        ws['!cols'] = COLUMNS.map((h) => {
            const bodyMax = rows.reduce((mx, r) => Math.max(mx, String(r[h] ?? '').length), 0);
            return { wch: Math.min(Math.max(h.length, bodyMax) + 2, 55) };
        });
        ws['!autofilter'] = {
            ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: Math.max(rows.length, 1), c: COLUMNS.length - 1 } }),
        };
        XLSX.utils.book_append_sheet(wb, ws, sheetName);
    });

    const stamp = new Date().toISOString().slice(0, 10);
    XLSX.writeFile(wb, `GLA_PMS_Governance_Master_${stamp}.xlsx`);
    return { totalRows, sheetCount: list.length, stats };
}
