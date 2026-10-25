import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarClock, Save, RefreshCw, Play, AlertCircle } from 'lucide-react';
import { panelAPI } from '../../services/api';
import { requirePanelId } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const toDateInput = (isoValue) => {
  if (!isoValue) return '';
  const d = new Date(isoValue);
  const adjusted = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 10);
};

const toTimeInput = (isoValue) => {
  if (!isoValue) return '';
  const d = new Date(isoValue);
  const adjusted = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(11, 16);
};

const HOURS_12 = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, '0'));
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'));

const time24To12Parts = (hhmm) => {
  if (!hhmm || !hhmm.includes(':')) {
    return { hour: '', minute: '', period: 'AM' };
  }
  const [hRaw, mRaw] = hhmm.split(':');
  const hour24 = Number(hRaw);
  const period = hour24 >= 12 ? 'PM' : 'AM';
  const hour12 = ((hour24 + 11) % 12) + 1;
  return {
    hour: String(hour12).padStart(2, '0'),
    minute: String(Number(mRaw)).padStart(2, '0'),
    period,
  };
};

const time12To24 = (hour12, minute, period) => {
  if (!hour12 || !minute || !period) {
    return '';
  }
  let hour = Number(hour12) % 12;
  if (period === 'PM') {
    hour += 12;
  }
  return `${String(hour).padStart(2, '0')}:${minute}`;
};

