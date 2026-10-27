import { getSessionSafe } from '../hooks/useStudentData';
import { getApiBaseUrl } from './apiBase';

const API_BASE_URL = getApiBaseUrl();

const studentDataCache = new Map();
const inFlightStudentRequests = new Map();
const STUDENT_CACHE_TTL = 3000; // 3s TTL for instant tab switches

export function clearStudentCache() {
  studentDataCache.clear();
  inFlightStudentRequests.clear();
}

async function apiRequest(endpoint, method = 'GET', body = null) {
  if (method !== 'GET') {
    clearStudentCache();
  } else {
    const cached = studentDataCache.get(endpoint);
    if (cached && (Date.now() - cached.timestamp < STUDENT_CACHE_TTL)) {
      return cached.data;
    }
    if (inFlightStudentRequests.has(endpoint)) {
      return inFlightStudentRequests.get(endpoint);
    }
  }

  const fetchPromise = (async () => {
    try {
      const session = await getSessionSafe();
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
      const data = json.data;

      if (method === 'GET') {
        studentDataCache.set(endpoint, { data, timestamp: Date.now() });
      }
      return data;
    } finally {
      if (method === 'GET') {
        inFlightStudentRequests.delete(endpoint);
      }
    }
  })();

  if (method === 'GET') {
    inFlightStudentRequests.set(endpoint, fetchPromise);
  }
  return fetchPromise;
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

// Procksi Chat. The backend re-derives the team from the session and rejects any
// conversation_id the student is not part of, so these are safe to call directly.
export const getChatConversations = () => apiRequest('/api/student/chat/conversations');
// Unread totals for the sidebar badge. Kept apart from the conversations call
// so the badge poll does not drag the thread list and roster with it.
export const getChatUnread = () => apiRequest('/api/student/chat/unread');
export const getChatMessages = (conversationId) =>
  apiRequest(`/api/student/chat/messages?conversation_id=${encodeURIComponent(conversationId)}`);
// Pass conversation_id for an existing thread, or kind to open one of the
// team's four standing threads for the first time.
export const sendChatMessage = ({ conversationId = null, kind = null, body }) =>
  apiRequest('/api/student/chat/messages', 'POST', {
    conversation_id: conversationId, kind, body,
  });
export const getAvailableStudents = () => apiRequest('/api/student/available-students');
export const apiRemoveMember = (studentId) => apiRequest(`/api/student/team/remove-member?student_id=${studentId}`, 'POST');
export const apiAddMember = (studentId) => apiRequest(`/api/student/team/add-member?student_id=${studentId}`, 'POST');
export const submitProposal = (payload) => apiRequest('/api/student/proposal', 'POST', payload);

// Team join request management (admin-initiated requests)
export const getJoinRequests = () => apiRequest('/api/student/join-requests');
export const acceptJoinRequest = (requestId) => apiRequest(`/api/student/join-requests/${requestId}/accept`, 'POST');
export const declineJoinRequest = (requestId) => apiRequest(`/api/student/join-requests/${requestId}/decline`, 'POST');
export const generateAiSuggestions = (payload) => apiRequest('/api/student/problem-statements/generate-ai-suggestions', 'POST', payload);
export const getTeamGithub = () => apiRequest('/api/student/team/github');
// Roster of the student's own team. Used by Procksi Chat for the member strip and
// the @-mention picker, both of which only ever address teammates.
export const getTeamMembers = () => apiRequest('/api/student/team/members');

