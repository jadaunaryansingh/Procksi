import { getApiBaseUrl } from '../lib/apiBase.js';

const API_BASE_URL = getApiBaseUrl();

// ─── In-flight request deduplication ────────────────────────────────────────
// If two components fire the same GET simultaneously, only one fetch is sent.
const _inflightRequests = new Map();

// ─── Client-side GET cache ───────────────────────────────────────────────────
// Stores { data, ts } for GET responses. TTL is per-endpoint (see CACHE_TTLS).
const _responseCache = new Map();

const CACHE_TTLS = {
  // Dashboard and team lists — refresh after 10s; fetched very often
  '/dashboard': 10_000,
  '/teams': 10_000,
  '/profile': 15_000,
  // Evaluation parameters rarely change — cache disabled to ensure fresh parameters
  '/evaluation/parameters': 0,
  // Evaluation sessions & drafts — DO NOT CACHE
  '/evaluation/session': 0,
  '/evaluation/draft': 0,
  // Chat must never serve a stale thread — a 10s cache would swallow replies
  '/chat/conversations': 0,
  '/chat/messages': 0,
  '/chat/unread': 0,
  // Default TTL for any other GET
  '_default': 10_000,
};

function getCacheTTL(endpoint) {
  const path = endpoint.split('?')[0];
  for (const [suffix, ttl] of Object.entries(CACHE_TTLS)) {
    if (suffix !== '_default' && (path.endsWith(suffix) || path.includes(suffix + '/'))) return ttl;
  }
  return CACHE_TTLS._default;
}

// Get stored auth token
const getAuthToken = () => {
  return localStorage.getItem('auth_token');
};

// Common headers for API requests
const getHeaders = () => ({
  'Content-Type': 'application/json',
  ...(getAuthToken() && { 'Authorization': `Bearer ${getAuthToken()}` })
});

// Generic API request function with deduplication + client-side caching for GETs
const apiRequest = async (endpoint, options = {}) => {
  const url = `${API_BASE_URL}${endpoint}`;
  const method = (options.method || 'GET').toUpperCase();
  const isGet = method === 'GET';

  // ── Client-side cache check (GET only) ──────────────────────────────────
  if (isGet) {
    const cached = _responseCache.get(url);
    if (cached) {
      const ttl = getCacheTTL(endpoint);
      if (Date.now() - cached.ts < ttl) {
        return cached.data;
      }
      _responseCache.delete(url);
    }
  }

  // ── In-flight deduplication (GET only) ──────────────────────────────────
  if (isGet && _inflightRequests.has(url)) {
    return _inflightRequests.get(url);
  }

  const config = {
    headers: getHeaders(),
    ...options,
  };

  const fetchPromise = fetch(url, config)
    .then(async (response) => {
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }
      const data = await response.json();

      // Store in client cache for GET requests
      if (isGet) {
        _responseCache.set(url, { data, ts: Date.now() });
      }
      return data;
    })
    .catch((error) => {
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    })
    .finally(() => {
      if (isGet) _inflightRequests.delete(url);
    });

  if (isGet) {
    _inflightRequests.set(url, fetchPromise);
  }

  return fetchPromise;
};

// Invalidate a cached endpoint so the next call fetches fresh data
export const invalidateCache = (endpoint) => {
  const url = `${API_BASE_URL}${endpoint}`;
  _responseCache.delete(url);
};

// Authentication API
export const authAPI = {
  login: async (email, password) => {
    return await apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
  },

  signup: async (userData) => {
    return await apiRequest('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(userData)
    });
  },

  getCurrentUser: async () => {
    return await apiRequest('/auth/me');
  }
};

