import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellDot, X } from 'lucide-react';
import { panelAPI } from '../../services/api';
import { requirePanelId } from '../../services/session';

import { cleanUUIDsFromText } from '../../lib/globalFilters';

const ReminderPopup = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [alert, setAlert] = useState(null);
  const [activeTeamId, setActiveTeamId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchReminder = async () => {
      try {
        const panelId = requirePanelId();
        const alerts = await panelAPI.getAlerts(panelId);

        const nextAlert = alerts?.[0] || null;
        setAlert(nextAlert);
        setActiveTeamId(nextAlert?.team_id || null);
        setIsVisible(Boolean(nextAlert));
      } catch (err) {
        console.error('Failed to load reminder popup data:', err);
      }
    };

    fetchReminder();
  }, []);

  const dismissAlert = async () => {
    try {
      if (alert?.id) {
        const panelId = requirePanelId();
        await panelAPI.acknowledgeAlert(panelId, alert.id);
      }
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    } finally {
      setIsVisible(false);
    }
  };

  const gotoEvaluation = () => {
    const teamId = activeTeamId || alert?.team_id;
    if (teamId) {
      navigate(`/panel/evaluation/${teamId}`);
      setIsVisible(false);
    }
  };

  if (!isVisible || !alert) {
    return null;
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-right-8 fade-in duration-500">
      <div className="bg-slate-900 dark:bg-slate-800 border-l-4 border-amber-500 rounded-xl p-5 shadow-[0_10px_40px_rgba(245,158,11,0.15)] dark:shadow-[0_10px_40px_rgba(245,158,11,0.2)] w-80 relative overflow-hidden group">
        <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 blur-2xl rounded-full pointer-events-none" />

        <button
          onClick={dismissAlert}
          className="absolute top-3 right-3 text-slate-400 hover:text-white transition-colors"
        >
          <X size={16} />
        </button>

        <div className="flex gap-3 relative z-10">
          <div className="text-amber-400 mt-0.5 animate-bounce">
            <BellDot size={20} />
          </div>
          <div>
            <h4 className="text-amber-400 font-bold mb-1">{cleanUUIDsFromText(alert.title)}</h4>
            <p className="text-slate-300 text-sm mb-3 font-medium">
              {cleanUUIDsFromText(alert.body || 'Please review and complete the required evaluation action.')}
            </p>
            <button
              onClick={gotoEvaluation}
              disabled={!activeTeamId && !alert.team_id}
              className="text-xs font-black uppercase tracking-wider bg-amber-500 hover:bg-amber-600 disabled:bg-slate-600 disabled:text-slate-300 text-slate-900 px-3 py-1.5 rounded transition-colors shadow-sm"
            >
              Go to Evaluation
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReminderPopup;
