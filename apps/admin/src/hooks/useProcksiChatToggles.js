/**
 * useProcksiChatToggles
 *
 * Reads and writes the per-portal Procksi Chat switches on the semester currently
 * selected in the global filter.
 *
 * The flags live on `semester_config` (one boolean per portal), so the toggle
 * follows the global semester selector automatically: switch semester and you
 * are editing that semester's settings.
 *
 * Degrades safely. The columns are added by
 * supabase/migrations/202608240001_procksi_chat_toggles.sql; until that has been
 * applied, reads come back without the fields and every portal reads as OFF
 * rather than throwing. `columnsMissing` lets the UI say so plainly instead of
 * showing switches that silently do nothing.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetchTable, apiPatchRow } from '../lib/api';
import { useGlobalFilters } from '../context/useGlobalFilters';

export const PORTALS = [
    { key: 'student', column: 'procksi_chat_student', label: 'Student Portal' },
    { key: 'mentor', column: 'procksi_chat_mentor', label: 'Mentor Portal' },
    { key: 'panel', column: 'procksi_chat_panel', label: 'Panel Portal' },
    { key: 'admin', column: 'procksi_chat_admin', label: 'Admin Portal' },
];

const OFF = { student: false, mentor: false, panel: false, admin: false };

export function useProcksiChatToggles() {
    const { filters, semesterOptions } = useGlobalFilters();
    const semesterId = filters?.semesterId || null;

    const [row, setRow] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(null); // portal key currently saving
    const [error, setError] = useState(null);

    const semesterLabel = useMemo(() => {
        const match = (semesterOptions || []).find((o) => String(o.value) === String(semesterId));
        return match?.label || null;
    }, [semesterOptions, semesterId]);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const rows = await apiFetchTable('semester_config');
            const list = Array.isArray(rows) ? rows : [];
            // Prefer the semester the global filter is on; fall back to the
            // active one so the panel still shows something sensible when no
            // explicit semester is selected.
            const found =
                list.find((r) => String(r.id) === String(semesterId)) ||
                list.find((r) => r.is_active) ||
                null;
            setRow(found);
        } catch (e) {
            setError(e?.message || 'Could not load semester settings.');
            setRow(null);
        } finally {
            setLoading(false);
        }
    }, [semesterId]);

    useEffect(() => { load(); }, [load]);

    // A row that predates the migration has none of the four columns.
    const columnsMissing = Boolean(
        row && PORTALS.every((p) => row[p.column] === undefined),
    );

    const values = useMemo(() => {
        if (!row) return OFF;
        return PORTALS.reduce((acc, p) => {
            acc[p.key] = row[p.column] === true;
            return acc;
        }, {});
    }, [row]);

    const setPortal = useCallback(async (portalKey, next) => {
        const portal = PORTALS.find((p) => p.key === portalKey);
        if (!portal || !row?.id) return;

        setSaving(portalKey);
        setError(null);
        // Optimistic: the switch should move under the cursor, not after a
        // round trip. Rolled back below if the write fails.
        const previous = row;
        setRow({ ...row, [portal.column]: next });
        try {
            await apiPatchRow('semester_config', row.id, { [portal.column]: next });
        } catch (e) {
            setRow(previous);
            setError(e?.message || `Could not update ${portal.label}.`);
        } finally {
            setSaving(null);
        }
    }, [row]);

    return {
        values,
        loading,
        saving,
        error,
        columnsMissing,
        semesterId: row?.id ?? null,
        semesterLabel,
        anyOn: Object.values(values).some(Boolean),
        reload: load,
        setPortal,
    };
}