// Panel Dashboard API
export const panelAPI = {
  getDashboard: async (panelId, forceSync = false) => {
    return await apiRequest(`/panel/${panelId}/dashboard${forceSync ? `?force_sync=true&_ts=${Date.now()}` : ''}`);
  },

  getTeams: async (panelId, forceSync = false) => {
    return await apiRequest(`/panel/${panelId}/teams${forceSync ? `?force_sync=true&_ts=${Date.now()}` : ''}`);
  },

  getMissed: async (panelId) => {
    return await apiRequest(`/panel/${panelId}/missed`);
  },

  getAlerts: async (panelId) => {
    return await apiRequest(`/panel/${panelId}/alerts`);
  },

  acknowledgeAlert: async (panelId, alertId) => {
    invalidateCache(`/panel/${panelId}/alerts`);
    return await apiRequest(`/panel/${panelId}/alerts/${alertId}/acknowledge`, {
      method: 'POST'
    });
  },

  getGithubData: async (panelId, teamId) => {
    return await apiRequest(`/panel/${panelId}/teams/${teamId}/github`);
  },

  requestReschedule: async (panelId, teamId) => {
    return await apiRequest(`/panel/${panelId}/missed/${teamId}/request-reschedule`, {
      method: 'POST'
    });
  },

  // ── Slot Management (SlotManagement.jsx) ────────────────────────────────
  getUnassignedTeams: async (panelId) => {
    return await apiRequest(`/panel/${panelId}/teams/unassigned`);
  },

  getTeamCatalog: async (panelId) => {
    return await apiRequest(`/panel/${panelId}/teams/catalog`);
  },

  upsertSlot: async (panelId, body) => {
    // body: { team_id, window_start, window_end, venue, slot_label }
    const { team_id, ...rest } = body;
    invalidateCache(`/panel/${panelId}/teams/unassigned`);
    invalidateCache(`/panel/${panelId}/teams/catalog`);
    invalidateCache(`/panel/${panelId}/teams`);
    invalidateCache(`/panel/${panelId}/dashboard`);
    return await apiRequest(`/panel/${panelId}/slots/${team_id}`, {
      method: 'PUT',
      body: JSON.stringify(rest),
    });
  },

  activateSlot: async (panelId, teamId, body = {}) => {
    invalidateCache(`/panel/${panelId}/teams`);
    invalidateCache(`/panel/${panelId}/dashboard`);
    return await apiRequest(`/panel/${panelId}/slots/${teamId}/activate`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};

// Evaluation API
export const evaluationAPI = {
  getParameters: async (teamId = null, panelId = null) => {
    const params = new URLSearchParams();
    if (teamId) params.append('team_id', teamId);
    if (panelId) params.append('panel_id', panelId);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return await apiRequest(`/evaluation/parameters${queryString}`);
  },

  getSession: async (teamId, panelId) => {
    return await apiRequest(`/evaluation/session/${teamId}?panel_id=${panelId}`);
  },

  saveDraft: async (teamId, panelId, draftData) => {
    return await apiRequest(`/evaluation/draft/${teamId}?panel_id=${panelId}`, {
      method: 'PUT',
      body: JSON.stringify(draftData)
    });
  },

  getDraft: async (teamId, panelId) => {
    return await apiRequest(`/evaluation/draft/${teamId}?panel_id=${panelId}`);
  },

  submitEvaluation: async (evaluationData) => {
    // Invalidate related caches after submitting so next visit fetches fresh
    invalidateCache(`/panel/${evaluationData.panel_id}/dashboard`);
    invalidateCache(`/panel/${evaluationData.panel_id}/teams`);
    invalidateCache(`/mentor/${evaluationData.panel_id}/teams`);
    invalidateCache(`/mentor/${evaluationData.panel_id}/profile`);
    return await apiRequest('/evaluation/panel', {
      method: 'POST',
      body: JSON.stringify(evaluationData)
    });
  },

  getSubmissionReceipt: async (teamId, panelId) => {
    return await apiRequest(`/evaluation/receipt/${teamId}?panel_id=${panelId}`);
  },

  extendSlot: async (teamId, panelId, extendMinutes) => {
    invalidateCache(`/panel/${panelId}/dashboard`);
    invalidateCache(`/panel/${panelId}/teams`);
    invalidateCache(`/evaluation/session/${teamId}?panel_id=${panelId}`);
    return await apiRequest(`/evaluation/extend/${teamId}`, {
      method: 'POST',
      body: JSON.stringify({ panel_id: panelId, extend_minutes: extendMinutes })
    });
  },
};

// Health check
export const healthAPI = {
  check: async () => {
    return await apiRequest('/health');
  }
};

// Mentor-specific API (profile & assigned teams)
export const mentorAPI = {
  getProfile: async (panelId) => {
    return await apiRequest(`/mentor/${panelId}/profile`);
  },

  getTeams: async (panelId) => {
    return await apiRequest(`/mentor/${panelId}/teams`);
  },
};

// Procksi Chat. Unlike the mentor client, apiRequest here returns the whole
// response body, so callers read `.data` themselves. The panel backend answers
// with {status, data}. Access is re-derived from the session on every call.
export const chatAPI = {
  getConversations: async () => {
    const res = await apiRequest('/panel/chat/conversations');
    return res?.data || [];
  },

  // Sidebar badge only. Separate from getConversations so the badge poll on
  // every page stays cheap.
  getUnread: async () => {
    const res = await apiRequest('/panel/chat/unread');
    return res?.data || {};
  },

  // Slash commands execute server-side; the result is posted into the
  // conversation as a message from ProcksiBot rather than returned for display.
  runCommand: async ({ command, option = null, conversationId = null }) => {
    const res = await apiRequest('/panel/chat/command', {
      method: 'POST',
      body: JSON.stringify({ command, option, conversation_id: conversationId }),
    });
    return res?.data || {};
  },

  getMessages: async (conversationId) => {
    const res = await apiRequest(
      `/panel/chat/messages?conversation_id=${encodeURIComponent(conversationId)}`
    );
    return res?.data || [];
  },

  sendMessage: async (conversationId, body) => {
    invalidateCache('/panel/chat/conversations');
    invalidateCache(`/panel/chat/messages?conversation_id=${encodeURIComponent(conversationId)}`);
    const res = await apiRequest('/panel/chat/messages', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: Number(conversationId), body }),
    });
    return res?.data || {};
  },
};

export default {
  authAPI,
  panelAPI,
  mentorAPI,
  evaluationAPI,
  healthAPI,
  chatAPI,
};
