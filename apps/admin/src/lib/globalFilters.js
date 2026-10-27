export const ADMIN_GLOBAL_FILTERS_KEY = 'procksi-admin-global-filters';

export const DEFAULT_GLOBAL_FILTERS = {
    search: '',
    semesterId: 'all',
    year: 'all',
    branch: 'all',
};

export function normalizeFilterValue(value) {
    return String(value ?? '').trim();
}

export function getStoredGlobalFilters() {
    if (typeof window === 'undefined') {
        return DEFAULT_GLOBAL_FILTERS;
    }

    try {
        const parsed = JSON.parse(localStorage.getItem(ADMIN_GLOBAL_FILTERS_KEY) || '{}');
        return {
            ...DEFAULT_GLOBAL_FILTERS,
            ...parsed,
        };
    } catch {
        return DEFAULT_GLOBAL_FILTERS;
    }
}

export function saveStoredGlobalFilters(filters) {
    if (typeof window === 'undefined') {
        return;
    }

    localStorage.setItem(
        ADMIN_GLOBAL_FILTERS_KEY,
        JSON.stringify({ ...DEFAULT_GLOBAL_FILTERS, ...filters })
    );
}

export function buildSemesterMap(semesters = []) {
    const map = {};
    semesters.forEach((semester) => {
        if (semester?.id) {
            map[String(semester.id)] = semester;
        }
    });
    return map;
}

export function academicYearFromSemesterNumber(semesterNumber) {
    const numeric = Number(semesterNumber);
    if (!Number.isFinite(numeric) || numeric <= 0) {
        return '';
    }
    return String(Math.ceil(numeric / 2));
}

export function resolveRowSemester(row, semesterMap = {}) {
    if (!row) {
        return null;
    }

    const directId = row.semester_id || row.semesterId;
    if (directId && semesterMap[String(directId)]) {
        return semesterMap[String(directId)];
    }

    const id = String(row.id || row.teamId || row.team_id || row.team || '');
    const semesterIdFromPrefix = Object.keys(semesterMap).find((semesterId) => id.startsWith(`${semesterId}-`));
    return semesterIdFromPrefix ? semesterMap[semesterIdFromPrefix] : null;
}

/**
 * True when a row belongs to a semester-scoped entity, i.e. its table carries a
 * semester column at all. PostgREST always returns declared columns, so the key
 * is present (possibly null) for those tables and absent for tables that have no
 * semester concept (mentors, panels, problem_statements...).
 *
 * This is what lets the semester filter fail *closed* for rows that should have a
 * batch but don't, without hiding rows that legitimately never had one.
 */
export function isSemesterScopedRow(row) {
    if (!row || typeof row !== 'object') {
        return false;
    }
    return 'semester_id' in row || 'semesterId' in row;
}

export function resolveRowSemesterId(row, semesterMap = {}) {
    if (!row) {
        return '';
    }

    const directId = row.semester_id || row.semesterId;
    if (directId) {
        return String(directId);
    }

    const id = String(row.id || row.teamId || row.team_id || row.team || '');
    return Object.keys(semesterMap).find((semesterId) => id.startsWith(`${semesterId}-`)) || '';
}

