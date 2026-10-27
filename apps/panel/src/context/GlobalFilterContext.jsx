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

        const fetchSemesters = async () => {
            try {
                const apiBaseUrl = getApiBaseUrl();
                const token = localStorage.getItem('auth_token') || localStorage.getItem('access_token');
                const response = await fetch(`${apiBaseUrl}/panel/semesters`, {
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    }
                });
                if (!response.ok) return;
                const payload = await response.json();
                const semData = Array.isArray(payload) ? payload : (Array.isArray(payload?.data) ? payload.data : []);
                if (isMounted) {
                    setSemesters(semData);
                }
            } catch (e) {
                console.error("Failed to fetch semesters for global filter", e);
                if (isMounted) {
                    setSemesters([]);
                }
            }
        };

        fetchSemesters();

        const handleAuthChange = () => fetchSemesters();
        window.addEventListener('procksi-auth-changed', handleAuthChange);
        window.addEventListener('storage', handleAuthChange);

        return () => {
            isMounted = false;
            window.removeEventListener('procksi-auth-changed', handleAuthChange);
            window.removeEventListener('storage', handleAuthChange);
        };
    }, []);

    useEffect(() => {
        saveStoredGlobalFilters(filters);
        window.dispatchEvent(new CustomEvent('procksi-panel-global-filters-changed', { detail: filters }));
    }, [filters]);

    useEffect(() => {
        const handleCustomEvent = (event) => {
            const newFilters = event.detail;
            if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                setFilters(newFilters);
            }
        };

        const handleStorageEvent = (event) => {
            if (event.key === 'procksi-panel-global-filters' && event.newValue) {
                try {
                    const newFilters = JSON.parse(event.newValue);
                    if (newFilters && JSON.stringify(newFilters) !== JSON.stringify(filters)) {
                        setFilters(newFilters);
                    }
                } catch (e) {
                    console.error("Failed to parse panel global filters from storage", e);
                }
            }
        };

        window.addEventListener('procksi-panel-global-filters-changed', handleCustomEvent);
        window.addEventListener('storage', handleStorageEvent);

        return () => {
            window.removeEventListener('procksi-panel-global-filters-changed', handleCustomEvent);
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
