import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { GlobalFilterContext } from './globalFilterContextObject';
import {
    DEFAULT_GLOBAL_FILTERS,
    buildSemesterMap,
    filterRowsByGlobalFilters,
    getStoredGlobalFilters,
    saveStoredGlobalFilters,
} from '../lib/globalFilters';
import { getApiBaseUrl } from '../lib/apiBase';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';



export function GlobalFilterProvider({ children }) {
    const [filters, setFilters] = useState(() => getStoredGlobalFilters());
    const [semesters, setSemesters] = useState([]);

    useEffect(() => {
        let isMounted = true;
        let loaded = false;      // have we ever received a usable list?
        let inFlight = false;    // guard against overlapping runs

        // The list rarely changes, so one fetch normally suffices — but that one
        // fetch used to be fatal: if the API was slow/down at mount (or the dev
        // backend restarted), semesters was set to [] and never retried, leaving
        // the header filter permanently empty until a re-login. So: retry with
        // backoff, refetch when the tab wakes up, and never overwrite a good
        // list with [] on a later failure.
        const fetchSemesters = async ({ retries = 4 } = {}) => {
            if (inFlight) return;
            inFlight = true;
            try {
                const apiBaseUrl = getApiBaseUrl();
                for (let attempt = 0; attempt <= retries; attempt += 1) {
                    if (!isMounted) return;
                    try {
                        const token = localStorage.getItem('accessToken') || localStorage.getItem('access_token');
                        const response = await fetch(`${apiBaseUrl}/api/mentor/semesters`, {
                            headers: {
                                'Content-Type': 'application/json',
                                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                            }
                        });
                        if (!response.ok) throw new Error(`HTTP ${response.status}`);
                        const payload = await response.json();
                        const semData = Array.isArray(payload)
                            ? payload
                            : (Array.isArray(payload?.data) ? payload.data : []);
                        if (isMounted) {
                            loaded = true;
                            setSemesters(semData);
                        }
                        return;
                    } catch (err) {
                        if (attempt === retries) {
                            console.error("Failed to fetch semesters for global filter", err);
                            // Only clear on the very first load; keep any list we
                            // already have if a later refresh fails.
                            if (isMounted && !loaded) setSemesters([]);
                            return;
                        }
                        await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** attempt, 8000)));
                    }
                }
            } finally {
                inFlight = false;
            }
        };

        fetchSemesters();

        const handleAuthChange = () => fetchSemesters();
        // Catches "backend came up after the page did" without polling.
        const handleWake = () => {
            if (document.visibilityState === 'visible' && !loaded) {
                fetchSemesters({ retries: 1 });
            }
        };
        window.addEventListener('pms-auth-changed', handleAuthChange);
        window.addEventListener('storage', handleAuthChange);
        window.addEventListener('focus', handleWake);
        window.addEventListener('online', handleAuthChange);
        document.addEventListener('visibilitychange', handleWake);

        return () => {
            isMounted = false;
            window.removeEventListener('pms-auth-changed', handleAuthChange);
            window.removeEventListener('storage', handleAuthChange);
            window.removeEventListener('focus', handleWake);
            window.removeEventListener('online', handleAuthChange);
            document.removeEventListener('visibilitychange', handleWake);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        saveStoredGlobalFilters(filters);
        window.dispatchEvent(new CustomEvent('pms-mentor-global-filters-changed', { detail: filters }));
    }, [filters]);

    useEffect(() => {
        const handleCustomEvent = (event) => {
            const newFilters = event.detail;
            if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                setFilters(newFilters);
            }
        };

        const handleStorageEvent = (event) => {
            if (event.key === 'pms-mentor-global-filters' && event.newValue) {
                try {
                    const newFilters = JSON.parse(event.newValue);
                    if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                        setFilters(newFilters);
                    }
                } catch (e) {
                    console.error("Failed to parse mentor global filters from storage", e);
                }
            }
        };

        window.addEventListener('pms-mentor-global-filters-changed', handleCustomEvent);
        window.addEventListener('storage', handleStorageEvent);

        return () => {
            window.removeEventListener('pms-mentor-global-filters-changed', handleCustomEvent);
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
