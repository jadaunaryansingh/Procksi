import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { supabase } from '../lib/supabase';
import { deadlineCompletion } from '../lib/reminders';
import { getApiBaseUrl } from '../lib/apiBase';
import { getOrFetch, clearQueryCache, invalidateQuery } from '../lib/queryCache';

export { invalidateQuery, clearQueryCache };

const API_BASE_URL = getApiBaseUrl();

// Get the current login session, but never wait forever for it.
//
// Sometimes supabase.auth.getSession() hangs and never comes back (e.g. an
// expired token that's stuck trying to refresh, or a lock shared between browser
// tabs). When that happened, every screen just showed a loading skeleton forever
// with no error. To prevent that, we "race" getSession() against a timer: if the
// session doesn't arrive within `timeoutMs`, we throw a timeout error instead,
// which the UI can show and recover from.
export async function getSessionSafe(timeoutMs = 8000) {
  // A promise that rejects after the timeout — whichever finishes first wins.
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Auth check timed out — please reload and sign in again.')), timeoutMs));
  const { data } = await Promise.race([supabase.auth.getSession(), timeout]);
  return data?.session ?? null;   // the session, or null if not logged in
}

export async function fetchWithAuth(path, options = {}) {
  const session = await getSessionSafe();
  const token = session?.access_token;
  if (!token) {
    throw new Error('Not authenticated');
  }

  // Serialize body: if it's a plain object (not already a string), JSON.stringify it
  let body = options.body;
  if (body !== undefined && body !== null && typeof body === 'object' && !(body instanceof FormData)) {
    body = JSON.stringify(body);
  }

  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...(options.headers || {})
  };

  // Remove Content-Type for FormData so browser sets multipart boundary automatically
  if (options.body instanceof FormData) {
    delete headers['Content-Type'];
    body = options.body;
  }

  // Abort the request if it takes too long, so one slow/hung endpoint can never
  // freeze the screen (works in any environment — restrictive networks, a stalled
  // backend, etc.). 20s is generous for a normal call but well under the minutes
  // a dropped connection would otherwise take.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);

  const config = {
    ...options,
    body,
    headers,
    signal: controller.signal,
  };

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, config);
  } catch (err) {
    // A timeout (our AbortController firing) gets its own clear message…
    if (err?.name === 'AbortError') {
      throw new Error('Request timed out. Please check your connection and try again.');
    }
    // …any other network failure is logged and surfaced as a friendly error.
    console.error(`Network error reaching ${path}:`, err);
    throw new Error('Network error. Unable to reach backend service.');
  } finally {
    // Always clear the abort timer so it can't fire after we're done.
    clearTimeout(timer);
  }

  if (response.status === 401) {
    const json = await response.json().catch(() => ({}));
    if (json?.code === 'SESSION_EXPIRED' || json?.detail === 'Invalid or expired session') {
      clearQueryCache();   // never let the next session read this one's data
      await supabase.auth.signOut();
      window.dispatchEvent(new CustomEvent("auth:expired"));
      throw new Error('Session expired');
    }
  }

  const json = await response.json().catch(() => ({}));
  
  if (!response.ok) {
    if (json?.code === 'SESSION_EXPIRED') {
      clearQueryCache();   // never let the next session read this one's data
      await supabase.auth.signOut();
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
    const errorMsg = typeof json?.detail === 'string' 
      ? json.detail 
      : Array.isArray(json?.detail) 
        ? json.detail.map(e => e.msg || JSON.stringify(e)).join(', ')
        : (json?.detail?.error?.message || json?.message || 'API request failed');
    throw new Error(errorMsg);
  }

  return json.data;
}

