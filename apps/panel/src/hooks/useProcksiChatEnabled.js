/**
 * useProcksiChatEnabled
 *
 * Whether Procksi Chat should be available in this portal right now.
 *
 * Two gates, both of which must pass:
 *
 *   1. PROCKSI_CHAT_ENABLED -- the build-time kill switch in config/features.js.
 *      False in production builds, so an admin cannot expose an unfinished
 *      feature on the live portals by flipping a database row.
 *   2. The coordinator's per-portal switch, set from the admin portal and
 *      stored on the active semester's semester_config row.
 *
 * The switch is read from this portal's own backend rather than straight from
 * Supabase: RLS hides semester_config from the anon key, so a direct browser
 * read comes back with zero rows and the flag silently never applies.
 *
 * Polled rather than pushed. The existing realtime channel only carries
 * `chat_events`, and putting semester_config on realtime would mean exposing
 * a table of weights and lock flags to the anon key. A 30s poll of one
 * boolean is the cheaper trade, and it also re-checks on tab focus so a user
 * coming back to the tab sees the current state immediately.
 *
 * Fails open to the build flag. A network error or an unreachable backend
 * leaves the feature exactly as the build intended -- a chat page that
 * disappears because a settings lookup failed is worse than one that stays.
 */
import { useCallback, useEffect, useState } from 'react';
import { PROCKSI_CHAT_ENABLED } from '../config/features';

const ENDPOINT = '/panel/procksi-chat-enabled';
const POLL_MS = 30000;

export function useProcksiChatEnabled() {
    // null means "not established yet" and is treated as the build default.
    const [dbEnabled, setDbEnabled] = useState(null);

    const check = useCallback(async (signal) => {
        try {
            const base = import.meta.env.VITE_API_BASE_URL || '';
            const res = await fetch(`${base}${ENDPOINT}`, { signal });
            if (!res.ok) return;
            const json = await res.json();
            const value = json?.enabled;
            if (typeof value === 'boolean') setDbEnabled(value);
        } catch {
            // Fail open, and leave the previous answer in place -- see above.
        }
    }, []);

    useEffect(() => {
        if (!PROCKSI_CHAT_ENABLED) return undefined; // kill switch: never ask

        const controller = new AbortController();

        // Scheduled rather than called inline so the first fetch resolves off
        // the render path; `check` only ever setStates from its callback.
        const first = window.setTimeout(() => check(controller.signal), 0);
        const timer = window.setInterval(() => check(controller.signal), POLL_MS);

        // Coming back to the tab is the moment a stale answer is most likely,
        // and the moment the user is most likely to act on it.
        const onVisible = () => {
            if (document.visibilityState === 'visible') check(controller.signal);
        };
        document.addEventListener('visibilitychange', onVisible);

        return () => {
            controller.abort();
            window.clearTimeout(first);
            window.clearInterval(timer);
            document.removeEventListener('visibilitychange', onVisible);
        };
    }, [check]);

    if (!PROCKSI_CHAT_ENABLED) return false;
    return dbEnabled === null ? PROCKSI_CHAT_ENABLED : dbEnabled;
}