function collectMembers(row) {
    const rawMembers = row?.members || row?.team_members || [];
    if (Array.isArray(rawMembers)) {
        return rawMembers;
    }

    if (typeof rawMembers === 'string') {
        try {
            const parsed = JSON.parse(rawMembers);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }

    return [];
}

export function rowBranchValues(row, semesterMap = {}) {
    const semester = resolveRowSemester(row, semesterMap);
    const values = new Set();

    [
        row?.branch,
        row?.student_branch,
        row?.mentor_branch,
        semester?.branch,
    ].forEach((value) => {
        const normalized = normalizeFilterValue(value);
        if (normalized) {
            values.add(normalized);
        }
    });

    collectMembers(row).forEach((member) => {
        if (member && typeof member === 'object') {
            const normalized = normalizeFilterValue(member.branch);
            if (normalized) {
                values.add(normalized);
            }
        }
    });

    return [...values];
}

export function rowYearValues(row, semesterMap = {}) {
    const values = new Set();

    const mainYear = resolveCollegeYear(row, semesterMap);
    if (mainYear) {
        values.add(mainYear);
    }

    collectMembers(row).forEach((member) => {
        if (member && typeof member === 'object') {
            const memberYear = resolveCollegeYear(member, semesterMap);
            if (memberYear) {
                values.add(memberYear);
            }
        }
    });

    return [...values];
}

export function teamNumberFromId(teamId) {
    if (teamId === null || teamId === undefined) return null;
    const text = String(teamId).trim();
    if (text === '') return null;
    
    // 1. Strip standard UUID patterns (36 chars with hyphens)
    const uuidRegex = /[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g;
    const cleanText = text.replace(uuidRegex, '').trim();

    // 2. Try extracting team number from cleanText or original text
    const match = /[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)/i.exec(cleanText)
        || /[-_]?[Tt](\d+)/i.exec(cleanText)
        || /[-_](\d+)/.exec(cleanText)
        || /(\d+)/.exec(cleanText)
        || /[-_]?[Tt][Ee][Aa][Mm][-_]?\s*(\d+)/i.exec(text)
        || /[-_]?[Tt](\d+)/i.exec(text);

    if (match) {
        const val = Number.parseInt(match[1], 10);
        if (!isNaN(val) && val > 0 && val < 100000) return val;
    }

    if (/^\d+$/.test(cleanText)) {
        const val = Number.parseInt(cleanText, 10);
        if (!isNaN(val) && val > 0 && val < 100000) return val;
    }

    // No real team number in the string. Return null — a team's identity is its
    // team_uid, never a number carved out of a uuid. (Deleting the old
    // "last 3 digits of the uuid" fallback: it invented numbers and made one
    // team's screen show another team's data.)
    return null;
}

export function resolveTeamNumber(teamId, row) {
    if (row) {
        if (row.team_no) {
            const num = parseInt(row.team_no, 10);
            if (!isNaN(num) && num < 100000) return num;
        }
        if (row.teamNo) {
            const num = parseInt(row.teamNo, 10);
            if (!isNaN(num) && num < 100000) return num;
        }
        if (row.team_number) {
            const num = parseInt(row.team_number, 10);
            if (!isNaN(num) && num < 100000) return num;
        }
        if (row.teamNumber) {
            const num = parseInt(row.teamNumber, 10);
            if (!isNaN(num) && num < 100000) return num;
        }
        const titleMatch = /Team\s*(\d+)/i.exec(String(row.title || ''));
        if (titleMatch) {
            const num = parseInt(titleMatch[1], 10);
            if (num < 100000) return num;
        }
        const nameMatch = /Team\s*(\d+)/i.exec(String(row.name || ''));
        if (nameMatch) {
            const num = parseInt(nameMatch[1], 10);
            if (num < 100000) return num;
        }
    }
    return teamNumberFromId(teamId);
}

export function resolveCollegeYear(row, semesterMap = {}) {
    const semester = resolveRowSemester(row, semesterMap);
    
    if (semester) {
        if (semester.academic_level) {
            const val = String(semester.academic_level).trim();
            if (val && !/\d{4}/.test(val)) {
                return val;
            }
        }
        if (semester.semester_number) {
            const num = Math.ceil(Number(semester.semester_number) / 2);
            if (num >= 1 && num <= 10) {
                return String(num);
            }
        }
    }
    
    const candidates = [
        row?.year,
        row?.academic_level,
        row?.academicLevel,
        row?.academic_year,
        row?.academicYear,
    ];
    
    for (const val of candidates) {
        if (val) {
            const s = String(val).trim();
            if (s && !/\d{4}/.test(s)) {
                return s;
            }
        }
    }
    
    const members = row?.members || row?.team_members || [];
    if (Array.isArray(members)) {
        for (const m of members) {
            if (m && typeof m === 'object') {
                const mcandidates = [
                    m.year,
                    m.academic_level,
                    m.academicLevel,
                    m.academic_year,
                    m.academicYear,
                ];
                for (const val of mcandidates) {
                    if (val) {
                        const s = String(val).trim();
                        if (s && !/\d{4}/.test(s)) {
                            return s;
                        }
                    }
                }
            }
        }
    }
    
    const teamId = row?.id || row?.teamId || row?.team_id || row?.team || '';
    if (teamId) {
        const text = String(teamId).trim();
        const yearMatch = /(\d+)(?:st|nd|rd|th)\s*[-_]?\s*year/i.exec(text)
            || /year[-_]?(\d+)/i.exec(text)
            || /semester[-_]?(\d+)/i.exec(text);
        if (yearMatch) {
            const num = parseInt(yearMatch[1], 10);
            if (num > 0 && num < 10) {
                return String(num);
            }
        }
        if (text.toLowerCase().includes('3rd-year') || text.toLowerCase().includes('3rd_year')) {
            return '3';
        }
        if (text.toLowerCase().includes('4th-year') || text.toLowerCase().includes('4th_year')) {
            return '4';
        }
        if (text.toLowerCase().includes('2nd-year') || text.toLowerCase().includes('2nd_year')) {
            return '2';
        }
        if (text.toLowerCase().includes('1st-year') || text.toLowerCase().includes('1st_year')) {
            return '1';
        }
    }
    
    return '';
}

export function formatAcademicYear(year) {
    const clean = String(year || '').trim().toLowerCase();
    
    if (/\d{4}/.test(clean)) {
        return '';
    }

    const match = /(^[1-9]\d?)(?:st|nd|rd|th)?/i.exec(clean) || /(\d+)/.exec(clean);
    if (match) {
        const num = match[1];
        if (num === '1') return '1st Year';
        if (num === '2') return '2nd Year';
        if (num === '3') return '3rd Year';
        if (num === '4') return '4th Year';
        return `${num}th Year`;
    }

    if (clean.includes('first')) return '1st Year';
    if (clean.includes('second')) return '2nd Year';
    if (clean.includes('third')) return '3rd Year';
    if (clean.includes('fourth')) return '4th Year';
    
    return year;
}

export function normalizeYearToNumber(year) {
    const clean = String(year || '').trim().toLowerCase();
    if (!clean) return '';

    const match = /(^[1-9]\d?)(?:st|nd|rd|th)?/i.exec(clean) || /(\d+)/.exec(clean);
    if (match) {
        return match[1];
    }

    if (clean.includes('first') || clean.includes('1st')) return '1';
    if (clean.includes('second') || clean.includes('2nd')) return '2';
    if (clean.includes('third') || clean.includes('3rd')) return '3';
    return clean;
}

export function cleanUUIDsFromText(str) {
    if (!str || typeof str !== 'string') return str;
    return str
        .replace(/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})[-_]?[Tt]eam[-_]?\s*(\d+)/gi, 'Team $2')
        .replace(/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})[-_]?[Tt](\d+)/gi, 'Team $2')
        .replace(/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})[-_]?/gi, '');
}

