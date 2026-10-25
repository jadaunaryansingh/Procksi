import { supabase } from './supabase';

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

async function apiRequest(endpoint, method = 'GET', body = null) {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;

  const headers = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const config = {
    method,
    headers,
  };

  if (body) {
    config.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData?.detail?.error?.message || errorData?.detail || 'API request failed');
  }

  const json = await response.json();
  return json.data;
}

export const getProfile = () => apiRequest('/api/student/me');
export const getMilestones = () => apiRequest('/api/student/milestones');
export const getMentor = () => apiRequest('/api/student/mentor');
export const getPresentations = () => apiRequest('/api/student/presentations');
export const getEvaluations = () => apiRequest('/api/student/evaluations');
export const getResults = () => apiRequest('/api/student/results');
export const getProblemStatements = () => apiRequest('/api/student/problem-statements');
export const getPreferences = () => apiRequest('/api/student/preferences');
export const savePreferences = (payload) => apiRequest('/api/student/preferences', 'POST', payload);
export const getExtraActivities = () => apiRequest('/api/student/extra-activities');
export const addExtraActivity = (payload) => apiRequest('/api/student/extra-activities', 'POST', payload);
export const getAnnouncements = () => apiRequest('/api/student/announcements');
export const getNotifications = () => apiRequest('/api/student/notifications');
export const getAvailableStudents = () => apiRequest('/api/student/available-students');
export const apiRemoveMember = (studentId) => apiRequest(`/api/student/team/remove-member?student_id=${studentId}`, 'POST');
export const apiAddMember = (studentId) => apiRequest(`/api/student/team/add-member?student_id=${studentId}`, 'POST');
export const submitProposal = (payload) => apiRequest('/api/student/proposal', 'POST', payload);

// Team join request management (admin-initiated requests)
export const getJoinRequests = () => apiRequest('/api/student/join-requests');
export const acceptJoinRequest = (requestId) => apiRequest(`/api/student/join-requests/${requestId}/accept`, 'POST');
export const declineJoinRequest = (requestId) => apiRequest(`/api/student/join-requests/${requestId}/decline`, 'POST');
export const generateAiSuggestions = (payload) => apiRequest('/api/student/problem-statements/generate-ai-suggestions', 'POST', payload);

