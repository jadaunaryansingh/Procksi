import React, { useState, useEffect, useCallback } from 'react';
import { AuthContext } from './authContextObject';
import { api } from '../services/api';
import { getApiBaseUrl } from '../lib/apiBase';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(localStorage.getItem('accessToken') || null);
  const [isAuthenticated, setIsAuthenticated] = useState(!!accessToken);
  const [loading, setLoading] = useState(true);

  // Declared before the session-restore effect below, which calls it when
  // /auth/me fails. It used to be defined further down the component, so that
  // call sat in the temporal dead zone — it happened to work only because
  // effects run after the component body finishes, and it captured whichever
  // copy existed at that render.
  const logout = useCallback(() => {
    const token = localStorage.getItem('accessToken');
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    setAccessToken(null);
    setUser(null);
    setIsAuthenticated(false);
    // Notify backend best-effort using fetch to avoid the intercepted axios client
    if (token) {
      const apiBase = getApiBaseUrl();
      fetch(
        `${apiBase}/auth/logout`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } }
      ).catch(() => {
        // Best effort — the local session is already cleared either way.
      });
    }
  }, []);

  // Restore session after page refresh
  useEffect(() => {
    const initAuth = async () => {
      if (accessToken) {
        try {
          const response = await api.get('/auth/me');
          const userData = response.data?.data?.user || response.data?.user || response.data;
          setUser(userData);
          setIsAuthenticated(true);
        } catch (error) {
          console.error('Failed to restore session:', error);
          logout();
        }
      } else {
        setLoading(false);
      }
      setLoading(false);
    };

    initAuth();
    // `logout` is a stable useCallback([]), so listing it cannot re-run this.
  }, [accessToken, logout]);

  const login = async (credentials) => {
    try {
      const response = await api.post('/auth/login', credentials);
      const data = response.data?.data || response.data;
      const { access_token, refresh_token, user: userData } = data;

      localStorage.setItem('accessToken', access_token);
      if (refresh_token) {
        localStorage.setItem('refreshToken', refresh_token);
      }
      setAccessToken(access_token);
      setUser(userData);
      setIsAuthenticated(true);
      return { success: true };
    } catch (error) {
      console.error('Login failed:', error);
      const errMsg = error.response?.data?.error?.message || error.response?.data?.detail || 'Login failed. Please check your credentials.';
      return {
        success: false,
        error: errMsg
      };
    }
  };

  const signup = async (userData) => {
    try {
      const response = await api.post('/auth/signup', userData);
      const data = response.data?.data || response.data;
      
      // If registration is pending approval
      if (data.status === 'pending') {
        return {
          success: false,
          pending: true,
          message: response.data?.message || 'Your registration is pending administrator approval. You can log in once approved.'
        };
      }

      const { access_token, refresh_token, user: newUserData } = data;
      localStorage.setItem('accessToken', access_token);
      if (refresh_token) {
        localStorage.setItem('refreshToken', refresh_token);
      }
      setAccessToken(access_token);
      setUser(newUserData);
      setIsAuthenticated(true);
      return { success: true };
    } catch (error) {
      console.error('Signup failed:', error);
      const errMsg = error.response?.data?.error?.message || error.response?.data?.detail || 'Signup failed. Please try again.';
      return {
        success: false,
        error: errMsg
      };
    }
  };


  const refreshToken = async () => {
    const raw = localStorage.getItem('refreshToken');
    if (!raw) {
      logout();
      return;
    }
    try {
      const response = await api.post('/auth/refresh', { refresh_token: raw });
      const data = response.data?.data || response.data;
      const { access_token, refresh_token: new_refresh } = data;
      localStorage.setItem('accessToken', access_token);
      if (new_refresh) {
        localStorage.setItem('refreshToken', new_refresh);
      }
      setAccessToken(access_token);
    } catch (error) {
      console.error('Failed to refresh token:', error);
      logout();
    }
  };

  const value = {
    user,
    accessToken,
    isAuthenticated,
    loading,
    login,
    signup,
    logout,
    refreshToken
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
