import React, { useState, useEffect } from 'react';
import { BellRing, ShieldX, Clock, ArrowUpRight, UserMinus, CheckSquare, Loader2, AlertCircle as AlertCircleIcon, BellOff, CheckCircle2 } from 'lucide-react';
import { api } from '../../services/api';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel, cleanUUIDsFromText } from '../../lib/globalFilters';

const fallbackAlerts = [];

const colorClasses = {
  rose: {
    badgeBg: 'bg-rose-100 dark:bg-rose-500/10',
    badgeText: 'text-rose-700 dark:text-rose-300',
    badgeBorder: 'border-rose-200 dark:border-rose-500/20',
    iconBg: 'bg-rose-50 dark:bg-rose-500/20',
    iconText: 'text-rose-600 dark:text-rose-400',
    btnBg: 'bg-rose-600 hover:bg-rose-700',
    btnShadow: 'shadow-rose-500/20',
    glow: 'bg-rose-500/5 dark:bg-rose-500/10'
  },
  amber: {
    badgeBg: 'bg-amber-100 dark:bg-amber-500/10',
    badgeText: 'text-amber-700 dark:text-amber-300',
    badgeBorder: 'border-amber-200 dark:border-amber-500/20',
    iconBg: 'bg-amber-50 dark:bg-amber-500/20',
    iconText: 'text-amber-600 dark:text-amber-400',
    btnBg: 'bg-amber-600 hover:bg-amber-700',
    btnShadow: 'shadow-amber-500/20',
    glow: 'bg-amber-500/5 dark:bg-amber-500/10'
  },
  indigo: {
    badgeBg: 'bg-indigo-100 dark:bg-indigo-500/10',
    badgeText: 'text-indigo-700 dark:text-indigo-300',
    badgeBorder: 'border-indigo-200 dark:border-indigo-500/20',
    iconBg: 'bg-indigo-50 dark:bg-indigo-500/20',
    iconText: 'text-indigo-600 dark:text-indigo-400',
    btnBg: 'bg-indigo-600 hover:bg-indigo-700',
    btnShadow: 'shadow-indigo-500/20',
    glow: 'bg-indigo-500/5 dark:bg-indigo-500/10'
  }
};

const iconMap = { critical: ShieldX, warning: Clock, info: UserMinus };

