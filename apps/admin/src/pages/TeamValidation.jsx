import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, ShieldAlert, AlertTriangle, Eye, Shield, Users, X, User, Clock, UserPlus, Lock, DatabaseZap, Filter, Plus, UserMinus, Send, Hourglass, RefreshCw, Search, Crown, Edit, Github, Code, Tag, Save, ExternalLink, Trash2, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { api } from '../services/api';
import { teamLabel, sortByTeamNumber, teamNumber } from '../lib/teamUtils';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { getAuthHeaders } from '../lib/api';
import { normalizeYearToNumber } from '../lib/globalFilters';
import { getApiBaseUrl } from '../lib/apiBase';

import PsArchitecturePlanModal from '../components/PsArchitecturePlanModal';
import NotifyPendingModal from '../components/NotifyPendingModal';


export default function TeamValidation() {
    const { semesterMap, filterRows, filters } = useGlobalFilters();
    const [teams, setTeams] = useState([]);
    const [unassigned, setUnassigned] = useState([]);
    const [selectedTeam, setSelectedTeam] = useState(null);
    const [selectedPsForAnalysis, setSelectedPsForAnalysis] = useState(null);
    const [problemStatements, setProblemStatements] = useState([]);
    const [globalLock, setGlobalLock] = useState(false);
    const [teamSearch, setTeamSearch] = useState('');
    const [teamSortOrder, setTeamSortOrder] = useState('asc'); // 'asc' = 1 -> N, 'desc' = N -> 1
    const [branchFilter, setBranchFilter] = useState('');
    const [domainFilter, setDomainFilter] = useState('');
    const [isNotifyModalOpen, setIsNotifyModalOpen] = useState(false);
    const [mentorFilter, setMentorFilter] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [selectedUnassigned, setSelectedUnassigned] = useState('');
    const [filterOptions, setFilterOptions] = useState({ branches: [], domains: [], mentors: [] });
    const [maxTeamSize, setMaxTeamSize] = useState(3);
    const [customAssignLeader, setCustomAssignLeader] = useState(null);
    const [customAssignMembers, setCustomAssignMembers] = useState([]);
    const [joinRequests, setJoinRequests] = useState([]); // pending requests for selected team
    const [sendingRequest, setSendingRequest] = useState(false);
    const [allPendingRequests, setAllPendingRequests] = useState([]); // all pending requests across all teams
    const [lockSaving, setLockSaving] = useState(false);
    const [renumbering, setRenumbering] = useState(false);
    const [bulkAssigning, setBulkAssigning] = useState(false);
    const [bulkPreview, setBulkPreview] = useState(null); // { groups: [...], totalStudents: n }

    // Renumbering re-points team-numbered data at the wrong teams — the backend
    // endpoint now rejects the call outright. Flip back to true only once that is
    // fixed; the handler below is kept so re-enabling is a one-line change.
    const RENUMBER_ENABLED = false;

    const handleRenumberTeams = async () => {
        if (!window.confirm('Renumber all teams sequentially (Team 1, Team 2, ...)?\n\nThis will re-assign team numbers 1 → N for the current active semester on-demand.')) return;
        setRenumbering(true);
        try {
            const semId = filters?.semesterId && filters.semesterId !== 'all' ? filters.semesterId : null;
            const res = await api.renumberTeams(semId);
            alert(`✅ ${res.message || 'Teams renumbered successfully!'}`);
            loadData();
        } catch (err) {
            console.error(err);
            alert('Failed to renumber teams: ' + (err.message || 'Unknown error'));
        } finally {
            setRenumbering(false);
        }
    };

    // Admin project details states
    const [editingDetails, setEditingDetails] = useState(false);
    const [teamProjectTitle, setTeamProjectTitle] = useState('');
    const [teamDescription, setTeamDescription] = useState('');
    const [teamDomain, setTeamDomain] = useState('');
    const [teamRepoUrl, setTeamRepoUrl] = useState('');
    const [teamTechStack, setTeamTechStack] = useState('');
    const [loadingProjectDetails, setLoadingProjectDetails] = useState(false);
    const [savingProjectDetails, setSavingProjectDetails] = useState(false);

    // Teams store a copy of the allotted project's title/description, so the canonical
    // record is resolved by title — the same join key Project Allocation uses. When no
    // problem statement matches (custom/legacy allotment), fall back to the team's own
    // copy so the blueprint still renders, just without a PS code.
    const resolveAllottedPs = (team) => {
        if (!team) return null;
        const teamTitle = String(team.title || '').trim().toLowerCase();
        const matched = teamTitle
            ? problemStatements.find(ps => String(ps.title || '').trim().toLowerCase() === teamTitle)
            : null;

        if (matched) {
            return {
                ...matched,
                description: matched.description || team.description,
                domain: matched.domain || team.domain || 'General',
            };
        }

        return {
            id: null,
            title: team.title,
            description: team.description,
            domain: team.domain || 'General',
            difficulty: 'Medium',
        };
    };

    const loadData = () => {
        // Fetch teams
        api.getTeams().then(res => {
            const data = Array.isArray(res) ? res : res.data || [];
            const mappedTeams = data.map(t => {
                let parsedMembers = [];
                if (Array.isArray(t.members)) {
                    parsedMembers = t.members;
                } else if (typeof t.members === 'string') {
                    try { parsedMembers = JSON.parse(t.members); } catch { /* non-fatal: fall through to the default below */ }
                }
                
                const mappedMembers = parsedMembers.map(s => {
                    if (typeof s === 'string') return { id: s, name: s, roll: 'N/A', branch: 'N/A' };
                    return {
                        id: String(s.id || s.student_id || s.roll || s.roll_number || ''),
                        name: s.name || s.student_id || 'Unknown',
                        roll: s.roll || s.roll_number || s.student_id || 'N/A',
                        branch: s.branch || 'N/A'
                    };
                });

                // Resolve leader: DB may store leader as roll number or name — resolve to name
                const leaderRaw = String(t.leader || 'Unknown');
                const leaderMember = mappedMembers.find(m =>
                    m.id === leaderRaw || m.roll === leaderRaw || m.name === leaderRaw
                );
                const leaderName = leaderMember ? leaderMember.name : leaderRaw;
                const leaderRoll = leaderMember ? leaderMember.roll : leaderRaw;

                const rawTitle = t.title || 'Untitled';
                const isCorruptTitle = /^team\s*\d{6,}$/i.test(rawTitle.trim()) || /^team\s*[0-9a-f-]{8,}$/i.test(rawTitle.trim());
                const cleanTitle = isCorruptTitle ? teamLabel(t.id, t, semesterMap) : rawTitle;

                return {
                    id: t.id,       // full UUID — no truncation
                    uuid: t.id,     // kept for backwards compat
                    team_number: t.team_number,
                    title: cleanTitle,
                    description: t.description || 'No proposal description provided.',
                    leader: leaderName,
                    leaderRoll: leaderRoll,
                    leaderRaw: leaderRaw,   // raw DB value for backend updates
                    domain: t.domain || 'General',
                    mentor: (() => {
                        const raw = t.mentor;
                        if (!raw) return '--';
                        try {
                            const parsed = JSON.parse(raw);
                            if (Array.isArray(parsed)) {
                                return parsed.join(', ');
                            }
                            return String(parsed);
                        } catch {
                            return String(raw);
                        }
                    })(),
                    memberCount: t.memberCount || mappedMembers.length || 0,
                    validationStatus: t.validationStatus ? t.validationStatus.charAt(0).toUpperCase() + t.validationStatus.slice(1) : 'Pending',
                    members: mappedMembers,
                    semester_id: t.semester_id,
                    year: t.year
                };
            });
            setTeams(mappedTeams);

            // Restore globalLock state: if ALL teams are Valid, consider it locked
            if (mappedTeams.length > 0 && mappedTeams.every(t => t.validationStatus === 'Valid')) {
                setGlobalLock(true);
            } else {
                setGlobalLock(false);
            }
            
            // Compute filter options from loaded teams (avoids empty API stub)
            const branches = [...new Set([
                'BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)',
                ...mappedTeams.flatMap(t => t.members.map(m => m.branch).filter(b => b && b !== 'N/A'))
            ])];
            const domains = [...new Set(mappedTeams.map(t => t.domain).filter(d => d && d !== 'General'))].sort();
            const mentors = [...new Set(
                mappedTeams.flatMap(t => {
                    if (!t.mentor || t.mentor === '--') return [];
                    return t.mentor.split(', ').map(m => m.trim());
                })
            )].sort().map(name => ({ name }));
            setFilterOptions({ branches, domains, mentors });

            if (selectedTeam) {
                const updatedTeam = mappedTeams.find(mt => mt.uuid === selectedTeam.uuid);
                if (updatedTeam) setSelectedTeam(updatedTeam);
            }
        }).catch(err => console.error("Error loading teams", err));

        // Fetch unassigned
        api.getUnassignedStudents().then(res => {
            const data = Array.isArray(res) ? res : res.data || [];
            setUnassigned(data.map(u => ({
                id: u.id,
                name: u.name,
                roll: u.roll,
                branch: u.branch,
                year: u.year
            })));
        }).catch(err => console.error("Error loading unassigned students", err));

        // Fetch config max team size
        api.getActiveSemester().then(res => {
            if (res && res.data) {
                setMaxTeamSize(res.data.team_size_max || 3);
            }
        }).catch(err => console.error("Error loading config", err));

        // Fetch ALL pending join requests (for sidebar badges)
        const API_BASE = getApiBaseUrl();
        fetch(`${API_BASE}/api/data/team_join_requests`, {
            headers: getAuthHeaders()
        }).then(r => r.json()).then(json => {
            const all = json.data || [];
            setAllPendingRequests(all.filter(r => r.status === 'pending'));
        }).catch(() => setAllPendingRequests([]));
    };

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 15000); // poll every 15s — 3s was too aggressive and caused request flooding
        return () => clearInterval(interval);
    }, [filters.semesterId, filters.year, filters.branch]);

    // Problem statements are the canonical source for an allotted project's blueprint.
    // The team row only carries a copy of the title/description, so the modal needs the
    // real record to show the correct PS code, domain and full specification.
    useEffect(() => {
        let cancelled = false;
        api.getProblemStatements()
            .then(res => {
                if (cancelled) return;
                const rows = Array.isArray(res) ? res : res?.data || [];
                setProblemStatements(rows);
            })
            .catch(err => console.warn('Failed to load problem statements for blueprint view:', err.message));
        return () => { cancelled = true; };
    }, []);

    useEffect(() => {
        if (teams.length > 0) {
            const params = new URLSearchParams(window.location.search);
            const teamIdParam = params.get('teamId');
            if (teamIdParam) {
                const target = teams.find(t => t.id === teamIdParam || t.uuid === teamIdParam);
                if (target) {
                    setSelectedTeam(target);
                    // Clear the query parameter from the browser history
                    window.history.replaceState({}, document.title, window.location.pathname);
                }
            }
        }
    }, [teams]);

    const handleAction = async (id, newStatus) => {
        try {
            const team = teams.find(t => t.id === id);
            if (!team) return;
            
            if (newStatus === 'Valid') {
                await api.validateTeam(team.uuid);
            } else if (newStatus === 'Invalid') {
                await api.manualOverrideTeam(team.uuid, "Manual override from dashboard");
            }
            loadData();
        } catch (err) {
            console.error(err);
        }
    };

    const handleDeleteTeam = async (team) => {
        if (!window.confirm(`Delete ${team.title || 'this team'} (${team.members?.length || 0} members will become unassigned)?\n\nThis will NOT delete student accounts.`)) return;
        try {
            await api.deleteTeam(team.uuid, team.members || []);
            if (selectedTeam?.uuid === team.uuid) setSelectedTeam(null);
            loadData();
            alert(`✅ Team deleted. ${team.members?.length || 0} student(s) moved back to unassigned.`);
        } catch (err) {
            console.error(err);
            alert('Failed to delete team: ' + (err.message || 'Unknown error'));
        }
    };


    // Feature 4 — Send join request (team must accept via student portal)
    const handleSendRequest = async (team) => {
        if (!selectedUnassigned || sendingRequest) return;
        const student = unassigned.find(u => u.id === selectedUnassigned);
        if (!student) return;
        setSendingRequest(true);
        try {
            await api.sendJoinRequest(student, team.uuid, team.title, team.members);
            setSelectedUnassigned('');
            // Reload join requests for this team (modal panel)
            const res = await api.getTeamJoinRequests(team.uuid);
            setJoinRequests(res.data || []);
            // Also refresh sidebar badges
            loadData();
        } catch (err) {
            console.error('Error sending join request:', err);
            alert('Failed to send request. Make sure the team_join_requests table exists in Supabase.');
        } finally {
            setSendingRequest(false);
        }
    };

    const handleCancelRequest = async (requestId) => {
        if (!window.confirm('Cancel this join request?')) return;
        try {
            await api.cancelJoinRequest(requestId);
            // Remove from modal list immediately
            setJoinRequests(prev => prev.filter(r => r.id !== requestId));
            // Remove from sidebar badge immediately (no loadData needed)
            setAllPendingRequests(prev => prev.filter(r => r.id !== requestId));
        } catch (err) {
            console.error('Error cancelling request:', err);
        }
    };

    // Force-add the currently selected unassigned student straight onto the team,
    // skipping the leader accept/decline step entirely.
    const handleForceAdd = async (team) => {
        if (!selectedUnassigned || sendingRequest) return;
        const student = unassigned.find(u => u.id === selectedUnassigned);
        if (!student) return;
        if (!window.confirm(`Add ${student.name} (${student.roll}) directly to ${team.title || 'this team'}? No approval from the team leader is required.`)) return;
        setSendingRequest(true);
        try {
            await api.forceAddToTeam(student.id, team.uuid, 'MEMBER');
            setSelectedUnassigned('');
            const res = await api.getTeamJoinRequests(team.uuid);
            setJoinRequests(res.data || []);
            setSelectedTeam(null);
            await new Promise(r => setTimeout(r, 400));
            loadData();
        } catch (err) {
            console.error('Force add error:', err);
            alert('Failed to add student: ' + (err.message || 'Unknown error'));
        } finally {
            setSendingRequest(false);
        }
    };

    // Approve a pending join request on the team's behalf (admin override):
    // adds the student now, marks this request accepted, cancels their others.
    const handleApproveRequest = async (req) => {
        if (!window.confirm(`Approve ${req.student_name}'s request and add them to this team now? This bypasses the team leader.`)) return;
        try {
            await api.acceptJoinRequest(req.id, req.student_id, req.student_name, req.student_branch, selectedTeam.uuid);
            setJoinRequests(prev => prev.filter(r => r.id !== req.id));
            setAllPendingRequests(prev => prev.filter(r => r.id !== req.id));
            setSelectedTeam(null);
            await new Promise(r => setTimeout(r, 400));
            loadData();
        } catch (err) {
            console.error('Error approving request:', err);
            alert('Failed to approve request: ' + (err.message || 'Unknown error'));
        }
    };

    const handleRemoveMember = async (member, teamId) => {
        if (!window.confirm(`Remove ${member.name} from this team? They will appear in the Unassigned list.`)) return;
        try {
            const team = teams.find(t => t.id === teamId);
            if (!team) return;

            await api.removeFromTeam(member.id, team.uuid, member);
            // Close modal — it will reopen with fresh data after reload
            setSelectedTeam(null);
            await new Promise(r => setTimeout(r, 400));
            loadData();
        } catch (err) {
            console.error('Remove member error:', err);
            alert('Failed to remove member: ' + (err.message || 'Unknown error'));
        }
    };

    const handleChangeLeader = async (member, team) => {
        if (!window.confirm(`Make ${member.name} the new team leader?`)) return;
        try {
            const newLeaderValue = member.name;
            let updatedMembers = team.members;
            if (Array.isArray(team.members)) {
                updatedMembers = team.members.map(m => ({
                    ...m,
                    role: (m.name === member.name || m.id === member.id || m.roll === member.id || m.student_id === member.id) ? 'LEADER' : 'MEMBER'
                }));
            }

            const API_BASE = getApiBaseUrl();
            const res = await fetch(`${API_BASE}/api/data/teams_validation/${team.uuid}`, {
                method: 'PATCH',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({
                    row_id: team.uuid,
                    fields: {
                        leader: newLeaderValue,
                        leader_roll: member.roll || member.id,
                        ...(updatedMembers ? { members: updatedMembers } : {})
                    }
                })
            });
            if (!res.ok) throw new Error(await res.text());
            loadData();
        } catch (err) {
            console.error('Error changing leader:', err);
            alert('Failed to change leader. Please try again.');
        }
    };


    // Step 1: Build preview groups and show modal
    const handleBulkAssign = () => {
        if (unassigned.length === 0) return;
        
        // Deduplicate unassigned students by ID and roll number
        const seenIds = new Set();
        const toAssign = unassigned.filter(s => {
            const idKey = String(s.id || '').trim().toLowerCase();
            const rollKey = String(s.roll || '').trim().toLowerCase();
            if ((idKey && seenIds.has(idKey)) || (rollKey && seenIds.has(rollKey))) {
                return false;
            }
            if (idKey) seenIds.add(idKey);
            if (rollKey) seenIds.add(rollKey);
            return true;
        });

        if (toAssign.length === 0) return;
        
        // Group by year and branch (batch)
        const groupsMap = {};
        toAssign.forEach(student => {
            const yearVal = normalizeYearToNumber(student.year) || '4';
            const branchVal = student.branch || 'BTech CSE';
            const key = `${yearVal}_${branchVal}`;
            if (!groupsMap[key]) {
                groupsMap[key] = [];
            }
            groupsMap[key].push(student);
        });

        // Group all unassigned students into teams of max maxTeamSize members
        const effectiveMax = maxTeamSize || 3;
        const groups = [];
        for (let i = 0; i < toAssign.length; i += effectiveMax) {
            groups.push(toAssign.slice(i, i + effectiveMax));
        }

        setBulkPreview({ groups, totalStudents: toAssign.length });
    };

    // Step 2: Confirmed — actually create the teams
    const handleBulkAssignConfirm = async () => {
        if (!bulkPreview || bulkAssigning) return;
        setBulkAssigning(true);
        const { groups } = bulkPreview;
        setBulkPreview(null);
        try {
            let assignedCount = 0;
            let createdTeamsCount = 0;
            const processedStudentIds = new Set();

            for (const group of groups) {
                // Filter group to students not yet processed in this bulk session
                const activeGroup = group.filter(u => {
                    const normId = String(u.id || '').trim().toLowerCase();
                    const normRoll = String(u.roll || '').trim().toLowerCase();
                    if (processedStudentIds.has(normId) || processedStudentIds.has(normRoll)) {
                        return false;
                    }
                    return true;
                });

                if (activeGroup.length === 0) continue;
                const leader = activeGroup[0];
                const memberIds = activeGroup.slice(1).map(u => u.id);

                // Mark group members as processed
                activeGroup.forEach(u => {
                    if (u.id) processedStudentIds.add(String(u.id).trim().toLowerCase());
                    if (u.roll) processedStudentIds.add(String(u.roll).trim().toLowerCase());
                });

                try {
                    const semId = filters?.semesterId && filters.semesterId !== 'all' ? filters.semesterId : null;
                    const res = await api.createCustomTeam(leader.id, memberIds, semId);
                    if (res && !res.skipped && !res.error) {
                        assignedCount += activeGroup.length;
                        createdTeamsCount += 1;
                    }
                } catch (err) {
                    console.error('Failed to create team for group', err);
                }
            }
            alert(`✅ Bulk assignment complete!\n${assignedCount} student(s) grouped into ${createdTeamsCount} new team(s).`);
            loadData();
        } catch (err) {
            console.error(err);
            alert('Bulk assign failed: ' + (err.message || 'Unknown error'));
        } finally {
            setBulkAssigning(false);
        }
    };

    const handleOpenCustomAssign = (student) => {
        setCustomAssignLeader(student);
        setCustomAssignMembers([]);
    };

    const submitCustomAssign = async () => {
        if (!customAssignLeader) return;
        try {
            const semId = filters?.semesterId && filters.semesterId !== 'all' ? filters.semesterId : null;
            await api.createCustomTeam(customAssignLeader.id, customAssignMembers, semId);
            setCustomAssignLeader(null);
            setCustomAssignMembers([]);
            loadData();
            alert('✅ Custom team formed successfully!');
        } catch (err) {
            console.error(err);
            alert('Failed to form custom team: ' + (err.message || 'Unknown error'));
        }
    };

    // Load join requests & project details when a team modal opens
    useEffect(() => {
        if (selectedTeam) {
            setEditingDetails(false);
            
            // 1. Fetch join requests
            api.getTeamJoinRequests(selectedTeam.uuid)
                .then(res => setJoinRequests(res.data || []))
                .catch(() => setJoinRequests([]));
                
            // 2. Fetch project details
            setLoadingProjectDetails(true);
            setTeamProjectTitle(selectedTeam.title || '');
            setTeamDescription(selectedTeam.description || '');
            setTeamDomain(selectedTeam.domain || '');
            setTeamRepoUrl('');
            setTeamTechStack('');
            
            const API_BASE = getApiBaseUrl();
            
            Promise.all([
                fetch(`${API_BASE}/api/data/github_data?team_ref=eq.${encodeURIComponent(selectedTeam.uuid)}`, { headers: getAuthHeaders() })
                    .then(r => r.json())
                    .then(json => json.data?.[0]?.repository_url || '')
                    .catch(() => ''),
                fetch(`${API_BASE}/api/data/proposals?teamId=eq.${selectedTeam.uuid}`, { headers: getAuthHeaders() })
                    .then(r => r.json())
                     .then(json => {
                         const props = json.data || [];
                         const latest = props.length > 0 ? props[props.length - 1] : null;
                         return latest ? latest.technology_stack || '' : '';
                     })
                     .catch(() => '')
            ]).then(([repoUrl, techStack]) => {
                setTeamRepoUrl(repoUrl);
                setTeamTechStack(techStack);
                setLoadingProjectDetails(false);
            }).catch(() => {
                setLoadingProjectDetails(false);
            });
        } else {
            setJoinRequests([]);
            setSelectedUnassigned('');
            setEditingDetails(false);
        }
    }, [selectedTeam]);

    const handleSaveProjectDetails = async (e) => {
        if (e) e.preventDefault();
        setSavingProjectDetails(true);
        const errors = [];
        try {
            const API_BASE = getApiBaseUrl();
            const headers = getAuthHeaders({ 'Content-Type': 'application/json' });
            
            // 1. Update teams_validation (title, description, domain)
            try {
                const tvRes = await fetch(`${API_BASE}/api/data/teams_validation/${selectedTeam.uuid}`, {
                    method: 'PATCH',
                    headers,
                    body: JSON.stringify({
                        row_id: selectedTeam.uuid,
                        fields: {
                            title: teamProjectTitle.trim(),
                            description: teamDescription.trim(),
                            domain: teamDomain.trim()
                        }
                    })
                });
                if (!tvRes.ok) {
                    const errJson = await tvRes.json().catch(() => ({}));
                    // Pydantic may return detail as an array of error objects — stringify safely
                    const rawDetail = errJson.detail;
                    const errMsg = Array.isArray(rawDetail)
                        ? rawDetail.map(e => e.msg || JSON.stringify(e)).join('; ')
                        : (typeof rawDetail === 'string' ? rawDetail : tvRes.statusText);
                    // Only treat as error if not the "approved proposal" conflict
                    if (!errMsg.includes('approved custom proposal')) {
                        errors.push(`Title/Description: ${errMsg}`);
                    }
                    // Even if blocked by proposal, we continue to save the repo URL below
                }
            } catch (tvErr) {
                errors.push(`Title save error: ${tvErr.message}`);
            }
            
            // 2. Update github_data repository_url — ALWAYS runs regardless of step 1
            // Keyed by the team's immutable team_ref (its teams_validation.id), not the
            // display-only team number, which can be absent or stale (e.g. teams without
            // a team_number yet) and is rejected by the DB's team-identity trigger.
            const numericId = teamNumber(selectedTeam.uuid, selectedTeam);
            if (selectedTeam.uuid && teamRepoUrl.trim()) {
                try {
                    const ghCheck = await fetch(`${API_BASE}/api/data/github_data?team_ref=eq.${encodeURIComponent(selectedTeam.uuid)}`, { headers });
                    const ghJson = await ghCheck.json();
                    const existingRow = ghJson.data?.[0];

                    if (existingRow) {
                        const repoRes = await fetch(`${API_BASE}/api/data/github_data/${existingRow.id}`, {
                            method: 'PATCH',
                            headers,
                            body: JSON.stringify({
                                row_id: existingRow.id,
                                fields: { repository_url: teamRepoUrl.trim() }
                            })
                        });
                        if (!repoRes.ok) {
                            const errJson = await repoRes.json().catch(() => ({}));
                            errors.push(`Repo URL: ${errJson.detail || repoRes.statusText}`);
                        }
                    } else {
                        const upsertRes = await fetch(`${API_BASE}/api/data/github_data/upsert`, {
                            method: 'POST',
                            headers,
                            body: JSON.stringify({
                                rows: [{ team_ref: selectedTeam.uuid, ...(numericId ? { team_id: numericId } : {}), repository_url: teamRepoUrl.trim() }],
                                onConflict: 'team_ref'
                            })
                        });
                        if (!upsertRes.ok) {
                            const errJson = await upsertRes.json().catch(() => ({}));
                            errors.push(`Repo URL (create): ${errJson.detail || upsertRes.statusText}`);
                        }
                    }
                } catch (repoErr) {
                    errors.push(`Repo URL error: ${repoErr.message}`);
                }
            }
            
            // 3. Update proposals tech_stack, title, description and status based on whether it is a placeholder
            try {
                const propRes = await fetch(`${API_BASE}/api/data/proposals?teamId=eq.${selectedTeam.uuid}`, { headers });
                const propJson = await propRes.json();
                const props = propJson.data || [];
                const latest = props.length > 0 ? props[props.length - 1] : null;
                
                const isPlaceholder = !teamProjectTitle.trim() || 
                                      teamProjectTitle.trim().toLowerCase() === "custom team" || 
                                      /^team\s*-?\s*\d+$/i.test(teamProjectTitle.trim());

                if (latest) {
                    const patchRes = await fetch(`${API_BASE}/api/data/proposals/${latest.id}`, {
                        method: 'PATCH',
                        headers,
                        body: JSON.stringify({
                            row_id: latest.id,
                            fields: { 
                                title: teamProjectTitle.trim() || `Team ${teamNumber(selectedTeam.uuid, selectedTeam) || '1'}`,
                                description: teamDescription.trim(),
                                technology_stack: teamTechStack.trim(),
                                status: isPlaceholder ? 'Pending' : 'Approved'
                            }
                        })
                    });
                    if (!patchRes.ok) {
                        const errJson = await patchRes.json().catch(() => ({}));
                        errors.push(`Proposal: ${errJson.detail || patchRes.statusText}`);
                    }
                } else {
                    const activeSemId = selectedTeam.semester_id || 'fbda379f-a0c3-4a78-9570-92baf5a84ba1';
                    const newPropId = 'PROP-' + Math.random().toString(36).substring(2, 9).toUpperCase();
                    await fetch(`${API_BASE}/api/data/proposals/upsert`, {
                        method: 'POST',
                        headers,
                        body: JSON.stringify({
                            rows: [{
                                id: newPropId,
                                teamId: selectedTeam.uuid,
                                semester_id: activeSemId,
                                title: teamProjectTitle.trim() || selectedTeam.title,
                                description: teamDescription.trim() || selectedTeam.description,
                                technology_stack: teamTechStack.trim(),
                                status: isPlaceholder ? 'Pending' : 'Approved'
                            }],
                            onConflict: 'id'
                        })
                    });
                }
            } catch (propErr) {
                errors.push(`Proposal error: ${propErr.message}`);
            }
            
            if (errors.length > 0) {
                alert('Saved with some warnings:\n' + errors.join('\n'));
            } else {
                alert('Project details saved successfully!');
            }
            
            setSelectedTeam(prev => ({
                ...prev,
                title: teamProjectTitle.trim(),
                description: teamDescription.trim(),
                domain: teamDomain.trim()
            }));
            
            setEditingDetails(false);
            loadData();
        } catch (err) {
            console.error('Error saving details:', err);
            alert('Failed to save project details: ' + err.message);
        } finally {
            setSavingProjectDetails(false);
        }

    };

    const filteredTeams = filterRows([...teams]).sort((a, b) => sortByTeamNumber(a, b, teamSortOrder)).filter(t => {
        try {
            const label = teamLabel(t.uuid, t, semesterMap).toLowerCase();
            const titleStr = String(t.title || '').toLowerCase();
            const leaderStr = String(t.leader || '').toLowerCase();
            const membersStr = t.members.map(m => (m.name || '') + ' ' + (m.roll || '')).join(' ').toLowerCase();
            const matchSearch = teamSearch
                ? label.includes(teamSearch.toLowerCase())
                  || titleStr.includes(teamSearch.toLowerCase())
                  || leaderStr.includes(teamSearch.toLowerCase())
                  || membersStr.includes(teamSearch.toLowerCase())
                : true;
            const matchDomain = domainFilter ? t.domain === domainFilter : true;
            const matchMentor = mentorFilter ? (t.mentor && t.mentor.includes(mentorFilter)) : true;
            // null-safe branch check — some members may lack branch field
            const matchBranch = branchFilter
                ? t.members.some(m => {
                    if (!m || typeof m.branch !== 'string') return false;
                    const mb = m.branch.toLowerCase();
                    const bf = branchFilter.toLowerCase();
                    return mb === bf || mb.includes(bf) || bf.includes(mb);
                })
                : true;
            const matchStatus = statusFilter ? t.validationStatus === statusFilter : true;
            return matchSearch && matchDomain && matchMentor && matchBranch && matchStatus;
        } catch (e) {
            console.warn('Filter error on team', t?.uuid, e);
            return true; // show team rather than crash
        }
    });

    const totalFormed = teams.length;
    const totalValidated = teams.filter(t => t.validationStatus === 'Valid').length;
    const totalPending = teams.filter(t => t.validationStatus !== 'Valid').length;

    const filteredUnassigned = useMemo(() => {
        return unassigned.filter(u => {
            const matchSearch = teamSearch
                ? (u.name || '').toLowerCase().includes(teamSearch.toLowerCase()) ||
                  (u.roll || '').toLowerCase().includes(teamSearch.toLowerCase()) ||
                  (u.branch || '').toLowerCase().includes(teamSearch.toLowerCase())
                : true;
            const matchBranch = branchFilter
                ? String(u.branch || '').toLowerCase().includes(branchFilter.toLowerCase()) || branchFilter.toLowerCase().includes(String(u.branch || '').toLowerCase())
                : true;
            return matchSearch && matchBranch;
        });
    }, [unassigned, teamSearch, branchFilter]);

    return (
        <div className="space-y-8 relative z-10 w-full min-h-[calc(100vh-8rem)]">
            
            {/* Header Banner */}
            <div className="bg-gradient-to-r from-emerald-600 via-emerald-700 to-teal-800 rounded-3xl p-8 text-white shadow-xl relative overflow-hidden flex items-center justify-between border border-emerald-500/30">
                <div className="absolute inset-0 opacity-20 mix-blend-overlay pointer-events-none">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                        <path d="M0,150 C300,50 600,250 1000,100 L1000,300 L0,300 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 lg:w-2/3">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20">
                        <Shield className="w-4 h-4 mr-2" /> Validation Protocol
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Team Group Validations</h1>
                    <p className="text-emerald-100/90 leading-relaxed max-w-lg">Enforce team size constraints and override automated system flags according to the approved semester configuration parameters.</p>
                </div>
                <div className="hidden lg:block relative z-10 opacity-90 drop-shadow-2xl hover:scale-105 transition-transform duration-500">
                    <svg viewBox="0 0 150 150" className="w-48 h-48 text-emerald-100 opacity-90" fill="currentColor">
                        <path d="M75,10 L20,35 L20,70 C20,110 40,140 75,150 C110,140 130,110 130,70 L130,35 L75,10 Z M75,25 L115,45 L115,70 C115,100 100,125 75,135 C50,125 35,100 35,70 L35,45 L75,25 Z M50,75 L65,90 L100,55 L90,45 L65,70 L60,65 L50,75 Z" />
                    </svg>
                </div>
                <button
                    onClick={loadData}
                    title="Refresh data"
                    className="absolute top-4 right-4 z-20 p-2.5 bg-white/10 hover:bg-white/20 border border-white/20 rounded-xl text-white transition-all active:scale-95"
                >
                    <RefreshCw className="w-4 h-4" />
                </button>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
                <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col shadow-sm group hover:-translate-y-1 transition-transform">
                    <span className="text-sm font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">Total Formed</span>
                    <span className="text-4xl font-black text-slate-800 dark:text-white group-hover:text-indigo-600 transition-colors">{totalFormed}</span>
                </div>
                <div className="bg-emerald-50 dark:bg-emerald-500/10 p-6 rounded-3xl border border-emerald-100 dark:border-emerald-500/20 flex flex-col shadow-sm group hover:-translate-y-1 transition-transform">
                    <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-2 flex items-center"><ShieldCheck className="w-4 h-4 mr-1"/> Validated</span>
                    <span className="text-4xl font-black text-emerald-700 dark:text-emerald-300">{totalValidated}</span>
                </div>
                <div className="bg-amber-50 dark:bg-amber-500/10 p-6 rounded-3xl border border-amber-100 dark:border-amber-500/20 flex flex-col shadow-sm group hover:-translate-y-1 transition-transform">
                    <span className="text-sm font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider mb-2 flex items-center"><AlertTriangle className="w-4 h-4 mr-1"/> Pending / Invalid</span>
                    <span className="text-4xl font-black text-amber-700 dark:text-amber-300">{totalPending}</span>
                </div>
            </div>

            {/* Main Area */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                {/* Data Table */}
                <div className="lg:col-span-3 min-w-0">
                    <div className={`bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden transition-all duration-500 ${globalLock ? 'ring-2 ring-amber-500/50' : ''}`}>
                        <div className={`p-6 border-b border-slate-100 dark:border-slate-700/50 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 transition-colors duration-500 ${globalLock ? 'bg-amber-50/50 dark:bg-amber-900/10' : 'bg-slate-50/50 dark:bg-slate-800/50'}`}>
                            <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center">
                                <Users className={`w-5 h-5 mr-2 ${globalLock ? 'text-amber-500' : 'text-indigo-500'}`} /> Database Roster
                                {globalLock && <span className="ml-3 px-2.5 py-1 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 text-[10px] font-black uppercase tracking-widest rounded-md border border-amber-200/50 dark:border-amber-500/30">LOCKED</span>}
                            </h2>
                            <div className="flex flex-wrap items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => setIsNotifyModalOpen(true)}
                                    className="flex items-center px-4 py-2.5 rounded-xl text-sm font-bold shadow-md bg-indigo-600 hover:bg-indigo-700 text-white transition-all shadow-indigo-500/20 active:scale-95 cursor-pointer"
                                    title="Send email reminders to teams pending PS selection or GitHub repository submission"
                                >
                                    <Send className="w-4 h-4 mr-2" /> Email Pending Teams
                                </button>
                                <button onClick={async () => {
                                    if (lockSaving) return;
                                    if (globalLock) {
                                        // Unlock: set all teams back to Pending
                                        if (!window.confirm('Unlock all teams? Students will be able to edit their rosters again.')) return;
                                        setLockSaving(true);
                                        try {
                                            await Promise.all(teams.map(t => 
                                                api.updateTeamValidationStatus(t.uuid, 'Pending')
                                            ));
                                            setGlobalLock(false);
                                            loadData();
                                        } catch (err) {
                                            alert('Failed to unlock teams: ' + (err.message || 'Unknown error'));
                                        } finally {
                                            setLockSaving(false);
                                        }
                                    } else {
                                        // Lock: set all teams to Valid
                                        if (!window.confirm('Lock ALL teams? Students will not be able to edit their rosters from any portal.')) return;
                                        setLockSaving(true);
                                        try {
                                            await Promise.all(teams.map(t => api.validateTeam(t.uuid)));
                                            setGlobalLock(true);
                                            setTimeout(() => loadData(), 800);
                                        } catch (err) {
                                            alert('Failed to lock teams: ' + (err.message || 'Unknown error'));
                                        } finally {
                                            setLockSaving(false);
                                        }
                                    }
                                }} className={`flex items-center px-5 py-2.5 rounded-xl text-sm font-bold shadow-md active:scale-95 transition-all ${lockSaving ? 'opacity-60 cursor-not-allowed' : ''} ${globalLock ? 'bg-amber-100 hover:bg-amber-200 text-amber-700 border border-amber-200 dark:bg-amber-500/20 dark:hover:bg-amber-500/30 dark:text-amber-400 dark:border-amber-500/30 shadow-amber-500/10' : 'bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 border border-transparent shadow-slate-900/20'}`}>
                                    <Lock className="w-4 h-4 mr-2" /> {lockSaving ? 'Saving...' : (globalLock ? 'Unlock Teams' : 'Lock All Teams')}
                                </button>
                                <button
                                    type="button"
                                    disabled={!RENUMBER_ENABLED || renumbering}
                                    onClick={handleRenumberTeams}
                                    title="Temporarily disabled: renumbering mis-links GitHub repos and analysis to the wrong teams"
                                    className="flex items-center px-4 py-2.5 rounded-xl text-sm font-bold shadow-md bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400 cursor-not-allowed"
                                >
                                    <RefreshCw className="w-4 h-4 mr-2" />
                                    Renumber Teams (disabled)
                                </button>
                            </div>
                        </div>
                        <div className="p-4 bg-slate-50/50 dark:bg-slate-800/80 border-b border-slate-100 dark:border-slate-700/50 flex flex-wrap gap-3 items-center">
                            {/* Search */}
                            <div className="relative flex-1 min-w-[200px]">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="Search team, title, leader…"
                                    value={teamSearch}
                                    onChange={e => setTeamSearch(e.target.value)}
                                    className="w-full pl-9 pr-4 py-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm text-slate-700 dark:text-slate-300 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>
                            {/* Sort Button */}
                            <button
                                type="button"
                                onClick={() => setTeamSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                                title={`Sorted by Team Number (${teamSortOrder === 'asc' ? '1 → N' : 'N → 1'}). Click to toggle.`}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 font-bold text-xs rounded-xl border border-indigo-200 dark:border-indigo-500/30 transition-all cursor-pointer shadow-sm active:scale-95 shrink-0"
                            >
                                <ArrowUpDown className="w-3.5 h-3.5" />
                                <span>Team No ({teamSortOrder === 'asc' ? '1 → N' : 'N → 1'})</span>
                            </button>

                            <div className="flex items-center text-slate-500 dark:text-slate-400 font-bold text-sm">
                                <Filter className="w-4 h-4 mr-1" />
                            </div>
                            <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500">
                                <option value="">All Status</option>
                                <option value="Pending">Pending</option>
                                <option value="Valid">Valid</option>
                                <option value="Invalid">Invalid</option>
                            </select>
                            <select value={branchFilter} onChange={e => setBranchFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500">
                                <option value="">All Branches</option>
                                {filterOptions.branches && filterOptions.branches.map(b => (
                                    <option key={b} value={b}>{b}</option>
                                ))}
                            </select>
                            <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500">
                                <option value="">All Domains</option>
                                {filterOptions.domains && filterOptions.domains.map(d => (
                                    <option key={d} value={d}>{d}</option>
                                ))}
                            </select>
                            <select value={mentorFilter} onChange={e => setMentorFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500">
                                <option value="">All Mentors</option>
                                {filterOptions.mentors && filterOptions.mentors.map(m => (
                                    <option key={m.id || m.name} value={m.name}>{m.name}</option>
                                ))}
                            </select>
                            {(teamSearch || statusFilter || branchFilter || domainFilter || mentorFilter) && (
                                <button onClick={() => { setTeamSearch(''); setStatusFilter(''); setBranchFilter(''); setDomainFilter(''); setMentorFilter(''); }} className="text-xs font-bold text-rose-500 hover:text-rose-700 underline">
                                    Clear
                                </button>
                            )}
                        </div>
                        <div className="overflow-x-auto relative">
                            {globalLock && <div className="absolute inset-0 z-10 bg-slate-100/10 dark:bg-slate-900/10 backdrop-blur-[1px] cursor-not-allowed"></div>}
                            <table className="w-full text-left border-collapse">
                        <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700">
                            <tr>
                                <th 
                                    onClick={() => setTeamSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                                    title="Click to toggle sorting by team number"
                                    className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider cursor-pointer select-none hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors inline-flex items-center gap-1.5"
                                >
                                    <span>Team</span>
                                    {teamSortOrder === 'asc' ? <ArrowUp className="w-3.5 h-3.5 text-indigo-500" /> : <ArrowDown className="w-3.5 h-3.5 text-indigo-500" />}
                                </th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Project Title</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Leader</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider text-center">Members</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Status</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {filteredTeams.length === 0 && (
                                <tr><td colSpan={6} className="p-8 text-center text-slate-400 text-sm">No teams match your filters.</td></tr>
                            )}
                            {filteredTeams.map(t => (
                                <tr key={t.uuid} className="hover:bg-slate-50/80 dark:hover:bg-slate-700/20 transition-colors group">
                                    <td className="p-5 whitespace-nowrap">
                                        <span className="inline-block whitespace-nowrap text-sm font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-100 dark:border-indigo-500/20">{teamLabel(t.uuid, t, semesterMap)}</span>
                                    </td>
                                    <td className="p-5">
                                        <div className="text-sm font-bold text-slate-800 dark:text-slate-200">
                                            {(!t.title || t.title === t.name || /^team\s*-?\s*\d+$/i.test(t.title.trim()) || t.title.toLowerCase().startsWith('admin-team')) ? (
                                                <span className="text-slate-400 font-normal italic">No Problem Statement Reserved</span>
                                            ) : (
                                                t.title
                                            )}
                                        </div>
                                    </td>
                                    <td className="p-5">
                                        <div className="flex items-center gap-2">
                                            <div className="w-7 h-7 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center shrink-0">
                                                <Crown className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                                            </div>
                                            <div>
                                                <div className="text-sm font-bold text-slate-800 dark:text-slate-200">{t.leader}</div>
                                                <div className="text-[10px] text-slate-400 font-mono">{t.leaderRoll !== t.leader ? t.leaderRoll : ''}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="p-5 text-center">
                                        <div className="inline-flex items-center justify-center bg-slate-100 dark:bg-slate-800 w-8 h-8 rounded-full font-bold text-xs text-slate-600 dark:text-slate-300 ring-2 ring-white dark:ring-slate-900 shadow-sm">
                                            {t.memberCount}
                                        </div>
                                    </td>
                                    <td className="p-5">
                                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border shadow-sm ${
                                            t.validationStatus === 'Valid' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30' :
                                            t.validationStatus === 'Pending' ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/30' :
                                            'bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/30'
                                        }`}>
                                            {t.validationStatus === 'Valid' && <ShieldCheck className="w-3.5 h-3.5 mr-1" />}
                                            {t.validationStatus === 'Pending' && <Clock className="w-3.5 h-3.5 mr-1" />}
                                            {t.validationStatus === 'Invalid' && <ShieldAlert className="w-3.5 h-3.5 mr-1" />}
                                            {t.validationStatus}
                                        </span>
                                    </td>
                                    <td className="p-5">
                                        <div className="flex items-center justify-end space-x-1 opacity-60 group-hover:opacity-100 transition-opacity">
                                            <button onClick={() => setSelectedTeam(t)} title="View Members" className="p-2 text-blue-600 hover:bg-blue-100 dark:text-blue-400 dark:hover:bg-blue-500/20 rounded-xl transition-all"><Eye className="w-4 h-4" /></button>
                                            <button onClick={() => handleAction(t.uuid, 'Valid')} title="Validate Team" className="p-2 text-emerald-600 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-500/20 rounded-xl transition-all"><ShieldCheck className="w-4 h-4" /></button>
                                            <button onClick={() => handleAction(t.uuid, 'Invalid')} title="Override Invalid" className="p-2 text-amber-600 hover:bg-amber-100 dark:text-amber-400 dark:hover:bg-amber-500/20 rounded-xl transition-all"><AlertTriangle className="w-4 h-4" /></button>
                                            <button onClick={() => handleDeleteTeam(t)} title="Delete Team (unassign members)" className="p-2 text-red-600 hover:bg-red-100 dark:text-red-400 dark:hover:bg-red-500/20 rounded-xl transition-all"><Trash2 className="w-4 h-4" /></button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        {/* Unassigned Sidebar */}
        <div className="lg:col-span-1 min-w-0">
            <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-rose-200/50 dark:border-rose-500/30 overflow-hidden sticky top-8 flex flex-col max-h-[600px]">
                <div className="p-6 border-b border-rose-100 dark:border-rose-700/50 bg-rose-50/50 dark:bg-rose-900/20 flex flex-col justify-center">
                    <div className="flex items-center justify-between mb-2">
                        <h2 className="text-xl font-bold text-slate-800 dark:text-white flex items-center">
                            <UserAlertIcon className="w-5 h-5 mr-2 text-rose-500" /> Unassigned
                        </h2>
                        <div className="px-2.5 py-1 bg-white dark:bg-slate-800 rounded-lg text-xs font-black text-rose-600 dark:text-rose-400 shadow-sm border border-rose-100 dark:border-rose-800">{filteredUnassigned.length}</div>
                    </div>
                    <p className="text-xs text-rose-600/80 dark:text-rose-400/80 font-medium">Students currently isolated from active groups.</p>
                </div>
                
                <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar bg-slate-50/30 dark:bg-slate-900/30">
                    {filteredUnassigned.map(u => {
                        const pendingReq = allPendingRequests.find(r => r.student_id === u.id);
                        return (
                        <div key={u.id} className={`bg-white dark:bg-slate-800 p-4 rounded-2xl border shadow-sm hover:shadow-md transition-shadow group ${
                            pendingReq
                                ? 'border-amber-200 dark:border-amber-500/30 bg-amber-50/30 dark:bg-amber-900/10'
                                : 'border-slate-100 dark:border-slate-700/50'
                        }`}>
                            <div className="flex justify-between items-start mb-3">
                                <div className="flex-1 min-w-0">
                                    <h4 className="font-bold text-sm text-slate-800 dark:text-white leading-tight truncate">{u.name}</h4>
                                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-1">{u.branch}</p>
                                </div>
                                <span className="text-[10px] font-black font-mono text-slate-400 bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded ml-2 shrink-0">{u.roll}</span>
                            </div>
                            {pendingReq ? (
                                <div className="w-full flex flex-col gap-1.5">
                                    <div className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30 rounded-xl">
                                        <Hourglass className="w-3 h-3 shrink-0" />
                                        <span className="text-[10px] font-black uppercase tracking-widest">Approval Pending</span>
                                    </div>
                                    <p className="text-[10px] text-center text-slate-400 dark:text-slate-500 font-medium truncate">
                                        Waiting on <span className="font-bold text-amber-600 dark:text-amber-500">{pendingReq.team_name || teamLabel(pendingReq.team_id, teams.find(t => t.id === pendingReq.team_id), semesterMap)}</span>
                                    </p>
                                </div>
                            ) : (
                                <button onClick={() => handleOpenCustomAssign(u)} className="w-full flex items-center justify-center px-4 py-2 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-600 hover:text-white dark:hover:bg-indigo-500 dark:hover:text-white border border-indigo-100 dark:border-indigo-500/20 rounded-xl text-xs font-bold transition-colors active:scale-[0.98]">
                                    <UserPlus className="w-3.5 h-3.5 mr-1.5" /> Custom Assign
                                </button>
                            )}
                        </div>
                        );
                    })}
                    {filteredUnassigned.length === 0 && (
                        <div className="text-center p-8 text-slate-500 text-sm font-medium">No unassigned students!</div>
                    )}
                </div>

                <div className="p-4 border-t border-slate-100 dark:border-slate-700/50 bg-white dark:bg-slate-800">
                    <button onClick={handleBulkAssign} className="w-full flex items-center justify-center px-4 py-3 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-rose-500/30 transition-all active:scale-95 disabled:opacity-50" disabled={filteredUnassigned.length === 0 || bulkAssigning}>
                        <DatabaseZap className="w-4 h-4 mr-2" /> {bulkAssigning ? 'Assigning...' : 'Bulk Assign'}
                    </button>
                </div>
            </div>
        </div>
    </div>

            {/* Custom Assign Modal */}
            <AnimatePresence>
                {customAssignLeader && (
                    <motion.div key="custom-modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" onClick={() => setCustomAssignLeader(null)}>
                        <motion.div key="custom-modal-content" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden w-full max-w-lg border border-slate-200 dark:border-slate-700" onClick={e => e.stopPropagation()}>
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-center text-white">
                                <div>
                                    <h2 className="text-xl font-black">Custom Assign Team</h2>
                                    <p className="text-indigo-100 mt-1 text-xs">Max members: {maxTeamSize}</p>
                                </div>
                                <button onClick={() => setCustomAssignLeader(null)} className="p-2 text-indigo-200 hover:text-white bg-black/10 hover:bg-black/20 rounded-full transition-colors"><X className="w-5 h-5"/></button>
                            </div>
                            
                            <div className="p-6">
                                <h3 className="text-xs font-bold text-slate-400 uppercase mb-3">Leader</h3>
                                <div className="p-3 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-800 rounded-xl mb-6 flex justify-between items-center">
                                    <div>
                                        <div className="font-bold text-sm dark:text-white">{customAssignLeader.name}</div>
                                        <div className="text-xs text-slate-500">{customAssignLeader.branch}</div>
                                    </div>
                                    <span className="text-xs font-mono bg-white dark:bg-slate-800 px-2 py-1 rounded shadow-sm">{customAssignLeader.roll}</span>
                                </div>
                                
                                <h3 className="text-xs font-bold text-slate-400 uppercase mb-3">Add Members ({customAssignMembers.length + 1} / {maxTeamSize})</h3>
                                <div className="max-h-[250px] overflow-y-auto space-y-2 pr-2 custom-scrollbar">
                                    {unassigned.filter(u => u.id !== customAssignLeader.id).map(u => (
                                        <label key={`add-${u.id}`} className="flex items-center p-3 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-200 dark:border-slate-700 cursor-pointer hover:border-indigo-300 transition-colors">
                                            <input 
                                                type="checkbox" 
                                                className="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500"
                                                checked={customAssignMembers.includes(u.id)}
                                                onChange={(e) => {
                                                    if (e.target.checked) {
                                                        if (customAssignMembers.length + 1 < maxTeamSize) {
                                                            setCustomAssignMembers([...customAssignMembers, u.id]);
                                                        }
                                                    } else {
                                                        setCustomAssignMembers(customAssignMembers.filter(id => id !== u.id));
                                                    }
                                                }}
                                                disabled={!customAssignMembers.includes(u.id) && customAssignMembers.length + 1 >= maxTeamSize}
                                            />
                                            <div className="ml-3 flex-1">
                                                <div className="text-sm font-bold dark:text-white">{u.name}</div>
                                                <div className="text-xs text-slate-500">{u.branch} | {u.roll}</div>
                                            </div>
                                        </label>
                                    ))}
                                    {unassigned.length <= 1 && <div className="text-sm text-slate-500 text-center py-4">No other unassigned students to add.</div>}
                                </div>
                                
                                <div className="mt-6 flex justify-end">
                                    <button onClick={submitCustomAssign} className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-xl transition-colors shadow-lg shadow-indigo-500/30">
                                        Form Custom Team
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Bulk Assign Preview Modal ───────────────────────────── */}
            <AnimatePresence>
                {bulkPreview && (
                    <motion.div
                        key="bulk-preview-backdrop"
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
                        onClick={() => setBulkPreview(null)}
                    >
                        <motion.div
                            key="bulk-preview-content"
                            initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden w-full max-w-2xl border border-slate-200 dark:border-slate-700"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Header */}
                            <div className="bg-gradient-to-r from-rose-600 to-rose-800 p-6 flex justify-between items-center text-white">
                                <div>
                                    <h2 className="text-xl font-black">Bulk Assign Preview</h2>
                                    <p className="text-rose-100 text-sm mt-1">
                                        {bulkPreview.totalStudents} students → {bulkPreview.groups.length} teams of up to {maxTeamSize}
                                    </p>
                                </div>
                                <button onClick={() => setBulkPreview(null)} className="p-2 bg-black/10 hover:bg-black/20 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            {/* Groups preview */}
                            <div className="p-6 overflow-y-auto max-h-[55vh] custom-scrollbar space-y-3">
                                <p className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest mb-4">
                                    Review the proposed groupings before confirming:
                                </p>
                                {bulkPreview.groups.map((group, idx) => (
                                    <div key={idx} className="bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-2xl p-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <span className="text-xs font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400">
                                                New Team {idx + 1}
                                            </span>
                                            <span className="text-[10px] font-bold text-slate-400">{group.length} member{group.length !== 1 ? 's' : ''}</span>
                                        </div>
                                        <div className="space-y-1.5">
                                            {group.map((student, sIdx) => (
                                                <div key={student.id} className="flex items-center gap-2">
                                                    <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 text-[9px] font-black ${sIdx === 0 ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400' : 'bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-400'}`}>
                                                        {sIdx === 0 ? '★' : sIdx + 1}
                                                    </div>
                                                    <span className="text-sm font-bold text-slate-800 dark:text-white">{student.name}</span>
                                                    <span className="text-[10px] font-mono text-slate-400">{student.roll}</span>
                                                    <span className="text-[10px] text-slate-400">{student.branch}</span>
                                                    {sIdx === 0 && (
                                                        <span className="ml-auto text-[9px] font-black uppercase tracking-widest text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-1.5 py-0.5 rounded">
                                                            Leader
                                                        </span>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>

                            {/* Footer */}
                            <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex gap-3">
                                <button
                                    onClick={() => setBulkPreview(null)}
                                    className="flex-1 px-4 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleBulkAssignConfirm}
                                    disabled={bulkAssigning}
                                    className="flex-1 px-4 py-2.5 text-sm font-black text-white bg-rose-600 hover:bg-rose-700 rounded-xl transition-all shadow-lg shadow-rose-500/20 active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2"
                                >
                                    {bulkAssigning
                                        ? <><DatabaseZap className="w-4 h-4 animate-pulse" /> Assigning...</>
                                        : <><DatabaseZap className="w-4 h-4" /> Confirm & Assign All</>
                                    }
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* View Team Modal */}
            <AnimatePresence>
                {selectedTeam && (
                    <motion.div key="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm" onClick={() => setSelectedTeam(null)}>
                        <motion.div key="modal-content" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} transition={{ type: 'spring', duration: 0.5 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl overflow-hidden w-full max-w-2xl border border-slate-200 dark:border-slate-700" onClick={e => e.stopPropagation()}>
                            {/* Modal Header */}
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 sm:p-8 flex justify-between items-start relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-48 h-48 bg-white/10 rounded-full blur-3xl transform translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
                                <div className="relative z-10 text-white flex-1 pr-4">
                                    <div className="flex items-center gap-2 mb-3 flex-wrap">
                                        <span className="inline-flex items-center px-3 py-1 bg-white/20 backdrop-blur-sm rounded-full text-xs font-bold uppercase tracking-wider">
                                            {teamLabel(selectedTeam.id, selectedTeam, semesterMap)}
                                        </span>
                                        {selectedTeam.title && (
                                            <button
                                                type="button"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setSelectedPsForAnalysis(resolveAllottedPs(selectedTeam));
                                                }}
                                                className="p-1 bg-white/20 hover:bg-white/30 text-white rounded-xl transition-all flex items-center gap-1.5 px-2.5 py-1 text-xs font-bold shrink-0 cursor-pointer shadow-sm border border-white/30"
                                                title="View Full Architecture Plan & Specs"
                                            >
                                                <Eye className="w-3.5 h-3.5" /> View Blueprint
                                            </button>
                                        )}
                                    </div>
                                    <h2 className="text-2xl font-black">{selectedTeam.title}</h2>
                                </div>
                                <button onClick={() => setSelectedTeam(null)} className="relative z-10 p-2 text-indigo-200 hover:text-white bg-black/10 hover:bg-black/20 rounded-full transition-colors">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            {/* Modal Body */}
                            <div className="p-6 sm:p-8 overflow-y-auto max-h-[70vh] custom-scrollbar">
                                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                                    <h3 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Team Composition ({selectedTeam.members.length} / {maxTeamSize})</h3>
                                    {selectedTeam.members.length < maxTeamSize && (
                                    <div className="flex items-center space-x-2">
                                        <select value={selectedUnassigned} onChange={(e) => setSelectedUnassigned(e.target.value)} className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 max-w-[160px]">
                                            <option value="" disabled>Select Student...</option>
                                            {unassigned
                                                .filter(u => !joinRequests.some(r => r.student_id === u.id && r.status === 'pending'))
                                                .map(u => <option key={u.id} value={u.id}>{u.name} ({u.roll})</option>)
                                            }
                                        </select>

                                        <button
                                            type="button"
                                            onClick={() => handleSendRequest(selectedTeam)}
                                            disabled={!selectedUnassigned || sendingRequest}
                                            className="flex items-center text-xs font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:bg-slate-400 px-3 py-2 rounded-xl transition-colors shadow-sm cursor-pointer"
                                            title="Send a join request the team leader must accept from the student portal"
                                        >
                                            {sendingRequest
                                                ? <><Hourglass className="w-3 h-3 mr-1 animate-spin" /> Sending...</>
                                                : <><Send className="w-3 h-3 mr-1" /> Send Invite</>
                                            }
                                        </button>

                                        <button
                                            type="button"
                                            onClick={() => handleForceAdd(selectedTeam)}
                                            disabled={!selectedUnassigned || sendingRequest}
                                            className="flex items-center text-xs font-black uppercase tracking-widest text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:bg-slate-400 px-3 py-2 rounded-xl transition-colors shadow-sm cursor-pointer"
                                            title="Add the student to this team immediately, without leader approval"
                                        >
                                            <UserPlus className="w-3 h-3 mr-1" /> Force Add
                                        </button>
                                    </div>
                                    )}
                                </div>
                                <div className="space-y-3">
                                    {selectedTeam.members.map((member) => {
                                        const isLeader = member.id === selectedTeam.leaderRaw
                                            || member.roll === selectedTeam.leaderRaw
                                            || member.name === selectedTeam.leader
                                            || member.roll === selectedTeam.leaderRoll;
                                        return (
                                        <div key={member.id} className={`flex items-center justify-between p-4 rounded-2xl border transition-colors ${
                                            isLeader
                                                ? 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30'
                                                : 'bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50 hover:border-indigo-200 dark:hover:border-indigo-500/30'
                                        }`}>
                                            <div className="flex items-center">
                                                <div className={`w-10 h-10 rounded-full flex items-center justify-center mr-4 shrink-0 shadow-sm border ${
                                                    isLeader
                                                        ? 'bg-amber-100 dark:bg-amber-900/50 border-amber-200 dark:border-amber-500/30'
                                                        : 'bg-indigo-100 dark:bg-indigo-900/50 border-indigo-200/50 dark:border-indigo-500/20'
                                                }`}>
                                                    {isLeader
                                                        ? <Crown className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                                                        : <User className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                                    }
                                                </div>
                                                <div>
                                                    <p className="text-sm font-bold text-slate-800 dark:text-white flex items-center gap-2">
                                                        {member.name}
                                                        {isLeader && (
                                                            <span className="px-2 py-0.5 bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 text-[10px] font-black uppercase rounded-full">
                                                                Leader
                                                            </span>
                                                        )}
                                                    </p>
                                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-mono">{member.roll} {member.branch !== 'N/A' ? `• ${member.branch}` : ''}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                {!isLeader && (
                                                    <button
                                                        onClick={() => handleChangeLeader(member, selectedTeam)}
                                                        title="Make Team Leader"
                                                        className="flex items-center gap-1 px-2 py-1.5 text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-400 bg-amber-100 dark:bg-amber-500/20 hover:bg-amber-200 dark:hover:bg-amber-500/30 rounded-lg transition-colors border border-amber-200 dark:border-amber-500/30"
                                                    >
                                                        <Crown className="w-3 h-3" /> Make Leader
                                                    </button>
                                                )}
                                                <p className="text-sm font-black text-slate-700 dark:text-slate-300 font-mono">{member.roll}</p>
                                                <button onClick={() => handleRemoveMember(member, selectedTeam.id)} className="p-1.5 text-rose-500 hover:bg-rose-100 dark:hover:bg-rose-500/20 rounded-lg transition-colors opacity-60 hover:opacity-100" title="Remove Member">
                                                    <UserMinus className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                        );
                                    })}
                                </div>

                                {/* Project Details / Configurations Section */}
                                <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700/60">
                                    <div className="flex justify-between items-center mb-4">
                                        <h4 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                                            <Code className="w-4 h-4 text-indigo-500" /> Project Workspace Settings
                                        </h4>
                                        {!editingDetails && !loadingProjectDetails && (
                                            <button
                                                onClick={() => setEditingDetails(true)}
                                                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-black uppercase tracking-widest text-indigo-750 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100 dark:hover:bg-indigo-500/20 rounded-lg transition-colors border border-indigo-200 dark:border-indigo-500/35"
                                            >
                                                <Edit className="w-3 h-3" /> Edit Project
                                            </button>
                                        )}
                                    </div>

                                    {loadingProjectDetails ? (
                                        <div className="py-6 flex justify-center items-center">
                                            <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
                                        </div>
                                    ) : editingDetails ? (
                                        <form onSubmit={handleSaveProjectDetails} className="space-y-4 bg-slate-50 dark:bg-slate-900/30 p-5 rounded-2xl border border-slate-150 dark:border-slate-700/40">
                                            <div className="space-y-1.5">
                                                <label className="block text-[10px] font-black text-slate-450 dark:text-slate-500 uppercase tracking-widest">
                                                    Project Title
                                                </label>
                                                <input
                                                    type="text"
                                                    required
                                                    value={teamProjectTitle}
                                                    onChange={e => setTeamProjectTitle(e.target.value)}
                                                    className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-205 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs dark:text-slate-105"
                                                    placeholder="Project Title"
                                                />
                                            </div>

                                            <div className="space-y-1.5">
                                                <label className="block text-[10px] font-black text-slate-455 dark:text-slate-500 uppercase tracking-widest">
                                                    Description / Abstract
                                                </label>
                                                <textarea
                                                    rows="3"
                                                    value={teamDescription}
                                                    onChange={e => setTeamDescription(e.target.value)}
                                                    className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-205 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs dark:text-slate-105 resize-none"
                                                    placeholder="Describe the project..."
                                                />
                                            </div>

                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                <div className="space-y-1.5">
                                                    <label className="block text-[10px] font-black text-slate-450 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1">
                                                        <Tag className="w-3 h-3 text-slate-400" /> Domains
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={teamDomain}
                                                        onChange={e => setTeamDomain(e.target.value)}
                                                        className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-205 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs dark:text-slate-105"
                                                        placeholder="Web Dev, ML, etc."
                                                    />
                                                </div>

                                                <div className="space-y-1.5">
                                                    <label className="block text-[10px] font-black text-slate-450 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1">
                                                        <Code className="w-3 h-3 text-slate-400" /> Technology Stack
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={teamTechStack}
                                                        onChange={e => setTeamTechStack(e.target.value)}
                                                        className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-205 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs dark:text-slate-105"
                                                        placeholder="React, Node.js, etc."
                                                    />
                                                </div>
                                            </div>

                                            <div className="space-y-1.5">
                                                <label className="block text-[10px] font-black text-slate-450 dark:text-slate-500 uppercase tracking-widest flex items-center gap-1">
                                                    <Github className="w-3 h-3 text-slate-400" /> GitHub Repository URL
                                                </label>
                                                <input
                                                    type="url"
                                                    value={teamRepoUrl}
                                                    onChange={e => setTeamRepoUrl(e.target.value)}
                                                    className="w-full px-3 py-2 bg-white dark:bg-slate-800 border border-slate-205 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs dark:text-slate-105"
                                                    placeholder="https://github.com/..."
                                                />
                                            </div>

                                            <div className="flex justify-end gap-2 pt-2">
                                                <button
                                                    type="button"
                                                    onClick={() => setEditingDetails(false)}
                                                    className="px-4 py-2 text-xs font-bold text-slate-605 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-650 transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                                <button
                                                    type="submit"
                                                    disabled={savingProjectDetails}
                                                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-black text-white bg-indigo-600 hover:bg-indigo-755 rounded-xl transition-all shadow-md disabled:opacity-50"
                                                >
                                                    {savingProjectDetails ? (
                                                        <><RefreshCw className="w-3 h-3 animate-spin" /> Saving...</>
                                                    ) : (
                                                        <><Save className="w-3 h-3" /> Save Changes</>
                                                    )}
                                                </button>
                                            </div>
                                        </form>
                                    ) : (
                                        <div className="bg-slate-50 dark:bg-slate-900/35 p-5 rounded-2xl border border-slate-100 dark:border-slate-750/30 space-y-4">
                                            <div>
                                                <h5 className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-1">Project Allocated Title</h5>
                                                <p className="text-sm font-bold text-slate-800 dark:text-white leading-snug">{teamProjectTitle || "No project title customized yet."}</p>
                                            </div>

                                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                                <div>
                                                    <h5 className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-1">Domains</h5>
                                                    <div className="flex flex-wrap gap-1.5 mt-1">
                                                        {teamDomain ? (
                                                            teamDomain.split(',').map((dom, i) => (
                                                                <span key={i} className="text-[10px] font-bold bg-slate-200/50 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 px-2.5 py-1 rounded-md border border-slate-250/30">
                                                                    {dom.trim()}
                                                                </span>
                                                            ))
                                                        ) : (
                                                            <span className="text-xs text-slate-400 italic">No domain set</span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>

                                            {teamRepoUrl && (
                                                <div className="pt-3 border-t border-slate-100 dark:border-slate-800/60">
                                                    <h5 className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-1">GitHub Repository</h5>
                                                    <a
                                                        href={teamRepoUrl}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 font-bold"
                                                    >
                                                        <Github className="w-4 h-4" /> {teamRepoUrl} <ExternalLink className="w-3.5 h-3.5" />
                                                    </a>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* Pending Join Requests Section */}
                                {joinRequests.filter(r => r.status === 'pending').length > 0 && (
                                    <div className="mt-6">
                                        <div className="flex items-center mb-3">
                                            <Hourglass className="w-3.5 h-3.5 text-amber-500 mr-2" />
                                            <h4 className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-widest">
                                                Pending Join Requests ({joinRequests.filter(r => r.status === 'pending').length})
                                            </h4>
                                        </div>
                                        <div className="space-y-2">
                                            {joinRequests.filter(r => r.status === 'pending').map(req => (
                                                <div key={req.id} className="flex items-center justify-between p-3.5 bg-amber-50 dark:bg-amber-500/10 rounded-2xl border border-amber-200/70 dark:border-amber-500/25 gap-3">
                                                    <div className="flex items-center min-w-0">
                                                        <div className="w-9 h-9 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center mr-3 shrink-0">
                                                            <User className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-bold text-slate-800 dark:text-white truncate">{req.student_name}</p>
                                                            <p className="text-xs text-slate-500 dark:text-slate-400">{req.student_branch} • {req.student_roll}</p>
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2 shrink-0">
                                                        <button
                                                            onClick={() => handleApproveRequest(req)}
                                                            title="Approve now and add the student to this team (bypasses the leader)"
                                                            className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] font-black uppercase tracking-widest text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors shadow-sm"
                                                        >
                                                            <UserPlus className="w-3 h-3" /> Approve &amp; Add
                                                        </button>
                                                        <button
                                                            onClick={() => handleCancelRequest(req.id)}
                                                            title="Cancel request"
                                                            className="p-1.5 text-rose-500 hover:bg-rose-100 dark:hover:bg-rose-500/20 rounded-lg transition-colors"
                                                        >
                                                            <X className="w-3.5 h-3.5" />
                                                        </button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                        <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-3 font-medium">
                                            ⓘ The team leader can accept or decline these from the student portal — or use <span className="font-bold text-emerald-600 dark:text-emerald-400">Approve &amp; Add</span> to place the student now.
                                        </p>
                                    </div>
                                )}

                                <div className="mt-8 flex justify-end">
                                    <button onClick={() => setSelectedTeam(null)} className="px-6 py-2.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold text-sm rounded-xl hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors">
                                        Close
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Problem Statement Detailed Analysis Modal */}
            {selectedPsForAnalysis && (
                <PsArchitecturePlanModal
                    ps={selectedPsForAnalysis}
                    onClose={() => setSelectedPsForAnalysis(null)}
                    allocation={selectedTeam ? {
                        ...selectedTeam,
                        team_label: teamLabel(selectedTeam.id, selectedTeam, semesterMap),
                    } : null}
                />
            )}

            {/* Email Pending Teams Modal */}
            <NotifyPendingModal
                isOpen={isNotifyModalOpen}
                onClose={() => setIsNotifyModalOpen(false)}
            />
        </div>
    );
}

// Helper icon
function UserAlertIcon(props) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <line x1="19" y1="8" x2="19" y2="14" />
      <line x1="19" y1="18" x2="19.01" y2="18" />
    </svg>
  );
}
