import React, { useEffect, useState } from 'react';
import { AlertTriangle, Bell, CheckCircle, X, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { panelAPI } from '../services/api';
import { requirePanelId } from '../services/session';

import { cleanUUIDsFromText } from '../lib/globalFilters';

const AlertNotifications = () => {
  const [alerts, setAlerts] = useState([]);
  const [dismissed, setDismissed] = useState(new Set());

  // fetchAlerts lives inside the effect: it is only used here, and declaring it
  // in the body meant the effect referenced a function recreated every render
  // while claiming an empty dependency list.
  //
  // It also used to filter on `dismissed`, capturing the empty Set from the
  // first render forever — a dismissed alert would reappear on the next poll.
  // Dismissal is now applied when rendering, against the current Set.
  useEffect(() => {
    let cancelled = false;

    const fetchAlerts = async () => {
      try {
        const panelId = requirePanelId();
        const data = await panelAPI.getAlerts(panelId);
        if (!cancelled) setAlerts(data.filter(alert => !alert.acknowledged_at));
      } catch (err) {
        console.error('Failed to fetch alerts:', err);
      }
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  const visibleAlerts = alerts.filter(alert => !dismissed.has(alert.id));

  const handleDismiss = async (alertId) => {
    // Optimistically dismiss the alert on the frontend
    setDismissed(prev => new Set(prev).add(alertId));
    setAlerts(prev => prev.filter(alert => alert.id !== alertId));

    try {
      const panelId = requirePanelId();
      await panelAPI.acknowledgeAlert(panelId, alertId);
    } catch (err) {
      console.error('Failed to dismiss alert on backend:', err);
      // We keep it dismissed on the frontend to avoid disrupting the user experience.
      // It will reload if they refresh the page and the backend update actually failed.
    }
  };

  const getAlertIcon = (type) => {
    switch (type) {
      case 'reminder':
        return <Bell className="text-blue-500" size={20} />;
      case 'missed':
        return <AlertTriangle className="text-red-500" size={20} />;
      case 'activation':
        return <CheckCircle className="text-green-500" size={20} />;
      case 'reschedule':
        return <CheckCircle className="text-emerald-500" size={20} />;
      default:
        return <AlertCircle className="text-yellow-500" size={20} />;
    }
  };

  const getAlertColors = (type) => {
    switch (type) {
      case 'reminder':
        return {
          bg: 'bg-blue-50 dark:bg-blue-500/10',
          border: 'border-blue-200 dark:border-blue-500/30',
          text: 'text-blue-900 dark:text-blue-100'
        };
      case 'missed':
        return {
          bg: 'bg-red-50 dark:bg-red-500/10',
          border: 'border-red-200 dark:border-red-500/30',
          text: 'text-red-900 dark:text-red-100'
        };
      case 'activation':
        return {
          bg: 'bg-green-50 dark:bg-green-500/10',
          border: 'border-green-200 dark:border-green-500/30',
          text: 'text-green-900 dark:text-green-100'
        };
      case 'reschedule':
        return {
          bg: 'bg-emerald-50 dark:bg-emerald-500/10',
          border: 'border-emerald-200 dark:border-emerald-500/30',
          text: 'text-emerald-900 dark:text-emerald-100'
        };
      default:
        return {
          bg: 'bg-yellow-50 dark:bg-yellow-500/10',
          border: 'border-yellow-200 dark:border-yellow-500/30',
          text: 'text-yellow-900 dark:text-yellow-100'
        };
    }
  };

  return (
    <div className="fixed top-20 right-4 z-50 space-y-3 max-w-md">

      <AnimatePresence>
        {visibleAlerts.map((alert) => {
          const colors = getAlertColors(alert.alert_type);
          
          return (
            <motion.div
              key={alert.id}
              initial={{ opacity: 0, x: 300, scale: 0.8 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 300, scale: 0.8 }}
              transition={{ duration: 0.3 }}
              className={`${colors.bg} ${colors.border} border rounded-xl shadow-lg p-4 relative`}
            >
              <button
                onClick={() => handleDismiss(alert.id)}
                className="absolute top-2 right-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                <X size={18} />
              </button>

              <div className="flex items-start gap-3 pr-6">
                <div className="flex-shrink-0 mt-0.5">
                  {getAlertIcon(alert.alert_type)}
                </div>
                
                <div className="flex-1">
                  <h4 className={`font-bold text-sm ${colors.text} mb-1`}>
                    {cleanUUIDsFromText(alert.title)}
                  </h4>
                  <p className={`text-xs ${colors.text} opacity-80`}>
                    {cleanUUIDsFromText(alert.body)}
                  </p>
                  {alert.created_at && (
                    <p className={`text-xs ${colors.text} opacity-60 mt-2`}>
                      {new Date(alert.created_at).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
};

export default AlertNotifications;
