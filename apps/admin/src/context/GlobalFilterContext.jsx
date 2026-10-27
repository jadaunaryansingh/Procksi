import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { GlobalFilterContext } from './globalFilterContextObject';
import {
    DEFAULT_GLOBAL_FILTERS,
    buildSemesterMap,
    filterRowsByGlobalFilters,
    getStoredGlobalFilters,
    saveStoredGlobalFilters,
} from '../lib/globalFilters';
import { getApiBaseUrl } from '../lib/apiBase.js';
import { getAuthHeaders, getAuthToken } from '../lib/api.js';



export function GlobalFilterProvider({ children }) {
    const [filters, setFilters] = useState(() => getStoredGlobalFilters());
    const [semesters, setSemesters] = useState([]);

    // The retry recursion lives in a plain function rather than inside the
    // useCallback: referencing `loadSemesters` from its own body meant reading
    // the binding before it was initialised, which is what the compiler flags.
    // Only setSemesters is captured, and setters are stable.
    const loadSemesters = useCallback(() => {
        // /api/data/semester_config now requires an admin session (it used to
        // be carved out as public, which meant anyone could dump the whole
        // table with no auth at all). Skip the call entirely until a token
        // exists -- e.g. while this provider is mounted under the login
        // screen -- rather than firing a request we know will 401. The
        // procksi-auth-changed listener below re-triggers this once login
        // succeeds.
        if (!getAuthToken()) {
            setSemesters([]);
            return;
        }
        const attempt = (retryCount) => {
            const apiBase = getApiBaseUrl();
            fetch(`${apiBase}/api/data/semester_config`, {
                headers: getAuthHeaders(),
            })
                .then((response) => {
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    return response.json();
                })
                .then((payload) => {
                    setSemesters(Array.isArray(payload?.data) ? payload.data : []);
                })
                .catch((err) => {
                    console.warn(`[GlobalFilter] Failed to load semester_config (attempt ${retryCount + 1}):`, err.message);
                    setSemesters([]);
                    // Retry up to 3 times with a 3s delay — handles the
                    // backend-still-starting race condition.
                    if (retryCount < 3) {
                        setTimeout(() => attempt(retryCount + 1), 3000);
                    }
                });
        };
        attempt(0);
    }, []);

    useEffect(() => {
        loadSemesters();
        const handleAuthChange = () => loadSemesters();
        window.addEventListener('procksi-semester-config-changed', loadSemesters);
        window.addEventListener('procksi-auth-changed', handleAuthChange);
        const handleStorageChange = (e) => {
            if (e.key === 'access_token' || e.key === 'procksi-admin-session') {
                loadSemesters();
            }
        };
        window.addEventListener('storage', handleStorageChange);

        return () => {
            window.removeEventListener('procksi-semester-config-changed', loadSemesters);
            window.removeEventListener('procksi-auth-changed', handleAuthChange);
            window.removeEventListener('storage', handleStorageChange);
        };
    }, [loadSemesters]);

    useEffect(() => {
        saveStoredGlobalFilters(filters);
        window.dispatchEvent(new CustomEvent('procksi-admin-global-filters-changed', { detail: filters }));
    }, [filters]);

    useEffect(() => {
        const handleCustomEvent = (event) => {
            const newFilters = event.detail;
            if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                setFilters(newFilters);
            }
        };

        const handleStorageEvent = (event) => {
            if (event.key === 'procksi-admin-global-filters' && event.newValue) {
                try {
                    const newFilters = JSON.parse(event.newValue);
                    if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                        setFilters(newFilters);
                    }
                } catch (e) {
                    console.error("Failed to parse admin global filters from storage", e);
                }
            }
        };

        window.addEventListener('procksi-admin-global-filters-changed', handleCustomEvent);
        window.addEventListener('storage', handleStorageEvent);

        return () => {
            window.removeEventListener('procksi-admin-global-filters-changed', handleCustomEvent);
            window.removeEventListener('storage', handleStorageEvent);
        };
    }, [filters]);

    const semesterMap = useMemo(() => buildSemesterMap(semesters), [semesters]);

    const semesterOptions = useMemo(() => semesters.map((semester) => ({
        id: semester.id,
        label: [
            semester.year,
            semester.semester_type ? `${String(semester.semester_type).charAt(0).toUpperCase()}${String(semester.semester_type).slice(1)}` : '',
            semester.branch,
            semester.academic_level ? `Yr ${semester.academic_level}` : '',
            semester.is_active ? 'Active' : '',
        ].filter(Boolean).join(' / '),
    })), [semesters]);

    const yearOptions = useMemo(() => {
        const years = new Set();
        semesters.forEach((semester) => {
            if (semester.year && !/\d{4}/.test(String(semester.year))) {
                years.add(String(semester.year));
            }
            if (semester.academic_level && !/\d{4}/.test(String(semester.academic_level))) {
                years.add(String(semester.academic_level));
            }
            if (semester.semester_number) {
                const yearVal = String(Math.ceil(Number(semester.semester_number) / 2));
                if (!/\d{4}/.test(yearVal)) {
                    years.add(yearVal);
                }
            }
        });
        return [...years].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    }, [semesters]);

    const branchOptions = useMemo(() => {
        const branches = new Set(['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)']);
        semesters.forEach((semester) => {
            if (semester.branch) {
                branches.add(String(semester.branch));
            }
        });
        return [...branches];
    }, [semesters]);

    const updateFilter = useCallback((key, value) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value,
        }));
    }, []);

    const updateFilters = useCallback((newFilters) => {
        setFilters((prev) => ({
            ...prev,
            ...newFilters,
        }));
    }, []);

    const resetFilters = useCallback(() => {
        setFilters(DEFAULT_GLOBAL_FILTERS);
    }, []);

    const filterRows = useCallback((rows) => (
        filterRowsByGlobalFilters(rows, filters, semesterMap)
    ), [filters, semesterMap]);

    const activeFilterCount = useMemo(() => (
        ['search', 'semesterId', 'year', 'branch'].filter((key) => {
            const value = filters[key];
            return value && value !== 'all';
        }).length
    ), [filters]);

    const value = useMemo(() => ({
        filters,
        semesters,
        semesterMap,
        semesterOptions,
        yearOptions,
        branchOptions,
        activeFilterCount,
        updateFilter,
        updateFilters,
        resetFilters,
        filterRows,
    }), [
        filters,
        semesters,
        semesterMap,
        semesterOptions,
        yearOptions,
        branchOptions,
        activeFilterCount,
        updateFilter,
        updateFilters,
        resetFilters,
        filterRows,
    ]);

    return (
        <GlobalFilterContext.Provider value={value}>
            {children}
        </GlobalFilterContext.Provider>
    );
}
