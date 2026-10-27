import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import { clearSemesterCache, apiUpsertTable, getActiveSemesterId, apiFetchTable, apiDeleteRows, getAuthToken } from '../lib/api.js';
import { teamNumber } from '../lib/teamUtils.js';
import { getApiBaseUrl } from '../lib/apiBase.js';

const API_BASE_URL = `${getApiBaseUrl()}/api`;

// Guard: tracks the last set of IDs cleaned up from unassigned_students.
// Prevents the 3-second poll in TeamValidation from firing hundreds of
// repeated DELETE requests for the same stale rows on every cycle.
let _lastUnassignedCleanupKey = null;

const getAuthHeaders = (isFormData = false) => {
    const token = getAuthToken();
    const headers = {};
    if (!isFormData) {
        headers['Content-Type'] = 'application/json';
    }
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
};

// Helper function to generate UUIDs for client-side creation
function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

const dispatchSemesterConfigChanged = () => {
    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('procksi-semester-config-changed'));
    }
};

export const api = {
    // Per-Team Personalized Communication
    getPerTeamFields: async () => {
        const response = await fetch(`${API_BASE_URL}/admin/communication/per-team-fields`, {
            headers: getAuthHeaders(),
        });
        if (!response.ok) throw new Error('Failed to load merge fields');
        const json = await response.json();
        return json.data ?? json;
    },
    getPerTeamCount: async ({ teamIds, segment, filterTeamId } = {}) => {
        const params = new URLSearchParams();
        if (teamIds) params.set('team_ids', teamIds);
        if (segment) params.set('segment', segment);
        if (filterTeamId) params.set('filter_team_id', filterTeamId);
        const qs = params.toString();
        const response = await fetch(`${API_BASE_URL}/admin/communication/per-team-count${qs ? `?${qs}` : ''}`, {
            headers: getAuthHeaders(),
        });
        if (!response.ok) throw new Error('Failed to load recipient count');
        const json = await response.json();
        return json.data ?? json;
    },
    sendPerTeam: async ({ subject, body, isHtml, teamIds, segment, filterTeamId, includePortalButton, dryRun, files }) => {
        const form = new FormData();
        form.append('subject', subject);
        form.append('body', body);
        form.append('is_html', isHtml ? 'true' : 'false');
        form.append('dry_run', dryRun ? 'true' : 'false');
        if (includePortalButton) form.append('include_portal_button', 'true');
        if (teamIds) form.append('team_ids', teamIds);
        if (segment) form.append('segment', segment);
        if (filterTeamId) form.append('filter_team_id', filterTeamId);
        (files || []).forEach((f) => form.append('files', f));
        const response = await fetch(`${API_BASE_URL}/admin/communication/send-per-team`, {
            method: 'POST',
            headers: getAuthHeaders(true),
            body: form,
        });
        const json = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(json.detail || 'Failed to send per-team emails');
        return json.data ?? json;
    },
    getAnalysisData: async () => {
        const response = await fetch(`${API_BASE_URL}/admin/analysis/data`, {
            headers: getAuthHeaders(),
        });
        if (!response.ok) throw new Error('Failed to load analysis');
        const json = await response.json();
        return json.data ?? json;
    },

    // Auth
    login: async (credentials) => {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(credentials)
        });
        if (!response.ok) throw new Error('Login failed');
        return response.json();
    },

    // Students
    getStudents: async (semesterId = null) => {
        let rows;
        if (semesterId) {
            // Fetch specifically for the given semester (e.g., right after an upload)
            rows = await apiFetchTable('students', { semesterOverride: semesterId });
        } else {
            rows = await apiFetchTable('students');
        }
        return { data: rows.map(s => ({...s, student_id: s.studentId || s.id})) };
    },
    updateStudentStatus: async (studentId, status) => {
        const response = await fetch(`${API_BASE_URL}/data/students/${studentId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: studentId,
                fields: { status }
            })
        });
        if (!response.ok) throw new Error('Failed to update status');
        return response.json();
    },
    uploadStudents: async (file, semesterId) => {
        let defaultYear = 4;
        try {
            const semConfig = await api.getSemesterConfig();
            const sems = semConfig.data || [];
            const targetSem = sems.find(s => s.id === semesterId);
            if (targetSem) {
                defaultYear = parseInt(targetSem.academic_level || targetSem.year) || 4;
            }
        } catch (err) {
            console.error('Failed to resolve default year from semester config:', err);
        }

        return new Promise((resolve, reject) => {
            const processData = async (data) => {
                console.log('Parsed data length:', data?.length);
                if (!data || data.length === 0) {
                    console.log('No data found in file');
                    resolve({ data: [], count: 0 });
                    return;
                }

                const studentRows = [];
                const groups = [];
                
                // First pass: Parse and clean basic student fields
                const parsedRows = data.map((row, index) => {
                    const keys = Object.keys(row);
                    const getVal = (possibleKeys) => {
                        // 1. Try exact match (alphanumeric only)
                        let key = keys.find(k => {
                            const cleanK = k.toLowerCase().replace(/[^a-z0-9]/g, '');
                            return possibleKeys.some(pk => {
                                const cleanPK = pk.toLowerCase().replace(/[^a-z0-9]/g, '');
                                return cleanK === cleanPK;
                            });
                        });
                        if (key) return row[key];

                        // 2. Try substring match as fallback for critical columns
                        key = keys.find(k => {
                            const cleanK = k.toLowerCase().replace(/[^a-z0-9]/g, '');
                            return possibleKeys.some(pk => {
                                const cleanPK = pk.toLowerCase().replace(/[^a-z0-9]/g, '');
                                // Special case for email
                                if ((cleanPK === 'email' || cleanPK === 'emailid' || cleanPK === 'mail') && 
                                    (cleanK.includes('email') || cleanK.includes('mail') || cleanK.includes('gmail'))) {
                                    return true;
                                }
                                // Special case for name
                                if (cleanPK === 'name' && (cleanK.includes('name') || cleanK.includes('candidate') || cleanK.includes('student'))) {
                                    return true;
                                }
                                // Special case for roll/ID
                                if ((cleanPK === 'rollnumber' || cleanPK === 'studentid' || cleanPK === 'roll') && 
                                    (cleanK.includes('roll') || cleanK.includes('id') || cleanK.includes('university') || cleanK.includes('reg'))) {
                                    return true;
                                }
                                return false;
                            });
                        });
                        return key ? row[key] : undefined;
                    };
                    
                    const sId = getVal(['Student ID', 'Roll Number', 'Roll', 'id', 'student_id', 'University Roll No', 'Reg No', 'Registration Number', 'RollNo', 'StudentID', 'University Roll Number', 'RollNo']) || `TMP-${index}-${Date.now()}`;
                    const name = getVal(['Name', 'Student Name', 'Full Name', 'Member Name', 'First Name', 'FirstName', 'Candidate Name', 'Student', 'Candidate']) || 'Unknown';
                    const email = getVal(['Email', 'Email ID', 'Mail', 'Email Address', 'EmailID', 'EmailAddress', 'Gmail', 'Official Email', 'Personal Email', 'E-Mail']) || `${sId}@example.com`;
                    const branch = getVal(['Branch', 'Course', 'Program', 'Department', 'Dept']) || 'BTech CSE';
                    const year = parseInt(getVal(['Year', 'Yr', 'Level', 'Academic Year'])) || defaultYear;
                    const section = getVal(['Section', 'Sec', 'Batch', 'Group']) || 'A';
                    
                    const rawTeamNo = getVal(['Team No', 'Team Number', 'Team ID', 'Group', 'Team', 'TeamNo', 'Group No', 'Group Number']);
                    const teamNo = (rawTeamNo !== undefined && rawTeamNo !== null && String(rawTeamNo).trim() !== '') ? String(rawTeamNo).trim() : null;
                    
                    const rawContact = getVal(['Contact Number', 'Contact', 'Phone', 'Mobile', 'Phone Number', 'Mobile Number']);
                    const contact = (rawContact !== undefined && rawContact !== null && String(rawContact).trim() !== '') ? String(rawContact).trim() : null;
                    
                    const pTitle = getVal(['Project Title', 'Project Name', 'Project', 'Title', 'ProjectTitle']);
                    const projectTitle = (pTitle !== undefined && pTitle !== null && String(pTitle).trim() !== '') ? String(pTitle).trim() : null;
                    
                    const pDesc = getVal(['Project Description', 'Description', 'ProjectDesc', 'Project Details', 'Details', 'Synopsis', 'Problem Statement']);
                    const projectDescription = (pDesc !== undefined && pDesc !== null && String(pDesc).trim() !== '') ? String(pDesc).trim() : null;
                    
                    const pDomain = getVal(['Domain', 'Project Domain', 'Domain Area', 'Area']);
                    const domain = (pDomain !== undefined && pDomain !== null && String(pDomain).trim() !== '') ? String(pDomain).trim() : null;
                    
                    return {
                        id: sId,
                        name,
                        email,
                        branch,
                        year,
                        section,
                        status: 'Active',
                        semester_id: semesterId,
                        teamNo,
                        contact,
                        projectTitle,
                        projectDescription,
                        domain
                    };
                });

                // Second pass: Group rows into teams BY teamNo field
                // Students WITH a teamNo -> grouped into teams
                // Students WITHOUT a teamNo -> go to unassigned_students
                const teamMap = {}; // teamNo -> array of rows
                const unassignedRows = [];

                parsedRows.forEach((row) => {
                    studentRows.push({
                        id: row.id,
                        name: row.name,
                        email: row.email,
                        branch: row.branch,
                        year: row.year,
                        section: row.section,
                        status: row.status,
                        semester_id: row.semester_id
                    });

                    if (row.teamNo) {
                        if (!teamMap[row.teamNo]) teamMap[row.teamNo] = [];
                        teamMap[row.teamNo].push(row);
                    } else {
                        unassignedRows.push(row);
                    }
                });

                // Build groups array from teamMap
                Object.values(teamMap).forEach(grp => groups.push(grp));

                console.log('Parsed student count:', studentRows.length);
                console.log('Parsed groups count:', groups.length);

                try {
                    // 1. Ingest/upsert all student records
                    const payload = await apiUpsertTable('students', studentRows, 'id');
                    
                    // 2. Form and upsert teams that have explicit team numbers
                    const teamRows = [];
                    groups.forEach((groupRows) => {
                        const teamNoRow = groupRows.find(r => r.teamNo);
                        if (teamNoRow && teamNoRow.teamNo) {
                            const teamNo = teamNoRow.teamNo;
                            const teamId = `${semesterId}-T${teamNo}`;
                            const leaderRow = groupRows.find(r => r.contact) || groupRows[0];
                            
                            const teamMembers = groupRows.map(r => ({
                                id: r.id,
                                name: r.name,
                                branch: r.branch,
                                year: r.year,
                                roll: r.id
                            }));
                            
                            const titleVal = groupRows.map(r => r.projectTitle).find(Boolean) || '';
                            const descVal = groupRows.map(r => r.projectDescription).find(Boolean) || '';
                            const domainVal = groupRows.map(r => r.domain).find(Boolean) || '';
                            
                            teamRows.push({
                                id: teamId,
                                title: titleVal || `Team ${teamNo}`,
                                description: descVal || null,
                                domain: domainVal || null,
                                leader: leaderRow.id,
                                members: teamMembers,
                                memberCount: teamMembers.length,
                                validationStatus: 'Pending',
                                branch: groupRows.map(r => r.branch).find(Boolean) || null,
                                year: groupRows.map(r => r.year).find(Boolean) || null,
                                semester_id: semesterId
                            });
                        }
                    });

                    if (teamRows.length > 0) {
                        console.log('Sending generated teams to upsert:', teamRows.length);
                        await apiUpsertTable('teams_validation', teamRows, 'id');
                    }

                    // 3. Upsert unassigned students (those without a team number)
                    if (unassignedRows.length > 0) {
                        const unassignedPayload = unassignedRows.map(r => ({
                            id: r.id,
                            name: r.name,
                            roll: r.id,
                            branch: r.branch,
                            semester_id: semesterId
                        }));
                        console.log('Sending unassigned students:', unassignedPayload.length);
                        try {
                            await apiUpsertTable('unassigned_students', unassignedPayload, 'id');
                        } catch (unassignedErr) {
                            console.warn('Could not save unassigned students:', unassignedErr.message);
                        }
                    }
                    
                    resolve(payload);
                } catch (e) {
                    reject(e);
                }
            };

            if (file.name.match(/\.(xlsx?|xlxs)$/i)) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    try {
                        const data = e.target.result;
                        const workbook = XLSX.read(data, { type: 'array' });
                        const firstSheetName = workbook.SheetNames[0];
                        const worksheet = workbook.Sheets[firstSheetName];

                        // Parse to JSON (merged continuation cells will have '' as defval)
                        const json = XLSX.utils.sheet_to_json(worksheet, { defval: '' });
                        console.log('Successfully parsed XLSX:', json.length, 'rows');

                        if (json.length === 0) { processData([]); return; }

                        // ── Merged-cell fill-down for "Team No" column ──────────────────
                        // Excel uses merged cells so team number appears only on first
                        // member row. XLSX.js leaves subsequent rows as ''.
                        // We detect the merge ranges and propagate the value downward.
                        // Rows with a GENUINELY empty Team No (not in any merge) stay ''.
                        // Find the Team No key from parsed header
                        const firstRow = json[0];
                        const teamNoKey = Object.keys(firstRow).find(k => {
                            const n = k.toLowerCase().replace(/[\s_-]/g, '');
                            return ['teamno', 'teamnumber', 'teamid', 'groupno', 'groupnumber', 'team', 'group'].includes(n);
                        });

                        if (teamNoKey) {
                            // Merged-cell fill-down: Excel often stores team number only in
                            // the first row of a merged range. Detect merges and fill all
                            // rows in that range with the same value.
                            // Rows NOT in any merge that are blank = genuinely unassigned.
                            const wsRange = XLSX.utils.decode_range(worksheet['!ref'] || 'A1');
                            const headerRowIdx = wsRange.s.r;

                            let teamNoColIdx = -1;
                            for (let c = wsRange.s.c; c <= wsRange.e.c; c++) {
                                const cell = worksheet[XLSX.utils.encode_cell({ r: headerRowIdx, c })];
                                if (cell && cell.v !== undefined) {
                                    const cellNorm = String(cell.v).toLowerCase().replace(/[\s_-]/g, '');
                                    const keyNorm  = teamNoKey.toLowerCase().replace(/[\s_-]/g, '');
                                    if (cellNorm === keyNorm) { teamNoColIdx = c; break; }
                                }
                            }

                            if (teamNoColIdx >= 0) {
                                const merges = worksheet['!merges'] || [];
                                const rowTeamNoMap = {};
                                merges.forEach(merge => {
                                    if (merge.s.c <= teamNoColIdx && merge.e.c >= teamNoColIdx) {
                                        const topCell = worksheet[XLSX.utils.encode_cell({ r: merge.s.r, c: teamNoColIdx })];
                                        if (topCell && topCell.v !== undefined && String(topCell.v).trim() !== '') {
                                            const val = String(topCell.v).trim();
                                            for (let r = merge.s.r; r <= merge.e.r; r++) {
                                                rowTeamNoMap[r] = val;
                                            }
                                        }
                                    }
                                });
                                // Apply merge fill-down; standalone-blank rows stay ''
                                json.forEach((row, idx) => {
                                    const xlsxRow = headerRowIdx + 1 + idx;
                                    if (rowTeamNoMap[xlsxRow] !== undefined) {
                                        row[teamNoKey] = rowTeamNoMap[xlsxRow];
                                    }
                                });
                            }
                        }
                        // ── End Team No resolution ────────────────────────────────────


                        processData(json);
                    } catch (error) {
                        console.error('XLSX parse error:', error);
                        reject(new Error('Failed to parse Excel file: ' + error.message));
                    }
                };
                reader.onerror = (error) => reject(error);
                reader.readAsArrayBuffer(file);
            } else {
                Papa.parse(file, {
                    header: true,
                    skipEmptyLines: true,
                    complete: (results) => processData(results.data),
                    error: (error) => reject(error)
                });
            }
        });
    },

    // Semester
    getSemesterConfig: async () => {
        const response = await fetch(`${API_BASE_URL}/data/semester_config`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch semester config');
        const data = await response.json();
        // Return sorted by creation theoretically, or just the list
        return data;
    },
    getActiveSemester: async () => {
        const response = await fetch(`${API_BASE_URL}/data/semester_config`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch active semester');
        const { data } = await response.json();
        const active = data.find(s => s.is_active);
        if (!active) return { success: false, error: { message: "No active semester" } };
        return { data: active };
    },
    createSemesterConfig: async (configData) => {
        const id = configData.id || uuidv4();
        const row = { ...configData, id, is_active: false, is_locked: false };
        const response = await fetch(`${API_BASE_URL}/data/semester_config/upsert`, { 
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ rows: [row], onConflict: 'id' })
        });
        if (!response.ok) throw new Error('Failed to create semester config');
        dispatchSemesterConfigChanged();
        return response.json();
    },
    updateSemesterConfig: async (semesterId, configData) => {
        // Use PATCH instead of upsert — safer when columns may not yet exist in schema cache
        const response = await fetch(`${API_BASE_URL}/data/semester_config/${semesterId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                row_id: semesterId,
                fields: configData
            })
        });
        if (!response.ok) throw new Error('Failed to update semester config');
        clearSemesterCache();
        dispatchSemesterConfigChanged();
        return response.json();
    },
    activateSemester: async (semesterId, isActive = true) => {
        const response = await fetch(`${API_BASE_URL}/data/semester_config/${semesterId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: semesterId,
                fields: { is_active: isActive }
            })
        });
        if (!response.ok) throw new Error(`Failed to ${isActive ? 'activate' : 'deactivate'} semester`);
        clearSemesterCache();
        dispatchSemesterConfigChanged();
        return response.json();
    },
    lockSemester: async (configId, lockStatus = true) => {
        const response = await fetch(`${API_BASE_URL}/data/semester_config/${configId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: configId,
                fields: { is_locked: lockStatus }
            })
        });
        if (!response.ok) throw new Error(`Failed to ${lockStatus ? 'lock' : 'unlock'} configuration`);
        dispatchSemesterConfigChanged();
        return response.json();
    },
    deleteSemester: async (semesterId) => {
        const response = await fetch(`${API_BASE_URL}/semester/${semesterId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        if (!response.ok) {
            const errBody = await response.json().catch(() => ({}));
            throw new Error(errBody.detail?.message || errBody.detail || 'Failed to delete semester');
        }
        clearSemesterCache();
        dispatchSemesterConfigChanged();
        return response.json();
    },
    
    // Proposals
    getProposals: async () => {
        const rows = await apiFetchTable('proposals');
        return { data: rows };
    },
    updateProposalStatus: async (proposalId, status, _feedback = '') => {
        const response = await fetch(`${API_BASE_URL}/data/proposals/${proposalId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: proposalId,
                fields: { status }
            })
        });
        if (!response.ok) throw new Error('Failed to update proposal status');
        return response.json();
    },
    approveProposal: async (data) => {
        const response = await fetch(`${API_BASE_URL}/data/proposals/${data.proposal_id}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: data.proposal_id,
                fields: { 
                    status: 'Approved',
                    remarks: ''
                }
            })
        });
        if (!response.ok) throw new Error('Failed to approve proposal');
        return response.json();
    },
    rejectProposal: async (data) => {
        const response = await fetch(`${API_BASE_URL}/data/proposals/${data.proposal_id}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: data.proposal_id,
                fields: { 
                    status: 'Rejected',
                    remarks: data.feedback || ''
                }
            })
        });
        if (!response.ok) throw new Error('Failed to reject proposal');
        return response.json();
    },
    revisionProposal: async (data) => {
        const response = await fetch(`${API_BASE_URL}/data/proposals/${data.proposal_id}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: data.proposal_id,
                fields: { 
                    status: 'Revision Requested',
                    remarks: data.feedback || ''
                }
            })
        });
        if (!response.ok) throw new Error('Failed to request revision');
        return response.json();
    },
    
    // Teams
    getTeams: async () => {
        const rows = await apiFetchTable('teams_validation');
        return { data: rows };
    },
    renumberTeams: async (semesterId = null) => {
        const response = await fetch(`${API_BASE_URL}/admin/teams/renumber`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ semester_id: semesterId })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to renumber teams');
        }
        return response.json();
    },

    deleteTeam: async (teamId, members = []) => {
        // 1. Get team info to verify members if not passed in
        let resolvedMembers = members;
        if (!resolvedMembers || resolvedMembers.length === 0) {
            try {
                const rows = await apiFetchTable('teams_validation');
                const team = rows.find(t => t.id === teamId);
                if (team) {
                    const raw = team.members;
                    if (Array.isArray(raw)) resolvedMembers = raw;
                    else if (typeof raw === 'string') {
                        try { resolvedMembers = JSON.parse(raw); } catch { /* non-fatal: fall through to the default below */ }
                    }
                }
            } catch { /* non-fatal: fall through to the default below */ }
        }

        // 2. Get active semester id for re-inserting unassigned students
        const activeSemId = await getActiveSemesterId();

        // 3. Re-add all members back to unassigned_students
        if (resolvedMembers && resolvedMembers.length > 0) {
            const unassignedRows = resolvedMembers.map(m => {
                const id = typeof m === 'string' ? m : (m.id || m.student_id || '');
                const name = typeof m === 'string' ? m : (m.name || '');
                const branch = typeof m === 'string' ? 'BTech CSE' : (m.branch || 'BTech CSE');
                const roll = typeof m === 'string' ? m : (m.roll || m.student_id || id);
                return {
                    id,
                    name,
                    branch,
                    roll,
                    ...(activeSemId && activeSemId !== 'NONE' ? { semester_id: activeSemId } : {})
                };
            }).filter(m => m.id);

            if (unassignedRows.length > 0) {
                await apiUpsertTable('unassigned_students', unassignedRows, 'id');
            }
        }

        // 4. Cancel any pending join requests, proposals, and locks for this team
        try {
            await apiDeleteRows('team_join_requests', { team_id: teamId }).catch(() => {});
            await apiDeleteRows('proposals', { team_id: teamId }).catch(() => {});
            await apiDeleteRows('proposals', { teamId: teamId }).catch(() => {});
            await apiDeleteRows('project_locked_ps', { team_id: teamId }).catch(() => {});
            await apiDeleteRows('project_locked_ps', { id: `LOCK-${teamId}` }).catch(() => {});
        } catch { /* non-fatal: fall through to the default below */ }

        // 5. Delete the team from teams_validation
        await apiDeleteRows('teams_validation', { id: teamId });

        return { success: true };
    },

    bulkAssignStudents: async () => {
        return { data: { message: "Bulk assigned 0 students" } }; 
    },

    createCustomTeam: async (leaderId, memberIds, semesterId = null) => {
        // Get active semester ID for all DB writes
        const activeSemId = semesterId || await getActiveSemesterId();

        // Fetch existing teams to calculate next team number AND check for already assigned students
        const allTeams = await apiFetchTable('teams_validation');
        let highestTeamNumber = 0;

        const assignedIds = new Set();
        allTeams.forEach(team => {
            if (String(team.semester_id || '') === String(activeSemId)) {
                const num = teamNumber(team.id, team) || teamNumber(team.title) || teamNumber(team.name);
                if (num !== null && num > highestTeamNumber && num < 5000) {
                    highestTeamNumber = num;
                }
            }

            // Track assigned student IDs, rolls, names across all teams
            ['leader', 'leader_id', 'leader_roll', 'leader_name', 'leaderName'].forEach(field => {
                const lv = team[field];
                if (lv) {
                    if (typeof lv === 'string') assignedIds.add(lv.trim().toLowerCase());
                    else if (typeof lv === 'object') {
                        ['id', 'roll', 'student_id', 'name', 'email'].forEach(k => {
                            if (lv[k]) assignedIds.add(String(lv[k]).trim().toLowerCase());
                        });
                    }
                }
            });

            let members = [];
            if (Array.isArray(team.members)) members = team.members;
            else if (typeof team.members === 'string') {
                try { members = JSON.parse(team.members); } catch { /* non-fatal: fall through to the default below */ }
            }
            members.forEach(m => {
                if (typeof m === 'string') assignedIds.add(m.trim().toLowerCase());
                else if (m && typeof m === 'object') {
                    ['id', 'roll', 'student_id', 'name', 'email', 'student_name'].forEach(k => {
                        if (m[k]) assignedIds.add(String(m[k]).trim().toLowerCase());
                    });
                }
            });
        });

        // Guard against assigning a leader who is already in a team
        const normalizedLeaderId = String(leaderId || '').trim().toLowerCase();
        if (assignedIds.has(normalizedLeaderId)) {
            console.warn(`[createCustomTeam] Leader ${leaderId} is already assigned to a team. Skipping duplicate team creation.`);
            return { error: 'Leader already assigned', skipped: true };
        }

        // Filter out any members already assigned to a team
        const uniqueMemberIds = (memberIds || []).filter(mid => {
            const norm = String(mid || '').trim().toLowerCase();
            return !assignedIds.has(norm) && norm !== normalizedLeaderId;
        });

        const nextTeamNumber = highestTeamNumber + 1;
        const id = `${activeSemId}-T${nextTeamNumber}`;

        // Fetch full student info from both unassigned_students AND students tables
        let unassignedRows = [];
        let studentRowsFromTable = [];
        try { unassignedRows = await apiFetchTable('unassigned_students'); } catch { /* non-fatal: fall through to the default below */ }
        try { studentRowsFromTable = await apiFetchTable('students'); } catch { /* non-fatal: fall through to the default below */ }
        
        const unassignedMap = {};
        unassignedRows.forEach(u => { unassignedMap[String(u.id)] = u; });
        const studentMap = {};
        studentRowsFromTable.forEach(s => { studentMap[String(s.id)] = s; });

        // Build proper member objects with all fields
        const allIds = [leaderId, ...uniqueMemberIds];
        const allMemberObjects = allIds.map(sid => {
            const u = unassignedMap[String(sid)];
            const s = studentMap[String(sid)];
            return {
                id: String(sid),
                name: s?.name || u?.name || String(sid),
                roll: s?.student_id || u?.roll || String(sid),
                student_id: s?.student_id || u?.roll || String(sid),
                branch: s?.branch || u?.branch || 'N/A',
                year: s?.year || u?.year || null,
            };
        });
        
        const leaderMember = allMemberObjects.find(m => m.id === leaderId);

        let defaultYear = 4;
        try {
            const semConfig = await api.getSemesterConfig();
            const sems = semConfig.data || [];
            const targetSem = sems.find(s => s.id === activeSemId);
            if (targetSem) {
                defaultYear = parseInt(targetSem.academic_level || targetSem.year) || 4;
            }
        } catch (err) {
            console.error('Failed to resolve default year in createCustomTeam:', err);
        }

        // 1. Create the team in teams_validation
        const row = {
            id,
            title: `Team ${nextTeamNumber}`,
            leader: leaderMember?.name || leaderId,
            leader_roll: leaderId,
            members: allMemberObjects,
            memberCount: allMemberObjects.length,
            validationStatus: 'Pending',
            branch: allMemberObjects.map(m => m.branch).find(b => b && b !== 'N/A') || null,
            year: allMemberObjects.map(m => m.year).find(Boolean) || defaultYear,
            ...(activeSemId && activeSemId !== 'NONE' ? { semester_id: activeSemId } : {}),
        };
        const payload = await apiUpsertTable('teams_validation', [row], 'id');

        // 2. Upsert each student into the students table (so they're searchable), preserving existing fields
        const studentRows = allMemberObjects.map(m => {
            const existingStudent = studentMap[m.id];
            // Preserve roll number: stored as student_id in the students table
            const rollValue = existingStudent?.student_id || m.roll || m.student_id || null;
            return {
                id: m.id,
                name: existingStudent?.name || m.name,
                branch: existingStudent?.branch || m.branch,
                year: existingStudent?.year || m.year || defaultYear,
                section: existingStudent?.section || 'A',
                status: 'Active',
                // student_id holds the roll number — critical for search to work
                ...(rollValue ? { student_id: rollValue } : {}),
                ...(activeSemId && activeSemId !== 'NONE' ? { semester_id: activeSemId } : {}),
            };
        });
        try {
            await apiUpsertTable('students', studentRows, 'id');
        } catch (e) {
            console.warn('Could not upsert students for bulk team:', e.message);
        }

        // 3. Remove each student from unassigned_students (by id and roll)
        for (const sid of allIds) {
            try {
                await apiDeleteRows('unassigned_students', { id: sid }).catch(() => {});
                await apiDeleteRows('unassigned_students', { roll: sid }).catch(() => {});
            } catch (e) {
                console.warn('Could not remove from unassigned_students:', sid, e.message);
            }
        }

        return payload;
    },
    getTeamFilters: async () => {
        return { data: [] }; // Mocked as it might need complex aggregation
    },
    getUnassignedStudents: async () => {
        try {
            const [students, teams, unassignedRows] = await Promise.all([
                apiFetchTable('students').catch(() => []),
                apiFetchTable('teams_validation').catch(() => []),
                apiFetchTable('unassigned_students').catch(() => [])
            ]);

            // Build set of all student IDs, rolls, and names currently assigned in a team
            const assignedIds = new Set();
            teams.forEach(team => {
                // Add leader info
                ['leader', 'leader_id', 'leader_roll', 'leader_name', 'leaderName'].forEach(field => {
                    const lv = team[field];
                    if (lv) {
                        if (typeof lv === 'string') assignedIds.add(lv.trim().toLowerCase());
                        else if (typeof lv === 'object') {
                            ['id', 'roll', 'student_id', 'name', 'email'].forEach(k => {
                                if (lv[k]) assignedIds.add(String(lv[k]).trim().toLowerCase());
                            });
                        }
                    }
                });

                let members = [];
                if (Array.isArray(team.members)) members = team.members;
                else if (typeof team.members === 'string') {
                    try { members = JSON.parse(team.members); } catch { /* non-fatal: fall through to the default below */ }
                }
                members.forEach(m => {
                    if (typeof m === 'string') assignedIds.add(m.trim().toLowerCase());
                    else if (m && typeof m === 'object') {
                        ['id', 'roll', 'student_id', 'name', 'email', 'student_name'].forEach(k => {
                            if (m[k]) assignedIds.add(String(m[k]).trim().toLowerCase());
                        });
                    }
                });
            });

            // Merge students + unassigned_students into one map (keyed by id)
            const allMap = new Map();
            students.forEach(s => {
                allMap.set(String(s.id).trim(), {
                    id: s.id,
                    name: s.name || s.student_name || s.id,
                    roll: s.student_id || s.roll || s.studentId || s.id,
                    branch: s.branch || 'N/A',
                    year: s.year || null
                });
            });
            
            unassignedRows.forEach(u => {
                const existing = allMap.get(String(u.id).trim());
                if (existing) {
                    allMap.set(String(u.id).trim(), {
                        ...existing,
                        name: u.name || existing.name,
                        roll: u.roll || existing.roll,
                        branch: u.branch || existing.branch,
                        year: u.year || existing.year || null
                    });
                } else {
                    allMap.set(String(u.id).trim(), {
                        id: u.id,
                        name: u.name || u.id,
                        roll: u.roll || u.id,
                        branch: u.branch || 'N/A',
                        year: u.year || null
                    });
                }
            });

            // Return only students who are NOT in any team
            const result = [];
            const idsToDelete = [];
            for (const [, student] of allMap.entries()) {
                const sId = String(student.id || '').trim().toLowerCase();
                const sRoll = String(student.roll || '').trim().toLowerCase();
                const sName = String(student.name || '').trim().toLowerCase();

                const isAssigned = (
                    (sId && assignedIds.has(sId)) ||
                    (sRoll && assignedIds.has(sRoll)) ||
                    (sName && assignedIds.has(sName))
                );

                const isProbe = (
                    sId.includes('probe') || sRoll.includes('probe') || sName.includes('probe') ||
                    sRoll === '99999997' || sId === '99999997' || sId.startsWith('__sec_')
                );

                if (!isAssigned && !isProbe) {
                    result.push(student);
                } else {
                    idsToDelete.push(student.id);
                    if (student.roll && student.roll !== student.id) idsToDelete.push(student.roll);
                }
            }

            // Asynchronously clean stale assigned students from unassigned_students table.
            // Guard against running while a previous cleanup is still in-flight to prevent
            // flooding the server with repeated DELETE requests on every poll cycle.
            const cleanupKey = idsToDelete.slice().sort().join(',');
            if (
                idsToDelete.length > 0 &&
                cleanupKey !== _lastUnassignedCleanupKey
            ) {
                _lastUnassignedCleanupKey = cleanupKey;
                (async () => {
                    for (const aid of idsToDelete) {
                        try { await apiDeleteRows('unassigned_students', { id: aid }); } catch { /* non-fatal: fall through to the default below */ }
                        try { await apiDeleteRows('unassigned_students', { roll: aid }); } catch { /* non-fatal: fall through to the default below */ }
                    }
                    // Reset the key after cleanup so a genuine future change triggers cleanup again
                    _lastUnassignedCleanupKey = null;
                })();
            }

            return { data: result };

        } catch (error) {
            console.error('Error computing unassigned students:', error);
            throw error;
        }
    },
    validateTeam: async (teamId) => {
        const response = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: teamId,
                fields: { validationStatus: 'Valid' }
            })
        });
        if (!response.ok) throw new Error('Failed to validate team');
        return response.json();
    },
    manualOverrideTeam: async (teamId, _panelId, _reason) => {
        const response = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: teamId,
                fields: {
                    validationStatus: 'Invalid'
                }
            })
        });
        if (!response.ok) throw new Error('Failed to override team');
        return response.json();
    },
    updateTeamValidationStatus: async (teamId, status) => {
        const response = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: teamId,
                fields: { validationStatus: status }
            })
        });
        if (!response.ok) throw new Error(`Failed to update team status to '${status}`);
        return response.json();
    },
    assignToTeam: async (studentId, teamId) => {
        try {
            // Fetch the team
            const response = await fetch(`${API_BASE_URL}/data/teams_validation?id=eq.${teamId}`, { headers: getAuthHeaders() });
            const { data } = await response.json();
            const team = data && data[0];
            if (!team) throw new Error('Team not found');
            
            let members = [];
            if (Array.isArray(team.members)) members = team.members;
            else if (typeof team.members === 'string') {
                try { members = JSON.parse(team.members); } catch { /* non-fatal: fall through to the default below */ }
            }
            
            if (!members.find(m => String(typeof m === 'string' ? m : m.id) === String(studentId))) {
                const studentRes = await fetch(`${API_BASE_URL}/data/students?id=eq.${studentId}`, { headers: getAuthHeaders() });
                const studentData = await studentRes.json();
                const student = studentData.data && studentData.data[0];
                
                // Also check unassigned_students to get full info
                let unassignedStudent = null;
                try {
                    const unassignedRes = await fetch(`${API_BASE_URL}/data/unassigned_students?id=eq.${studentId}`, { headers: getAuthHeaders() });
                    const unassignedData = await unassignedRes.json();
                    unassignedStudent = unassignedData.data?.[0];
                } catch { /* non-fatal: fall through to the default below */ }
                
                if (student || unassignedStudent) {
                    const s = student || unassignedStudent;
                    members.push({ 
                        id: s.id, 
                        name: s.name, 
                        branch: s.branch, 
                        roll: s.student_id || unassignedStudent?.roll || s.id,
                        student_id: s.student_id || unassignedStudent?.roll || s.id
                    });
                } else {
                    members.push(studentId);
                }
                
                const patchRes = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
                    method: 'PATCH',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({
                        row_id: teamId,
                        fields: {
                            members: members,
                            memberCount: members.length
                        }
                    })
                });
                if (!patchRes.ok) throw new Error('Failed to update team');

                // Proactively remove the student from the unassigned_students table
                try {
                    await apiDeleteRows('unassigned_students', { id: studentId });
                } catch (delErr) {
                    console.error("Failed to delete from unassigned_students:", delErr);
                }

                return await patchRes.json();
            }
            return { data: { success: true } };
        } catch (err) {
            console.error("Error assigning to team:", err);
            throw err;
        }
    },
    removeFromTeam: async (studentId, teamId, _memberObj = null) => {
        try {
            const params = new URLSearchParams({ student_id: studentId });
            if (teamId) params.set('team_id', teamId);
            const response = await fetch(`${API_BASE_URL}/admin/team/remove-member?${params}`, {
                method: 'POST',
                headers: getAuthHeaders(),
            });

            if (!response.ok) {
                const errorBody = await response.json().catch(() => ({}));
                throw new Error(errorBody.detail?.message || errorBody.detail || 'Failed to remove from team');
            }

            return await response.json();
        } catch (err) {
            console.error('Error removing from team:', err);
            throw err;
        }
    },

    /**
     * Force-add a student to a team with NO leader approval.
     * Writes the canonical team_memberships row server-side; DB triggers rebuild
     * teams_validation.members / memberCount and the legacy team_members row.
     * teamId may be the teams_validation slug id or its uid.
     */
    forceAddToTeam: async (studentId, teamId, role = 'MEMBER') => {
        const params = new URLSearchParams({ student_id: studentId, team_id: teamId, role });
        const response = await fetch(`${API_BASE_URL}/admin/team/add-member?${params}`, {
            method: 'POST',
            headers: getAuthHeaders(),
        });
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail?.message || body.detail || body.message || 'Failed to add student to team');
        }
        return response.json();
    },


    // Join Requests (Feature 4 - Team Agreement Flow)
    sendJoinRequest: async (student, teamId, teamName, teamMembers = []) => {
        // Identify the leader: match by name or fall back to first member
        const leaderMember = teamMembers.find(m => m.isLeader) || teamMembers[0] || null;
        const leaderId = leaderMember?.id || '';

        const row = {
            id: uuidv4(),
            team_id: teamId,
            team_name: teamName || '',
            student_id: student.id,
            student_name: student.name || '',
            student_branch: student.branch || '',
            leader_id: leaderId,
            status: 'pending',
            initiated_by: 'admin',
            requested_at: new Date().toISOString()
        };
        const response = await fetch(`${API_BASE_URL}/data/team_join_requests/upsert`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ rows: [row], onConflict: 'id' })
        });
        if (!response.ok) throw new Error('Failed to send join request');
        return response.json();
    },
    getTeamJoinRequests: async (teamId) => {
        const response = await fetch(`${API_BASE_URL}/data/team_join_requests`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch join requests');
        const json = await response.json();
        const all = json.data || [];
        return { data: all.filter(r => r.team_id === teamId) };
    },

    /**
     * Accept a join request on the team's behalf (admin override).
     * Delegates to the canonical force-add endpoint, which writes
     * team_memberships, lets triggers rebuild the roster, clears the student
     * from unassigned, marks THIS request 'accepted' and cancels the student's
     * other pending requests.
     */
    acceptJoinRequest: async (requestId, studentId, studentName, studentBranch, teamId) => {
        const params = new URLSearchParams({ student_id: studentId, team_id: teamId, role: 'MEMBER' });
        const response = await fetch(`${API_BASE_URL}/admin/team/add-member?${params}`, {
            method: 'POST',
            headers: getAuthHeaders(),
        });
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail?.message || body.detail || body.message || 'Failed to accept join request');
        }
        return { success: true };
    },

    /** Cancel (decline) a single join request */
    cancelJoinRequest: async (requestId) => {
        const response = await fetch(`${API_BASE_URL}/data/team_join_requests/${requestId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                row_id: requestId,
                fields: { status: 'cancelled', resolved_at: new Date().toISOString() }
            })
        });
        if (!response.ok) throw new Error('Failed to cancel join request');
        return response.json();
    },

    getProjectConflicts: async () => {
        const rows = await apiFetchTable('project_locked_ps');
        return { data: rows };
    },
    getDetailedUnallocated: async () => {
        const rows = await apiFetchTable('project_unallocated_students');
        return { data: rows };
    },
    resolveConflict: async (conflictId, _reason) => {
        const response = await fetch(`${API_BASE_URL}/data/project_locked_ps/delete`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ filters: { id: conflictId } })
        });
        if (!response.ok) throw new Error('Failed to resolve conflict');
        return response.json();
    },
    forceAssign: async (studentId) => {
        const response = await fetch(`${API_BASE_URL}/data/project_unallocated_students/delete`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ filters: { id: studentId } })
        });
        if (!response.ok) throw new Error('Failed to force assign');
        return response.json();
    },

    // Mentors
    getMentors: async (page = 1, limit = 100) => {
        const response = await fetch(`${API_BASE_URL}/data/mentors?page=${page}&limit=${limit}`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch mentors');
        return response.json();
    },
    assignMentor: async (mentorId, teamId) => {
        const response = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                row_id: teamId,
                fields: { mentor: mentorId }
            })
        });
        if (!response.ok) throw new Error('Failed to assign mentor');
        return response.json();
    },
    autoAssignMentors: async () => {
        return { data: { message: "Auto-assigned mentors" } };
    },
    getMentorRecommendations: async (_teamId) => {
        const response = await fetch(`${API_BASE_URL}/data/mentors`, { headers: getAuthHeaders() });
        return response.json();
    },

    // Schedule / Panels
    getSchedule: async () => {
        const rows = await apiFetchTable('schedule_slots');
        return { data: rows };
    },
    getPanels: async () => {
        const rows = await apiFetchTable('panels');
        return { data: rows };
    },

    // Evaluations
    getEvaluations: async () => {
        const rows = await apiFetchTable('evaluation_queue');
        return { data: rows };
    },

    // Governance
    getGovernanceStatus: async () => {
        return { data: { activeSemesters: 1, pendingProposals: 0 } };
    },
    getDeadlines: async (semesterId = null) => {
        // Display metadata for the standard deadline types — labels ONLY, and
        // deliberately no dates.
        //
        // This used to be DEFAULT_DEADLINES_LIST, carrying invented due dates
        // (2026-04-01 / 04-15 / 05-15 / 06-20). Because the fallbacks below
        // returned that whole list whenever the table was empty or the read
        // failed, the Governance screen showed four fully-configured deadlines
        // that existed nowhere — and publishing them broadcast those invented
        // dates to real students. Three of the four did reach recipients.
        //
        // Naming a deadline the admin really created is fine; inventing one is
        // not. Hence labels here and an empty list below.
        const DEADLINE_LABELS = {
            teamFormation:   { title: 'Team Formation',      description: 'Last day to form or join a team.',         color: 'indigo' },
            proposalUpload:  { title: 'Proposal Submission', description: 'Last day to submit the project proposal.', color: 'blue' },
            midTerm:         { title: 'Mid-Term Evaluation', description: 'Mid-term presentation and marking date.',  color: 'amber' },
            finalEvaluation: { title: 'Final Evaluation',    description: 'Final presentation and result date.',      color: 'emerald' }
        };

        try {
            localStorage.removeItem('system_deadlines_list');
            localStorage.removeItem('system_deadlines');
        } catch { /* non-fatal: fall through to the default below */ }

        try {
            const rows = await apiFetchTable('deadlines');
            if (rows && rows.length > 0) {
                const list = rows.map(r => {
                    const std = DEADLINE_LABELS[r.type] || DEADLINE_LABELS[r.id] || {};
                    return {
                        id: r.id || r.type,
                        db_id: r.id,
                        semester_id: r.semester_id || null,
                        type: r.type || r.id,
                        title: r.title || r.name || std.title || r.type,
                        description: r.description || std.description || '',
                        start_date: r.start_date || '',
                        due_date: r.due_date ? String(r.due_date) : '',
                        color: r.color || std.color || 'indigo'
                    };
                });
                if (semesterId && semesterId !== 'all' && semesterId !== 'NONE') {
                    return { data: list.filter(d => !d.semester_id || String(d.semester_id) === String(semesterId)) };
                }
                return { data: list };
            }
            return { data: [] };
        } catch (e) {
            console.error('Failed to fetch deadlines from DB', e);
            return { data: [] };
        }
    },

    sendDeadlineEmail: async () => {
        const response = await fetch(`${API_BASE_URL}/admin/communication/send-deadline-email`, {
            method: 'POST',
            headers: getAuthHeaders(),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to dispatch mass deadline email');
        }
        return response.json();
    },
    sendPsReleasedEmail: async () => {
        const response = await fetch(`${API_BASE_URL}/admin/communication/send-ps-released-email`, {
            method: 'POST',
            headers: getAuthHeaders(),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to dispatch Problem Statement release email');
        }
        return response.json();
    },
    updateDeadlines: async (deadlinesInput) => {
        let deadlinesList = [];
        if (Array.isArray(deadlinesInput)) {
            deadlinesList = deadlinesInput;
        } else if (deadlinesInput && typeof deadlinesInput === 'object') {
            deadlinesList = Object.entries(deadlinesInput).map(([key, val]) => {
                if (typeof val === 'object' && val !== null) return { id: key, type: key, ...val };
                return { id: key, type: key, due_date: val };
            });
        }
        try {
            localStorage.removeItem('system_deadlines_list');
            localStorage.removeItem('system_deadlines');
        } catch { /* non-fatal: fall through to the default below */ }

        try {
            let existingRows = [];
            try {
                existingRows = await apiFetchTable('deadlines');
            } catch (e) {
                console.error("Failed to fetch existing deadlines for update", e);
            }
            const existingMapByDbId = {};
            const existingMapByTypeSem = {};
            existingRows.forEach(r => {
                if (r.id) existingMapByDbId[r.id] = r.id;
                const semKey = r.semester_id ? String(r.semester_id) : 'global';
                existingMapByTypeSem[`${r.type}_${semKey}`] = r.id;
                if (r.id) existingMapByTypeSem[`${r.id}_${semKey}`] = r.id;
            });

            const rows = deadlinesList.map((item, idx) => {
                let semId = item.semester_id;
                if (!semId || semId === 'all' || semId === 'global') {
                    semId = null;
                }
                const semKey = semId ? String(semId) : 'global';
                const typeSemKey = `${item.type || item.id || `custom_${idx}`}_${semKey}`;
                
                let rowId = item.db_id || existingMapByDbId[item.id];
                if (!rowId) {
                    rowId = existingMapByTypeSem[typeSemKey];
                }
                if (!rowId && item.id && item.id.includes('-')) {
                    rowId = item.id;
                }
                if (!rowId) {
                    rowId = uuidv4();
                }

                const dDate = item.due_date || item.deadline_date || '';
                const sDate = item.start_date || '';
                return {
                    id: rowId,
                    semester_id: semId,
                    type: item.type || item.id || `custom_${idx}`,
                    title: item.title || item.name || item.type,
                    description: item.description || '',
                    start_date: sDate ? (sDate.includes('T') ? sDate : `${sDate}T00:00:00`) : null,
                    due_date: dDate ? (dDate.includes('T') ? dDate : `${dDate}T23:59:59`) : null
                };
            });
            await apiUpsertTable('deadlines', rows, 'id');
        } catch (e) {
            console.error('Failed to update DB deadlines', e);
            throw e;
        }
        return { success: true };
    },
    deleteDeadline: async (deadlineId) => {
        try {
            if (deadlineId) {
                await apiDeleteRows('deadlines', { id: deadlineId }).catch(() => {});
                await apiDeleteRows('deadlines', { type: deadlineId }).catch(() => {});
            }
        } catch (e) {
            console.error('Failed to delete deadline from DB', e);
        }
        return { success: true };
    },
    getAuditLogs: async (page = 1, limit = 4) => {
        const response = await fetch(`${API_BASE_URL}/data/governance_audit`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch audit logs');
        const json = await response.json();
        if (json.data && Array.isArray(json.data)) {
            // Sort by id descending
            json.data = json.data.sort((a, b) => b.id - a.id).slice((page - 1) * limit, page * limit);
        }
        return json;
    },
    
    // Custom dashboard methods
    getDashboardStats: async (semesterId) => {
        const targetId = semesterId || 'ALL';
        const response = await fetch(`${API_BASE_URL}/dashboard/stats?semester_id=${targetId}`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch stats');
        return response.json();
    },
    getDashboardActivity: async () => {
        const response = await fetch(`${API_BASE_URL}/dashboard/activity`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch activity');
        return response.json();
    },
    importProblemStatements: async (file, year = null) => {
        const formData = new FormData();
        formData.append('file', file);
        let url = `${API_BASE_URL}/admin/projects/import-ps`;
        if (year) {
            url += `?year=${year}`;
        }
        const response = await fetch(url, {
            method: 'POST',
            headers: getAuthHeaders(true),
            body: formData
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to import problem statements');
        }
        const data = await response.json().catch(() => ({}));
        return data || {};
    },
    generateAiSuggestions: async (psData) => {
        const response = await fetch(`${API_BASE_URL}/admin/projects/generate-ai-suggestions`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(psData)
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            const errDetail = typeof err.detail === 'string'
                ? err.detail
                : (Array.isArray(err.detail) ? err.detail.map(d => `${d.loc ? d.loc.join('.') : ''}: ${d.msg}`).join(', ') : JSON.stringify(err.detail || 'Failed to generate AI suggestions'));
            throw new Error(errDetail);
        }
        return response.json();
    },
    getStudentPreferences: async () => {
        const response = await fetch(`${API_BASE_URL}/data/student_preferences`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch preferences');
        return response.json();
    },
    getProblemStatements: async () => {
        const response = await fetch(`${API_BASE_URL}/data/problem_statements`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch problem statements');
        return response.json();
    },
    allocateProject: async (teamId, title, description, domain) => {
        const response = await fetch(`${API_BASE_URL}/data/teams_validation/${teamId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                row_id: teamId,
                fields: {
                    title,
                    description,
                    domain,
                    validationStatus: 'Valid',
                    allow_override: true
                }
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to allocate project');
        }
        return response.json();
    },
    getTeamsAnalysis: async () => {
        const response = await fetch(`${API_BASE_URL}/admin/github/teams-analysis`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error('Failed to fetch teams repository analysis list');
        return response.json();
    },
    getTeamAnalysisDetail: async (teamId) => {
        const response = await fetch(`${API_BASE_URL}/admin/github/team-analysis/${teamId}`, { headers: getAuthHeaders() });
        if (!response.ok) throw new Error(`Failed to fetch team analysis details for ${teamId}`);
        return response.json();
    },
    triggerTeamAnalysis: async (teamId) => {
        const response = await fetch(`${API_BASE_URL}/admin/github/trigger-analysis/${teamId}`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Failed to trigger/refresh analysis for team ${teamId}`);
        }
        return response.json();
    },
    notifyPendingTeams: async (payload = {}) => {
        const response = await fetch(`${API_BASE_URL}/admin/teams/notify-pending`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to send notifications to pending teams');
        }
        return response.json();
    }
};