const SlotManagement = () => {
  const navigate = useNavigate();
  const [unassignedTeams, setUnassignedTeams] = useState([]);
  const [catalogTeams, setCatalogTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState('');
  const { semesterMap, filterRows } = useGlobalFilters();
  const filteredUnassignedTeams = filterRows(unassignedTeams);
  const filteredCatalogTeams = filterRows(catalogTeams);

  const [form, setForm] = useState({
    team_id: '',
    date: '',
    start_hour: '',
    start_minute: '',
    start_period: 'AM',
    end_hour: '',
    end_minute: '',
    end_period: 'AM',
    venue: 'Main Hall'
  });

  const fetchTeamCatalog = async () => {
    try {
      const panelId = requirePanelId();
      const [unassigned, catalog] = await Promise.all([
        panelAPI.getUnassignedTeams(panelId),
        panelAPI.getTeamCatalog(panelId)
      ]);
      setUnassignedTeams(unassigned || []);
      setCatalogTeams(catalog || []);
      setError(null);
    } catch (err) {
      console.error('Failed to load team catalog:', err);
      setError(err.message || 'Failed to load teams');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeamCatalog();
  }, []);

  const pickTeam = (team) => {
    const start = time24To12Parts(toTimeInput(team.window_start));
    const end = time24To12Parts(toTimeInput(team.window_end));
    setForm({
      team_id: String(team.team_id),
      date: toDateInput(team.window_start),
      start_hour: start.hour,
      start_minute: start.minute,
      start_period: start.period,
      end_hour: end.hour,
      end_minute: end.minute,
      end_period: end.period,
      venue: team.venue || 'Main Hall'
    });
    setSuccess('');
  };

  const handleFormChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setSuccess('');
  };

  const saveSlot = async () => {
    if (!form.team_id || !form.date || !form.start_hour || !form.start_minute || !form.end_hour || !form.end_minute) {
      setError('Select a team and fill date/start/end time.');
      return;
    }

    const startTime24 = time12To24(form.start_hour, form.start_minute, form.start_period);
    const endTime24 = time12To24(form.end_hour, form.end_minute, form.end_period);
    const start = new Date(`${form.date}T${startTime24}:00`);
    const end = new Date(`${form.date}T${endTime24}:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      setError('Invalid date or time format.');
      return;
    }
    if (end <= start) {
      setError('End time must be after start time.');
      return;
    }

    setSaving(true);
    try {
      const panelId = requirePanelId();
      await panelAPI.upsertSlot(panelId, {
        team_id: Number(form.team_id),
        window_start: start.toISOString(),
        window_end: end.toISOString(),
        venue: form.venue || 'Main Hall',
        slot_label: `${form.start_hour}:${form.start_minute} ${form.start_period} - ${form.end_hour}:${form.end_minute} ${form.end_period}`,
        status: 'Upcoming'
      });
      setSuccess('Slot saved successfully.');
      setError(null);
      await fetchTeamCatalog();
    } catch (err) {
      console.error('Failed to save slot:', err);
      setError(err.message || 'Failed to save slot');
    } finally {
      setSaving(false);
    }
  };

  const activateSelectedTeam = async () => {
    if (!form.team_id) {
      setError('Select a team first.');
      return;
    }
    try {
      const panelId = requirePanelId();
      await panelAPI.activateSlot(panelId, Number(form.team_id), {});
      setSuccess('Selected team slot activated.');
      setError(null);
      await fetchTeamCatalog();
    } catch (err) {
      console.error('Failed to activate slot:', err);
      setError(err.message || 'Failed to activate selected slot');
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100">Slot Management</h2>
          <p className="text-slate-500 font-medium">Select any team from backend data and assign/update their slot time.</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={fetchTeamCatalog}
            className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
          >
            <RefreshCw size={16} />
            Refresh List
          </button>
          <button
            onClick={() => navigate('/panel/slots')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 rounded-lg font-medium hover:bg-blue-200 dark:hover:bg-blue-500/30 transition-colors"
          >
            <CalendarClock size={16} />
            View Slot List
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-700 dark:text-emerald-300 px-4 py-3 rounded-xl">
          {success}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-6 shadow-sm space-y-4">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Assign Or Update Slot</h3>

          <div>
            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Team</label>
            <select
              value={form.team_id}
              onChange={(e) => handleFormChange('team_id', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
            >
              <option value="">Select team</option>
              {filteredUnassignedTeams.map((team) => (
                <option key={team.team_id} value={team.team_id}>
                  {teamDisplayLabel(team.team_id, team, semesterMap)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Date</label>
            <input
              type="date"
              value={form.date}
              onChange={(e) => handleFormChange('date', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Start</label>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={form.start_hour}
                  onChange={(e) => handleFormChange('start_hour', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="">HH</option>
                  {HOURS_12.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
                <select
                  value={form.start_minute}
                  onChange={(e) => handleFormChange('start_minute', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="">MM</option>
                  {MINUTES.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <select
                  value={form.start_period}
                  onChange={(e) => handleFormChange('start_period', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">End</label>
              <div className="grid grid-cols-3 gap-2">
                <select
                  value={form.end_hour}
                  onChange={(e) => handleFormChange('end_hour', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="">HH</option>
                  {HOURS_12.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
                <select
                  value={form.end_minute}
                  onChange={(e) => handleFormChange('end_minute', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="">MM</option>
                  {MINUTES.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <select
                  value={form.end_period}
                  onChange={(e) => handleFormChange('end_period', e.target.value)}
                  className="w-full px-2 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
                >
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">Venue</label>
            <input
              type="text"
              value={form.venue}
              onChange={(e) => handleFormChange('venue', e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg dark:bg-slate-900 dark:text-slate-200"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={saveSlot}
              disabled={saving}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 text-white rounded-lg font-medium transition-colors"
            >
              <Save size={16} />
              {saving ? 'Saving...' : 'Save Slot'}
            </button>
            <button
              onClick={activateSelectedTeam}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
            >
              <Play size={14} />
              Activate
            </button>
          </div>
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
            <CalendarClock size={18} className="text-emerald-500" />
            <h3 className="font-bold text-slate-900 dark:text-slate-100">Unassigned Teams (Schedule From Here)</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-300 uppercase tracking-wider text-xs">
                <tr>
                  <th className="px-4 py-3 text-left">Team</th>
                  <th className="px-4 py-3 text-left">Project</th>
                  <th className="px-4 py-3 text-left">Current Slot</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {filteredUnassignedTeams.map((team) => (
                  <tr key={team.team_id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-900 dark:text-slate-100">{teamDisplayLabel(team.team_id, team, semesterMap)}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{team.project_title || 'N/A'}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{team.current_slot || 'Not set'}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold">
                        {team.current_status || 'Unassigned'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => pickTeam(team)}
                        className="text-emerald-600 dark:text-emerald-400 font-semibold hover:underline"
                      >
                        Select
                      </button>
                    </td>
                  </tr>
                ))}
                {filteredUnassignedTeams.length === 0 && (
                  <tr>
                    <td className="px-4 py-4 text-slate-500" colSpan={5}>No unassigned teams available.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex items-center gap-2">
          <CalendarClock size={18} className="text-blue-500" />
          <h3 className="font-bold text-slate-900 dark:text-slate-100">Already Scheduled Or Completed Teams</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-300 uppercase tracking-wider text-xs">
              <tr>
                <th className="px-4 py-3 text-left">Team</th>
                <th className="px-4 py-3 text-left">Project</th>
                <th className="px-4 py-3 text-left">Current Slot</th>
                <th className="px-4 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {filteredCatalogTeams.filter((team) => team.current_slot).map((team) => (
                <tr key={team.team_id} className="hover:bg-slate-50 dark:hover:bg-slate-900/30">
                  <td className="px-4 py-3 font-semibold text-slate-900 dark:text-slate-100">{teamDisplayLabel(team.team_id, team, semesterMap)}</td>
                  <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{team.project_title || 'N/A'}</td>
                  <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{team.current_slot}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold">{team.current_status || 'Scheduled'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4 flex items-start gap-3">
        <AlertCircle className="text-amber-600 dark:text-amber-400 mt-0.5" size={18} />
        <p className="text-sm text-amber-700 dark:text-amber-300">
          Only unassigned teams are selectable for slot scheduling. Teams already scheduled/done are shown separately for reference.
        </p>
      </div>
    </div>
  );
};

export default SlotManagement;
