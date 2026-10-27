import React, { useState, useCallback, useEffect, useMemo } from 'react';

// ── Persistent configurator helpers ────────────────────────────────────────
const CONFIG_KEY = 'procksi-schedule-config';
const DEFAULT_CONFIG = {
    rooms:                [
        { id: 1, name: 'Seminar Hall 1',   capacity: 30 },
        { id: 2, name: 'Lab 402',          capacity: 20 },
        { id: 3, name: 'Conference Room B', capacity: 15 },
    ],
    configDates:          { start: '2026-05-15', end: '2026-05-20' },
    configTimes:          { start: '09:00', end: '17:00' },
    presentationDuration: 30,
    venueMode:            'offline',
};
function loadConfig() {
    try { return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}') }; }
    catch { return DEFAULT_CONFIG; }
}
function saveConfig(patch) {
    try {
        const current = loadConfig();
        localStorage.setItem(CONFIG_KEY, JSON.stringify({ ...current, ...patch }));
    } catch { /* quota errors ignored */ }
}
import { Calendar as CalendarIcon, Clock, MapPin, Users, Edit, Wand2, Plus, Bell, CheckCircle, Settings, X, DoorOpen, Trash2, Video, Globe, Search, Filter, Square, CheckSquare, MinusSquare, ChevronDown, ChevronUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { apiDeleteRows, apiUpsertTable, apiPatchRow, getAuthHeaders } from '../lib/api';
import { Loader2, AlertTriangle } from 'lucide-react';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { getAllEvaluations, deleteSlot, syncScheduleSlotsBulk } from '../services/panelSync';
import { teamLabel, sortByTeamNumber } from '../lib/teamUtils';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { getApiBaseUrl } from '../lib/apiBase';

const teamNumericId = (teamStr) => {
    if (!teamStr) return null;
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
        return parseWithLeadingZero(tMatch[1]) || null;
    }

    // 2. Check for trailing digits after a hyphen (e.g., TEAM-11)
    const lastDashMatch = str.match(/-(\d+)$/);
    if (lastDashMatch) {
        return parseWithLeadingZero(lastDashMatch[1]) || null;
    }

    // 3. Fallback: match the last digit sequence
    const allNums = str.match(/\d+/g);
    if (allNums && allNums.length > 0) {
        return parseWithLeadingZero(allNums[allNums.length - 1]) || null;
    }

    return null;
};

// Parse single time string "09:00 AM" or "9:00 AM" to minutes from midnight
const parseTimeToMinutes = (tStr) => {
    if (!tStr) return 0;
    const match = tStr.trim().match(/^(\d+):(\d+)\s*(AM|PM)$/i);
    if (!match) return 0;
    let h = parseInt(match[1], 10);
    const m = parseInt(match[2], 10);
    const ampm = match[3].toUpperCase();
    if (ampm === 'PM' && h !== 12) h += 12;
    if (ampm === 'AM' && h === 12) h = 0;
    return h * 60 + m;
};

const parseTimeInputToMinutes = (tStr) => {
    if (!tStr) return null;
    const clean = tStr.trim();
    const match24 = clean.match(/^(\d{1,2}):(\d{2})$/);
    if (match24) {
        return parseInt(match24[1], 10) * 60 + parseInt(match24[2], 10);
    }
    const match12 = clean.match(/^(\d+):(\d+)\s*(AM|PM)$/i);
    if (match12) {
        let h = parseInt(match12[1], 10);
        const m = parseInt(match12[2], 10);
        const ampm = match12[3].toUpperCase();
        if (ampm === 'PM' && h !== 12) h += 12;
        if (ampm === 'AM' && h === 12) h = 0;
        return h * 60 + m;
    }
    return null;
};

// Convert minutes from midnight to "9:00 AM" format matching the existing app standard
const minutesToTimeStr = (mins) => {
    const hh = Math.floor(mins / 60) % 24;
    const mm = mins % 60;
    const ampm = hh >= 12 ? 'PM' : 'AM';
    const h12 = hh % 12 || 12;
    return `${h12}:${String(mm).padStart(2, '0')} ${ampm}`;
};

// Parse a slot time range like "09:00 AM - 09:30 AM" into start and end minutes
const parseSlotTime = (timeStr) => {
    if (!timeStr) return { start: 0, end: 0 };
    const parts = timeStr.split('-').map(p => p.trim());
    if (parts.length < 2) return { start: 0, end: 0 };
    return {
        start: parseTimeToMinutes(parts[0]),
        end: parseTimeToMinutes(parts[1])
    };
};

// Shift a time range string by a delta in minutes
const shiftSlotTime = (timeStr, deltaMinutes) => {
    if (!timeStr || !deltaMinutes) return timeStr;
    const { start, end } = parseSlotTime(timeStr);
    const newStart = start + deltaMinutes;
    const newEnd = end + deltaMinutes;
    return `${minutesToTimeStr(newStart)} - ${minutesToTimeStr(newEnd)}`;
};

