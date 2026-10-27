import { getStoredGlobalFilters } from './globalFilters.js';
import { getApiBaseUrl } from './apiBase.js';

const API_BASE_URL = getApiBaseUrl();

const SESSION_KEY = 'procksi-admin-session';

function getJsonOrThrow(response, fallbackMessage) {
    return response
        .json()
        .catch(() => {
            throw new Error(fallbackMessage);
        });
}

export function getStoredSession() {
    try {
        const raw = localStorage.getItem(SESSION_KEY);
        if (!raw) {
            return null;
        }
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export function getAuthToken() {
    const directToken = localStorage.getItem('access_token');
    if (directToken) return directToken;
    const session = getStoredSession();
    return session?.access_token || null;
}

export function getRefreshToken() {
    return getStoredSession()?.refresh_token || null;
}

// Session renewal.
//
// Supabase access tokens last an hour. Without renewal the portal simply
// starts 401-ing at the sixty-minute mark, every component retries with the
// same dead token, and the only remedy is a manual re-login.
//
// One flight at a time: a page can have a dozen requests in the air, and each
// 401 must not start its own refresh -- the first rotates the token and the
// rest would then present one that has already been replaced.
let refreshInFlight = null;

// Set by App.jsx so an unrenewable session ends at the login screen rather
// than in a silent loop of failures.
let onSessionExpired = null;
export function setSessionExpiredHandler(fn) {
    onSessionExpired = typeof fn === 'function' ? fn : null;
}

export async function refreshSession() {
    if (refreshInFlight) return refreshInFlight;

    const refresh_token = getRefreshToken();
    if (!refresh_token) return null;

    refreshInFlight = (async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token }),
            });
            if (!response.ok) return null;
            const payload = await response.json().catch(() => null);
            if (!payload?.access_token) return null;
            // Keep the existing user object when the refresh omits it, so a
            // renewal cannot quietly blank out who is logged in.
            const prev = getStoredSession() || {};
            storeSession({ ...prev, ...payload, user: payload.user || prev.user });
            return payload.access_token;
        } catch {
            return null;   // offline: leave the session alone and let the caller fail
        } finally {
            refreshInFlight = null;
        }
    })();

    return refreshInFlight;
}

/**
 * Run a request, and on a 401 renew the session once and run it again.
 *
 * `send` is called with the current headers and must return the Response.
 * Anything that is not a 401 is passed straight through, so existing callers
 * keep their own error handling.
 */
export async function withAuthRetry(send) {
    let response = await send(getAuthHeaders());
    if (response.status !== 401) return response;

    const token = await refreshSession();
    if (!token) {
        // Unrenewable. Clear up front so nothing keeps presenting a dead token.
        if (onSessionExpired) onSessionExpired();
        return response;
    }
    response = await send(getAuthHeaders());
    return response;
}

export function getAuthHeaders(extra = {}) {
    const token = getAuthToken();
    return {
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...extra,
    };
}

export function storeSession(sessionPayload) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessionPayload));
    if (sessionPayload?.access_token) {
        localStorage.setItem('access_token', sessionPayload.access_token);
    }
    window.dispatchEvent(new CustomEvent('procksi-auth-changed'));
}

export function clearSession() {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem('access_token');
    window.dispatchEvent(new CustomEvent('procksi-auth-changed'));
}

export async function apiLogin(email, password) {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
    });

    const payload = await getJsonOrThrow(response, 'Invalid server response during login.');

    if (!response.ok) {
        throw new Error(payload.detail || 'Login failed.');
    }

    if (payload.access_token) {
        localStorage.setItem('access_token', payload.access_token);
        window.dispatchEvent(new CustomEvent('procksi-auth-changed'));
    }

    return payload;
}

export async function apiLogout(accessToken) {
    // The caller may pass a token explicitly — during logout the stored one is
    // often already cleared. getAuthHeaders() only reads storage, so the
    // computed token was being discarded and the request sent unauthenticated.
    const token = accessToken || getAuthToken();
    const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: {
            ...getAuthHeaders({ 'Content-Type': 'application/json' }),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
    });

    if (!response.ok) {
        const payload = await getJsonOrThrow(response, 'Logout failed.');
        throw new Error(payload.detail || 'Logout failed.');
    }
}

