import { useContext } from 'react';
import { GlobalFilterContext } from './globalFilterContextObject';
import { DEFAULT_GLOBAL_FILTERS } from '../lib/globalFilters';

// Falls back to an inert filter set when no provider is mounted, so components
// rendered outside the provider (login screens, error boundaries) still work.
export function useGlobalFilters() {
    const context = useContext(GlobalFilterContext);
    if (context) {
        return context;
    }

    return {
        filters: DEFAULT_GLOBAL_FILTERS,
        semesters: [],
        semesterMap: {},
        semesterOptions: [],
        yearOptions: [],
        branchOptions: [],
        activeFilterCount: 0,
        updateFilter: () => {},
        updateFilters: () => {},
        resetFilters: () => {},
        filterRows: (rows) => Array.isArray(rows) ? rows : [],
    };
}