const severityLabel = (sev) => {
  const map = {
    critical: { text: 'Critical', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border-rose-200 dark:border-rose-500/30' },
    high:     { text: 'High',     cls: 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400 border-rose-200 dark:border-rose-500/30' },
    warning:  { text: 'Warning',  cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 border-amber-200 dark:border-amber-500/30' },
    medium:   { text: 'Medium',   cls: 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 border-amber-200 dark:border-amber-500/30' },
    low:      { text: 'Low',      cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/30' },
    info:     { text: 'Info',     cls: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/30' },
  };
  return map[sev] || map.medium;
};

const AlertsUI = () => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('Active');
  const [ackLoadingId, setAckLoadingId] = useState(null);
  const [ackError, setAckError] = useState(null);

  // MUST stay above the `if (loading)` early return below. React requires the
  // same hooks in the same order on every render; calling this after that return
  // meant the first (loading) render ran one fewer hook than the next, and React
  // threw "Rendered more hooks than during the previous render" the moment the
  // alerts finished loading — i.e. every single time this page was opened.
  const { filterRows, semesterMap } = useGlobalFilters();

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const response = await api.get('/alerts');
        const data = Array.isArray(response.data) ? response.data : response.data.alerts || [];
        // Normalize: ensure each alert has an `acknowledged` field
        setAlerts(data.map(a => ({ ...a, acknowledged: a.acknowledged ?? false })));
      } catch (err) {
        // Use fallback data if API not ready
        setAlerts(fallbackAlerts);
      } finally {
        setLoading(false);
      }
    };
    fetchAlerts();
  }, []);

  // ---------- Acknowledge handler ----------
  const handleAcknowledge = async (alertId) => {
    setAckLoadingId(alertId);
    setAckError(null);

    // Optimistic update: move to acknowledged immediately
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: true } : a));

    try {
      await api.patch(`/alerts/${alertId}/acknowledge`);
      // Success — state already updated optimistically
    } catch (err) {
      // Rollback on failure
      setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: false } : a));
      setAckError(`Failed to acknowledge alert: ${err.response?.data?.detail || err.message}`);

      // Auto-clear the error after 4 seconds
      setTimeout(() => setAckError(null), 4000);
    } finally {
      setAckLoadingId(null);
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center min-h-[400px]"><Loader2 className="w-10 h-10 animate-spin text-indigo-500" /></div>;
  }

  // Partition alerts into active vs acknowledged
  const filteredAlerts = filterRows(alerts);
  const activeAlerts = filteredAlerts.filter(a => !a.acknowledged);
  const acknowledgedAlerts = filteredAlerts.filter(a => a.acknowledged);
  const displayedAlerts = activeTab === 'Active' ? activeAlerts : acknowledgedAlerts;

  // Summary counters (based on active only)
  const warningCount = activeAlerts.filter(a => a.type === 'warning' || a.severity === 'warning' || a.severity === 'medium').length;
  const infoCount = activeAlerts.filter(a => a.type === 'info' || a.severity === 'low' || a.severity === 'info').length;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 mt-2">
        <div>
           <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              Alerts & Risks
           </h2>
           <p className="text-sm font-medium text-slate-500">Monitor and manage team alerts</p>
        </div>
      </div>

      {/* Acknowledge Error Toast */}
      {ackError && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm animate-in fade-in">
          <AlertCircleIcon className="w-5 h-5 mr-3 shrink-0" />
          {ackError}
        </div>
      )}

      {/* Top Summary Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
              <h3 className="text-3xl font-black text-rose-500 mb-1">{activeAlerts.length}</h3>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Active Alerts</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
              <h3 className="text-3xl font-black text-amber-500 mb-1">{warningCount}</h3>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Warnings</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
              <h3 className="text-3xl font-black text-indigo-500 mb-1">{infoCount}</h3>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Info / Low</p>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
              <h3 className="text-3xl font-black text-emerald-500 mb-1">{acknowledgedAlerts.length}</h3>
              <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">Acknowledged</p>
          </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-4 border-b border-slate-200 dark:border-slate-700 mb-6 pb-2 relative">
          <div onClick={() => setActiveTab('Active')} className={`flex items-center gap-2 cursor-pointer relative top-2.5 pb-2 border-b-2 z-10 transition-colors ${activeTab === 'Active' ? 'border-rose-500' : 'border-transparent hover:border-slate-300 dark:hover:border-slate-600'}`}>
              <span className={`font-bold text-sm ${activeTab === 'Active' ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500'}`}>Active</span>
              <span className="bg-rose-500 text-white text-[10px] font-black px-1.5 py-0.5 rounded-full">{activeAlerts.length}</span>
          </div>
          <div onClick={() => setActiveTab('Acknowledged')} className={`flex items-center gap-2 cursor-pointer relative top-2.5 pb-2 border-b-2 transition-colors ${activeTab === 'Acknowledged' ? 'border-emerald-500' : 'border-transparent hover:border-slate-300 dark:hover:border-slate-600'}`}>
              <span className={`font-bold text-sm ${activeTab === 'Acknowledged' ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500'}`}>Acknowledged</span>
              <span className="bg-emerald-500 text-white text-[10px] font-black px-1.5 py-0.5 rounded-full">{acknowledgedAlerts.length}</span>
          </div>
      </div>

      {/* Alert Feed */}
      <div className="space-y-4">
        {displayedAlerts.length === 0 && (
          <div className="flex flex-col items-center justify-center p-12 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm text-center">
            <div className="w-16 h-16 bg-slate-100 dark:bg-slate-700 rounded-full flex items-center justify-center mb-4">
              {activeTab === 'Active' ? <BellOff className="w-8 h-8 text-slate-400" /> : <CheckCircle2 className="w-8 h-8 text-slate-400" />}
            </div>
            <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">
              {activeTab === 'Active' ? 'No active alerts' : 'No acknowledged alerts'}
            </h3>
            <p className="text-slate-500 dark:text-slate-400 font-medium">
              {activeTab === 'Active' ? 'All teams are operating within normal parameters.' : 'Acknowledged alerts will appear here.'}
            </p>
          </div>
        )}

        {displayedAlerts.map((alert) => {
          const color = alert.color || (alert.type === 'critical' ? 'rose' : alert.type === 'warning' ? 'amber' : 'indigo');
          const classes = colorClasses[color] || colorClasses.amber;
          const IconComp = iconMap[alert.type] || Clock;
          const sev = severityLabel(alert.severity || alert.type);
          const isAcking = ackLoadingId === alert.id;

          return (
            <div key={alert.id} className={`bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200 dark:border-slate-700/50 shadow-sm flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between group transition-all ${alert.acknowledged ? 'opacity-75' : ''}`}>
              <div className="flex items-start gap-4 flex-1 min-w-0">
                <div className={`p-2.5 rounded-xl ${classes.iconBg} ${classes.iconText} border ${classes.badgeBorder} shrink-0`}>
                  <IconComp size={20} />
                </div>
                <div className="min-w-0">
                  {/* Title + Team */}
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{cleanUUIDsFromText(alert.title)}</h3>
                    <span className={`text-[10px] uppercase font-black px-2 py-0.5 rounded-full border ${sev.cls}`}>{sev.text}</span>
                  </div>

                  {/* Message */}
                  <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">{cleanUUIDsFromText(alert.description || alert.message)}</p>

                  {/* Meta row: Team + Date */}
                  <div className="flex flex-wrap items-center gap-3 text-xs font-semibold text-slate-400">
                    <span className="flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-300 dark:bg-slate-600 inline-block"></span>
                      {teamDisplayLabel(alert.team, null, semesterMap)}
                    </span>
                    <span>{alert.date || alert.time}</span>
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-3 w-full sm:w-auto shrink-0">
                {!alert.acknowledged ? (
                  <>
                    <button
                      onClick={() => handleAcknowledge(alert.id)}
                      disabled={isAcking}
                      className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 border border-slate-200 dark:border-slate-700 rounded-lg text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 hover:text-emerald-600 dark:hover:text-emerald-400 hover:border-emerald-200 dark:hover:border-emerald-500/30 transition-colors disabled:opacity-50"
                    >
                      {isAcking ? (
                        <><Loader2 size={16} className="animate-spin" /> Processing...</>
                      ) : (
                        <><CheckSquare size={16} className="text-slate-400 group-hover:text-emerald-500" /> Acknowledge</>
                      )}
                    </button>
                    <button className={`flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 ${classes.btnBg} text-white rounded-lg text-sm font-bold shadow-sm ${classes.btnShadow} transition-colors`}>
                      Escalate <ArrowUpRight size={16} />
                    </button>
                  </>
                ) : (
                  <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-lg text-sm font-bold border border-emerald-200 dark:border-emerald-500/30">
                    <CheckCircle2 size={16} /> Acknowledged
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AlertsUI;