// --- Semester Cache ---
let cachedActiveSemesterIds = null;
let lastCacheTime = 0;
const CACHE_TTL_MS = 10000; // 10s cache

export function clearSemesterCache() {
    cachedActiveSemesterIds = null;
    lastCacheTime = 0;
}

export async function getActiveSemesterIds() {
    if (cachedActiveSemesterIds && (Date.now() - lastCacheTime < CACHE_TTL_MS)) {
        return cachedActiveSemesterIds;
    }
    try {
        const response = await withAuthRetry((headers) =>
            fetch(`${API_BASE_URL}/api/data/semester_config`, { headers }),
        );
        const payload = await getJsonOrThrow(response, 'Failed to fetch semesters');
        if (response.ok && payload.data && payload.data.length > 0) {
            const activeSems = payload.data.filter(s => s.is_active !== false);
            const targetSems = activeSems.length > 0 ? activeSems : payload.data;
            const ids = targetSems.map(s => s.id);
            cachedActiveSemesterIds = ids;
            lastCacheTime = Date.now();
            return ids;
        }
    } catch (e) {
        console.error('Failed to resolve active semesters', e);
    }
    cachedActiveSemesterIds = [];
    lastCacheTime = Date.now();
    return [];
}

export async function getActiveSemesterId() {
    const ids = await getActiveSemesterIds();
    return ids.length > 0 ? ids[0] : 'NONE';
}
// ----------------------

// --- Table Fetch Cache & Request Deduplication ---
const tableDataCache = new Map();
const inFlightTableRequests = new Map();
const TABLE_CACHE_TTL = 3000; // 3s TTL for lightning-fast UI navigation

export function clearTableCache() {
    tableDataCache.clear();
    inFlightTableRequests.clear();
}

if (typeof window !== 'undefined') {
    window.addEventListener('procksi-admin-global-filters-changed', () => {
        clearTableCache();
        clearSemesterCache();
    });
}

export async function apiFetchTable(tableName, { select = '*', orderBy, ascending = true, semesterOverride = null } = {}) {
    const queryParams = new URLSearchParams({ select, ascending: String(Boolean(ascending)) });
    if (orderBy) {
        queryParams.set('orderBy', orderBy);
    }

    // Skip semester filtering for these tables (global data, or student-submitted data without semester_id)
    const noSemesterFilter = [
        'semester_config', 
        'mentors', 
        'panels', 
        'proposals', 
        'notifications', 
        'team_join_requests', 
        'problem_statements', 
        'student_preferences', 
        'extra_activities', 
        'presentation_submissions', 
        'presentation_evaluations', 
        'presentation_schedule', 
        'presentation_cycle_audit',
        'presentation_rubrics',
        'presentation_evaluation_scores',
        'conversation_messages'
    ];
    if (!noSemesterFilter.includes(tableName)) {
        if (semesterOverride) {
            // Explicit semester requested
            if (semesterOverride === 'all') {
                queryParams.set('semester_id', 'all');
            } else {
                queryParams.set('semester_id', `in.(${semesterOverride})`);
            }
        } else {
            const globalFilters = getStoredGlobalFilters();
            const selectedSemesterId = globalFilters?.semesterId;
            if (selectedSemesterId && selectedSemesterId !== 'all') {
                queryParams.set('semester_id', `eq.${selectedSemesterId}`);
            } else {
                const activeSemIds = await getActiveSemesterIds();
                if (activeSemIds.length > 0) {
                    queryParams.set('semester_id', `in.(${activeSemIds.join(',')})`);
                }
            }
        }
    }


    const cacheKey = `${tableName}?${queryParams.toString()}`;
    const cached = tableDataCache.get(cacheKey);
    if (cached && (Date.now() - cached.timestamp < TABLE_CACHE_TTL)) {
        return cached.data;
    }

    if (inFlightTableRequests.has(cacheKey)) {
        return inFlightTableRequests.get(cacheKey);
    }

    const fetchPromise = (async () => {
        try {
            const response = await withAuthRetry((headers) =>
                fetch(`${API_BASE_URL}/api/data/${tableName}?${queryParams.toString()}`, { headers }),
            );
            const payload = await getJsonOrThrow(response, 'Failed to fetch table data.');

            if (!response.ok) {
                throw new Error(payload.detail || 'Failed to fetch table data.');
            }

            const rows = Array.isArray(payload.data) ? payload.data : [];
            tableDataCache.set(cacheKey, { data: rows, timestamp: Date.now() });
            return rows;
        } finally {
            inFlightTableRequests.delete(cacheKey);
        }
    })();

    inFlightTableRequests.set(cacheKey, fetchPromise);
    return fetchPromise;
}