export function teamDisplayLabel(teamId, row = null, semesterMap = {}) {
    if (teamId === null || teamId === undefined || teamId === '') return 'Unknown Team';
    const teamNo = resolveTeamNumber(teamId, row);
    
    const rowObj = row || { id: teamId };
    let yearStr = resolveCollegeYear(rowObj, semesterMap);

    if (!yearStr && rowObj) {
        if (rowObj.year) yearStr = formatAcademicYear(rowObj.year);
        else if (rowObj.members && rowObj.members.length > 0) {
            const mYear = rowObj.members[0].year || rowObj.members[0].student?.year;
            if (mYear) yearStr = formatAcademicYear(mYear);
        }
        if (!yearStr && rowObj.semester_id && semesterMap[String(rowObj.semester_id)]) {
            const sem = semesterMap[String(rowObj.semester_id)];
            if (sem.year) yearStr = formatAcademicYear(sem.year);
        }
    } else if (yearStr) {
        yearStr = formatAcademicYear(yearStr);
    }

    if (!yearStr) {
        yearStr = '3rd Year';
    }

    const cleanTeamNo = teamNo ? `Team ${teamNo}` : 'Team 1';

    return `${yearStr} - ${cleanTeamNo}`;
}

function rowSearchText(row, semesterMap = {}) {
    const semester = resolveRowSemester(row, semesterMap);
    const teamId = row?.id || row?.teamId || row?.team_id || row?.team || '';

    return [
        JSON.stringify(row || {}),
        semester ? JSON.stringify(semester) : '',
        teamDisplayLabel(teamId, row, semesterMap),
    ].join(' ').toLowerCase();
}

export function matchesGlobalFilters(row, filters = DEFAULT_GLOBAL_FILTERS, semesterMap = {}) {
    if (!row) {
        return false;
    }

    const effectiveFilters = { ...DEFAULT_GLOBAL_FILTERS, ...filters };
    const search = normalizeFilterValue(effectiveFilters.search).toLowerCase();

    if (search && !rowSearchText(row, semesterMap).includes(search)) {
        return false;
    }

    const selectedSemesterId = normalizeFilterValue(effectiveFilters.semesterId);
    if (selectedSemesterId && selectedSemesterId !== 'all') {
        const rowSemesterId = resolveRowSemesterId(row, semesterMap);
        if (rowSemesterId) {
            if (rowSemesterId !== selectedSemesterId) {
                return false;
            }
        } else if (isSemesterScopedRow(row)) {
            // Semester-scoped row with a null/blank batch: it cannot be claimed by
            // the selected batch, so it must not leak into every batch view.
            return false;
        }
    }

    const selectedBranch = normalizeFilterValue(effectiveFilters.branch);
    if (selectedBranch && selectedBranch !== 'all') {
        const branches = rowBranchValues(row, semesterMap);
        if (branches.length > 0) {
            const match = branches.some((branch) => {
                const rb = normalizeFilterValue(branch).toLowerCase();
                const sb = normalizeFilterValue(selectedBranch).toLowerCase();
                return rb === sb || rb.includes(sb) || sb.includes(rb);
            });
            if (!match) {
                return false;
            }
        }
    }

    const selectedYear = normalizeFilterValue(effectiveFilters.year);
    if (selectedYear && selectedYear !== 'all') {
        const years = rowYearValues(row, semesterMap);
        if (years.length > 0) {
            const normalizedSelectedYear = normalizeYearToNumber(selectedYear);
            const match = years.some((year) => normalizeYearToNumber(year) === normalizedSelectedYear);
            if (!match) {
                return false;
            }
        }
    }

    return true;
}

export function filterRowsByGlobalFilters(rows, filters = DEFAULT_GLOBAL_FILTERS, semesterMap = {}) {
    if (!Array.isArray(rows)) {
        return [];
    }

    return rows.filter((row) => matchesGlobalFilters(row, filters, semesterMap));
}
