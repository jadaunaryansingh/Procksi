import axios from 'axios';
import { getApiBaseUrl } from '../lib/apiBase.js';

const API_BASE_URL = getApiBaseUrl();

// Create Axios instance
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach the access token automatically and prefix URLs
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Prefix endpoints that do not start with '/auth', '/api/mentor', 'http', or 'https'
    if (config.url && !config.url.startsWith('/auth') && !config.url.startsWith('/api/mentor') && !config.url.startsWith('http') && !config.url.startsWith('https')) {
      const cleanUrl = config.url.startsWith('/') ? config.url : `/${config.url}`;
      config.url = `/api/mentor${cleanUrl}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor to handle API errors and refresh token structure
// Track whether a redirect is already in progress to prevent multiple redirects
let isRedirectingToLogin = false;

apiClient.interceptors.response.use(
  (response) => {
    // Automatically unwrap standard backend response envelopes
    if (response.data && response.data.success === true && response.data.data !== undefined) {
      response.data = response.data.data;
    }
    return response;
  },
  async (error) => {
    const originalRequest = error.config;

    // Skip refresh logic for auth endpoints to avoid loops
    const isAuthEndpoint =
      originalRequest.url?.includes('/auth/refresh') ||
      originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/logout') ||
      originalRequest.url?.includes('/auth/signup');

    // Attempt a silent token refresh on 401
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      const storedRefreshToken = localStorage.getItem('refreshToken');

      if (storedRefreshToken) {
        try {
          // Use plain axios (not the intercepted client) to avoid recursive interception
          const { data: refreshData } = await axios.post(
            `${API_BASE_URL}/auth/refresh`,
            { refresh_token: storedRefreshToken },
            { headers: { 'Content-Type': 'application/json' } }
          );

          const payload = refreshData?.data || refreshData;
          const newAccessToken = payload?.access_token;
          const newRefreshToken = payload?.refresh_token;

          if (newAccessToken) {
            localStorage.setItem('accessToken', newAccessToken);
            if (newRefreshToken) {
              localStorage.setItem('refreshToken', newRefreshToken);
            }
            // Retry the original failed request with the new token
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
            return apiClient(originalRequest);
          }
        } catch (_refreshError) {
          // Refresh failed — session is dead, redirect once
        }
      }

      // No refresh token or refresh failed — clear session and redirect once
      if (!isRedirectingToLogin) {
        isRedirectingToLogin = true;
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

// Export reusable HTTP methods
export const api = {
  get: (url, config = {}) => apiClient.get(url, config),
  post: (url, data, config = {}) => apiClient.post(url, data, config),
  patch: (url, data, config = {}) => apiClient.patch(url, data, config),
  delete: (url, config = {}) => apiClient.delete(url, config),
};

// PMS-Chat. The response interceptor above already unwraps the `{success, data}`
// envelope, so `res.data` here is the payload itself, not another envelope.
// The backend re-derives the mentor's allocated teams on every call and rejects
// any conversation_id outside them, so these are safe to call directly.
export const chatAPI = {
  getConversations: async () => (await apiClient.get('/chat/conversations')).data,
  // Sidebar badge only. Separate from getConversations so the badge poll on
  // every page does not drag the thread list and team lookup along with it.
  getUnread: async () => (await apiClient.get('/chat/unread')).data,
  getMessages: async (conversationId) =>
    (await apiClient.get(`/chat/messages?conversation_id=${encodeURIComponent(conversationId)}`)).data,
  // Pass conversationId to reply, or teamId to open a supervised team's
  // mentor thread for the first time.
  // Slash commands execute server-side; the result is posted into the
  // conversation as a message from PMSbot rather than returned for display.
  runCommand: async ({ command, option = null, teamId = null, conversationId = null }) =>
    (await apiClient.post('/chat/command', {
      command, option, team_id: teamId, conversation_id: conversationId,
    })).data,
    sendMessage: async ({ conversationId = null, teamId = null, body }) =>
    (await apiClient.post('/chat/messages', {
      conversation_id: conversationId, team_id: teamId, body,
    })).data,
};

export default apiClient;