function useQuery(path) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Guards against setting state after unmount — several of these hooks are
  // mounted by components that come and go with routing.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  // `force` decides whether this read may be served from the shared cache.
  // Initial mounts must not force: that is what collapses the ~31 requests a
  // dashboard load used to make into one per endpoint. Explicit refetches
  // (polling, manual retry, post-mutation reload) always hit the network.
  const load = useCallback(async ({ silent = false, force = false } = {}) => {
    if (!silent) {
      setLoading(true);
      setError(null);
    }
    try {
      const result = await getOrFetch(path, () => fetchWithAuth(path), { force });
      if (mounted.current) setData(result);
    } catch (err) {
      if (!silent && mounted.current) {
        setError(err.message);
      }
    } finally {
      if (!silent && mounted.current) {
        setLoading(false);
      }
    }
  }, [path]);

  const fetchData = useCallback(() => load({}), [load]);

  useEffect(() => {
    // `active` guards against setting state after the component unmounts
    // (e.g. the user navigates away before the request finishes).
    let active = true;
    (async () => {
      try {
        // Make sure we're logged in before fetching. getSessionSafe won't hang.
        const session = await getSessionSafe();
        if (!session) {
          // Not logged in — stop loading and show a clear message.
          if (active) {
            setError('Not authenticated');
            setLoading(false);
          }
          return;
        }
        // Logged in — go get the data.
        if (active) {
          fetchData();
        }
      } catch (err) {
        // The login check timed out or failed. Show the error instead of
        // leaving the screen stuck on a loading skeleton forever.
        if (active) {
          setError(err.message || 'Auth check failed');
          setLoading(false);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [fetchData]);

  // An explicit refetch always bypasses the cache — callers ask for it because
  // they need current data. Stable identity so callers can put it in effect
  // dependency arrays.
  const refetch = useCallback((silent = false) => load({ silent, force: true }), [load]);

  return { data, loading, error, refetch };
}

export const useProfile = () => useQuery('/api/student/me');
export const useTeam = () => useQuery('/api/student/team');
export const useProposals = () => useQuery('/api/student/proposals');
export const useSchedule = () => useQuery('/api/student/schedule');
export const useEvaluations = () => useQuery('/api/student/evaluations');
export const useResults = (semesterId = '') => useQuery(`/api/student/results${semesterId ? `?semester_id=${semesterId}` : ''}`);
export const useResultSemesters = () => useQuery('/api/student/results/semesters');
export const useMentor = () => useQuery('/api/student/mentor');
export const useAnnouncements = () => useQuery('/api/student/announcements');
export const useMilestones = () => useQuery('/api/student/milestones');
export const usePreferences = () => useQuery('/api/student/preferences');
export const useExtraActivities = () => useQuery('/api/student/extra-activities');
export const useProblemStatements = () => useQuery('/api/student/problem-statements');
export const useDeadlines = () => useQuery('/api/student/deadlines');
export const useAvailableStudents = () => useQuery('/api/student/available-students');
export const useJoinRequests = () => useQuery('/api/student/join-requests');
export const usePresentationCycles = (semesterId = '') => useQuery(`/api/student/presentation-cycles${semesterId ? `?semester_id=${semesterId}` : ''}`);
export const useNotifications = () => useQuery('/api/student/notifications');

// Whether the student has met each deadline (team formed, proposal submitted,
// evaluations scored), together with the load state of the four queries it is
// derived from. Callers that auto-open UI MUST wait for `loading` to clear:
// until then every source is null and the map reads "nothing met", which makes
// completed deadlines look overdue.
export const useDeadlineCompletionState = () => {
  const { data: team, loading: tLoading, refetch: refetchTeam } = useTeam();
  const { data: proposals, loading: pLoading, refetch: refetchProposals } = useProposals();
  const { data: evaluations, loading: eLoading, refetch: refetchEvaluations } = useEvaluations();
  const { data: profile, loading: prLoading, refetch: refetchProfile } = useProfile();
  const completion = useMemo(
    () => deadlineCompletion({ team, proposals, evaluations, profile }),
    [team, proposals, evaluations, profile]
  );
  // Refresh all four sources. Callers that poll pass silent=true so the UI never
  // flickers back to a loading state on a background refresh.
  const refetch = useCallback((silent = false) => {
    refetchTeam(silent);
    refetchProposals(silent);
    refetchEvaluations(silent);
    refetchProfile(silent);
  }, [refetchTeam, refetchProposals, refetchEvaluations, refetchProfile]);
  return { completion, loading: tLoading || pLoading || eLoading || prLoading, refetch };
};

// Map-only view of the above, keyed by deadline `type` — pass it to
// buildReminders(...). Use when you don't need the load state.
export const useDeadlineCompletion = () => useDeadlineCompletionState().completion;
