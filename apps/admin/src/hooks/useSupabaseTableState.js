import { useEffect, useMemo, useState } from 'react';
import { apiFetchTable } from '../lib/api.js';
import { useGlobalFilters } from '../context/useGlobalFilters';

export function useSupabaseTableState(tableName, fallbackData, options = {}) {
    const { select = '*', orderBy, ascending = true, transform } = options;
    const [rawData, setRawData] = useState(fallbackData);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const { filterRows, filters } = useGlobalFilters();

    const data = useMemo(() => {
        const filterableTables = [
            'students',
            'teams_validation',
            'proposals',
            'schedule_slots',
            'results',
            // 'absent_students' excluded intentionally: AbsentStudents.jsx enriches rows
            // with semester_id from allTeams BEFORE filtering, so pre-filtering here
            // would remove rows before that enrichment can set their semester context.
            'extra_activities',
            'makeup_slots'
        ];
        if (filterableTables.includes(tableName)) {
            return filterRows(rawData);
        }
        return rawData;
    }, [rawData, tableName, filterRows, filters]);

    useEffect(() => {
        let isMounted = true;

        const loadData = async () => {
            if (!tableName) {
                return;
            }

            setLoading(true);
            setError(null);

            try {
                const rows = await apiFetchTable(tableName, { select, orderBy, ascending });

                if (!isMounted) {
                    return;
                }

                setRawData(typeof transform === 'function' ? transform(rows) : rows);
                setLoading(false);
            } catch (fetchError) {
                if (!isMounted) {
                    return;
                }

                setError(fetchError);
                setLoading(false);
            }
        };

        loadData();

        return () => {
            isMounted = false;
        };
        // filters.semesterId participates because apiFetchTable scopes the request to
        // the selected batch. Without it the hook keeps serving rows fetched under the
        // previously selected batch, which then leak through as cross-batch rows.
    }, [tableName, select, orderBy, ascending, transform, filters.semesterId]);

    return { data, setData: setRawData, loading, error };
}
