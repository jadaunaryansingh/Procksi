import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { getApiBaseUrl } from '../lib/apiBase';

export default function GoogleAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('processing');
  const [errorMsg, setErrorMsg] = useState('');
  const hasExchanged = useRef(false);

  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setStatus('error');
      setErrorMsg('No authorization code received from Google.');
      return;
    }

    if (hasExchanged.current) return;
    hasExchanged.current = true;

    const exchangeCode = async () => {
      try {
        const apiBase = getApiBaseUrl();
        const response = await fetch(`${apiBase}/api/events/google-auth-callback?code=${encodeURIComponent(code)}`);
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail?.detail || 'Failed to connect Google Calendar');
        }
        setStatus('success');
        setTimeout(() => {
          navigate('/admin/schedule', { state: { googleConnected: true } });
        }, 2000);
      } catch (err) {
        console.error(err);
        setStatus('error');
        setErrorMsg(err.message);
      }
    };

    exchangeCode();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 px-4">
      <div className="bg-white dark:bg-slate-800 rounded-3xl shadow-xl border border-slate-200/50 dark:border-slate-700/50 p-8 w-full max-w-md text-center space-y-6">
        {status === 'processing' && (
          <>
            <div className="flex justify-center">
              <Loader2 className="w-16 h-16 text-indigo-500 animate-spin" />
            </div>
            <h3 className="text-xl font-black text-slate-800 dark:text-white">Connecting Google Calendar</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">Please wait while we set up secure API access to your calendar...</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="flex justify-center">
              <CheckCircle className="w-16 h-16 text-emerald-500 animate-bounce" />
            </div>
            <h3 className="text-xl font-black text-slate-800 dark:text-white">Successfully Connected!</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">Your Google Calendar is now integrated. Redirecting to Schedule config...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="flex justify-center">
              <XCircle className="w-16 h-16 text-rose-500" />
            </div>
            <h3 className="text-xl font-black text-slate-800 dark:text-white">Connection Failed</h3>
            <p className="text-sm text-rose-500 font-bold bg-rose-50 dark:bg-rose-500/10 p-3 rounded-xl border border-rose-100 dark:border-rose-500/20">{errorMsg}</p>
            <button 
              onClick={() => navigate('/admin/schedule')}
              className="px-6 py-2.5 bg-slate-600 hover:bg-slate-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors"
            >
              Back to Schedule
            </button>
          </>
        )}
      </div>
    </div>
  );
}
