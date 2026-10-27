import React, { useState, useRef, useEffect, useCallback } from 'react';
import { UserMinus, AlertTriangle, Calendar, Clock, MapPin, RefreshCcw, CheckCircle, Search, Filter, Plus, X, Edit2, Trash2, Users, Video, DoorOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { apiUpsertTable, apiDeleteRows, apiPatchRow, apiFetchTable, getAuthHeaders } from '../lib/api';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { syncScheduleSlot, createPanelAlert } from '../services/panelSync';
import { getApiBaseUrl } from '../lib/apiBase';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { filterRowsByGlobalFilters } from '../lib/globalFilters';
import { teamLabel } from '../lib/teamUtils';

const EMPTY_ABSENT = { name: '', roll: '', team: '', reason: '', status: 'Pending' };
const EMPTY_MAKEUP = { date: '', time: '', panel: '', room: '', capacity: 20, enrolled: 0, meetLink: '' };

const CONFIG_KEY = 'procksi-schedule-config';
const DEFAULT_CONFIG = {
    rooms: [
        { id: 1, name: 'Seminar Hall 1',   capacity: 30 },
        { id: 2, name: 'Lab 402',          capacity: 20 },
        { id: 3, name: 'Conference Room B', capacity: 15 },
    ],
    configDates:          { start: '2026-05-15', end: '2026-05-20' },
    configTimes:          { start: '09:00', end: '17:00' },
    presentationDuration: 30,
    venueMode:            'offline',
};

function loadScheduleConfig() {
    try {
        return { ...DEFAULT_CONFIG, ...JSON.parse(localStorage.getItem(CONFIG_KEY) || '{}') };
    } catch {
        return DEFAULT_CONFIG;
    }
}

const TIME_OPTIONS = [
    '09:00 AM - 09:30 AM', '09:30 AM - 10:00 AM',
    '10:00 AM - 10:30 AM', '10:30 AM - 11:00 AM',
    '11:00 AM - 11:30 AM', '11:30 AM - 12:00 PM',
    '12:00 PM - 12:30 PM', '12:30 PM - 01:00 PM',
    '01:00 PM - 01:30 PM', '01:30 PM - 02:00 PM',
    '02:00 PM - 02:30 PM', '02:30 PM - 03:00 PM',
    '03:00 PM - 03:30 PM', '03:30 PM - 04:00 PM',
    '04:00 PM - 04:30 PM', '04:30 PM - 05:00 PM',
];

/** Generate a unique string id matching the DB format: ABS-<timestamp><random> */
const genAbsentId = () => `ABS-${Date.now()}${Math.floor(Math.random() * 10000)}`;

const toNumericId = (teamStr) => {
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
};

export default function AbsentStudents() {
    const { semesterMap, filters } = useGlobalFilters();
    // Absent students must be visible across all branches — semester filter already implies branch.
    // Using a branch-neutral filter here so P-003 (AIML) reschedule requests are visible
    // even when admin has "B.Tech CS" selected globally.
    const filterAbsentRows = useCallback(
        (rows) => filterRowsByGlobalFilters(rows, { ...filters, branch: 'all' }, semesterMap),
        [filters, semesterMap]
    );
    const { data: absentStudents, setData: setAbsentStudents } = useSupabaseTableState('absent_students', [], { orderBy: 'id' });
    const [refreshingAbsent, setRefreshingAbsent] = useState(false);

    // Auto-poll absent_students every 30 s so panel reschedule requests appear without a manual reload.
    const refreshAbsentStudents = useCallback(async (silent = false) => {
        if (!silent) setRefreshingAbsent(true);
        try {
            const rows = await apiFetchTable('absent_students', { orderBy: 'id' });
            setAbsentStudents(rows || []);
        } catch { /* non-fatal: fall through to the default below */ }
        finally { if (!silent) setRefreshingAbsent(false); }
    }, [setAbsentStudents]);

    useEffect(() => {
        const interval = setInterval(() => refreshAbsentStudents(true), 30000);
        return () => clearInterval(interval);
    }, [refreshAbsentStudents]);
    const { data: makeupSlots, setData: setMakeupSlots } = useSupabaseTableState('makeup_slots', [], { orderBy: 'date' });
    // Source of truth for panel and room dropdowns
    const { data: scheduleSlots, setData: setScheduleSlots } = useSupabaseTableState('schedule_slots', [], { orderBy: 'date'   });
    const { data: allTeams }      = useSupabaseTableState('teams_validation', [], { orderBy: 'id' });
    const { data: allStudents }   = useSupabaseTableState('students',        [], { orderBy: 'name'  });
    const { data: panels }        = useSupabaseTableState('panels',          [], { orderBy: 'name' });

    // Unique rooms already configured on the Schedule page (merging global config rooms)
    const globalRooms = loadScheduleConfig().rooms.map(r => r.name).filter(Boolean);
    const scheduleRooms = scheduleSlots.map(s => s.room).filter(Boolean);
    const roomOptions = [...new Set([...globalRooms, ...scheduleRooms])].filter(r => r !== 'Online').sort();
    // Panel options = panel names
    const panelOptions  = panels.map(p => p.name).filter(Boolean);

    const [searchTerm, setSearchTerm]       = useState('');
    const [statusFilter, setStatusFilter]   = useState('');
    const [selectedStudent, setSelectedStudent] = useState(null);
    const [selectedMakeupSlot, setSelectedMakeupSlot] = useState('');

    // Modal states for Add/Edit Makeup Slot
    const [makeupVenueMode, setMakeupVenueMode] = useState('offline'); // 'offline' | 'online'
    const [makeupSelectedRoom, setMakeupSelectedRoom] = useState(''); // room name, '_custom_', or ''
    const [makeupCustomRoom, setMakeupCustomRoom] = useState(''); // text typed for custom room

    // Modal states for Custom Reschedule
    const [rescheduleVenueMode, setRescheduleVenueMode] = useState('offline'); // 'offline' | 'online'
    const [rescheduleSelectedRoom, setRescheduleSelectedRoom] = useState(''); // room name, '_custom_', or ''
    const [rescheduleCustomRoom, setRescheduleCustomRoom] = useState(''); // text typed for custom room

    // Add Absent Student modal
    const [absentMode, setAbsentMode]         = useState('individual'); // 'individual' | 'team'
    const [showAddAbsent, setShowAddAbsent]   = useState(false);
    const [absentForm, setAbsentForm]         = useState(EMPTY_ABSENT);
    const [savingAbsent, setSavingAbsent]     = useState(false);
    // Team-absent
    const [selectedTeamId, setSelectedTeamId] = useState('');
    const [teamReason, setTeamReason]         = useState('');
    // Autocomplete for the student name field
    const [nameSuggestions, setNameSuggestions]     = useState([]);
    const [showSuggestions, setShowSuggestions]     = useState(false);
    const [autoFilled, setAutoFilled]               = useState(false); // true once user picks from dropdown
    const autocompleteRef                           = useRef(null);

    // Add / Edit Makeup Slot modal
    const [showAddMakeup, setShowAddMakeup] = useState(false);
    const [editingMakeupId, setEditingMakeupId] = useState(null); // null = create, id = edit
    const [makeupForm, setMakeupForm]       = useState(EMPTY_MAKEUP);
    const [savingMakeup, setSavingMakeup]   = useState(false);

    // Reschedule mode: 'existing' (from makeup slots) or 'custom' (one-off)
    const [rescheduleMode, setRescheduleMode] = useState('existing');
    const [customReschedule, setCustomReschedule] = useState({ date: '', time: '', panel: '', room: '' });
    const [generatingMeet, setGeneratingMeet] = useState(false);

    // Create a real Google Meet link (invited people join, no host) for an
    // online makeup / reschedule slot and drop it into the given form setter.
    const generateMeetLink = async ({ date, time, team, room }, setForm) => {
        if (!date || !time) { alert('Pick a date and time first.'); return; }
        setGeneratingMeet(true);
        try {
            const res = await fetch(`${getApiBaseUrl()}/api/events/generate-meet-link`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ slot_id: 'new', date, time, team: team || 'TBD', room: room || null }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.meetLink) throw new Error(data.detail || 'Could not generate link');
            setForm(f => ({ ...f, meetLink: data.meetLink }));
        } catch (e) {
            alert(`Generate failed: ${e.message}. Connect Google Calendar on the Schedule page, or paste a link manually.`);
        } finally {
            setGeneratingMeet(false);
        }
    };

    // ── Autocomplete helpers ──────────────────────────────────────────
    /** Find the team ID that a student (by name) belongs to */
    const findStudentTeam = (studentName) => {
        if (!studentName) return '';
        const lower = studentName.toLowerCase().trim();
        const matched = allTeams.find(t => {
            if ((t.leader || '').toLowerCase().trim() === lower) return true;
            const raw = t.members || '';
            const memberList = (Array.isArray(raw) ? raw : String(raw).split(/[,\s]+/)).map(s => String(s).trim().toLowerCase()).filter(Boolean);
            return memberList.some(m => m === lower);
        });
        return matched ? matched.id : '';
    };

    const handleNameInput = (value) => {
        setAbsentForm(f => ({ ...f, name: value }));
        setAutoFilled(false);
        if (value.trim().length < 2) {
            setNameSuggestions([]);
            setShowSuggestions(false);
            return;
        }
        const lower = value.toLowerCase();
        const hits = allStudents
            .filter(s => (s.name || '').toLowerCase().includes(lower))
            .slice(0, 8); // max 8 suggestions
        setNameSuggestions(hits);
        setShowSuggestions(hits.length > 0);
    };

    const handleSelectSuggestion = (student) => {
        const teamId = findStudentTeam(student.name);
        setAbsentForm(f => ({
            ...f,
            name: student.name,
            roll: student.id,
            team: teamId || f.team,
        }));
        setAutoFilled(true);
        setShowSuggestions(false);
        setNameSuggestions([]);
    };

    const clearAutoFill = () => {
        setAbsentForm(EMPTY_ABSENT);
        setAutoFilled(false);
        setShowSuggestions(false);
        setNameSuggestions([]);
    };

    // Close suggestions on outside click
    useEffect(() => {
        const handler = (e) => {
            if (autocompleteRef.current && !autocompleteRef.current.contains(e.target)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Panel-initiated reschedule requests must always show regardless of semester/branch
    // filters — the panel may belong to a different branch context than what admin has selected.
    const isPanelRescheduleRequest = (s) =>
        typeof s.reason === 'string' && s.reason.toLowerCase().includes('reschedule requested by panel');

    const enrichedAbsent = absentStudents.map(s => {
        const teamObj = allTeams.find(t => t.id === s.team);
        return {
            ...s,
            semester_id: s.semester_id || teamObj?.semester_id || ''
        };
    });

    // Apply global filters only to non-panel-reschedule rows; always include panel reschedule requests.
    const filtered = [
        ...enrichedAbsent.filter(isPanelRescheduleRequest),
        ...filterAbsentRows(enrichedAbsent.filter(s => !isPanelRescheduleRequest(s))),
    ].filter(s => {
        const matchSearch = (s.name || '').toLowerCase().includes(searchTerm.toLowerCase()) || (s.roll || '').includes(searchTerm);
        const matchStatus = statusFilter
            ? s.status === statusFilter
            : s.status !== 'Completed';
        return matchSearch && matchStatus;
    });

    // Modal opener / closer helpers
    const openAddMakeup = () => {
        setEditingMakeupId(null);
        setMakeupForm({ date: '', time: '', panel: '', room: '', capacity: 20, enrolled: 0, meetLink: '' });
        setMakeupVenueMode('offline');
        setMakeupSelectedRoom('');
        setMakeupCustomRoom('');
        setShowAddMakeup(true);
    };

    const openEditMakeup = (slot) => {
        setEditingMakeupId(slot.id);
        const isOnline = slot.room === 'Online';
        const isCustom = !isOnline && slot.room && !roomOptions.includes(slot.room);
        setMakeupForm({
            date: slot.date || '',
            time: slot.time || '',
            panel: slot.panel || '',
            room: slot.room || '',
            capacity: slot.capacity ?? 20,
            enrolled: slot.enrolled ?? 0,
            meetLink: slot.meetLink || '',
        });
        setMakeupVenueMode(isOnline ? 'online' : 'offline');
        setMakeupSelectedRoom(isOnline ? '' : (isCustom ? '_custom_' : (slot.room || '')));
        setMakeupCustomRoom(isCustom ? slot.room : '');
        setShowAddMakeup(true);
    };

    const closeMakeupModal = () => {
        setShowAddMakeup(false);
        setEditingMakeupId(null);
        setMakeupForm(EMPTY_MAKEUP);
    };

    const openRescheduleModal = (student) => {
        setSelectedStudent(student);
        setSelectedMakeupSlot('');
        setCustomReschedule({ date: '', time: '', panel: '', room: '', meetLink: '' });
        setRescheduleVenueMode('offline');
        setRescheduleSelectedRoom('');
        setRescheduleCustomRoom('');
    };

    const closeRescheduleModal = () => {
        setSelectedStudent(null);
        setRescheduleMode('existing');
        setCustomReschedule({ date: '', time: '', panel: '', room: '', meetLink: '' });
    };

    const handleReschedule = async () => {
        if (!selectedStudent) return;
        if (rescheduleMode === 'existing' && !selectedMakeupSlot) return;
        if (rescheduleMode === 'custom' && (!customReschedule.date || !customReschedule.time || !customReschedule.panel)) return;

        const student = selectedStudent;
        let slotData = null;

        if (rescheduleMode === 'existing') {
            const slotId = selectedMakeupSlot;
            slotData = makeupSlots.find(s => String(s.id) === String(slotId));
            if (!slotData) return;
            // Update enrollment count
            setMakeupSlots(prev => prev.map(s => s.id == slotId ? { ...s, enrolled: (s.enrolled ?? 0) + 1 } : s));
            await apiPatchRow('makeup_slots', slotId, { enrolled: (slotData.enrolled ?? 0) + 1 });
        } else {
            slotData = customReschedule;
        }

        const teamId = student.team;
        const panelName = slotData.panel;
        const panelRow = panels.find(p => (p.name || '').trim().toLowerCase() === panelName.trim().toLowerCase());
        const panelId = panelRow?.id || panelName?.replace(/\s+/g, '-').toUpperCase() || 'PANEL-UNKNOWN';
        const teamIdNum = toNumericId(teamId);

        // Reschedule all members of the same team who are currently absent and Pending
        const teamMembersToReschedule = absentStudents.filter(s => s.team === teamId && s.status === 'Pending');
        if (!teamMembersToReschedule.some(s => s.id === student.id)) {
            teamMembersToReschedule.push(student);
        }
        const updatedRows = teamMembersToReschedule.map(s => ({ ...s, status: 'Rescheduled' }));

        setAbsentStudents(prev => prev.map(s => {
            const match = updatedRows.find(ur => ur.id === s.id);
            return match ? match : s;
        }));
        setSelectedStudent(null);
        setSelectedMakeupSlot('');
        setCustomReschedule({ date: '', time: '', panel: '', room: '', meetLink: '' });

        try {
            await apiUpsertTable('absent_students', updatedRows, 'id');

            // Push the makeup slot into schedule_slots so the panel portal picks it up
            const existingSched = scheduleSlots.find(s => s.team === teamId);
            const roomVal = slotData.room || 'Main Hall';
            const isOnline = String(roomVal).trim().toLowerCase() === 'online';
            let meetLink = slotData.meetLink || existingSched?.meetLink || existingSched?.meet_link || null;
            const schedPayload = {
                date: slotData.date,
                time: slotData.time,
                team: teamId,
                panel: panelName,
                room: roomVal,
                meetLink,
            };
            let schedSlotId = existingSched?.id ?? null;
            if (existingSched?.id) {
                await apiPatchRow('schedule_slots', existingSched.id, schedPayload);
                setScheduleSlots(prev => prev.map(s => s.id === existingSched.id ? { ...s, ...schedPayload } : s));
            } else {
                const res = await apiUpsertTable('schedule_slots', [schedPayload], null);
                const saved = res?.data?.[0] ?? schedPayload;
                schedSlotId = saved?.id ?? null;
                setScheduleSlots(prev => [...prev, saved]);
            }

            // Online + no link yet -> create a real Google Meet on the shared
            // account (panel + team invited, so everyone joins without a host).
            if (isOnline && !meetLink && schedSlotId != null) {
                try {
                    const r = await fetch(`${getApiBaseUrl()}/api/events/ensure-slot-meet`, {
                        method: 'POST',
                        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({ slot_ids: [schedSlotId] }),
                    });
                    const d = await r.json().catch(() => ({}));
                    const made = [...(d.created || []), ...(d.updated || [])].find(x => x.meetLink);
                    if (made?.meetLink) {
                        meetLink = made.meetLink;
                        setScheduleSlots(prev => prev.map(s => s.id === schedSlotId ? { ...s, meetLink } : s));
                    }
                } catch (meErr) {
                    console.warn('ensure-slot-meet (reschedule) failed:', meErr);
                }
            }

            // Sync slot + notify the panel portal
            if (panelId && !isNaN(teamIdNum)) {
                try {
                    await syncScheduleSlot({
                        panelId,
                        panel: panelName,
                        team: teamId,
                        date: slotData.date,
                        time: slotData.time,
                        room: slotData.room || 'Main Hall',
                        meetLink,
                    });
                    await createPanelAlert({
                        panel_id: panelId,
                        team_id: teamIdNum,
                        alert_type: 'reschedule',
                        title: `Reschedule Confirmed — ${teamId}`,
                        body: `Admin has rescheduled your missed evaluation. New slot: ${slotData.date} at ${slotData.time}, venue: ${slotData.room === 'Online' ? 'Online' : (slotData.room || 'Main Hall')}.`,
                    });
                } catch (syncErr) {
                    console.error('Panel sync/alert failed:', syncErr);
                }
            } else {
                console.warn('Could not resolve panel_id for mentor:', panelName);
            }

            AuditLogger.logUserAction(getCurrentUser(), `Rescheduled team ${teamId} (students: ${teamMembersToReschedule.map(s => s.name).join(', ')}) to ${rescheduleMode} slot on ${slotData.date || 'unknown date'}`);
        } catch (e) {
            console.error(e);
            alert('Reschedule saved partially — check console for sync errors.');
        }
    };

    const handleAddAbsent = async (e) => {
        e.preventDefault();
        setSavingAbsent(true);
        const row = { id: genAbsentId(), ...absentForm, status: 'Pending' };
        try {
            const res = await apiUpsertTable('absent_students', [row], 'id');
            const saved = res?.data?.[0] ?? row;
            setAbsentStudents(prev => [...prev, saved]);
            setShowAddAbsent(false);
            setAbsentForm(EMPTY_ABSENT);
            AuditLogger.logUserAction(getCurrentUser(), `Marked student ${absentForm.name} (${absentForm.roll}) as absent. Reason: ${absentForm.reason}`);
        } catch (e) { alert('Failed to save: ' + e.message); }
        finally { setSavingAbsent(false); }
    };

    const handleMarkTeamAbsent = async () => {
        const team = allTeams.find(t => t.id === selectedTeamId);
        if (!team) return;
        setSavingAbsent(true);
        try {
            // Build member list — members can be array or string
            const rawMembers = team.members || '';
            const memberArr = Array.isArray(rawMembers) ? rawMembers : String(rawMembers).split(/[,\s]+/);
            
            // Helper function to extract name from object or string
            const extractName = (item) => {
                if (typeof item === 'object' && item !== null) {
                    return item.name || '';
                }
                return String(item).trim();
            };
            
            const memberNames = [team.leader, ...memberArr]
                .map(extractName)
                .filter(Boolean)
                .filter((v, i, a) => a.indexOf(v) === i); // dedupe
            // Look up roll numbers from students table
            const rows = memberNames.map((name, idx) => {
                const student = allStudents.find(s => (s.name || '').toLowerCase().trim() === name.toLowerCase().trim());
                return {
                    id: genAbsentId() + idx,
                    name,
                    roll: student ? student.id : `${team.id}-M${idx + 1}`,
                    team: team.id,
                    reason: teamReason || 'Team absence',
                    status: 'Pending',
                };
            });
            const res = await apiUpsertTable('absent_students', rows, 'id');
            const saved = res?.data?.length ? res.data : rows;
            setAbsentStudents(prev => [...prev, ...saved]);
            setShowAddAbsent(false);
            setAbsentMode('individual');
            setSelectedTeamId('');
            setTeamReason('');
            AuditLogger.logUserAction(getCurrentUser(), `Marked entire team ${team.id} as absent. Reason: ${teamReason || 'Team absence'}`);
        } catch (e) { alert('Failed to save: ' + e.message); }
        finally { setSavingAbsent(false); }
    };

    const handleAddMakeup = async (e) => {
        e.preventDefault();
        setSavingMakeup(true);
        try {
            if (editingMakeupId) {
                // PATCH — never send id back, Supabase id is GENERATED ALWAYS
                await apiPatchRow('makeup_slots', editingMakeupId, makeupForm);
                setMakeupSlots(prev => prev.map(s => s.id === editingMakeupId ? { ...s, ...makeupForm } : s));
            } else {
                // Create — no id field, let DB generate it
                const { enrolled: _e, ...createPayload } = makeupForm;
                const res = await apiUpsertTable('makeup_slots', [createPayload], null);
                const saved = res?.data?.[0] ?? createPayload;
                setMakeupSlots(prev => [...prev, saved]);
            }
            closeMakeupModal();
            AuditLogger.logAdminAction(getCurrentUser(), editingMakeupId ? `Updated makeup slot for ${makeupForm.date}` : `Created new makeup slot for ${makeupForm.date}`);
        } catch (e) { alert('Failed to save: ' + e.message); }
        finally { setSavingMakeup(false); }
    };

    const handleDeleteMakeup = async (slot) => {
        if (!window.confirm(`Delete makeup slot (${slot.date} ${slot.time})?`)) return;
        // Optimistic removal
        setMakeupSlots(prev => prev.filter(s => s.id !== slot.id));
        try {
            await apiDeleteRows('makeup_slots', { id: slot.id });
            AuditLogger.logAdminAction(getCurrentUser(), `Deleted makeup slot on ${slot.date} at ${slot.time}`);
        } catch (e) {
            // Rollback on failure
            setMakeupSlots(prev => [...prev, slot]);
            alert('Delete failed: ' + e.message);
        }
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            {/* Header */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                className="bg-gradient-to-br from-rose-600 via-rose-700 to-red-900 rounded-3xl p-8 text-white shadow-xl shadow-rose-500/20 relative overflow-hidden border border-rose-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20">
                        <UserMinus className="w-4 h-4 mr-2" /> Evaluation Exceptions
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Absent Students</h1>
                    <p className="text-rose-100/90 text-sm md:text-base max-w-lg font-medium">Manage students who missed their scheduled presentations and assign them to dedicated makeup slots.</p>
                </div>
            </motion.div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Students Table */}
                <div className="lg:col-span-2 space-y-4">
                    <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                        <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 flex flex-col sm:flex-row gap-3 justify-between items-center">
                            <div className="relative w-full max-w-md group">
                                <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                                <input type="text" placeholder="Search by name or roll..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
                                    className="w-full pl-11 pr-5 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none" />
                            </div>
                            <div className="flex items-center gap-3 w-full sm:w-auto">
                                <div className="flex items-center">
                                    <Filter className="w-4 h-4 mr-2 text-slate-400" />
                                    <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-indigo-500">
                                        <option value="">All Statuses</option>
                                        <option value="Pending">Pending</option>
                                        <option value="Rescheduled">Rescheduled</option>
                                        <option value="Completed">Completed</option>
                                    </select>
                                </div>
                                <button
                                    onClick={() => refreshAbsentStudents(false)}
                                    disabled={refreshingAbsent}
                                    title="Refresh to see new panel reschedule requests"
                                    className="flex items-center px-3 py-2.5 bg-slate-100 hover:bg-indigo-50 dark:bg-slate-700 dark:hover:bg-indigo-500/20 text-slate-500 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 rounded-xl text-xs font-black uppercase tracking-widest transition-all border border-slate-200 dark:border-slate-600 hover:border-indigo-200 dark:hover:border-indigo-500/40 disabled:opacity-50">
                                    <RefreshCcw className={`w-4 h-4 ${refreshingAbsent ? 'animate-spin' : ''}`} />
                                </button>
                                <button onClick={() => setShowAddAbsent(true)}
                                    className="flex items-center px-4 py-2.5 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg shadow-rose-500/30 whitespace-nowrap">
                                    <Plus className="w-4 h-4 mr-1.5" /> Add Student
                                </button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-left">
                                <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700">
                                    <tr>
                                        {['Student', 'Original Team', 'Reason', 'Status', 'Action'].map(h => (
                                            <th key={h} className="p-4 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                                    {filtered.map(s => (
                                        <tr key={s.id} className={`hover:bg-slate-50/50 dark:hover:bg-slate-700/20 transition-colors ${isPanelRescheduleRequest(s) ? 'bg-amber-50/40 dark:bg-amber-500/5' : ''}`}>
                                            <td className="p-4">
                                                <div className="font-bold text-sm text-slate-800 dark:text-white">{s.name}</div>
                                                <div className="text-[10px] font-bold text-slate-500 font-mono">{s.roll}</div>
                                                {isPanelRescheduleRequest(s) && (
                                                    <span className="mt-1 inline-flex items-center text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/20 px-2 py-0.5 rounded border border-amber-200 dark:border-amber-500/30">
                                                        Panel Request
                                                    </span>
                                                )}
                                            </td>
                                            <td className="p-4 whitespace-nowrap">
                                                <span className="inline-block whitespace-nowrap text-xs font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-1 rounded-md border border-indigo-100 dark:border-indigo-500/20">{teamLabel(s.team, allTeams.find(t => t.id === s.team) || null, semesterMap)}</span>
                                            </td>
                                            <td className="p-4 text-sm font-medium text-slate-600 dark:text-slate-400">{s.reason}</td>
                                            <td className="p-4">
                                                {s.status === 'Pending' ? (
                                                    <span className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-rose-600 dark:text-rose-400 bg-rose-100 dark:bg-rose-500/20 px-2.5 py-1 rounded">
                                                        <AlertTriangle className="w-3 h-3 mr-1" /> Pending
                                                    </span>
                                                ) : (
                                                    <div className="space-y-1.5">
                                                        <span className="inline-flex items-center text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/20 px-2.5 py-1 rounded">
                                                            <CheckCircle className="w-3 h-3 mr-1" /> Rescheduled
                                                        </span>
                                                        {(() => {
                                                            const slot = scheduleSlots.find(sl => sl.team === s.team);
                                                            if (!slot) return null;
                                                            return (
                                                                <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 space-y-1 bg-slate-50 dark:bg-slate-900/40 p-2 rounded-xl border border-slate-100 dark:border-slate-700/60 max-w-[180px]">
                                                                    <div className="flex items-center gap-1.5">
                                                                        <Calendar className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                                                                        <span className="truncate">{slot.date}</span>
                                                                    </div>
                                                                    <div className="flex items-center gap-1.5">
                                                                        <Clock className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                                                                        <span className="truncate">{slot.time}</span>
                                                                    </div>
                                                                    <div className="flex items-center gap-1.5">
                                                                        {slot.room === 'Online' ? (
                                                                            <>
                                                                                <Video className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                                                                <span className="mr-1">Online</span>
                                                                                {slot.meetLink && (
                                                                                    <a href={slot.meetLink} target="_blank" rel="noreferrer" className="text-indigo-600 dark:text-indigo-400 hover:underline">Link</a>
                                                                                )}
                                                                            </>
                                                                        ) : (
                                                                            <>
                                                                                <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                                                                                <span className="truncate">{slot.room || 'Main Hall'}</span>
                                                                            </>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            );
                                                        })()}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="p-4 text-right">
                                                {s.status === 'Pending' && (
                                                    <button onClick={() => openRescheduleModal(s)}
                                                        className="px-3 py-1.5 bg-slate-100 hover:bg-rose-50 dark:bg-slate-800 dark:hover:bg-rose-500/20 text-slate-700 dark:text-slate-300 hover:text-rose-600 dark:hover:text-rose-400 text-xs font-black uppercase tracking-widest rounded-lg transition-colors border border-transparent hover:border-rose-200 dark:hover:border-rose-500/30">
                                                        Reschedule
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                    {filtered.length === 0 && (
                                        <tr><td colSpan="5" className="p-10 text-center text-sm font-bold text-slate-400">
                                            <UserMinus className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                            No absent students recorded. Click "Add Student" to mark one.
                                        </td></tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {/* Makeup Slots */}
                <div className="lg:col-span-1 space-y-4">
                    <h2 className="text-lg font-black text-slate-800 dark:text-white flex items-center px-2">
                        <Calendar className="w-5 h-5 mr-3 text-rose-500" /> Makeup Slots
                    </h2>
                    {makeupSlots.map(slot => (
                        <div key={slot.id} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-5 relative group">
                            {/* Edit / Delete buttons */}
                            <div className="absolute top-4 right-4 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => openEditMakeup(slot)}
                                    className="p-1.5 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-300 shadow-sm transition-all"
                                >
                                    <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                    onClick={() => handleDeleteMakeup(slot)}
                                    className="p-1.5 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:border-rose-300 shadow-sm transition-all"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </div>
                            <div className="flex justify-between items-start mb-4 pr-16">
                                <div>
                                    <h3 className="font-black text-slate-800 dark:text-white">{slot.panel || '—'}</h3>
                                    <div className="flex flex-wrap gap-2 mt-1.5">
                                        {slot.room === 'Online' ? (
                                            <span className="inline-flex items-center px-2 py-0.5 bg-emerald-50 dark:bg-emerald-500/10 text-[10px] font-black uppercase tracking-widest rounded text-emerald-600 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-500/20">
                                                <Video className="w-3 h-3 mr-1" /> Online
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-[10px] font-black uppercase tracking-widest rounded text-slate-500 dark:text-slate-400">
                                                <MapPin className="w-3 h-3 mr-1" /> {slot.room || '—'}
                                            </span>
                                        )}
                                        {slot.room === 'Online' && slot.meetLink && (
                                            <a href={slot.meetLink} target="_blank" rel="noreferrer" className="inline-flex items-center px-2 py-0.5 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-[10px] font-black uppercase tracking-widest rounded text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-500/20 transition-colors">
                                                Link
                                            </a>
                                        )}
                                    </div>
                                </div>
                                <div className="text-right">
                                    <div className="text-xs font-bold text-slate-500">Capacity</div>
                                    <div className="text-sm font-black text-indigo-600 dark:text-indigo-400">{slot.enrolled ?? 0} / {slot.capacity ?? 20}</div>
                                </div>
                            </div>
                            <div className="flex items-center text-sm font-bold text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/50 p-2 rounded-xl border border-slate-100 dark:border-slate-700">
                                <Calendar className="w-4 h-4 mr-2 text-rose-500" />
                                {slot.date ? new Date(slot.date).toLocaleDateString() : '—'}
                                <span className="mx-2 text-slate-300">|</span>
                                <Clock className="w-4 h-4 mr-2 text-indigo-500" /> {slot.time || '—'}
                            </div>
                        </div>
                    ))}
                    {makeupSlots.length === 0 && (
                        <div className="bg-white/60 dark:bg-slate-800/60 rounded-3xl border border-dashed border-slate-300 dark:border-slate-600 p-6 text-center text-sm font-medium text-slate-400">
                            No makeup slots yet.
                        </div>
                    )}
                    <button onClick={openAddMakeup}
                        className="w-full py-3 bg-white hover:bg-rose-50 dark:bg-slate-800 dark:hover:bg-rose-500/10 border border-dashed border-slate-200 dark:border-slate-600 hover:border-rose-300 dark:hover:border-rose-500/40 dark:text-slate-200 text-slate-500 rounded-2xl text-xs uppercase tracking-widest font-black transition-all flex items-center justify-center">
                        <Plus className="w-4 h-4 mr-2" /> Add Makeup Slot
                    </button>
                </div>
            </div>

            {/* ── Add Absent Student Modal ── */}
            <AnimatePresence>
                {showAddAbsent && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                            <div className="bg-gradient-to-r from-rose-600 to-rose-800 p-6 flex justify-between items-center text-white">
                                <h3 className="font-black text-xl">{absentMode === 'individual' ? 'Mark Student Absent' : 'Mark Team Absent'}</h3>
                                <button onClick={() => { setShowAddAbsent(false); setAbsentMode('individual'); }} className="p-1.5 bg-black/10 hover:bg-black/20 rounded-full transition-colors"><X className="w-5 h-5" /></button>
                            </div>

                            {/* ── Mode tabs ── */}
                            <div className="flex border-b border-slate-200 dark:border-slate-700">
                                <button type="button" onClick={() => setAbsentMode('individual')}
                                    className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-black uppercase tracking-widest transition-colors ${absentMode === 'individual' ? 'text-rose-600 dark:text-rose-400 border-b-2 border-rose-500 bg-rose-50/50 dark:bg-rose-500/5' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'}`}>
                                    <UserMinus className="w-4 h-4" /> Individual
                                </button>
                                <button type="button" onClick={() => setAbsentMode('team')}
                                    className={`flex-1 flex items-center justify-center gap-2 py-3 text-xs font-black uppercase tracking-widest transition-colors ${absentMode === 'team' ? 'text-rose-600 dark:text-rose-400 border-b-2 border-rose-500 bg-rose-50/50 dark:bg-rose-500/5' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'}`}>
                                    <Users className="w-4 h-4" /> Entire Team
                                </button>
                            </div>

                            {absentMode === 'individual' ? (
                            <form onSubmit={handleAddAbsent} className="p-6 space-y-4">
                                {/* ── Full Name with live-search autocomplete ── */}
                                <div ref={autocompleteRef} className="relative">
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">
                                        Full Name
                                        {autoFilled && (
                                            <span onClick={clearAutoFill} className="ml-2 cursor-pointer inline-flex items-center gap-1 px-2 py-0.5 bg-rose-100 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400 rounded-full text-[9px] font-black hover:bg-rose-200 dark:hover:bg-rose-500/30 transition-colors normal-case tracking-normal">
                                                Auto-filled ✕
                                            </span>
                                        )}
                                    </label>
                                    <div className="relative">
                                        <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                        <input required type="text" placeholder="Type a student name to search…" value={absentForm.name}
                                            onChange={e => handleNameInput(e.target.value)}
                                            onFocus={() => nameSuggestions.length > 0 && setShowSuggestions(true)}
                                            className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                    </div>
                                    {showSuggestions && (
                                        <div className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl shadow-xl overflow-hidden max-h-60 overflow-y-auto">
                                            {nameSuggestions.map(student => {
                                                const team = findStudentTeam(student.name);
                                                return (
                                                    <button key={student.id} type="button" onMouseDown={() => handleSelectSuggestion(student)}
                                                        className="w-full flex items-center justify-between px-4 py-3 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors border-b border-slate-100 dark:border-slate-700/50 last:border-0 text-left group">
                                                        <div>
                                                            <div className="text-sm font-bold text-slate-800 dark:text-white group-hover:text-rose-600 dark:group-hover:text-rose-400 transition-colors">{student.name}</div>
                                                            <div className="text-[11px] font-mono text-slate-400 dark:text-slate-500 mt-0.5">{student.id}</div>
                                                        </div>
                                                        <div className="flex items-center gap-1.5 shrink-0 ml-3">
                                                            {team && <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-500/20 rounded-md">{team}</span>}
                                                            <span className="text-[10px] font-bold text-slate-400 dark:text-slate-500">{student.branch}</span>
                                                        </div>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Roll Number</label>
                                    <input required type="text" placeholder="e.g. 2100123" value={absentForm.roll}
                                        onChange={e => !autoFilled && setAbsentForm(f => ({ ...f, roll: e.target.value }))} readOnly={autoFilled}
                                        className={`w-full px-4 py-2.5 border rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none transition-colors ${autoFilled ? 'bg-slate-100 dark:bg-slate-700/50 border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400 cursor-not-allowed' : 'bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700'}`} />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Original Team</label>
                                    <input required type="text" placeholder="e.g. TEAM-5" value={absentForm.team}
                                        onChange={e => !autoFilled && setAbsentForm(f => ({ ...f, team: e.target.value }))} readOnly={autoFilled}
                                        className={`w-full px-4 py-2.5 border rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none transition-colors ${autoFilled ? 'bg-slate-100 dark:bg-slate-700/50 border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400 cursor-not-allowed' : 'bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700'}`} />
                                </div>
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Reason for Absence</label>
                                    <input required type="text" placeholder="e.g. Medical emergency" value={absentForm.reason}
                                        onChange={e => setAbsentForm(f => ({ ...f, reason: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                </div>
                                <div className="flex justify-end gap-3 pt-2">
                                    <button type="button" onClick={() => { setShowAddAbsent(false); setAutoFilled(false); setAbsentForm(EMPTY_ABSENT); }} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" disabled={savingAbsent} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400 rounded-xl transition-colors shadow-lg shadow-rose-500/30">
                                        {savingAbsent ? 'Saving...' : 'Add Student'}
                                    </button>
                                </div>
                            </form>
                            ) : (
                            /* ── Team mode ── */
                            <div className="p-6 space-y-4">
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Select Team</label>
                                    <select value={selectedTeamId} onChange={e => setSelectedTeamId(e.target.value)}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none cursor-pointer">
                                        <option value="" disabled>-- Choose a team --</option>
                                        {allTeams.map(t => (
                                            <option key={t.id} value={t.id}>{t.id} — {t.leader || 'No leader'}</option>
                                        ))}
                                    </select>
                                </div>
                                {selectedTeamId && (() => {
                                    const team = allTeams.find(t => t.id === selectedTeamId);
                                    if (!team) return null;
                                    let memberArr = [];
                                    if (Array.isArray(team.members)) {
                                        memberArr = team.members;
                                    } else {
                                        memberArr = String(team.members).split(/[,\s]+/).filter(Boolean);
                                    }
                                    // Helper function to extract name from object or string
                                    const extractName = (item) => {
                                        if (typeof item === 'object' && item !== null) {
                                            return item.name || '';
                                        }
                                        return String(item).trim();
                                    };
                                    
                                    const names = [team.leader, ...memberArr]
                                        .map(extractName)
                                        .filter(Boolean)
                                        .filter((v,i,a) => a.indexOf(v) === i);
                                    return (
                                        <div className="p-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl">
                                            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Members ({names.length})</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {names.map((n, i) => (
                                                    <span key={i} className="inline-flex items-center px-2.5 py-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg text-xs font-bold text-slate-700 dark:text-slate-300">
                                                        {i === 0 && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mr-1.5" title="Leader" />}
                                                        {n}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })()}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Reason for Absence</label>
                                    <input type="text" placeholder="e.g. Team unavailable" value={teamReason}
                                        onChange={e => setTeamReason(e.target.value)}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                </div>
                                <div className="flex justify-end gap-3 pt-2">
                                    <button type="button" onClick={() => { setShowAddAbsent(false); setAbsentMode('individual'); setSelectedTeamId(''); setTeamReason(''); }} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="button" onClick={handleMarkTeamAbsent} disabled={!selectedTeamId || savingAbsent}
                                        className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400 rounded-xl transition-colors shadow-lg shadow-rose-500/30">
                                        {savingAbsent ? 'Saving...' : 'Mark Team Absent'}
                                    </button>
                                </div>
                            </div>
                            )}
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Add Makeup Slot Modal ── */}
            <AnimatePresence>
                {showAddMakeup && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center text-white">
                                <h3 className="font-black text-xl">{editingMakeupId ? 'Edit Makeup Slot' : 'Add Makeup Slot'}</h3>
                                <button onClick={() => { setShowAddMakeup(false); setEditingMakeupId(null); }} className="p-1.5 bg-black/10 hover:bg-black/20 rounded-full transition-colors"><X className="w-5 h-5" /></button>
                            </div>
                            <form onSubmit={handleAddMakeup} className="p-6 space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Date</label>
                                        <input required type="date" value={makeupForm.date} onChange={e => setMakeupForm(f => ({ ...f, date: e.target.value }))}
                                            className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none" />
                                    </div>
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Time</label>
                                        <select required value={makeupForm.time} onChange={e => setMakeupForm(f => ({ ...f, time: e.target.value }))}
                                            className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none cursor-pointer">
                                            <option value="" disabled>-- Select time --</option>
                                            {TIME_OPTIONS.map(opt => (
                                                <option key={opt} value={opt}>{opt}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                {/* Panel dropdown — from mentors table */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Panel / Evaluator</label>
                                    <select required value={makeupForm.panel} onChange={e => setMakeupForm(f => ({ ...f, panel: e.target.value }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none cursor-pointer">
                                        <option value="" disabled>-- Select panel / evaluator --</option>
                                        {panelOptions.map(name => (
                                            <option key={name} value={name}>{name}</option>
                                        ))}
                                    </select>
                                    {panelOptions.length === 0 && <p className="text-[10px] text-amber-500 mt-1 font-bold">No mentors found. Add mentors first.</p>}
                                </div>

                                {/* Presentation Mode / Room Selection */}
                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Presentation Mode</label>
                                    <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-xl shadow-inner mb-4">
                                        <button type="button" onClick={() => {
                                            setMakeupVenueMode('offline');
                                            setMakeupForm(f => ({ ...f, room: makeupSelectedRoom === '_custom_' ? makeupCustomRoom : makeupSelectedRoom }));
                                        }} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${makeupVenueMode === 'offline' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                        </button>
                                        <button type="button" onClick={() => {
                                            setMakeupVenueMode('online');
                                            setMakeupForm(f => ({ ...f, room: 'Online' }));
                                        }} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${makeupVenueMode === 'online' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                            <Video className="w-4 h-4 mr-2" /> Online
                                        </button>
                                    </div>
                                </div>

                                {makeupVenueMode === 'offline' ? (
                                    <div className="space-y-4">
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Room / Venue</label>
                                            <select required={makeupVenueMode === 'offline'} value={makeupSelectedRoom} onChange={e => {
                                                const val = e.target.value;
                                                setMakeupSelectedRoom(val);
                                                setMakeupForm(f => ({ ...f, room: val === '_custom_' ? makeupCustomRoom : val }));
                                            }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none cursor-pointer">
                                                <option value="" disabled>-- Select room --</option>
                                                {roomOptions.map(room => (
                                                    <option key={room} value={room}>{room}</option>
                                                ))}
                                                <option value="_custom_">-- Custom Room --</option>
                                            </select>
                                        </div>
                                        {makeupSelectedRoom === '_custom_' && (
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Custom Room Name</label>
                                                <input required={makeupSelectedRoom === '_custom_'} type="text" placeholder="e.g. Lab 403" value={makeupCustomRoom} onChange={e => {
                                                    const val = e.target.value;
                                                    setMakeupCustomRoom(val);
                                                    setMakeupForm(f => ({ ...f, room: val }));
                                                }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none" />
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Google Meet Link</label>
                                        <div className="flex gap-2">
                                            <div className="relative flex-1">
                                                <Video className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                                <input required={makeupVenueMode === 'online'} type="url" placeholder="https://meet.google.com/xxx-xxxx-xxx" value={makeupForm.meetLink || ''} onChange={e => {
                                                    const val = e.target.value;
                                                    setMakeupForm(f => ({ ...f, meetLink: val }));
                                                }} className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none" />
                                            </div>
                                            <button type="button" disabled={generatingMeet || !makeupForm.date || !makeupForm.time}
                                                onClick={() => generateMeetLink({ date: makeupForm.date, time: makeupForm.time, team: makeupForm.team, room: 'Online' }, setMakeupForm)}
                                                className="px-4 py-2.5 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-xl text-xs font-black uppercase tracking-widest transition-all border border-indigo-100 dark:border-indigo-500/20 disabled:opacity-50 shrink-0">
                                                {generatingMeet ? '…' : 'Generate'}
                                            </button>
                                        </div>
                                    </div>
                                )}

                                <div>
                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Capacity</label>
                                    <input required type="number" min="1" value={makeupForm.capacity} onChange={e => setMakeupForm(f => ({ ...f, capacity: parseInt(e.target.value) || 20 }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none" />
                                </div>
                                <div className="flex justify-end gap-3 pt-2">
                                    <button type="button" onClick={closeMakeupModal} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" disabled={savingMakeup} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-xl transition-colors shadow-lg shadow-indigo-500/30">
                                        {savingMakeup ? 'Saving...' : (editingMakeupId ? 'Save Changes' : 'Create Slot')}
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Reschedule Modal ── */}
            <AnimatePresence>
                {selectedStudent && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                            <div className="bg-gradient-to-r from-rose-600 to-rose-800 p-6 text-white">
                                <h3 className="font-black text-xl">Reschedule Team</h3>
                                <p className="text-xs uppercase tracking-widest mt-1 opacity-80">Team: {teamLabel(selectedStudent.team, allTeams.find(t => t.id === selectedStudent.team) || null, semesterMap)} (Requested by: {selectedStudent.name})</p>
                            </div>

                            {/* Mode tabs */}
                            <div className="flex border-b border-slate-200 dark:border-slate-700">
                                <button type="button" onClick={() => setRescheduleMode('existing')}
                                    className={`flex-1 flex items-center justify-center gap-2 py-3 text-[10px] font-black uppercase tracking-widest transition-colors ${rescheduleMode === 'existing' ? 'text-rose-600 dark:text-rose-400 border-b-2 border-rose-500 bg-rose-50/50 dark:bg-rose-500/5' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'}`}>
                                    Existing Slot
                                </button>
                                <button type="button" onClick={() => setRescheduleMode('custom')}
                                    className={`flex-1 flex items-center justify-center gap-2 py-3 text-[10px] font-black uppercase tracking-widest transition-colors ${rescheduleMode === 'custom' ? 'text-rose-600 dark:text-rose-400 border-b-2 border-rose-500 bg-rose-50/50 dark:bg-rose-500/5' : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'}`}>
                                    Custom Schedule
                                </button>
                            </div>

                            <div className="p-6 space-y-4">
                                {rescheduleMode === 'existing' ? (
                                    <div>
                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Select Makeup Slot</label>
                                        <select value={selectedMakeupSlot} onChange={e => setSelectedMakeupSlot(e.target.value)}
                                            className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none cursor-pointer">
                                            <option value="" disabled>-- Select a slot --</option>
                                            {makeupSlots.map(s => (
                                                <option key={s.id} value={s.id}>{s.date} • {s.time} ({s.panel})</option>
                                            ))}
                                        </select>
                                        {makeupSlots.length === 0 && (
                                            <p className="text-xs text-rose-500 mt-2 font-bold">No makeup slots available. Use Custom Schedule instead.</p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Date</label>
                                                <input required type="date" value={customReschedule.date} onChange={e => setCustomReschedule(f => ({ ...f, date: e.target.value }))}
                                                    className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Time</label>
                                                <select required value={customReschedule.time} onChange={e => setCustomReschedule(f => ({ ...f, time: e.target.value }))}
                                                    className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none cursor-pointer">
                                                    <option value="" disabled>-- Time --</option>
                                                    {TIME_OPTIONS.map(opt => (
                                                        <option key={opt} value={opt}>{opt}</option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Panel / Evaluator</label>
                                            <select required value={customReschedule.panel} onChange={e => setCustomReschedule(f => ({ ...f, panel: e.target.value }))}
                                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none cursor-pointer">
                                                <option value="" disabled>-- Select mentor --</option>
                                                {panelOptions.map(name => (
                                                    <option key={name} value={name}>{name}</option>
                                                ))}
                                            </select>
                                        </div>
                                        {/* Presentation Mode / Room Selection */}
                                        <div>
                                            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Presentation Mode</label>
                                            <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-xl shadow-inner mb-4">
                                                <button type="button" onClick={() => {
                                                    setRescheduleVenueMode('offline');
                                                    setCustomReschedule(f => ({ ...f, room: rescheduleSelectedRoom === '_custom_' ? rescheduleCustomRoom : rescheduleSelectedRoom }));
                                                }} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${rescheduleVenueMode === 'offline' ? 'bg-white dark:bg-slate-700 text-rose-600 dark:text-rose-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                                    <DoorOpen className="w-4 h-4 mr-2" /> Offline
                                                </button>
                                                <button type="button" onClick={() => {
                                                    setRescheduleVenueMode('online');
                                                    setCustomReschedule(f => ({ ...f, room: 'Online' }));
                                                }} className={`flex-1 py-2 text-xs font-black uppercase tracking-widest rounded-lg flex items-center justify-center transition-all ${rescheduleVenueMode === 'online' ? 'bg-white dark:bg-slate-700 text-rose-600 dark:text-rose-400 shadow-sm' : 'text-slate-500 dark:text-slate-400'}`}>
                                                    <Video className="w-4 h-4 mr-2" /> Online
                                                </button>
                                            </div>
                                        </div>

                                        {rescheduleVenueMode === 'offline' ? (
                                            <div className="space-y-4">
                                                <div>
                                                    <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Room / Venue</label>
                                                    <select required={rescheduleVenueMode === 'offline'} value={rescheduleSelectedRoom} onChange={e => {
                                                        const val = e.target.value;
                                                        setRescheduleSelectedRoom(val);
                                                        setCustomReschedule(f => ({ ...f, room: val === '_custom_' ? rescheduleCustomRoom : val }));
                                                    }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none cursor-pointer">
                                                        <option value="" disabled>-- Select room --</option>
                                                        {roomOptions.map(room => (
                                                            <option key={room} value={room}>{room}</option>
                                                        ))}
                                                        <option value="_custom_">-- Custom Room --</option>
                                                    </select>
                                                </div>
                                                {rescheduleSelectedRoom === '_custom_' && (
                                                    <div>
                                                        <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Custom Room Name</label>
                                                        <input required={rescheduleSelectedRoom === '_custom_'} type="text" placeholder="e.g. Lab 403" value={rescheduleCustomRoom} onChange={e => {
                                                            const val = e.target.value;
                                                            setRescheduleCustomRoom(val);
                                                            setCustomReschedule(f => ({ ...f, room: val }));
                                                        }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                                    </div>
                                                )}
                                            </div>
                                        ) : (
                                            <div>
                                                <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1.5">Google Meet Link</label>
                                                <div className="flex gap-2">
                                                    <div className="relative flex-1">
                                                        <Video className="w-4 h-4 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                                        <input required={rescheduleVenueMode === 'online'} type="url" placeholder="Auto-created on confirm, or generate now" value={customReschedule.meetLink || ''} onChange={e => {
                                                            const val = e.target.value;
                                                            setCustomReschedule(f => ({ ...f, meetLink: val }));
                                                        }} className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-rose-500 dark:text-white outline-none" />
                                                    </div>
                                                    <button type="button" disabled={generatingMeet || !customReschedule.date || !customReschedule.time}
                                                        onClick={() => generateMeetLink({ date: customReschedule.date, time: customReschedule.time, team: selectedStudent?.team, room: 'Online' }, setCustomReschedule)}
                                                        className="px-4 py-2.5 bg-rose-50 hover:bg-rose-100 dark:bg-rose-500/10 dark:hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 rounded-xl text-xs font-black uppercase tracking-widest transition-all border border-rose-100 dark:border-rose-500/20 disabled:opacity-50 shrink-0">
                                                        {generatingMeet ? '…' : 'Generate'}
                                                    </button>
                                                </div>
                                                <p className="text-[10px] text-slate-400 mt-1 font-bold">Leave blank and a real Meet is created automatically when you confirm.</p>
                                            </div>
                                        )}
                                        </div>
                                    )}
                                    <div className="p-4 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl flex items-start">
                                        <AlertTriangle className="w-5 h-5 text-amber-500 mr-3 mt-0.5 shrink-0" />
                                        <p className="text-xs font-bold text-amber-700 dark:text-amber-400">This will mark all pending absent members of team {teamLabel(selectedStudent?.team, allTeams.find(t => t.id === selectedStudent?.team) || null, semesterMap)} as rescheduled. Please ensure the panel is informed.</p>
                                    </div>
                                </div>
                                <div className="p-5 bg-slate-50/50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex justify-end gap-3">
                                    <button onClick={closeRescheduleModal} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button onClick={handleReschedule} disabled={rescheduleMode === 'existing' ? !selectedMakeupSlot : (!customReschedule.date || !customReschedule.time || !customReschedule.panel)} className="px-5 py-2.5 text-xs font-black uppercase tracking-widest text-white bg-rose-600 hover:bg-rose-700 disabled:bg-rose-300 rounded-xl transition-colors shadow-lg shadow-rose-500/30 flex items-center">
                                        <RefreshCcw className="w-4 h-4 mr-2" /> Confirm Reschedule
                                    </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
