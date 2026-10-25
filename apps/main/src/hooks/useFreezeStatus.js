/**
 * useFreezeStatus — polls the active semester's is_locked flag every 30s.
 * Any portal can import this to enforce a system freeze banner.
 */
import { useState, useEffect } from 'react';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || '';
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || '';

export function useFreezeStatus() {
  const [isFrozen, setIsFrozen] = useState(false);

  // `check` lives inside the effect so it is not recreated on every render and
  // so the effect owns everything it calls. setIsFrozen only ever runs after
  // two awaits — never synchronously during the effect — and `cancelled` stops
  // a late response from writing state after unmount.
  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return;
      try {
        const r = await fetch(
          `${SUPABASE_URL}/rest/v1/semester_config?is_active=eq.true&select=is_locked&limit=1`,
          { headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` } }
        );
        if (!r.ok) return;
        const data = await r.json();
        if (!cancelled) setIsFrozen(data?.[0]?.is_locked === true);
      } catch { /* silent */ }
    };

    check();
    const interval = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return isFrozen;
}
