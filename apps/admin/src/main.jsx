import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Global fetch interceptor to catch 403 System Frozen errors
const originalFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalFetch.apply(window, args);
  if (response.status === 403 && response.url && !response.url.includes('/auth/')) {
     try {
         const cloned = response.clone();
         const data = await cloned.json();
         if (data?.detail && typeof data.detail === 'string' && data.detail.includes('System is frozen')) {
             window.dispatchEvent(new CustomEvent('system-frozen-error', { detail: data.detail }));
         }
     } catch (e) {
         console.error("Interceptor failed to parse response:", e);
     }
  }
  return response;
};

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