export default function Schedule() {
    const { semesterMap, filterRows } = useGlobalFilters();
    const { data: schedule, setData: setSchedule } = useSupabaseTableState('schedule_slots', [], { orderBy: 'date' });
    // Used by handleGenerate to know which teams already have slots and which panels exist
    const { data: allTeams } = useSupabaseTableState('teams_validation', [], { orderBy: 'id' });
    const { data: cycles } = useSupabaseTableState('presentation_cycles', []);
    const getTeamRow = (teamId) => allTeams.find(t => t.id === teamId) || null;
    const { data: mentors } = useSupabaseTableState('mentors', [], { orderBy: 'name' });
    const { data: panels } = useSupabaseTableState('panels', [], { orderBy: 'name' });
    const { data: results } = useSupabaseTableState('results', []);
    const { data: absentStudents } = useSupabaseTableState('absent_students', []);

    const panelOptions = useMemo(() => {
        const list = [];
        (panels || []).forEach(p => {
            if (p.name) list.push({ id: `panel-${p.id || p.name}`, name: p.name, label: p.name });
        });
        (mentors || []).forEach(m => {
            if (m.name && !list.some(item => item.name === m.name)) {
                list.push({ id: `mentor-${m.id || m.name}`, name: m.name, label: `${m.name}${m.department ? ` (${m.department})` : ''}` });
            }
        });
        return list;
    }, [panels, mentors]);
    const [evaluatedKeys, setEvaluatedKeys] = useState(new Set());
    const [googleConnected, setGoogleConnected] = useState(false);
    const [checkingGoogle, setCheckingGoogle] = useState(true);
    const [meetWarning, setMeetWarning] = useState(null);

    // Filters State
    const [searchTerm, setSearchTerm] = useState('');
    const [dateFilter, setDateFilter] = useState('');
    const [panelFilter, setPanelFilter] = useState('');
    const [roomFilter, setRoomFilter] = useState('');

    const uniqueDates = useMemo(() => {
        return [...new Set(schedule.map(slot => slot.date).filter(Boolean))].sort();
    }, [schedule]);

    const uniquePanels = useMemo(() => {
        return [...new Set(schedule.map(slot => slot.panel).filter(Boolean))].sort();
    }, [schedule]);

    const uniqueRooms = useMemo(() => {
        return [...new Set(schedule.map(slot => slot.room).filter(Boolean))].sort();
    }, [schedule]);

    const filteredSchedule = useMemo(() => {
        const slotsWithSemester = schedule.map(slot => {
            const teamObj = allTeams.find(t => t.id === slot.team);
            return {
                ...slot,
                semester_id: slot.semester_id || teamObj?.semester_id || ''
            };
        });
        return filterRows(slotsWithSemester).filter(slot => {
            const matchSearch = searchTerm ? (
                String(slot.team || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                String(slot.panel || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                String(slot.room || '').toLowerCase().includes(searchTerm.toLowerCase())
            ) : true;
            const matchDate = dateFilter ? slot.date === dateFilter : true;
            const matchPanel = panelFilter ? slot.panel === panelFilter : true;
            const matchRoom = roomFilter ? slot.room === roomFilter : true;
            return matchSearch && matchDate && matchPanel && matchRoom;
        });
    }, [schedule, allTeams, filterRows, searchTerm, dateFilter, panelFilter, roomFilter]);

    const activeFilterCount = [dateFilter, panelFilter, roomFilter].filter(Boolean).length;

    useEffect(() => {
        let cancelled = false;
        getAllEvaluations()
            .then((evals) => {
                if (cancelled) return;
                const keys = new Set((evals || []).map((e) => `${e.team_id}-${e.cycle_id || 'null'}`));
                setEvaluatedKeys(keys);
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [schedule.length]);

    const checkGoogleStatus = useCallback(async () => {
        try {
            const API_BASE = getApiBaseUrl();
            const res = await fetch(`${API_BASE}/api/events/google-auth-status`, {
                headers: getAuthHeaders()
            });
            if (res.ok) {
                const data = await res.json();
                setGoogleConnected(Boolean(data.connected));
            }
        } catch (err) {
            console.error('Error checking Google auth status:', err);
        } finally {
            setCheckingGoogle(false);
        }
    }, []);

    useEffect(() => {
        checkGoogleStatus();
    }, [checkGoogleStatus]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get('googleConnected') === 'true') {
            alert('🎉 Google Calendar connected successfully!');
            window.history.replaceState({}, document.title, window.location.pathname);
            checkGoogleStatus();
        } else if (params.get('error')) {
            alert('❌ Failed to connect Google Calendar: ' + params.get('error'));
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }, [checkGoogleStatus]);

    const handleGoogleConnect = async () => {
        try {
            const API_BASE = getApiBaseUrl();
            const res = await fetch(`${API_BASE}/api/events/google-auth-url`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) {
                const payload = await res.json().catch(() => ({}));
                throw new Error(payload.detail || `Server error (${res.status})`);
            }
            const data = await res.json();
            if (data.url) {
                window.location.href = data.url;
            }
        } catch (err) {
            console.error(err);
            alert('Failed to launch Google auth flow: ' + err.message);
        }
    };

    const [isGenerating, setIsGenerating] = useState(false);
    const [isGeneratingMeetLink, setIsGeneratingMeetLink] = useState(false);
    const [isNotifying, setIsNotifying] = useState(false);
    const [notified, setNotified] = useState(false);
    const [isSavingSlot, setIsSavingSlot] = useState(false);
    const [slotMode, setSlotMode] = useState('edit');
    const [deletingSlotId, setDeletingSlotId] = useState(null);
    const [showSlotMenu, setShowSlotMenu] = useState(false);

    // Bulk selection state
    const [selectedSlotIds, setSelectedSlotIds] = useState(new Set());
    const [showBulkEditModal, setShowBulkEditModal] = useState(false);
    const [isBulkDeleting, setIsBulkDeleting] = useState(false);
    const [isBulkSaving, setIsBulkSaving] = useState(false);
    const [bulkEditFields, setBulkEditFields] = useState({ time: '', panel: '', room: '', venueMode: '' });

    const toggleSelectSlot = useCallback((slotId) => {
        setSelectedSlotIds(prev => {
            const next = new Set(prev);
            if (next.has(String(slotId))) next.delete(String(slotId));
            else next.add(String(slotId));
            return next;
        });
    }, []);

    const isAllFilteredSelected = filteredSchedule.length > 0 && filteredSchedule.every(s => selectedSlotIds.has(String(s.id)));
    const isSomeFilteredSelected = filteredSchedule.some(s => selectedSlotIds.has(String(s.id)));

    const toggleSelectAll = () => {
        if (isAllFilteredSelected) {
            setSelectedSlotIds(prev => {
                const next = new Set(prev);
                filteredSchedule.forEach(s => next.delete(String(s.id)));
                return next;
            });
        } else {
            setSelectedSlotIds(prev => {
                const next = new Set(prev);
                filteredSchedule.forEach(s => next.add(String(s.id)));
                return next;
            });
        }
    };

    const handleBulkDelete = async () => {
        const toDelete = schedule.filter(s => selectedSlotIds.has(String(s.id)));
        if (!toDelete.length) return;
        const completed = toDelete.filter(s => slotIsCompleted(s));
        const deletable = toDelete.filter(s => !slotIsCompleted(s));
        if (!deletable.length) { alert('All selected slots are completed and cannot be deleted.'); return; }
        const confirmMsg = `Delete ${deletable.length} slot(s)?${completed.length ? `\n(${completed.length} completed slot(s) will be skipped.)` : ''}`;
        if (!window.confirm(confirmMsg)) return;
        setIsBulkDeleting(true);
        const previousSchedule = schedule;
        setSchedule(prev => prev.filter(s => !deletable.some(d => String(d.id) === String(s.id))));
        try {
            for (const slot of deletable) {
                await apiDeleteRows('schedule_slots', { id: slot.id });
                const panelRow = panels.find(p => p.name === slot.panel);
                const teamIdNum = teamNumericId(slot.team);
                if (panelRow?.id && teamIdNum) {
                    try { await deleteSlot(panelRow.id, teamIdNum); } catch { /* non-fatal: fall through to the default below */ }
                }
            }
            setSelectedSlotIds(new Set());
            AuditLogger.logScheduleAction(getCurrentUser(), `Bulk deleted ${deletable.length} presentation slots`);
        } catch (err) {
            alert('Bulk delete failed: ' + err.message);
            setSchedule(previousSchedule);
        } finally {
            setIsBulkDeleting(false);
        }
    };

    const handleBulkEdit = async () => {
        const toEdit = schedule.filter(s => selectedSlotIds.has(String(s.id)) && !slotIsCompleted(s));
        if (!toEdit.length) { alert('No editable slots selected (completed slots are skipped).'); return; }
        const fields = {};
        if (bulkEditFields.time) fields.time = bulkEditFields.time;
        if (bulkEditFields.panel) fields.panel = bulkEditFields.panel;
        if (bulkEditFields.venueMode === 'online') { fields.room = 'Online'; }
        else if (bulkEditFields.room) fields.room = bulkEditFields.room;
        if (!Object.keys(fields).length) { alert('Please set at least one field to update.'); return; }
        setIsBulkSaving(true);
        try {
            for (const slot of toEdit) {
                await apiPatchRow('schedule_slots', slot.id, fields);
            }
            setSchedule(prev => prev.map(s => {
                if (!selectedSlotIds.has(String(s.id)) || slotIsCompleted(s)) return s;
                return { ...s, ...fields };
            }));

            const updatedSlots = toEdit.map(s => ({ ...s, ...fields }));
            try {
                await syncScheduleSlotsBulk(updatedSlots, panels, allTeams);
            } catch (syncErr) {
                console.warn('Bulk edit sync failed:', syncErr);
            }

            setShowBulkEditModal(false);
            setSelectedSlotIds(new Set());
            setBulkEditFields({ time: '', panel: '', room: '', venueMode: '' });
            AuditLogger.logScheduleAction(getCurrentUser(), `Bulk updated ${toEdit.length} slots: ${JSON.stringify(fields)}`);
        } catch (err) {
            alert('Bulk edit failed: ' + err.message);
        } finally {
            setIsBulkSaving(false);
        }
    };

    // Edit Modal State
    const [editingSlot, setEditingSlot] = useState(null);

    // Bulk Schedule Modal State
    const [showBulkModal, setShowBulkModal] = useState(false);
    const [isSavingBulk, setIsSavingBulk] = useState(false);
    const [bulkConfig, setBulkConfig] = useState({
        count: 10,
        startDate: new Date().toISOString().slice(0, 10),
        startTime: '',
        panel: '',
        venueMode: 'offline',
        room: '',
        cycle_id: '',
        breakDuration: 0,
        lunchStartTime: '13:00',
        lunchDuration: 0,
    });
    const [configCycleId, setConfigCycleId] = useState('');

    // Configurator State — initialised once from localStorage, saved on every change
    const [showConfig, setShowConfig] = useState(false);
    const [rooms, _setRooms]                         = useState(() => loadConfig().rooms);
    const [configDates, _setConfigDates]             = useState(() => loadConfig().configDates);
    const [configTimes, _setConfigTimes]             = useState(() => loadConfig().configTimes);
    const [presentationDuration, _setPresentationDuration] = useState(() => loadConfig().presentationDuration);
    const [venueMode, _setVenueMode]                 = useState(() => loadConfig().venueMode);

    // Wrapped setters that also persist to localStorage
    const setRooms = useCallback((v) => {
        _setRooms(v);
        saveConfig({ rooms: typeof v === 'function' ? v(rooms) : v });
    }, [rooms]);
    const setConfigDates = useCallback((v) => {
        _setConfigDates(v);
        saveConfig({ configDates: typeof v === 'function' ? v(configDates) : v });
    }, [configDates]);
    const setConfigTimes = useCallback((v) => {
        _setConfigTimes(v);
        saveConfig({ configTimes: typeof v === 'function' ? v(configTimes) : v });
    }, [configTimes]);
    const setPresentationDuration = useCallback((v) => {
        _setPresentationDuration(v);
        saveConfig({ presentationDuration: typeof v === 'function' ? v(presentationDuration) : v });
    }, [presentationDuration]);
    const setVenueMode = useCallback((v) => {
        _setVenueMode(v);
        saveConfig({ venueMode: typeof v === 'function' ? v(venueMode) : v });
    }, [venueMode]);

    // Whether a slot is an online (Meet) slot vs a physical room.
    const isOnlineRoom = (room) => {
        const r = String(room || '').trim().toLowerCase();
        return r === '' || r === 'online' || r === 'google meet' || r === 'meet';
    };

    // After schedule_slots rows are saved, ask the backend to create a real Google
    // Meet on each assigned panel's own calendar (panel = host). Merges the real
    // links back into local state and surfaces panels that still need to connect.
    const ensureSlotMeets = async (rows) => {
        const slot_ids = (rows || [])
            .filter(r => r && r.id != null && isOnlineRoom(r.room))
            .map(r => r.id);
        if (!slot_ids.length) return;
        try {
            const API_BASE = getApiBaseUrl();
            const res = await fetch(`${API_BASE}/api/events/ensure-slot-meet`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ slot_ids }),
            });
            if (!res.ok) return;
            const data = await res.json();
            const linkById = {};
            [...(data.created || []), ...(data.updated || [])].forEach(r => {
                if (r.meetLink) linkById[String(r.slot_id)] = r.meetLink;
            });
            if (Object.keys(linkById).length) {
                setSchedule(prev => prev.map(s =>
                    linkById[String(s.id)] ? { ...s, meetLink: linkById[String(s.id)] } : s));
            }
            const errs = data.errors || [];
            const notConnected = errs.filter(e => e.reason === 'coordinator_not_connected');
            if (notConnected.length) {
                setMeetWarning(`${notConnected.length} online slot(s) have no Meet link — connect Google Calendar with the button above.`);
            } else if (errs.length) {
                setMeetWarning(`${errs.length} online slot(s) could not get a Meet link (Google error). Try again or paste a link manually.`);
            } else {
                setMeetWarning(null);
            }
        } catch (e) {
            console.warn('ensureSlotMeets failed:', e);
        }
    };

    const normalizeSlot = (slot, generatedMeetLink = null) => ({
        ...slot,
        capacity: Number.parseInt(slot.capacity, 10) || 20,
        meetLink: generatedMeetLink ?? slot.meetLink ?? null,
    });

    const slotMatches = (left, right) => {
        if (!left || !right) {
            return false;
        }

        if (left.id != null && right.id != null && String(left.id) === String(right.id)) {
            return true;
        }

        return [left.date, left.time, left.team, left.room].every((value, index) => value && value === [right.date, right.time, right.team, right.room][index]);
    };

    const openCustomSlot = () => {
        setSlotMode('create');
        setEditingSlot({
            date: new Date().toISOString().slice(0, 10),
            time: '',
            team: '',
            panel: '',
            room: '',
            capacity: 20,
            meetLink: null,
            slotVenueMode: venueMode,
            cycle_id: '',
            extraMinutes: 0,
        });
    };

    // Build time options from configurator settings
    const buildTimeOptions = () => {
        const [startH, startM] = configTimes.start.split(':').map(Number);
        const [endH, endM] = configTimes.end.split(':').map(Number);
        const dailyStartMins = startH * 60 + startM;
        const dailyEndMins = endH * 60 + endM;
        const fmt = (mins) => {
            const hh = Math.floor(mins / 60);
            const mm = mins % 60;
            const ampm = hh >= 12 ? 'PM' : 'AM';
            const h12 = hh % 12 || 12;
            return `${h12}:${String(mm).padStart(2, '0')} ${ampm}`;
        };
        const options = [];
        for (let m = dailyStartMins; m + presentationDuration <= dailyEndMins; m += presentationDuration) {
            options.push(`${fmt(m)} - ${fmt(m + presentationDuration)}`);
        }
        return options;
    };

    const handleGenerateMeetLinkForSlot = async () => {
        setIsGeneratingMeetLink(true);
        try {
            const API_BASE = getApiBaseUrl();
            const response = await fetch(`${API_BASE}/api/events/generate-meet-link`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    slot_id: editingSlot.id ?? 'new',
                    date: editingSlot.date,
                    time: editingSlot.time,
                    team: editingSlot.team,
                    room: editingSlot.room || null,
                }),
            });
            if (!response.ok) {
                const detailData = await response.json().catch(() => ({}));
                throw new Error(detailData?.detail || response.statusText);
            }
            const data = await response.json();
            setEditingSlot(prev => ({ ...prev, meetLink: data.meetLink }));
        } catch (err) {
            alert('Failed to generate Meet link: ' + err.message);
        } finally {
            setIsGeneratingMeetLink(false);
        }
    };

    const handleGenerateMeetLink = async (slot) => {
        setIsGenerating(true);
        try {
            // Call backend endpoint to generate Meet link
            const API_BASE = getApiBaseUrl();
            const response = await fetch(`${API_BASE}/api/events/generate-meet-link`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    slot_id: slot.id,
                    date: slot.date,
                    time: slot.time,
                    team: slot.team,
                    room: slot.room || null,
                }),
            });

            if (!response.ok) {
                const detailData = await response.json().catch(() => ({}));
                throw new Error(detailData?.detail || response.statusText);
            }

            const data = await response.json();
            const meetLink = data.meetLink;

            // Update the slot with the generated Meet link
            const updatedSlot = normalizeSlot(slot, meetLink);
            setSchedule(prev => prev.map(s => slotMatches(s, slot) ? updatedSlot : s));

            // Persist to database using PATCH (not upsert) so we never send the
            // identity `id` column back — Supabase forbids that on GENERATED ALWAYS columns.
            try {
                await apiPatchRow('schedule_slots', slot.id, { meetLink });
            } catch (error) {
                console.error('Failed to save Meet link to database:', error);
                setSchedule(prev => prev.map(s => slotMatches(s, slot) ? slot : s));
            }
        } catch (error) {
            console.error('Error generating Meet link:', error);
            alert('Failed to generate Google Meet link: ' + error.message);
        } finally {
            setIsGenerating(false);
        }
    };


    const handleBulkSchedule = async () => {
        const targetCycle = cycles.find(c => c.id === bulkConfig.cycle_id);
        const filteredTeams = targetCycle 
            ? allTeams.filter(t => t.semester_id === targetCycle.semester_id)
            : allTeams;

        const unscheduled = filteredTeams.filter(t => 
            !schedule.find(s => s.team === t.id && (targetCycle ? s.cycle_id === targetCycle.id : !slotIsCompleted(s)))
        );
        const teamsToSchedule = unscheduled.slice(0, bulkConfig.count);
        if (!teamsToSchedule.length) {
            alert('No unscheduled teams found. All teams may already have slots.');
            return;
        }
        if (!bulkConfig.startTime) { alert('Please select a start time.'); return; }
        if (bulkConfig.venueMode === 'offline' && !bulkConfig.room) { alert('Please select a venue/room.'); return; }
        if (!bulkConfig.panel) { alert('Please select a panel/mentor.'); return; }

        setIsSavingBulk(true);
        try {
            const [startH, startM] = configTimes.start.split(':').map(Number);
            const [endH, endM] = configTimes.end.split(':').map(Number);
            const dailyStartMins = startH * 60 + startM;
            const dailyEndMins = endH * 60 + endM;

            const breakDuration = parseInt(bulkConfig.breakDuration, 10) || 0;
            const lunchStartMins = bulkConfig.lunchDuration > 0 && bulkConfig.lunchStartTime 
                ? parseTimeInputToMinutes(bulkConfig.lunchStartTime)
                : null;
            const lunchDur = parseInt(bulkConfig.lunchDuration, 10) || 0;

            const timeOptions = buildTimeOptions();
            let timeIdx = timeOptions.indexOf(bulkConfig.startTime);
            if (timeIdx < 0) timeIdx = 0;
            let currentMins = dailyStartMins + timeIdx * presentationDuration;

            const cursor = new Date(bulkConfig.startDate + 'T00:00:00');
            let currentDayOffset = 0;

            const newSlots = [];

            for (const team of teamsToSchedule) {
                // Loop to find the next valid time slot
                while (true) {
                    if (lunchStartMins !== null && lunchDur > 0) {
                        const lunchEndMins = lunchStartMins + lunchDur;
                        const hasLunchOverlap = (currentMins < lunchEndMins) && (currentMins + presentationDuration > lunchStartMins);
                        if (hasLunchOverlap) {
                            currentMins = lunchEndMins;
                            continue;
                        }
                    }

                    if (currentMins + presentationDuration > dailyEndMins) {
                        currentDayOffset += 1;
                        currentMins = dailyStartMins;
                        continue;
                    }

                    break;
                }

                const slotDate = new Date(cursor);
                slotDate.setDate(slotDate.getDate() + currentDayOffset);
                const dateStr = slotDate.toISOString().slice(0, 10);

                const slotTimeRange = `${minutesToTimeStr(currentMins)} - ${minutesToTimeStr(currentMins + presentationDuration)}`;

                const room = bulkConfig.venueMode === 'offline' ? bulkConfig.room : 'Online';
                const capacity = bulkConfig.venueMode === 'offline'
                    ? (rooms.find(r => r.name === room)?.capacity ?? 20)
                    : 999;

                // Real Meet links are created after save, on the panel's calendar.
                const meetLink = null;

                newSlots.push(normalizeSlot({
                    date: dateStr,
                    time: slotTimeRange,
                    team: team.id,
                    panel: bulkConfig.panel,
                    room,
                    capacity,
                    meetLink,
                    cycle_id: bulkConfig.cycle_id || null,
                }));

                // Advance for next slot
                currentMins += presentationDuration + breakDuration;
            }

            const response = await apiUpsertTable('schedule_slots', newSlots);
            const saved = (response.data?.length ? response.data : newSlots).map(r => normalizeSlot(r));
            setSchedule(prev => {
                const keys = new Set(prev.map(s => `${s.team}-${s.date}-${s.time}`));
                return [...prev, ...saved.filter(r => !keys.has(`${r.team}-${r.date}-${r.time}`))];
            });

            ensureSlotMeets(saved);

            try {
                await syncScheduleSlotsBulk(saved, panels, allTeams);
            } catch (syncErr) {
                console.warn('Bulk sync failed:', syncErr);
            }

            setShowBulkModal(false);
        } catch (err) {
            alert('Bulk schedule failed: ' + err.message);
        } finally {
            setIsSavingBulk(false);
        }
    };

    const handleGenerate = async () => {
        setShowConfig(false);
        setIsGenerating(true);
        setNotified(false);

        try {
            // ── Build time slot grid from configurator settings ──────────────
            const activeRooms = venueMode === 'online' ? [{ name: 'Online', capacity: 999 }] : rooms.filter(r => r.name.trim());
            if (!activeRooms.length) { alert('Add at least one room/venue in the configurator.'); return; }

            // Collect all dates in range
            const dates = [];
            const cursor = new Date(configDates.start + 'T00:00:00');
            const endDate = new Date(configDates.end + 'T00:00:00');
            while (cursor <= endDate) {
                dates.push(cursor.toISOString().slice(0, 10));
                cursor.setDate(cursor.getDate() + 1);
            }

            // Build time slots per day (HH:MM increments)
            const [startH, startM] = configTimes.start.split(':').map(Number);
            const [endH,   endM  ] = configTimes.end.split(':').map(Number);
            const dailyStartMins = startH * 60 + startM;
            const dailyEndMins   = endH   * 60 + endM;
            const timesPerDay = [];
            for (let m = dailyStartMins; m + presentationDuration <= dailyEndMins; m += presentationDuration) {
                const fmt = (mins) => {
                    const hh = Math.floor(mins / 60);
                    const mm = mins % 60;
                    const ampm = hh >= 12 ? 'PM' : 'AM';
                    const h12 = hh % 12 || 12;
                    return `${h12}:${String(mm).padStart(2, '0')} ${ampm}`;
                };
                timesPerDay.push(`${fmt(m)} - ${fmt(m + presentationDuration)}`);
            }

            const targetCycle = cycles.find(c => c.id === configCycleId);
            const filteredTeams = targetCycle 
                ? allTeams.filter(t => t.semester_id === targetCycle.semester_id)
                : allTeams;

            // Determine which teams still need scheduling
            const incompleteScheduledTeams = new Set(
                schedule
                    .filter(s => targetCycle ? s.cycle_id === targetCycle.id : !slotIsCompleted(s))
                    .map(s => s.team)
            );
            const unscheduled = filteredTeams.filter(t => !incompleteScheduledTeams.has(t.id));

            // Build flat list of (date, time, room) slots available
            const availableSlots = [];
            for (const date of dates) {
                for (const time of timesPerDay) {
                    for (const room of activeRooms) {
                        availableSlots.push({ date, time, room: room.name, capacity: room.capacity ?? 20 });
                    }
                }
            }

            // Assign teams to slots
            const generatedSlots = unscheduled.slice(0, availableSlots.length).map((team, i) => {
                const slot = availableSlots[i];
                return normalizeSlot({
                    date: slot.date,
                    time: slot.time,
                    team: team.id,
                    panel: team.mentor || 'TBD',
                    room: slot.room,
                    capacity: slot.capacity,
                    meetLink: null,
                    cycle_id: configCycleId || null,
                });
            });

            if (!generatedSlots.length) {
                alert('All teams already have scheduled slots, or no teams found. Add teams first.');
                return;
            }

            // Persist to DB — use plain insert (no onConflict) since these are new rows
            const response = await apiUpsertTable('schedule_slots', generatedSlots);
            const savedRows = (response.data && response.data.length ? response.data : generatedSlots).map(r => normalizeSlot(r));

            setSchedule(prev => {
                const existingKeys = new Set(prev.map(s => `${s.team}-${s.date}-${s.time}`));
                const newRows = savedRows.filter(r => !existingKeys.has(`${r.team}-${r.date}-${r.time}`));
                return [...prev, ...newRows];
            });

            ensureSlotMeets(savedRows);

            try {
                await syncScheduleSlotsBulk(savedRows, panels, allTeams);
            } catch (syncErr) {
                console.warn('Auto-generation sync failed:', syncErr);
            }

            // Log schedule generation
            await AuditLogger.logScheduleAction(
                getCurrentUser(),
                `Schedule generation completed - ${generatedSlots.length} presentation slots created for ${unscheduled.length} teams`
            );
        } catch (err) {
            console.error('Generation failed:', err);
            alert('Failed to generate schedule: ' + err.message);
        } finally {
            setIsGenerating(false);
        }
    };


    const handleNotify = () => {
        setIsNotifying(true);
        setTimeout(() => {
            setIsNotifying(false);
            setNotified(true);
        }, 1200);
    };

    const handleSaveSlot = async (e) => {
        e.preventDefault();

        const isCreateMode = slotMode === 'create' || editingSlot?.id == null;

        // Guard: prevent duplicate slot for same team in same cycle
        const hasConflict = schedule.some(s => 
            String(s.id) !== String(editingSlot.id) && 
            s.team === editingSlot.team && 
            s.cycle_id === editingSlot.cycle_id
        );
        if (hasConflict) {
            alert(`Team "${editingSlot.team}" already has a scheduled slot for this presentation cycle.`);
            return;
        }
        const effectiveVenueMode = editingSlot.slotVenueMode ?? venueMode;

        // Extract extraMinutes and strip it from slotForDB to avoid DB schema mismatch
        const extraMinutes = parseInt(editingSlot.extraMinutes, 10) || 0;
        const { slotVenueMode: _stripped, id: _id, extraMinutes: _extra, ...slotForDB } = editingSlot;

        // Parse base slot time range
        const baseTime = slotForDB.time;
        const { start, end } = parseSlotTime(baseTime);
        const finalTime = extraMinutes > 0 ? `${minutesToTimeStr(start)} - ${minutesToTimeStr(end + extraMinutes)}` : baseTime;

        // Online slots get their real Meet link from the backend after save
        // (created on the assigned panel's calendar so the panel is host).
        const slotToSave = normalizeSlot(
            { ...slotForDB, time: finalTime },
            effectiveVenueMode === 'online' ? (slotForDB.meetLink ?? null) : null
        );

        setIsSavingSlot(true);

        try {
            let savedRow;
            let updatedSubsequentSlots = [];

            if (isCreateMode) {
                // INSERT — do not send id (GENERATED ALWAYS column)
                const response = await apiUpsertTable('schedule_slots', [slotToSave]);
                savedRow = normalizeSlot({
                    ...slotToSave,
                    ...(response.data && response.data[0] ? response.data[0] : {}),
                });
            } else {
                // UPDATE — use PATCH so we never send the id or DB-controlled columns back to Postgres
                const editableFields = {
                    date:     slotToSave.date,
                    time:     slotToSave.time,
                    team:     slotToSave.team,
                    panel:    slotToSave.panel,
                    room:     slotToSave.room,
                    capacity: slotToSave.capacity,
                    meetLink: slotToSave.meetLink ?? null,
                    cycle_id: slotToSave.cycle_id ?? null,
                };
                const response = await apiPatchRow('schedule_slots', editingSlot.id, editableFields);
                savedRow = normalizeSlot({
                    ...editingSlot,
                    ...editableFields,
                    ...(response.data && response.data[0] ? response.data[0] : {}),
                    id: editingSlot.id,
                });
            }

            // Auto-shift subsequent slots if extraMinutes is provided
            if (extraMinutes > 0) {
                const oldSlot = isCreateMode ? null : schedule.find(s => String(s.id) === String(editingSlot.id));
                const oldTime = oldSlot ? oldSlot.time : baseTime;
                const originalStart = parseSlotTime(oldTime).start;

                const isOnline = slotToSave.room === 'Online';
                const subsequentSlots = schedule.filter(s => 
                    s.date === slotToSave.date &&
                    String(s.id) !== String(editingSlot.id) &&
                    (s.panel === slotToSave.panel || (!isOnline && slotToSave.room && s.room === slotToSave.room)) &&
                    parseSlotTime(s.time).start >= originalStart
                );

                // Sort chronologically by start time
                subsequentSlots.sort((a, b) => parseSlotTime(a.time).start - parseSlotTime(b.time).start);

                // Sequentially shift start and end times by extraMinutes
                updatedSubsequentSlots = subsequentSlots.map(s => {
                    const newTimeRange = shiftSlotTime(s.time, extraMinutes);
                    return { ...s, time: newTimeRange };
                });

                // Persist shifted slots to DB
                for (const shiftedSlot of updatedSubsequentSlots) {
                    await apiPatchRow('schedule_slots', shiftedSlot.id, { time: shiftedSlot.time });
                }
            }

            // Update local React state with both the saved row and all shifted subsequent slots
            setSchedule(prev => {
                const replacedIds = new Set([editingSlot.id, ...updatedSubsequentSlots.map(s => s.id)].filter(Boolean).map(String));
                const filtered = prev.filter(s => !replacedIds.has(String(s.id)) && !slotMatches(s, { ...slotToSave, id: editingSlot.id }));
                return [...filtered, savedRow, ...updatedSubsequentSlots];
            });

            // Create / move / clear the real Meet on the panel's calendar.
            ensureSlotMeets([savedRow, ...updatedSubsequentSlots]);

            try {
                await syncScheduleSlotsBulk([savedRow, ...updatedSubsequentSlots], panels, allTeams);
            } catch (syncErr) {
                console.warn('Panel slot sync failed:', syncErr);
            }

            setEditingSlot(null);
            setSlotMode('edit');

            // Log slot creation/update
            await AuditLogger.logScheduleAction(
                getCurrentUser(),
                `Presentation slot ${isCreateMode ? 'created' : 'updated'} (added ${extraMinutes} extra mins) - Team: ${slotToSave.team}, Date: ${slotToSave.date}, Time: ${slotToSave.time}, Room: ${slotToSave.room}`
            );
        } catch (err) {
            alert('Failed to save slot: ' + (err.message || 'Unknown error. Check if the system is frozen.'));
        } finally {
            setIsSavingSlot(false);
        }
    };

    const handleDeleteSlot = async (slot) => {
        if (slot?.id == null) {
            alert('Cannot delete: slot has no database id.');
            return;
        }

        const confirmDelete = window.confirm(`Delete ${teamLabel(slot.team, getTeamRow(slot.team), semesterMap)} from the schedule?`);
        if (!confirmDelete) return;

        const slotId = slot.id;
        setDeletingSlotId(slotId);
        const previousSchedule = schedule;
        setSchedule(prev => prev.filter(item => String(item.id) !== String(slotId)));

        try {
            await apiDeleteRows('schedule_slots', { id: slotId });

            const panelRow = panels.find(p => p.name === slot.panel);
            const teamIdNum = teamNumericId(slot.team);
            if (panelRow?.id && teamIdNum) {
                try {
                    await deleteSlot(panelRow.id, teamIdNum);
                } catch (syncErr) {
                    console.warn('Panel slot cleanup failed:', syncErr);
                }
            }

            setEditingSlot(null);
            setSlotMode('edit');
            AuditLogger.logScheduleAction(
                getCurrentUser(),
                `Presentation slot deleted - Team: ${slot.team}, Date: ${slot.date}, Time: ${slot.time}, Room: ${slot.room}`
            );
        } catch (error) {
            alert('Failed to delete slot: ' + (error.message || 'Unknown error. Check if the system is frozen.'));
            setSchedule(previousSchedule);
        } finally {
            setDeletingSlotId(null);
        }
    };

    const slotIsCompleted = useCallback((slot) => {
        const tid = teamNumericId(slot.team);
        if (tid == null) return false;
        const key = `${tid}-${slot.cycle_id || 'null'}`;
        if (evaluatedKeys.has(key)) return true;

        // Check if there is an evaluation for this team in results table (legacy fallback)
        if (!slot.cycle_id) {
            const teamStr = slot.team; // e.g. "TEAM-3"
            const resultRow = results.find(r => r.team === teamStr || teamNumericId(r.team) === tid);
            if (resultRow && (resultRow.midMarks !== null || resultRow.proposalMarks !== null || resultRow.finalMarks !== null)) {
                return true;
            }
        }

        return false;
    }, [evaluatedKeys, results]);

    const [scrolledDown, setScrolledDown] = useState(false);

    useEffect(() => {
        const handleScroll = () => setScrolledDown(window.scrollY > 300);
        window.addEventListener('scroll', handleScroll, { passive: true });
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);

    const handleScrollToggle = () => {
        if (scrolledDown) {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)] overflow-y-auto max-w-full pb-12">

            {meetWarning && (
                <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300 text-sm font-medium">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span className="flex-1">{meetWarning}</span>
                    <button onClick={() => setMeetWarning(null)} className="text-amber-600 dark:text-amber-400 font-black">×</button>
                </div>
            )}

            {/* Action Header */}
            <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-4 border-b border-slate-200/50 dark:border-slate-700/50">
                <div>
                    <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Presentation Sync</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Orchestrate timelines, reserve venues, and coordinate evaluation panels programmatically.</p>
                </div>
                <div className="flex w-full sm:w-auto flex-wrap gap-2">
                    <button
                        onClick={handleGoogleConnect}
                        disabled={checkingGoogle}
                        className={`flex-1 sm:flex-none justify-center px-5 py-3 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm flex items-center gap-2 border ${
                            googleConnected
                                ? 'bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-500/10 dark:hover:bg-emerald-500/20 border-emerald-200 dark:border-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                                : 'bg-rose-50 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 border-rose-200 dark:border-rose-500/20 text-rose-700 dark:text-rose-300'
                        }`}
                    >
                        <Video className={`w-4 h-4 ${googleConnected ? 'text-emerald-500' : 'text-rose-500 animate-pulse'}`} />
                        {checkingGoogle ? 'Checking...' : (googleConnected ? 'Google Meet Active' : 'Connect Calendar')}
                    </button>
                    <button onClick={handleNotify} disabled={isNotifying || notified} className="flex-1 sm:flex-none justify-center px-5 py-3 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm flex items-center disabled:opacity-50 disabled:cursor-not-allowed">
                        {notified ? <CheckCircle className="w-4 h-4 mr-2 text-emerald-500" /> : <Bell className="w-4 h-4 mr-2 text-amber-500" />} 
                        {notified ? 'Notified All' : (isNotifying ? 'Sending...' : 'Notify Students')}
                    </button>
                    {/* Custom Slot split button */}
                    <div className="relative">
                        <button
                            onClick={() => setShowSlotMenu(v => !v)}
                            className="flex-1 sm:flex-none justify-center px-5 py-3 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4 text-indigo-500" /> Add Schedule
                            <svg className="w-3 h-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg>
                        </button>
                        <AnimatePresence>
                            {showSlotMenu && (
                                <motion.div
                                    initial={{ opacity: 0, y: -8, scale: 0.95 }}
                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                    exit={{ opacity: 0, y: -8, scale: 0.95 }}
                                    className="absolute right-0 top-full mt-2 w-64 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden z-50"
                                >
                                    <button
                                        onClick={() => { setShowSlotMenu(false); setShowBulkModal(true); }}
                                        className="w-full flex items-start gap-3 px-5 py-4 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition-colors text-left group"
                                    >
                                        <div className="p-2 bg-indigo-100 dark:bg-indigo-500/20 rounded-xl text-indigo-600 dark:text-indigo-400 shrink-0 group-hover:scale-110 transition-transform">
                                            <Wand2 className="w-4 h-4" />
                                        </div>
                                        <div>
                                            <div className="text-sm font-black text-slate-800 dark:text-white">Bulk Schedule</div>
                                            <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">Auto-assign 10–20 teams to slots</div>
                                        </div>
                                    </button>
                                    <div className="h-px bg-slate-100 dark:bg-slate-700" />
                                    <button
                                        onClick={() => { setShowSlotMenu(false); openCustomSlot(); }}
                                        className="w-full flex items-start gap-3 px-5 py-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors text-left group"
                                    >
                                        <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-xl text-slate-600 dark:text-slate-400 shrink-0 group-hover:scale-110 transition-transform">
                                            <Plus className="w-4 h-4" />
                                        </div>
                                        <div>
                                            <div className="text-sm font-black text-slate-800 dark:text-white">Custom Slot</div>
                                            <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">Schedule a specific team manually</div>
                                        </div>
                                    </button>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                    <button onClick={() => setShowConfig(true)} disabled={isGenerating} className="flex-1 sm:flex-none justify-center px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-lg shadow-indigo-500/30 flex items-center active:scale-95 disabled:scale-100">
                        {isGenerating ? (
                            <><svg className="animate-spin -ml-1 mr-3 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Compiling Matrix...</>
                        ) : (
                            <><Settings className="w-4 h-4 mr-2" /> Global Configurator</>
                        )}
                    </button>
                </div>
            </motion.div>

            {/* Bulk Action Toolbar */}
            <AnimatePresence>
                {selectedSlotIds.size > 0 && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 20 }}
                        className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 px-5 py-3.5 bg-slate-900 dark:bg-slate-950 rounded-2xl shadow-2xl border border-slate-700 text-white"
                    >
                        <span className="text-xs font-black uppercase tracking-widest text-slate-300 pr-2 border-r border-slate-700">
                            {selectedSlotIds.size} Selected
                        </span>
                        <button
                            onClick={() => { setBulkEditFields({ time: '', panel: '', room: '', venueMode: '' }); setShowBulkEditModal(true); }}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-xs font-black uppercase tracking-widest transition-colors"
                        >
                            <Edit className="w-3.5 h-3.5" /> Edit Selected
                        </button>
                        <button
                            onClick={handleBulkDelete}
                            disabled={isBulkDeleting}
                            className="flex items-center gap-2 px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:bg-rose-800 rounded-xl text-xs font-black uppercase tracking-widest transition-colors"
                        >
                            <Trash2 className="w-3.5 h-3.5" /> {isBulkDeleting ? 'Deleting...' : 'Delete Selected'}
                        </button>
                        <button
                            onClick={() => setSelectedSlotIds(new Set())}
                            className="p-2 hover:bg-slate-700 rounded-xl transition-colors text-slate-400 hover:text-white"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Calendar Layout */}
            <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6 xl:p-8">
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-8 pb-4 border-b border-slate-100 dark:border-slate-700/50">
                    <div className="flex items-center space-x-3 text-slate-800 dark:text-white">
                        <div className="p-2.5 bg-indigo-50 dark:bg-indigo-500/10 rounded-xl text-indigo-500"><CalendarIcon className="w-5 h-5" /></div>
                        <div>
                            <h2 className="text-xl font-black">Timeline Matrix</h2>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{filteredSchedule.length} of {schedule.length} slots shown</p>
                        </div>
                    </div>
                    
                    <div className="flex items-center gap-2 flex-wrap">
                        {/* Select all toggle */}
                        <button
                            onClick={toggleSelectAll}
                            title={isAllFilteredSelected ? 'Deselect all' : 'Select all visible'}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-black text-slate-600 dark:text-slate-300 hover:border-indigo-400 hover:text-indigo-600 transition-all shadow-sm"
                        >
                            {isAllFilteredSelected ? (
                                <CheckSquare className="w-4 h-4 text-indigo-500" />
                            ) : isSomeFilteredSelected ? (
                                <MinusSquare className="w-4 h-4 text-indigo-400" />
                            ) : (
                                <Square className="w-4 h-4 text-slate-400" />
                            )}
                            Select
                        </button>
                        <div className="relative group max-w-xs">
                            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                            <input
                                type="text"
                                placeholder="Search team or panel..."
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                className="pl-8 pr-4 py-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow w-44 focus:w-56"
                            />
                        </div>
                        <span className="text-slate-500 dark:text-slate-400 font-bold text-sm flex items-center">
                            <Filter className="w-4 h-4 mr-1" />
                            {activeFilterCount > 0 && <span className="w-5 h-5 bg-indigo-500 text-white text-[10px] font-black rounded-full flex items-center justify-center ml-1">{activeFilterCount}</span>}
                        </span>
                        <select value={dateFilter} onChange={e => setDateFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Dates</option>
                            {uniqueDates.map(d => <option key={d} value={d}>{new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</option>)}
                        </select>
                        <select value={panelFilter} onChange={e => setPanelFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Panels</option>
                            {uniquePanels.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                        <select value={roomFilter} onChange={e => setRoomFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Rooms</option>
                            {uniqueRooms.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                        {(activeFilterCount > 0 || searchTerm) && (
                            <button onClick={() => { setSearchTerm(''); setDateFilter(''); setPanelFilter(''); setRoomFilter(''); }} className="text-[10px] font-black text-red-500 hover:text-red-600 uppercase tracking-widest px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
                                Clear
                            </button>
                        )}
                    </div>
                </div>

                <motion.div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
                    initial="hidden" animate="visible" variants={{
                        hidden: {}, visible: { transition: { staggerChildren: 0.1 } }
                    }}>
                    <AnimatePresence>
                        {filteredSchedule.map(slot => {
                            const isSelected = selectedSlotIds.has(String(slot.id));
                            return (
                            <motion.div key={slot.id} 
                                variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
                                exit={{ opacity: 0, scale: 0.9 }}
                                className={`bg-slate-50/80 dark:bg-slate-900/50 rounded-2xl p-6 border transition-all group relative hover:shadow-lg hover:shadow-indigo-500/5 ${
                                    isSelected
                                        ? 'border-indigo-400 dark:border-indigo-500 ring-2 ring-indigo-400/30 dark:ring-indigo-500/30'
                                        : 'border-slate-200/60 dark:border-slate-700/60 hover:border-indigo-300 dark:hover:border-indigo-500/50'
                                }`}>

                                {/* Checkbox */}
                                <button
                                    onClick={(e) => { e.stopPropagation(); toggleSelectSlot(slot.id); }}
                                    className={`absolute top-4 left-4 z-20 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
                                        isSelected
                                            ? 'bg-indigo-500 border-indigo-500 text-white'
                                            : 'border-slate-300 dark:border-slate-500 bg-white dark:bg-slate-700 text-transparent hover:border-indigo-400 dark:hover:border-indigo-400'
                                    }`}
                                    title={isSelected ? 'Deselect' : 'Select'}
                                >
                                    {isSelected && <CheckSquare className="w-3.5 h-3.5" />}
                                </button>
                                
                                <button onClick={() => { setSlotMode('edit'); setEditingSlot(slot); }} className="absolute top-4 right-4 p-2 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 bg-white dark:bg-slate-800 rounded-xl opacity-0 group-hover:opacity-100 transition-all shadow-sm border border-slate-100 dark:border-slate-700 hover:scale-110 active:scale-95 z-20">
                                    <Edit className="w-4 h-4" />
                                </button>
                                {!slotIsCompleted(slot) && (
                                <button onClick={(e) => { e.stopPropagation(); handleDeleteSlot(slot); }} disabled={String(deletingSlotId) === String(slot.id)} className="absolute top-4 right-14 p-2 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 bg-white dark:bg-slate-800 rounded-xl opacity-0 group-hover:opacity-100 transition-all shadow-sm border border-slate-100 dark:border-slate-700 hover:scale-110 active:scale-95 z-20 disabled:opacity-50 disabled:cursor-not-allowed">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                                )}
                                
                                <div className="mb-6 pb-5 border-b border-slate-200/60 dark:border-slate-700/60 relative z-10">
                                    {(() => {
                                        const slotCycle = cycles.find(c => c.id === slot.cycle_id);
                                        return (
                                            <div className="flex flex-wrap items-center gap-2 mb-3">
                                                <span className="inline-flex items-center justify-center bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg shadow-inner">
                                                    <CalendarIcon className="w-3 h-3 mr-1.5" /> {new Date(slot.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
                                                </span>
                                                {slotCycle && (
                                                    <span className="inline-flex items-center justify-center bg-violet-100 text-violet-700 dark:bg-violet-500/20 dark:text-violet-400 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg shadow-inner">
                                                        {slotCycle.title}
                                                    </span>
                                                )}
                                            </div>
                                        );
                                    })()}
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="text-2xl font-black text-slate-800 dark:text-slate-100 leading-none whitespace-nowrap">{teamLabel(slot.team, getTeamRow(slot.team), semesterMap)}</h3>
                                        {slotIsCompleted(slot) && (
                                            <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-100 dark:border-emerald-500/20">Completed</span>
                                        )}
                                        {absentStudents.some(abs => abs.team === slot.team && abs.status === 'Rescheduled') && (
                                            <span className="text-[10px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2.5 py-0.5 rounded border border-indigo-100 dark:border-indigo-500/20">Rescheduled</span>
                                        )}
                                    </div>
                                </div>
                                
                                <div className="space-y-4 relative z-10">
                                    <div className="flex items-start text-sm text-slate-600 dark:text-slate-400 group/item">
                                        <div className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 mr-3 shadow-sm group-hover/item:text-indigo-500 transition-colors shrink-0"><Clock className="w-4 h-4" /></div>
                                        <div className="pt-1 font-bold">{slot.time}</div>
                                    </div>
                                    <div className="flex items-start text-sm text-slate-600 dark:text-slate-400 group/item">
                                        <div className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 mr-3 shadow-sm group-hover/item:text-emerald-500 transition-colors shrink-0"><Users className="w-4 h-4" /></div>
                                        <div className="pt-1 font-medium">{slot.panel}</div>
                                    </div>
                                    <div className="flex items-start text-sm text-slate-600 dark:text-slate-400 group/item">
                                        <div className="p-1.5 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 mr-3 shadow-sm group-hover/item:text-rose-500 transition-colors shrink-0"><MapPin className="w-4 h-4" /></div>
                                        <div className="pt-1 font-medium flex-1">{slot.room} <span className="text-[10px] bg-slate-100 dark:bg-slate-700 px-1.5 rounded ml-2">Cap: {slot.capacity || 20}</span></div>
                                    </div>

                                    <div className="pt-4 mt-4 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between">
                                        {slotIsCompleted(slot) ? (
                                            <div className="flex items-center justify-between w-full">
                                                <span className="flex items-center text-xs font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                                                    <CheckCircle className="w-4 h-4 mr-1.5" /> Evaluation Completed
                                                </span>
                                                <span className="text-[10px] bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 px-2 py-0.5 rounded font-black border border-emerald-100 dark:border-emerald-500/20">Completed</span>
                                            </div>
                                        ) : slot.meetLink ? (
                                            <div className="flex items-center justify-between w-full">
                                                <a href={slot.meetLink.includes('jit.si') ? `https://meet.google.com/${slot.meetLink.split('/').pop().replace('procksi-evaluation-', '')}` : slot.meetLink} target="_blank" rel="noreferrer" className="flex items-center text-xs font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 transition-colors">
                                                    <Video className="w-4 h-4 mr-1.5" /> Join Meet
                                                </a>
                                                <span className="text-[10px] bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400 px-2 py-0.5 rounded font-black border border-emerald-100 dark:border-emerald-500/20">Generated</span>
                                            </div>
                                        ) : (
                                            <button onClick={() => handleGenerateMeetLink(slot)} disabled={isGenerating} className="w-full flex items-center justify-center px-4 py-2 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-xl text-xs font-black uppercase tracking-widest transition-colors border border-indigo-100 dark:border-indigo-500/20 active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed">
                                                <Video className={`w-3.5 h-3.5 mr-1.5 ${isGenerating ? 'animate-spin' : ''}`} /> {isGenerating ? 'Generating...' : (slot.meetLink ? 'Upgrade to Google Meet' : 'Generate Meet Link')}
                                            </button>
                                        )}
                                    </div>
                                </div>

                                <div className="absolute -bottom-6 -right-6 opacity-[0.03] dark:opacity-10 pointer-events-none group-hover:scale-110 transition-transform duration-700">
                                    <CalendarIcon className="w-48 h-48" />
                                </div>
                            </motion.div>
                            );
                        })}
                    </AnimatePresence>
                </motion.div>
            </div>

            {/* Editing Slot Modal */}
            <AnimatePresence>
                {editingSlot && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 top-16 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col max-h-[80vh]">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/50">
                                <h3 className="text-xl font-black text-slate-800 dark:text-white">{slotMode === 'create' ? 'Create Custom Slot' : 'Configure Slot'}</h3>
                                <p className="text-xs font-black uppercase tracking-widest text-indigo-500 mt-2">{teamLabel(editingSlot.team, getTeamRow(editingSlot.team), semesterMap)}</p>
                            </div>
                            <form onSubmit={handleSaveSlot} className="flex flex-col flex-1 min-h-0">
                                <div className="p-6 space-y-5 overflow-y-auto flex-1">

                                    {/* Team */}
                                    {slotMode === 'create' && (
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Team</label>
                                            <div className="relative">
                                                <Users className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                                <select value={editingSlot.team} onChange={e => setEditingSlot({...editingSlot, team: e.target.value})} required className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                    <option value="">-- Select Team --</option>
                                                    {[...allTeams].sort(sortByTeamNumber)
                                                        .map(t => <option key={t.id} value={t.id}>{teamLabel(t.id, t, semesterMap)}{t.title ? ` – ${t.title}` : ''}</option>)
                                                    }
                                                </select>
                                                <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Presentation Cycle */}
                                    {editingSlot.team && (() => {
                                        const selectedTeamObj = allTeams.find(t => t.id === editingSlot.team);
                                        const teamSemesterId = selectedTeamObj?.semester_id;
                                        const filteredCycles = cycles.filter(c => c.semester_id === teamSemesterId);
                                        return (
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Presentation Cycle</label>
                                                <div className="relative">
                                                    <CalendarIcon className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                                    <select
                                                        value={editingSlot.cycle_id || ''}
                                                        onChange={e => setEditingSlot({...editingSlot, cycle_id: e.target.value || null})}
                                                        required={filteredCycles.length > 0}
                                                        className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer"
                                                    >
                                                        <option value="">{filteredCycles.length > 0 ? '-- Select Cycle --' : 'Legacy (No cycle)'}</option>
                                                        {filteredCycles.map(c => (
                                                            <option key={c.id} value={c.id}>
                                                                {c.title} ({c.type}) {c.status === 'active' ? '[Active]' : ''}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                                </div>
                                            </div>
                                        );
                                    })()}

                                    {/* Calendar Date */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Calendar Date</label>
                                        <input type="date" value={editingSlot.date} onChange={e => setEditingSlot({...editingSlot, date: e.target.value})} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" required />
                                    </div>

                                    {/* Time Window */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Time Window</label>
                                        <div className="relative">
                                            <Clock className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                            <select value={editingSlot.time} onChange={e => setEditingSlot({...editingSlot, time: e.target.value})} required className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                <option value="">-- Select Time Slot --</option>
                                                {buildTimeOptions().map(t => <option key={t} value={t}>{t}</option>)}
                                                {editingSlot.time && !buildTimeOptions().includes(editingSlot.time) && <option value={editingSlot.time}>{editingSlot.time}</option>}
                                            </select>
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                        </div>
                                    </div>

                                    {/* Extra Minutes to Add */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Extra Minutes to Add</label>
                                        <input
                                            type="number"
                                            min="0"
                                            value={editingSlot.extraMinutes || 0}
                                            onChange={e => setEditingSlot({...editingSlot, extraMinutes: parseInt(e.target.value, 10) || 0})}
                                            className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner"
                                            placeholder="0"
                                        />
                                        <p className="text-[10px] text-slate-400 dark:text-slate-500 font-bold mt-1.5 leading-normal">
                                            If extra minutes are added, this slot's duration will extend and all subsequent slots on the same date for this room/panel will shift forward.
                                        </p>
                                    </div>

                                    {/* Panel Allocation */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Panel Allocation</label>
                                        <div className="relative">
                                            <Users className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                            <select value={editingSlot.panel} onChange={e => setEditingSlot({...editingSlot, panel: e.target.value})} required className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                <option value="">-- Select Panel / Mentor --</option>
                                                {panelOptions.map(p => <option key={p.id} value={p.name}>{p.label}</option>)}
                                                {editingSlot.panel && !panelOptions.find(p => p.name === editingSlot.panel) && <option value={editingSlot.panel}>{editingSlot.panel}</option>}
                                            </select>
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                        </div>
                                    </div>

                                    {/* Venue Mode Toggle */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Presentation Mode</label>
                                        <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-xl shadow-inner">
                                            <button type="button" onClick={() => setEditingSlot({...editingSlot, slotVenueMode: 'offline', meetLink: null})} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${(editingSlot.slotVenueMode ?? venueMode) === 'offline' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                                <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                            </button>
                                            <button type="button" onClick={() => setEditingSlot({...editingSlot, slotVenueMode: 'online', room: ''})} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${(editingSlot.slotVenueMode ?? venueMode) === 'online' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                                <Video className="w-4 h-4 mr-2" /> Online
                                            </button>
                                        </div>
                                    </div>

                                    {/* Offline: Room dropdown | Online: Meet link */}
                                    {(editingSlot.slotVenueMode ?? venueMode) === 'offline' ? (
                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Venue / Room</label>
                                                <div className="relative">
                                                    <MapPin className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                                    <select value={editingSlot.room} onChange={e => {
                                                        const chosen = rooms.find(r => r.name === e.target.value);
                                                        setEditingSlot({...editingSlot, room: e.target.value, capacity: chosen?.capacity ?? editingSlot.capacity});
                                                    }} required className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                        <option value="">-- Select Room --</option>
                                                        {rooms.map(r => <option key={r.id} value={r.name}>{r.name} (Cap: {r.capacity})</option>)}
                                                        {editingSlot.room && !rooms.find(r => r.name === editingSlot.room) && <option value={editingSlot.room}>{editingSlot.room}</option>}
                                                    </select>
                                                    <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                                </div>
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Room Capacity</label>
                                                <input type="number" value={editingSlot.capacity || 20} onChange={e => setEditingSlot({...editingSlot, capacity: parseInt(e.target.value)})} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" required />
                                            </div>
                                        </div>
                                    ) : (
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Online Meeting Link</label>
                                            <div className="flex gap-2">
                                                <input
                                                    type="url"
                                                    placeholder="https://meet.google.com/xxx-yyyy-zzz or Jitsi Link"
                                                    value={editingSlot.meetLink || ''}
                                                    onChange={e => setEditingSlot({...editingSlot, meetLink: e.target.value})}
                                                    className="flex-1 px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={handleGenerateMeetLinkForSlot}
                                                    disabled={isGeneratingMeetLink || !editingSlot?.time || !editingSlot?.team}
                                                    className="px-4 py-3 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-xl text-xs font-black uppercase tracking-widest transition-all border border-indigo-100 dark:border-indigo-500/20 active:scale-95 disabled:opacity-60 flex items-center justify-center shrink-0"
                                                >
                                                    {isGeneratingMeetLink ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Generate'}
                                                </button>
                                            </div>
                                            <p className="text-[10px] text-slate-400 dark:text-slate-500 font-bold mt-1.5 leading-normal">
                                                Online slots get a real Google Meet automatically when scheduled (needs the
                                                Google Calendar connected via the button above). The panel and team are added as
                                                invitees, so everyone joins without waiting for a host. 'Generate' / manual paste is a fallback.
                                            </p>
                                        </div>
                                    )}
                                </div>
                                <div className="p-5 bg-slate-50/50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex justify-end space-x-3">
                                    {slotMode === 'edit' && editingSlot?.id != null && !slotIsCompleted(editingSlot) && (
                                        <button type="button" onClick={() => handleDeleteSlot(editingSlot)} disabled={String(deletingSlotId) === String(editingSlot.id)} className="mr-auto px-5 py-2.5 text-xs font-black uppercase tracking-widest text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 rounded-xl transition-colors border border-rose-100 dark:border-rose-500/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center">
                                            <Trash2 className="w-4 h-4 mr-2" /> {String(deletingSlotId) === String(editingSlot.id) ? 'Deleting...' : 'Delete Slot'}
                                        </button>
                                    )}
                                    <button type="button" onClick={() => { setEditingSlot(null); setSlotMode('edit'); }} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" disabled={isSavingSlot} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-xl transition-colors shadow-lg shadow-indigo-500/30">{isSavingSlot ? 'Saving...' : (slotMode === 'create' ? 'Create Slot' : 'Commit Changes')}</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Global Matrix Configurator Modal */}
            <AnimatePresence>
                {showConfig && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 top-16 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-2xl border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col max-h-[80vh]">
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center shrink-0">
                                <div className="flex items-center text-white">
                                    <Settings className="w-6 h-6 mr-3" />
                                    <h3 className="font-black text-xl">Global Matrix Configurator</h3>
                                </div>
                                <button onClick={() => setShowConfig(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-5 h-5"/></button>
                            </div>
                            
                            <div className="p-6 flex-1 overflow-y-auto space-y-8 bg-slate-50/50 dark:bg-slate-900/50">
                                
                                {/* Target Presentation Cycle */}
                                <div>
                                    <h4 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest mb-4 flex items-center">
                                        <CalendarIcon className="w-4 h-4 mr-2 text-indigo-500" /> Target Presentation Cycle
                                    </h4>
                                    <div className="relative">
                                        <CalendarIcon className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <select 
                                            value={configCycleId} 
                                            onChange={e => setConfigCycleId(e.target.value)} 
                                            className="w-full pl-10 pr-10 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-sm cursor-pointer"
                                        >
                                            <option value="">-- Legacy Mode (No Cycle) --</option>
                                            {cycles.map(c => {
                                                const semObj = semesterMap[c.semester_id];
                                                const semesterName = semObj 
                                                    ? [
                                                        semObj.year,
                                                        semObj.semester_type ? `${String(semObj.semester_type).charAt(0).toUpperCase()}${String(semObj.semester_type).slice(1)}` : '',
                                                        semObj.branch,
                                                        semObj.academic_level ? `Yr ${semObj.academic_level}` : '',
                                                        semObj.is_active ? 'Active' : ''
                                                      ].filter(Boolean).join(' / ')
                                                    : (c.semester_id || 'Legacy');
                                                return (
                                                    <option key={c.id} value={c.id}>
                                                        {c.title} ({semesterName})
                                                    </option>
                                                );
                                            })}
                                        </select>
                                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                    </div>
                                </div>

                                {/* Bounds Config */}
                                <div>
                                    <h4 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest mb-4 flex items-center">
                                        <Clock className="w-4 h-4 mr-2 text-indigo-500" /> Presentation Cycle & Duration
                                    </h4>
                                    <div className="grid grid-cols-2 gap-4 mb-4">
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Cycle Start Date</label>
                                            <input type="date" value={configDates.start} onChange={e => setConfigDates({...configDates, start: e.target.value})} className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-sm" required />
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Cycle End Date</label>
                                            <input type="date" value={configDates.end} onChange={e => setConfigDates({...configDates, end: e.target.value})} className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-sm" required />
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-3 gap-4">
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Daily Start Time</label>
                                            <input type="time" value={configTimes.start} onChange={e => setConfigTimes({...configTimes, start: e.target.value})} className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-sm" required />
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Daily End Time</label>
                                            <input type="time" value={configTimes.end} onChange={e => setConfigTimes({...configTimes, end: e.target.value})} className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-sm" required />
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Slot Duration (Mins)</label>
                                            <input type="number" min="10" max="180" step="5" value={presentationDuration} onChange={e => setPresentationDuration(parseInt(e.target.value))} className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-sm" required />
                                        </div>
                                    </div>
                                </div>

                                {/* Venue Mode Config */}
                                <div>
                                    <h4 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest mb-4 flex items-center">
                                        <MapPin className="w-4 h-4 mr-2 text-indigo-500" /> Presentation Venue Mode
                                    </h4>
                                    <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded-xl shadow-inner">
                                        <button 
                                            onClick={() => setVenueMode('offline')}
                                            className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${venueMode === 'offline' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-200/50 dark:hover:bg-slate-700/50'}`}>
                                            <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                        </button>
                                        <button 
                                            onClick={() => setVenueMode('online')}
                                            className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${venueMode === 'online' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:bg-slate-200/50 dark:hover:bg-slate-700/50'}`}>
                                            <Video className="w-4 h-4 mr-2" /> Online
                                        </button>
                                    </div>
                                </div>

                                {/* Rooms Config */}
                                {venueMode === 'offline' ? (
                                    <div>
                                        <div className="flex justify-between items-end mb-4">
                                            <h4 className="text-sm font-black text-slate-800 dark:text-white uppercase tracking-widest flex items-center">
                                                <DoorOpen className="w-4 h-4 mr-2 text-indigo-500" /> Available Venue Pool
                                            </h4>
                                            <button onClick={() => setRooms([...rooms, { id: Date.now(), name: 'New Room', capacity: 20 }])} className="text-[10px] font-black uppercase tracking-widest text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 flex items-center transition-colors bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1.5 rounded-lg border border-indigo-100 dark:border-indigo-500/20">
                                                <Plus className="w-3 h-3 mr-1" /> Add Venue
                                            </button>
                                        </div>
                                        <div className="space-y-3">
                                            {rooms.map(room => (
                                                <div key={room.id} className="flex items-center gap-3 p-3 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm group">
                                                    <input type="text" value={room.name} onChange={e => setRooms(rooms.map(r => r.id === room.id ? {...r, name: e.target.value} : r))} className="flex-1 px-3 py-2 bg-transparent text-sm font-bold text-slate-800 dark:text-white outline-none focus:ring-1 focus:ring-indigo-500 rounded-md" />
                                                    <div className="flex items-center space-x-2">
                                                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Cap</span>
                                                        <input type="number" value={room.capacity} onChange={e => setRooms(rooms.map(r => r.id === room.id ? {...r, capacity: parseInt(e.target.value) || 0} : r))} className="w-16 px-2 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-md text-sm font-bold text-center text-slate-800 dark:text-white outline-none focus:ring-1 focus:ring-indigo-500" />
                                                    </div>
                                                    <button onClick={() => setRooms(rooms.filter(r => r.id !== room.id))} className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/20 rounded-lg transition-colors opacity-60 group-hover:opacity-100"><Trash2 className="w-4 h-4" /></button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="p-6 bg-indigo-50/50 dark:bg-indigo-500/5 rounded-2xl border border-indigo-100 dark:border-indigo-500/20 flex flex-col items-center justify-center text-center space-y-3">
                                        <div className="w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-500/20 text-indigo-500 flex items-center justify-center shadow-inner">
                                            <Globe className="w-6 h-6" />
                                        </div>
                                        <div>
                                            <h5 className="text-sm font-black text-slate-800 dark:text-white">Online Presentations Enabled</h5>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm">No venue allocation needed. A real Google Meet is created for each slot automatically and shared with the panel and team.</p>
                                        </div>
                                    </div>
                                )}
                                
                                <div className="p-4 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-xl">
                                    <p className="text-xs font-bold text-indigo-700 dark:text-indigo-300 leading-relaxed">
                                        Executing the matrix generation will parse the selected dates and distribute teams optimally across the defined venue pool, taking mentor constraints into account automatically.
                                    </p>
                                </div>

                            </div>
                            
                            <div className="p-5 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 flex justify-end space-x-3 shrink-0">
                                <button onClick={() => setShowConfig(false)} className="px-6 py-3 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Abort</button>
                                <button onClick={handleGenerate} className="px-6 py-3 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 flex items-center">
                                    <Wand2 className="w-4 h-4 mr-2" /> Auto-Generate Matrix
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Bulk Edit Modal */}
            <AnimatePresence>
                {showBulkEditModal && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4" onClick={() => setShowBulkEditModal(false)}>
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} onClick={e => e.stopPropagation()} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center">
                                <div className="flex items-center text-white gap-3">
                                    <div className="p-2 bg-white/10 rounded-xl"><Edit className="w-5 h-5" /></div>
                                    <div>
                                        <h3 className="font-black text-xl">Bulk Edit Slots</h3>
                                        <p className="text-indigo-200 text-xs mt-0.5">Updating {selectedSlotIds.size} selected slot(s)</p>
                                    </div>
                                </div>
                                <button onClick={() => setShowBulkEditModal(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-5 h-5"/></button>
                            </div>
                            <div className="p-6 space-y-5">
                                <p className="text-xs text-slate-500 dark:text-slate-400 font-medium bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl px-4 py-3">
                                    Only filled fields will be applied. Leave blank to keep existing values. Completed slots are skipped.
                                </p>

                                {/* Time */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Time Window</label>
                                    <div className="relative">
                                        <Clock className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <select value={bulkEditFields.time} onChange={e => setBulkEditFields(f => ({...f, time: e.target.value}))} className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                            <option value="">-- Keep existing time --</option>
                                            {buildTimeOptions().map(t => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                    </div>
                                </div>

                                {/* Panel */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Panel / Evaluator</label>
                                    <div className="relative">
                                        <Users className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <select value={bulkEditFields.panel} onChange={e => setBulkEditFields(f => ({...f, panel: e.target.value}))} className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                            <option value="">-- Keep existing panel --</option>
                                            {panelOptions.map(p => <option key={p.id} value={p.name}>{p.label}</option>)}
                                        </select>
                                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                    </div>
                                </div>

                                {/* Venue Mode */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Venue Mode</label>
                                    <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-xl shadow-inner">
                                        <button type="button" onClick={() => setBulkEditFields(f => ({...f, venueMode: '', room: ''}))} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${bulkEditFields.venueMode === '' ? 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            No change
                                        </button>
                                        <button type="button" onClick={() => setBulkEditFields(f => ({...f, venueMode: 'offline'}))} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${bulkEditFields.venueMode === 'offline' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                        </button>
                                        <button type="button" onClick={() => setBulkEditFields(f => ({...f, venueMode: 'online', room: ''}))} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${bulkEditFields.venueMode === 'online' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <Video className="w-4 h-4 mr-2" /> Online
                                        </button>
                                    </div>
                                </div>

                                {/* Room (offline only) */}
                                {bulkEditFields.venueMode === 'offline' && (
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Venue / Room</label>
                                        <div className="relative">
                                            <MapPin className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                            <select value={bulkEditFields.room} onChange={e => setBulkEditFields(f => ({...f, room: e.target.value}))} className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                <option value="">-- Keep existing room --</option>
                                                {rooms.map(r => <option key={r.id} value={r.name}>{r.name} (Cap: {r.capacity})</option>)}
                                            </select>
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                        </div>
                                    </div>
                                )}
                            </div>
                            <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end gap-3">
                                <button onClick={() => setShowBulkEditModal(false)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                <button onClick={handleBulkEdit} disabled={isBulkSaving} className="flex items-center px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 gap-2">
                                    {isBulkSaving ? <><Loader2 className="w-4 h-4 animate-spin" />Applying...</> : <><CheckCircle className="w-4 h-4" />Apply to {selectedSlotIds.size} Slots</>}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Bulk Schedule Modal */}
            <AnimatePresence>
                {showBulkModal && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 top-16 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4" onClick={() => setShowBulkModal(false)}>
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} onClick={e => e.stopPropagation()} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-lg border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col max-h-[80vh]">
                            
                            {/* Header */}
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center">
                                <div className="flex items-center text-white gap-3">
                                    <div className="p-2 bg-white/10 rounded-xl"><Wand2 className="w-5 h-5" /></div>
                                    <div>
                                        <h3 className="font-black text-xl">Bulk Schedule</h3>
                                        <p className="text-indigo-200 text-xs mt-0.5">Auto-assign multiple teams at once</p>
                                    </div>
                                </div>
                                <button onClick={() => setShowBulkModal(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-5 h-5"/></button>
                            </div>

                            <div className="p-6 space-y-5 overflow-y-auto flex-1">

                                {/* Target Presentation Cycle */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Target Presentation Cycle</label>
                                    <div className="relative">
                                        <CalendarIcon className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <select 
                                            value={bulkConfig.cycle_id || ''} 
                                            onChange={e => setBulkConfig(c => ({...c, cycle_id: e.target.value || ''}))} 
                                            className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer"
                                        >
                                            <option value="">-- Legacy Mode (No Cycle) --</option>
                                            {cycles.map(c => {
                                                const semObj = semesterMap[c.semester_id];
                                                const semesterName = semObj 
                                                    ? [
                                                        semObj.year,
                                                        semObj.semester_type ? `${String(semObj.semester_type).charAt(0).toUpperCase()}${String(semObj.semester_type).slice(1)}` : '',
                                                        semObj.branch,
                                                        semObj.academic_level ? `Yr ${semObj.academic_level}` : '',
                                                        semObj.is_active ? 'Active' : ''
                                                      ].filter(Boolean).join(' / ')
                                                    : (c.semester_id || 'Legacy');
                                                return (
                                                    <option key={c.id} value={c.id}>
                                                        {c.title} ({semesterName})
                                                    </option>
                                                );
                                            })}
                                        </select>
                                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                    </div>
                                </div>

                                {/* Team Count */}
                                <div>
                                    <div className="flex justify-between items-center mb-2">
                                        <label className="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Number of Teams to Schedule</label>
                                        <span className="text-lg font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-100 dark:border-indigo-500/20">{bulkConfig.count}</span>
                                    </div>
                                    <input type="range" min="1" max="20" value={bulkConfig.count} onChange={e => setBulkConfig(c => ({...c, count: parseInt(e.target.value)}))} className="w-full accent-indigo-600 h-2 rounded-full cursor-pointer" />
                                    <div className="flex justify-between text-[10px] font-bold text-slate-400 mt-1"><span>1</span><span>10</span><span>20</span></div>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                                        <span className="font-bold text-slate-700 dark:text-slate-300">{allTeams.filter(t => !schedule.find(s => s.team === t.id)).length}</span> unscheduled teams available
                                    </p>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    {/* Start Date */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Start Date</label>
                                        <input type="date" value={bulkConfig.startDate} onChange={e => setBulkConfig(c => ({...c, startDate: e.target.value}))} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" required />
                                    </div>
                                    {/* Start Time */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Start Time Slot</label>
                                        <div className="relative">
                                            <Clock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                            <select value={bulkConfig.startTime} onChange={e => setBulkConfig(c => ({...c, startTime: e.target.value}))} className="w-full pl-9 pr-8 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                <option value="">-- First slot --</option>
                                                {buildTimeOptions().map(t => <option key={t} value={t}>{t}</option>)}
                                            </select>
                                            <div className="absolute inset-y-0 right-2 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                        </div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    {/* Break Between Presentations */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Break Between Slots (mins)</label>
                                        <input type="number" min="0" value={bulkConfig.breakDuration || 0} onChange={e => setBulkConfig(c => ({...c, breakDuration: parseInt(e.target.value, 10) || 0}))} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" placeholder="0" />
                                    </div>
                                    {/* Lunch Break Duration */}
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Lunch Break (mins)</label>
                                        <input type="number" min="0" value={bulkConfig.lunchDuration || 0} onChange={e => setBulkConfig(c => ({...c, lunchDuration: parseInt(e.target.value, 10) || 0}))} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" placeholder="0" />
                                    </div>
                                </div>

                                {bulkConfig.lunchDuration > 0 && (
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Lunch Start Time</label>
                                        <input type="time" value={bulkConfig.lunchStartTime || ""} onChange={e => setBulkConfig(c => ({...c, lunchStartTime: e.target.value}))} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none shadow-inner" required={bulkConfig.lunchDuration > 0} />
                                    </div>
                                )}

                                {/* Panel */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Panel / Mentor</label>
                                    <div className="relative">
                                        <Users className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <select value={bulkConfig.panel} onChange={e => setBulkConfig(c => ({...c, panel: e.target.value}))} className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                            <option value="">-- Select Panel --</option>
                                            {panelOptions.map(p => <option key={p.id} value={p.name}>{p.label}</option>)}
                                        </select>
                                        <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                    </div>
                                </div>

                                {/* Venue Mode */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Venue Mode</label>
                                    <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-xl shadow-inner">
                                        <button type="button" onClick={() => setBulkConfig(c => ({...c, venueMode: 'offline'}))} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${bulkConfig.venueMode === 'offline' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                        </button>
                                        <button type="button" onClick={() => setBulkConfig(c => ({...c, venueMode: 'online', room: ''}))} className={`flex-1 py-2.5 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${bulkConfig.venueMode === 'online' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <Video className="w-4 h-4 mr-2" /> Online
                                        </button>
                                    </div>
                                </div>

                                {/* Room (offline only) */}
                                {bulkConfig.venueMode === 'offline' && (
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Venue / Room</label>
                                        <div className="relative">
                                            <MapPin className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                            <select value={bulkConfig.room} onChange={e => setBulkConfig(c => ({...c, room: e.target.value}))} className="w-full pl-10 pr-10 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none appearance-none shadow-inner cursor-pointer">
                                                <option value="">-- Select Room --</option>
                                                {rooms.map(r => <option key={r.id} value={r.name}>{r.name} (Cap: {r.capacity})</option>)}
                                            </select>
                                            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400"><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/></svg></div>
                                        </div>
                                    </div>
                                )}

                                {bulkConfig.venueMode === 'online' && (
                                    <div className="p-4 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 rounded-xl flex items-center gap-3">
                                        <Globe className="w-5 h-5 text-indigo-500 shrink-0" />
                                        <p className="text-xs font-bold text-indigo-700 dark:text-indigo-300">Google Meet links will be auto-generated for each team's slot.</p>
                                    </div>
                                )}
                            </div>

                            <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end gap-3">
                                <button onClick={() => setShowBulkModal(false)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                <button onClick={handleBulkSchedule} disabled={isSavingBulk} className="flex items-center px-6 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-xl transition-colors shadow-lg shadow-indigo-500/30 gap-2">
                                    {isSavingBulk ? <><Loader2 className="w-4 h-4 animate-spin" />Scheduling...</> : <><Wand2 className="w-4 h-4" />Schedule {bulkConfig.count} Teams</>}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
            {/* Floating scroll button */}
            <button
                onClick={handleScrollToggle}
                title={scrolledDown ? 'Scroll to top' : 'Scroll to bottom'}
                className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-2xl bg-indigo-600 hover:bg-indigo-700 active:scale-95 text-white shadow-xl shadow-indigo-500/40 flex items-center justify-center transition-all duration-200 border border-indigo-500/30"
            >
                {scrolledDown ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
            </button>
        </div>
    );
}