export async function apiUpsertTable(tableName, rows, onConflict = null) {
    let processedRows = Array.isArray(rows) ? [...rows] : [rows];

    if (!['semester_config', 'mentors', 'panels', 'notifications', 'problem_statements', 'student_preferences', 'extra_activities', 'presentation_rubrics', 'presentation_evaluation_scores', 'conversation_messages'].includes(tableName)) {
        const activeSemId = await getActiveSemesterId();
        if (activeSemId !== 'NONE') {
            processedRows = processedRows.map(row => ({
                ...row,
                semester_id: row.semester_id || activeSemId
            }));
        }
    }

    // Deduplicate rows client-side if a conflict resolution column is provided,
    // keeping the last occurrence of each key to prevent Postgres upsert constraints.
    if (onConflict && Array.isArray(processedRows)) {
        const seen = new Set();
        const deduplicated = [];
        for (let i = processedRows.length - 1; i >= 0; i--) {
            const row = processedRows[i];
            const keyVal = row[onConflict];
            if (keyVal !== undefined && keyVal !== null && keyVal !== '') {
                const keyValStr = String(keyVal).trim().toLowerCase();
                if (!seen.has(keyValStr)) {
                    seen.add(keyValStr);
                    deduplicated.unshift(row);
                }
            } else {
                deduplicated.unshift(row);
            }
        }
        processedRows = deduplicated;
    }

    const response = await withAuthRetry((headers) =>
        fetch(`${API_BASE_URL}/api/data/${tableName}/upsert`, {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ rows: processedRows, onConflict }),
        }),
    );

    const payload = await getJsonOrThrow(response, 'Failed to upsert table data.');

    if (!response.ok) {
        throw new Error(payload.detail || 'Failed to upsert table data.');
    }

    clearTableCache();
    return payload;
}

export async function apiDeleteRows(tableName, filters) {
    const response = await withAuthRetry((headers) =>
        fetch(`${API_BASE_URL}/api/data/${tableName}/delete`, {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ filters }),
        }),
    );

    const payload = await getJsonOrThrow(response, 'Failed to delete table rows.');

    if (!response.ok) {
        throw new Error(payload.detail || 'Failed to delete table rows.');
    }

    clearTableCache();
    return payload;
}

export async function apiPatchRow(tableName, rowId, fields) {
    const response = await withAuthRetry((headers) =>
        fetch(`${API_BASE_URL}/api/data/${tableName}/${rowId}`, {
            method: 'PATCH',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ row_id: rowId, fields }),
        }),
    );

    const payload = await getJsonOrThrow(response, 'Failed to patch row.');

    if (!response.ok) {
        throw new Error(payload.detail || 'Failed to patch row.');
    }

    clearTableCache();
    return payload;
}

// Manual, on-demand dispatch: mentor emails are always one email per mentor
// listing every team in scope, never one per team. No automatic email fires
// for mentor-team assignment — an admin sends this deliberately, choosing:
// - mentorName: null for every mentor with an assigned team, or one name to
//   scope to just that mentor (and their teams)
// - notifyMentor / notifyTeams: which side(s) to email
export async function sendMentorAssignmentEmails({ mentorName = null, notifyMentor = true, notifyTeams = false } = {}) {
    const response = await withAuthRetry((headers) =>
        fetch(`${API_BASE_URL}/api/admin/communication/send-mentor-assignment-emails`, {
            method: 'POST',
            headers: { ...headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ mentor_name: mentorName, notify_mentor: notifyMentor, notify_teams: notifyTeams }),
        }),
    );

    const payload = await getJsonOrThrow(response, 'Failed to dispatch mentor assignment emails.');

    if (!response.ok) {
        throw new Error(payload.detail || 'Failed to dispatch mentor assignment emails.');
    }

    return payload;
}
