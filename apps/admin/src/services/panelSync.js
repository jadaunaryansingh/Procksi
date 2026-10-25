/**
 * panelSync.js
 *
 * Admin portal → Panel portal sync service.
 *
 * Requests go through admin-api's own `/api/panel-sync/*` proxy, not to the
 * Panel portal directly. Until 2026-09-03 remediation this called panel-api's
 * `/admin/sync/*` endpoints straight from the browser with a shared
 * `X-Admin-Api-Key` header (`VITE_ADMIN_API_KEY`) — Vite inlines build-time
 * env vars into the shipped bundle, so that key was readable by anyone who
 * opened the admin portal's JS (incident §2.8). admin-api now holds that key
 * server-side only and forwards the call after checking the caller's normal
 * admin session — see backend/admin-api/app/panel_sync_proxy.py.
 */

import { withAuthRetry } from '../lib/api.js';
import { getApiBaseUrl } from '../lib/apiBase.js';

const ADMIN_API_URL = getApiBaseUrl();

async function request(path, options = {}) {
  const url = `${ADMIN_API_URL}/api/panel-sync${path}`;
  // withAuthRetry calls this with the current auth headers already resolved,
  // and retries once with a refreshed token on a 401.
  const res = await withAuthRetry((headers) =>
    fetch(url, { ...options, headers: { ...headers, 'Content-Type': 'application/json' } }),
  );
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch { /* non-fatal: fall through to the default below */ }
    throw new Error(`Panel sync error [${path}]: ${detail}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Evaluation parameters sync
// ---------------------------------------------------------------------------

/**
 * Fetch the current evaluation rubric from the panel portal (admin-keyed endpoint).
 * Returns an array of sections in the same format used by SemesterSettings config state,
 * or null if the table is empty or the portal is unreachable.
 */
export async function fetchEvaluationParameters() {
  try {
    const data = await request('/admin/sync/evaluation-parameters');
    // data = { sections: [{category, criteria: [{criterion_name, max_marks}]}] }
    if (!data?.sections?.length) return null;
    // Flatten: each criterion becomes a top-level parameter; description defaults to empty
    return data.sections.flatMap(s =>
      (s.criteria || []).map(c => ({
        name: c.name || c.criterion_name || '',
        description: c.description || '',
        max_marks: c.max_marks ?? 0,
      }))
    );
  } catch (_) {
    return null;
  }
}

/**
 * Push evaluation rubric parameters from admin to panel portal.
 * Called when admin saves evaluation config.
 * @param {Array<{category: string, criteria: Array<{criterion_name: string, max_marks: number}>}>} sections
 */
export async function syncEvaluationParameters(parameters) {
  // Accept either flat array [{name, description, max_marks}]
  // or old nested [{category, criteria:[...]}]
  // Panel backend expects: { sections: [{category, criteria:[{criterion_name, max_marks}]}] }
  let sections;
  if (parameters.length > 0 && 'criteria' in parameters[0]) {
    // Already nested format
    sections = parameters.map(section => ({
      ...section,
      criteria: section.criteria.map(c => ({
        criterion_name: c.name || c.criterion_name,
        max_marks: c.max_marks,
      }))
    }));
  } else {
    // Flat format — each parameter becomes its own section with one criterion
    sections = parameters.map(p => ({
      category: p.name,
      criteria: [{
        criterion_name: p.name,
        max_marks: p.max_marks,
      }]
    }));
  }
  return request('/admin/sync/evaluation-parameters', {
    method: 'POST',
    body: JSON.stringify({ sections }),
  });
}

// ---------------------------------------------------------------------------
// Panel management
// ---------------------------------------------------------------------------

/**
 * Create or update a panel in the Panel portal.
 * @param {string} panelId  – unique identifier (e.g. "PANEL-A")
 * @param {object} data     – { display_name, round_name, is_active, email?, password? }
 */
export async function upsertPanel(panelId, data) {
  return request(`/admin/sync/panels/${encodeURIComponent(panelId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * List all panels registered in the Panel portal.
 */
export async function listPanels() {
  return request('/admin/sync/panels');
}

// ---------------------------------------------------------------------------
// Team management
// ---------------------------------------------------------------------------

/**
 * Push team / project / GitHub metadata in bulk.
 * @param {Array<{team_id, team_name, project_title?, project_description?, github_url?}>} items
 */
export async function upsertTeams(items) {
  return request('/admin/sync/teams', {
    method: 'POST',
    body: JSON.stringify(items),
  });
}

// ---------------------------------------------------------------------------
// Slot management
// ---------------------------------------------------------------------------

/**
 * Push (create / update) evaluation slots for a panel.
 * @param {string} panelId
 * @param {Array<{team_id, slot_label, window_start, window_end, venue?}>} slots
 */
export async function upsertSlots(panelId, slots) {
  return request(`/admin/sync/slots/${encodeURIComponent(panelId)}`, {
    method: 'POST',
    body: JSON.stringify(slots),
  });
}

/**
 * Remove a slot from a panel (only if not yet submitted).
 */
export async function deleteSlot(panelId, teamId) {
  return request(
    `/admin/sync/slots/${encodeURIComponent(panelId)}/${teamId}`,
    { method: 'DELETE' }
  );
}

/**
 * Get the current slot schedule for a panel (for verification).
 */
export async function getPanelSlots(panelId) {
  return request(`/admin/sync/slots/${encodeURIComponent(panelId)}`);
}

// ---------------------------------------------------------------------------
// Evaluation results
// ---------------------------------------------------------------------------

/**
 * Fetch all submitted evaluations across all panels.
 * Returns an array of EvaluationResult objects.
 */
export async function getAllEvaluations() {
  return request('/admin/sync/evaluations');
}

/**
 * Fetch submitted evaluations for a specific panel.
 */
export async function getPanelEvaluations(panelId) {
  return request(`/admin/sync/evaluations/${encodeURIComponent(panelId)}`);
}

// ---------------------------------------------------------------------------
// Alerts / Reschedule requests
// ---------------------------------------------------------------------------

/**
 * Fetch all alerts (optionally filter by type or unacknowledged).
 * @param {object} opts – { alert_type?: string, unacknowledged_only?: boolean }
 */
export async function getAlerts(opts = {}) {
  const params = new URLSearchParams();
  if (opts.alert_type) params.set('alert_type', opts.alert_type);
  if (opts.unacknowledged_only) params.set('unacknowledged_only', 'true');
  const qs = params.toString();
  return request(`/admin/sync/alerts${qs ? `?${qs}` : ''}`);
}

/**
 * Acknowledge an alert on the Panel portal side.
 */
export async function acknowledgeAlert(alertId) {
  return request(`/admin/sync/alerts/${alertId}/acknowledge`, { method: 'POST' });
}

/**
 * Create a panel-facing alert (e.g. after admin confirms a reschedule).
 * @param {object} alert – { panel_id, team_id?, alert_type, title, body? }
 */
export async function createPanelAlert(alert) {
  return request('/admin/sync/alerts', {
    method: 'POST',
    body: JSON.stringify(alert),
  });
}

// ---------------------------------------------------------------------------
// Full schedule sync helper
// ---------------------------------------------------------------------------

/**
 * High-level helper: given a schedule slot from the Admin portal,
 * ensure the corresponding panel, team, and slot all exist in the Panel portal.
 *
 * @param {object} slot - Admin schedule slot with fields:
 *   panel (string like "Panel A"), team (string like "TEAM-400"),
 *   date (YYYY-MM-DD), time (e.g. "10:00 AM - 10:30 AM"),
 *   room (string), panel_email (optional), panel_password (optional),
 *   round_name (optional), window_start (ISO), window_end (ISO)
 */
function toNumericId(teamStr) {
  if (!teamStr) return 0;
  const str = String(teamStr).trim();

  const parseWithLeadingZero = (numStr) => {
    const val = parseInt(numStr, 10);
    if (numStr.startsWith('0') && val !== 0) {
      return 10000 + val;
    }
    return val;
  };

  // 1. Check for -T\d+ suffix (case insensitive)
  const tMatch = str.match(/-T(\d+)/i);
  if (tMatch) {
    return parseWithLeadingZero(tMatch[1]);
  }

  // 2. Check for trailing digits after a hyphen (e.g., TEAM-11)
  const lastDashMatch = str.match(/-(\d+)$/);
  if (lastDashMatch) {
    return parseWithLeadingZero(lastDashMatch[1]);
  }

  // 3. Fallback: match the last digit sequence
  const allNums = str.match(/\d+/g);
  if (allNums && allNums.length > 0) {
    return parseWithLeadingZero(allNums[allNums.length - 1]);
  }

  return 0;
}

export async function syncScheduleSlot(slot) {
  const panelId = slot.panelId || slot.panel?.replace(/\s+/g, '-').toUpperCase() || 'PANEL-UNKNOWN';
  const teamIdNum = toNumericId(slot.team);

  if (!teamIdNum) throw new Error(`Cannot derive numeric team_id from "${slot.team}"`);

  // 1. Ensure panel exists
  await upsertPanel(panelId, {
    display_name: slot.panel,
    round_name: slot.round_name || 'Mid-Term Evaluation - Round 1',
    is_active: true,
    email: slot.panel_email || undefined,
    password: slot.panel_password || undefined,
  });

  // 2. Ensure team exists
  await upsertTeams([
    {
      team_id: teamIdNum,
      team_name: slot.team,
      project_title: slot.project_title || slot.team,
    },
  ]);

  // 3. Push slot
  const windowStart = slot.window_start || _buildWindowStart(slot.date, slot.time);
  const windowEnd = slot.window_end || _buildWindowEnd(slot.date, slot.time);

  await upsertSlots(panelId, [
    {
      team_id: teamIdNum,
      slot_label: slot.time || slot.slot_label || slot.date,
      window_start: windowStart,
      window_end: windowEnd,
      venue: (slot.meetLink || slot.meet_link || slot.slotVenueMode === 'online' || slot.venue_mode === 'online' || slot.room === 'Online') ? 'Online' : (slot.room || slot.venue || 'Main Hall'),
      cycle_id: slot.cycle_id || null,
      meet_link: slot.meetLink || slot.meet_link || null,
    },
  ]);

  return { panelId, teamId: teamIdNum };
}

export async function syncScheduleSlotsBulk(slots, panels = [], allTeams = []) {
  if (!slots || !slots.length) return;

  const panelsMap = new Map();
  const teamsToUpsertMap = new Map();
  const slotsByPanel = new Map();

  for (const slot of slots) {
    const panelId = slot.panelId || slot.panel?.replace(/\s+/g, '-').toUpperCase() || 'PANEL-UNKNOWN';
    const teamIdNum = toNumericId(slot.team);
    if (!teamIdNum) continue;

    // Find panel info if available
    const panelRow = panels.find(p => p.id === panelId || p.name === slot.panel);
    if (!panelsMap.has(panelId)) {
      panelsMap.set(panelId, {
        display_name: slot.panel || panelRow?.name || panelId,
        round_name: slot.round_name || panelRow?.description || 'Mid-Term Evaluation - Round 1',
        is_active: true,
        email: slot.panel_email || panelRow?.email || undefined,
        password: slot.panel_password || panelRow?.password || undefined,
      });
    }

    const teamObj = allTeams.find(t => String(t.id) === String(slot.team));
    const projectTitle = teamObj?.title || slot.project_title || slot.team;

    teamsToUpsertMap.set(teamIdNum, {
      team_id: teamIdNum,
      team_name: slot.team,
      project_title: projectTitle,
    });

    if (!slotsByPanel.has(panelId)) {
      slotsByPanel.set(panelId, []);
    }

    const windowStart = slot.window_start || _buildWindowStart(slot.date, slot.time);
    const windowEnd = slot.window_end || _buildWindowEnd(slot.date, slot.time);

    slotsByPanel.get(panelId).push({
      team_id: teamIdNum,
      slot_label: slot.time || slot.slot_label || slot.date,
      window_start: windowStart,
      window_end: windowEnd,
      venue: (slot.meetLink || slot.meet_link || slot.slotVenueMode === 'online' || slot.venue_mode === 'online' || slot.room === 'Online') ? 'Online' : (slot.room || slot.venue || 'Main Hall'),
      cycle_id: slot.cycle_id || null,
      meet_link: slot.meetLink || slot.meet_link || null,
    });
  }

  // 1. Upsert panels
  for (const [panelId, panelData] of panelsMap.entries()) {
    try {
      await upsertPanel(panelId, panelData);
    } catch (err) {
      console.error(`Failed to upsert panel ${panelId}:`, err);
    }
  }

  // 2. Upsert teams in bulk
  const teamsToUpsert = Array.from(teamsToUpsertMap.values());
  if (teamsToUpsert.length > 0) {
    try {
      await upsertTeams(teamsToUpsert);
    } catch (err) {
      console.error('Failed to upsert teams in bulk:', err);
    }
  }

  // 3. Upsert slots per panel in bulk
  for (const [panelId, panelSlots] of slotsByPanel.entries()) {
    try {
      await upsertSlots(panelId, panelSlots);
    } catch (err) {
      console.error(`Failed to upsert slots for panel ${panelId}:`, err);
    }
  }
}


// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _parseTime(timeStr) {
  // Parses "10:00 AM" or "10:30" into { hours, minutes }
  const clean = (timeStr || '').trim();
  const ampm = /([ap]m)/i.exec(clean);
  const parts = clean.replace(/[apm]/gi, '').trim().split(':');
  let hours = parseInt(parts[0], 10) || 0;
  const minutes = parseInt(parts[1], 10) || 0;
  if (ampm) {
    if (/pm/i.test(ampm[1]) && hours !== 12) hours += 12;
    if (/am/i.test(ampm[1]) && hours === 12) hours = 0;
  }
  return { hours, minutes };
}

function _buildWindowStart(date, timeRange) {
  // timeRange: "10:00 AM - 10:30 AM"
  const start = (timeRange || '').split('-')[0];
  const { hours, minutes } = _parseTime(start);
  const d = new Date(date);
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
}

function _buildWindowEnd(date, timeRange) {
  const parts = (timeRange || '').split('-');
  const end = parts[1] || parts[0];
  const { hours, minutes } = _parseTime(end);
  const d = new Date(date);
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
}

