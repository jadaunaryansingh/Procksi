import { useState, useEffect, useCallback } from 'react';
import { supabase } from '../lib/supabase';

const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL !== undefined && import.meta.env.VITE_API_BASE_URL !== '') {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return '';
  }
  return 'http://localhost:8002';
};

const API_BASE_URL = getApiBaseUrl();

export async function fetchWithAuth(path, options = {}) {
  const { data: { session } } = await supabase.auth.getSession();
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

  const config = {
    ...options,
    body,
    headers
  };

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, config);
  } catch (netErr) {
    console.error(`Network error reaching ${path}:`, netErr);
    throw new Error('Network error. Unable to reach backend service.');
  }

  if (response.status === 401) {
    const json = await response.json().catch(() => ({}));
    if (json?.code === 'SESSION_EXPIRED' || json?.detail === 'Invalid or expired session') {
      await supabase.auth.signOut();
      window.dispatchEvent(new CustomEvent("auth:expired"));
      throw new Error('Session expired');
    }
  }

  const json = await response.json().catch(() => ({}));
  
  if (!response.ok) {
    if (json?.code === 'SESSION_EXPIRED') {
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

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchWithAuth(path);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    let active = true;
    (async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        if (active) {
          setError('Not authenticated');
          setLoading(false);
        }
        return;
      }
      if (active) {
        fetchData();
      }
    })();

    return () => {
      active = false;
    };
  }, [fetchData]);

  return { data, loading, error, refetch: fetchData };
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
