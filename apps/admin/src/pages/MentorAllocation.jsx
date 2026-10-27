import React, { useState, useEffect, useMemo } from 'react';
import { UserCheck, Shuffle, Search, AlertCircle, Edit3, Briefcase, Zap, X as XIcon, Filter, Check, ShieldCheck, Mail, Star, Users, Plus, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { apiUpsertTable, apiPatchRow, apiDeleteRows, sendMentorAssignmentEmails } from '../lib/api';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';

// Sentinel for the mentor filter's "Unassigned" option — distinct from '' (no
// filter/"All Mentors") and from any real mentor name.
const UNASSIGNED_MENTOR_FILTER = '__unassigned__';

// teams_validation.domain is free text and arrives in three shapes: a single
// label ("General"), a JSON-encoded array ('["Software"]'), or — most often — a
// comma-separated list of a dozen topics. Splitting it into individual tokens is
// what lets the filter match on one domain rather than an exact whole-string
// compare, which no multi-domain team could ever satisfy.
const parseDomains = (raw) => {
    if (!raw) return [];
    const value = String(raw).trim();
    if (value.startsWith('[')) {
        try {
            const parsed = JSON.parse(value);
            if (Array.isArray(parsed)) return parsed.map(d => String(d).trim()).filter(Boolean);
        } catch {
            // Not valid JSON after all — fall through to comma splitting.
        }
    }
    return value.split(',').map(d => d.trim()).filter(Boolean);
};
import { teamLabel, sortByTeamNumber } from '../lib/teamUtils';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { emailPlaceholder } from '../lib/emailPolicy';

export default function MentorAllocation() {
    const { semesterMap, filterRows } = useGlobalFilters();
    const { data: mentors, setData: setMentors } = useSupabaseTableState('mentors', [], { orderBy: 'name' });

    // Manual Mentor Add/Delete state
    const [isAddMentorOpen, setIsAddMentorOpen] = useState(false);
    const [newMentorForm, setNewMentorForm] = useState({
        name: '',
        email: '',
        domain: '',
        expertise: '',
        capacity: '5'
    });

    const handleAddMentor = async (e) => {
        e.preventDefault();
        try {
            const row = {
                id: 'M-' + Date.now().toString().slice(-6),
                name: newMentorForm.name.trim(),
                email: newMentorForm.email.trim(),
                domain: newMentorForm.domain.trim(),
                expertise: newMentorForm.expertise.trim(),
                capacity: parseInt(newMentorForm.capacity) || 5,
                maxLoad: parseInt(newMentorForm.capacity) || 5,
                is_active: true
            };
            const response = await apiUpsertTable('mentors', [row]);
            const saved = response?.[0] || row;
            setMentors(prev => [...prev, saved]);
            setIsAddMentorOpen(false);
            setNewMentorForm({ name: '', email: '', domain: '', expertise: '', capacity: '5' });
            alert('Mentor added successfully!');
        } catch (err) {
            console.error(err);
            alert('Error adding mentor: ' + err.message);
        }
    };

    const handleDeleteMentor = async (mentorId) => {
        if (!confirm("Are you sure you want to delete this mentor? This will remove all their database records.")) return;
        try {
            await apiDeleteRows('mentors', { id: mentorId });
            setMentors(prev => prev.filter(m => m.id !== mentorId));
            alert("Mentor deleted successfully.");
        } catch (err) {
            console.error(err);
            alert("Error deleting mentor: " + err.message);
        }
    };

    const { data: rawTeams, setData: setRawTeams } = useSupabaseTableState('teams_validation', [], { orderBy: 'id' });

    const teams = useMemo(() => {
        return [...rawTeams].sort(sortByTeamNumber).map(t => {
            let assignedMentor = [];
            if (t.mentor) {
                try { assignedMentor = JSON.parse(t.mentor); } catch { assignedMentor = [t.mentor]; }
            }
            if (!Array.isArray(assignedMentor)) assignedMentor = [assignedMentor].filter(Boolean);
            return {
                ...t,
                id: t.id,
                title: t.title || 'Untitled',
                domain: t.domain || 'General',
                keywords: t.keywords || '',
                assignedMentor,
                aiRecommended: t.aiRecommended || '',
                semester_id: t.semester_id,
            };
        });
    }, [rawTeams]);

    const activeLoad = useMemo(() => {
        const counts = {};
        teams.forEach(t => {
            if (Array.isArray(t.assignedMentor)) {
                t.assignedMentor.forEach(mentor => {
                    counts[mentor] = (counts[mentor] || 0) + 1;
                });
            }
        });
        return counts;
    }, [teams]);

    const [setTeams] = useState(() => () => { }); // kept for compat
    const [searchTerm, setSearchTerm] = useState('');
    const [editingTeam, setEditingTeam] = useState(null);
    const [selectedMentors, setSelectedMentors] = useState([]);
    const [editingMentorConfig, setEditingMentorConfig] = useState(null);
    const [isEditingDomains, setIsEditingDomains] = useState(false);
    const [localDomainsStr, setLocalDomainsStr] = useState('');

    useEffect(() => {
        if (editingMentorConfig) {
            const domainsVal = editingMentorConfig.domains;
            const initial = (Array.isArray(domainsVal) && domainsVal.length > 0)
                ? domainsVal.join(', ')
                : (domainsVal || editingMentorConfig.domain || '');
            setLocalDomainsStr(initial);
        } else {
            setLocalDomainsStr('');
        }
    }, [editingMentorConfig]);
    const [domainFilter, setDomainFilter] = useState('');
    const [mentorFilter, setMentorFilter] = useState('');

    // Mentor Search & Filter State
    const [mentorSearchTerm, setMentorSearchTerm] = useState('');
    const [debouncedMentorSearch, setDebouncedMentorSearch] = useState('');
    const [mentorDomainFilter, setMentorDomainFilter] = useState('');
    const [mentorExpertiseFilter, setMentorExpertiseFilter] = useState('');
    const [mentorWorkloadFilter, setMentorWorkloadFilter] = useState('all');
    const [mentorSortBy, setMentorSortBy] = useState('name_asc');

    // Auto-assign feedback
    const [autoBusy, setAutoBusy] = useState(false);
    // The workload cards used to sit on the dashboard permanently, pushing the
    // allocation table below the fold. They are only decision-support for
    // auto-assign, so they now live behind that button.
    const [workloadOpen, setWorkloadOpen] = useState(false);
    const [autoMsg, setAutoMsg] = useState(null); // { type: 'success' | 'warn', text }
    const [sendingMentorEmails, setSendingMentorEmails] = useState(false);
    // '' = every mentor with an assigned team; a mentor name scopes to just them.
    const [mentorEmailModalOpen, setMentorEmailModalOpen] = useState(false);
    const [emailScopeMentor, setEmailScopeMentor] = useState('');
    const [emailNotifyMentor, setEmailNotifyMentor] = useState(true);
    const [emailNotifyTeams, setEmailNotifyTeams] = useState(false);

    // Debounce mentor search
    useEffect(() => {
        const handler = setTimeout(() => {
            setDebouncedMentorSearch(mentorSearchTerm);
        }, 300);
        return () => clearTimeout(handler);
    }, [mentorSearchTerm]);

    // Mentors who have actually been approved for portal access.
    //
    // Self-registration creates a mentor with is_active=false, which means
    // "has requested access, pending an administrator". Those accounts used to
    // appear here as allocatable faculty with a full set of open slots, so a
    // team could be assigned to someone who cannot even log in yet. Approval
    // happens in Views -> pending registrations; until then they are not
    // faculty for allocation purposes.
    //
    // `!== false` on purpose: rows predating the column have is_active
    // undefined and must keep counting as approved. Same convention as the
    // auto-assign pool below.
    const approvedMentors = useMemo(
        () => mentors.filter(m => m.is_active !== false),
        [mentors]
    );
    const pendingMentorCount = mentors.length - approvedMentors.length;

    // Processed Mentors
    const processedMentors = useMemo(() => {
        return approvedMentors.map(m => {
            const load = activeLoad[m.name] || 0;
            const capacity = m.maxLoad || 1;
            const availableSlots = Math.max(0, capacity - load);
            let workloadStatus = 'available';
            if (load >= capacity) workloadStatus = 'full';
            else if (load >= capacity - 1 || (load / capacity) > 0.75) workloadStatus = 'near_capacity';

            return {
                ...m,
                calculatedLoad: load,
                capacity,
                availableSlots,
                workloadStatus
            };
        });
    }, [approvedMentors, activeLoad]);

    // Filtered Mentors for UI
    const filteredMentors = useMemo(() => {
        let result = processedMentors.filter(m => {
            // Search
            if (debouncedMentorSearch) {
                const query = debouncedMentorSearch.toLowerCase();
                const matchesName = m.name?.toLowerCase().includes(query);
                const matchesEmail = m.email?.toLowerCase().includes(query);
                const matchesDomain = m.domain?.toLowerCase().includes(query);
                const matchesExpertise = m.expertise?.toLowerCase().includes(query);
                const matchesSkills = (m.skills || []).some(s => s.toLowerCase().includes(query));
                const matchesDomainsArray = (m.domains || []).some(d => d.toLowerCase().includes(query));

                if (!matchesName && !matchesEmail && !matchesDomain && !matchesExpertise && !matchesSkills && !matchesDomainsArray) {
                    return false;
                }
            }

            // Domain Filter
            if (mentorDomainFilter) {
                const domainLower = mentorDomainFilter.toLowerCase();
                const domMatch = m.domain?.toLowerCase().includes(domainLower);
                const domArrayMatch = (m.domains || []).some(d => d.toLowerCase().includes(domainLower));
                if (!domMatch && !domArrayMatch) {
                    return false;
                }
            }

            // Expertise Filter
            if (mentorExpertiseFilter) {
                const mentorSkills = (m.skills || []).map(s => s.toLowerCase());
                if (!mentorSkills.includes(mentorExpertiseFilter.toLowerCase())) return false;
            }

            // Workload Filter
            if (mentorWorkloadFilter && mentorWorkloadFilter !== 'all') {
                if (mentorWorkloadFilter === 'available_slots' && m.availableSlots <= 0) return false;
                if (mentorWorkloadFilter === 'no_available_slots' && m.availableSlots > 0) return false;
                if (['available', 'near_capacity', 'full'].includes(mentorWorkloadFilter) && m.workloadStatus !== mentorWorkloadFilter) return false;
            }

            return true;
        });

        // Sort
        result.sort((a, b) => {
            if (mentorSortBy === 'name_asc') return (a.name || '').localeCompare(b.name || '');
            if (mentorSortBy === 'name_desc') return (b.name || '').localeCompare(a.name || '');
            if (mentorSortBy === 'workload_lowest') return a.calculatedLoad - b.calculatedLoad;
            if (mentorSortBy === 'workload_highest') return b.calculatedLoad - a.calculatedLoad;
            if (mentorSortBy === 'capacity_most') return b.availableSlots - a.availableSlots;
            return 0;
        });

        return result;
    }, [processedMentors, debouncedMentorSearch, mentorDomainFilter, mentorExpertiseFilter, mentorWorkloadFilter, mentorSortBy]);

    // What auto-assign would actually have to work with, shown on the confirm.
    // Deliberately uses autoAssign's own capacity rule (`maxLoad`, absent = 0)
    // rather than the card's display rule (absent = 1), so the number promises
    // exactly what the run can deliver.
    const { openSlotCount, mentorsWithRoom } = useMemo(() => {
        const capacityOf = (m) => Number(m.maxLoad) || 0;
        const roomFor = (m) => Math.max(0, capacityOf(m) - (activeLoad[m.name] || 0));
        const pool = approvedMentors.filter(m => capacityOf(m) > 0);
        return {
            openSlotCount: pool.reduce((sum, m) => sum + roomFor(m), 0),
            mentorsWithRoom: pool.filter(m => roomFor(m) > 0).length,
        };
    }, [approvedMentors, activeLoad]);

    const pendingTeamCount = useMemo(
        () => teams.filter(t => (t.assignedMentor || []).filter(Boolean).length === 0).length,
        [teams]
    );

    // Escape closes the workload dialog, but never mid-run — dismissing the
    // window while assignments are still being written would hide the outcome.
    useEffect(() => {
        if (!workloadOpen) return;
        const onKeyDown = (e) => {
            if (e.key === 'Escape' && !autoBusy) setWorkloadOpen(false);
        };
        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [workloadOpen, autoBusy]);

    const uniqueMentorExpertise = useMemo(() => {
        const skillsSet = new Set();
        approvedMentors.forEach(m => {
            if (Array.isArray(m.skills)) {
                m.skills.forEach(s => skillsSet.add(s));
            }
        });
        return Array.from(skillsSet).sort();
    }, [approvedMentors]);

    const getRecommendedMentors = (team, mentorsList) => {
        if (!team) return { recommended: [], others: mentorsList.map(m => ({ mentor: m })) };

        const teamDomain = (team.domain || '').toLowerCase();
        const teamTitle = (team.title || '').toLowerCase();

        const scoredMentors = mentorsList.map(m => {
            let score = 0;
            const reasons = [];
            const mDomain = (m.domain || '').toLowerCase();
            const mDomains = Array.isArray(m.domains) ? m.domains.map(d => d.toLowerCase()) : [];
            const mSkills = Array.isArray(m.skills) ? m.skills.map(s => s.toLowerCase()) : [];

            // 1. Primary Domain Match (+50)
            if (mDomain && (mDomain.includes(teamDomain) || teamDomain.includes(mDomain))) {
                score += 50;
                reasons.push('Primary Domain Match');
            }

            // 2. Secondary Domain Match (+30)
            if (mDomains.some(d => d.includes(teamDomain) || teamDomain.includes(d))) {
                score += 30;
                if (!reasons.includes('Primary Domain Match')) reasons.push('Secondary Domain Match');
            }

            // 3. Expertise Match (+15 per skill)
            let expertiseMatches = 0;
            const titleWords = teamTitle.split(' ').filter(w => w.length > 3);
            for (const word of titleWords) {
                if (mSkills.some(s => s.includes(word))) {
                    expertiseMatches++;
                }
            }
            if (expertiseMatches > 0) {
                score += (15 * expertiseMatches);
                reasons.push(`${expertiseMatches} Expertise Matches`);
            }

            // 4. Capacity (+10)
            if (m.availableSlots > 0) {
                score += 10;
                reasons.push(`${m.availableSlots} Available Slots`);
            } else {
                score -= 50; // penalize full mentors heavily so they are not recommended
            }

            // 5. Lower Workload (+5)
            if (m.calculatedLoad < m.capacity && m.calculatedLoad === 0) {
                score += 5;
                reasons.push('Low Workload');
            }

            return { mentor: m, score, reasons };
        });

        scoredMentors.sort((a, b) => b.score - a.score);

        const recommended = scoredMentors.filter(sm => sm.score >= 10);
        const recommendedIds = new Set(recommended.map(sm => sm.mentor.id));
        const others = mentorsList.filter(m => !recommendedIds.has(m.id)).map(m => ({ mentor: m }));

        return { recommended: recommended.slice(0, 3), others };
    };

    const modalMentors = editingTeam ? getRecommendedMentors(editingTeam, processedMentors) : { recommended: [], others: [] };

    const filtered = useMemo(() => filterRows(teams).filter(t => {
        const matchSearch = t.title.toLowerCase().includes(searchTerm.toLowerCase())
            || teamLabel(t.id, t, semesterMap).toLowerCase().includes(searchTerm.toLowerCase());
        // Membership, not equality: a team listing twelve domains should still
        // surface when you filter by any one of them.
        const matchDomain = domainFilter
            ? parseDomains(t.domain).some(d => d.toLowerCase() === domainFilter.toLowerCase())
            : true;
        const matchMentor = mentorFilter
            ? (mentorFilter === UNASSIGNED_MENTOR_FILTER
                ? (t.assignedMentor || []).filter(Boolean).length === 0
                : (Array.isArray(t.assignedMentor) ? t.assignedMentor.includes(mentorFilter) : t.assignedMentor === mentorFilter))
            : true;
        return matchSearch && matchDomain && matchMentor;
    }), [teams, filterRows, searchTerm, domainFilter, mentorFilter, semesterMap]);

    const handleAssign = async () => {
        if (!editingTeam) return;

        // Deselecting everyone means "take this team's mentor away", which is
        // destructive in a way that picking a different mentor is not: the team
        // is left unassigned and drops out of the mentor's workload. Confirm it
        // rather than treating an empty selection as a no-op, which is what
        // this used to do -- silently, with the button merely disabled.
        const isRemoval = selectedMentors.length === 0;
        if (isRemoval) {
            const had = editingTeam.assignedMentor || [];
            if (had.length === 0) { setEditingTeam(null); return; }
            const ok = window.confirm(
                `Remove ${had.join(', ')} from ${editingTeam.title || editingTeam.id}?\n\n`
                + 'The team will have no mentor until one is assigned again.'
            );
            if (!ok) return;
        }

        const removedFrom = editingTeam;
        setEditingTeam(null);
        setSelectedMentors([]);

        try {
            const mentorName = selectedMentors[0] || 'TBD';

            await apiPatchRow('teams_validation', removedFrom.id, { mentor: JSON.stringify(selectedMentors) });

            setRawTeams(prev => prev.map(t => t.id === removedFrom.id ? { ...t, mentor: JSON.stringify(selectedMentors) } : t));

            const nextTeams = teams.map(t => t.id === removedFrom.id ? { ...t, assignedMentor: selectedMentors } : t);
            const updatedMentors = mentors.map(m => {
                const load = nextTeams.filter(t =>
                    Array.isArray(t.assignedMentor) ? t.assignedMentor.includes(m.name) : t.assignedMentor === m.name
                ).length;
                return { ...m, load, teams: load };
            });
            setMentors(updatedMentors);
            await apiUpsertTable('mentors', updatedMentors, 'id');

            await apiUpsertTable('results', [{ team: removedFrom.id, mentor: mentorName }], 'team');

            const updatedTeam = nextTeams.find(t => t.id === removedFrom.id);
            const teamLabel = `${updatedTeam.id}${updatedTeam.title ? ` (${updatedTeam.title})` : ''}`;
            await AuditLogger.logMentorAction(
                getCurrentUser(),
                isRemoval
                    ? `Mentor ${(removedFrom.assignedMentor || []).join(', ')} removed from team ${teamLabel}`
                    : `Mentor ${mentorName} assigned to team ${teamLabel}`
            );
        } catch (error) {
            console.error('Failed to persist mentor assignment:', error.message);
        }
    };

    const handleSaveMentor = async (updatedMentor, oldName) => {
        try {
            // Filter out UI-only derived fields to prevent PostgREST 400 errors on non-existent columns
            // These four are named purely so the rest spread excludes them — they
            // are UI-only derived fields and PostgREST 400s on columns that do not
            // exist. The underscore marks them as deliberately unread; removing the
            // names would put them straight back into dbMentor.
            const { calculatedLoad: _calculatedLoad, capacity: _capacity,
                    availableSlots: _availableSlots, workloadStatus: _workloadStatus,
                    ...dbMentor } = updatedMentor;

            if (updatedMentor.isNew) {
                const newMentor = { ...dbMentor, id: 'MEN' + Math.floor(Math.random() * 10000), load: 0, teams: 0 };
                delete newMentor.isNew;
                await apiUpsertTable('mentors', [newMentor], 'id');
                setMentors([...mentors, newMentor]);
                await AuditLogger.logMentorAction(
                    getCurrentUser(),
                    `New Mentor ${newMentor.name} registered`
                );
            } else {
                const newMentors = mentors.map(m => m.id === updatedMentor.id ? updatedMentor : m);
                setMentors(newMentors);
                await apiUpsertTable('mentors', [dbMentor], 'id');

                if (updatedMentor.name !== oldName) {
                    const affectedTeams = teams.filter(t => t.assignedMentor.includes(oldName) || t.aiRecommended === oldName);
                    if (affectedTeams.length > 0) {
                        const updatedTeams = affectedTeams.map(t => ({
                            ...t,
                            aiRecommended: t.aiRecommended === oldName ? updatedMentor.name : t.aiRecommended,
                            assignedMentor: t.assignedMentor.map(name => name === oldName ? updatedMentor.name : name)
                        }));

                        setTeams(prev => prev.map(t => {
                            const ut = updatedTeams.find(x => x.id === t.id);
                            return ut ? ut : t;
                        }));

                        await apiUpsertTable('mentor_allocations', updatedTeams, 'id');

                        const validationUpdates = updatedTeams.map(t => ({ id: t.id, mentor: JSON.stringify(t.assignedMentor) }));
                        const resultsUpdates = updatedTeams.map(t => ({ team: t.id, mentor: t.assignedMentor[0] || 'TBD' }));

                        for (const update of validationUpdates) {
                            try {
                                await apiPatchRow('teams_validation', update.id, { mentor: update.mentor });
                            } catch (err) {
                                console.error('Failed to cascade sync mentor:', err.message);
                            }
                        }
                        await apiUpsertTable('results', resultsUpdates, 'team');
                    }
                }

                await AuditLogger.logMentorAction(
                    getCurrentUser(),
                    `Mentor ${updatedMentor.name} ${updatedMentor.name !== oldName ? 'updated (renamed from ' + oldName + ')' : 'updated'} - Load: ${updatedMentor.load}, Teams: ${updatedMentor.teams}`
                );
            }
        } catch (error) {
            console.error('Failed to save mentor:', error.message);
        }
        setEditingMentorConfig(null);
    };

    // Rule-based auto-assign over the authoritative, name-based teams_validation
    // model (admin-api REST — unaffected by the blocked Postgres ports). Assigns
    // each pending team to the least-loaded mentor that still has capacity,
    // preferring a domain match. Capacity is `maxLoad` (the column the admin
    // portal uses); the mentor-api's max_teams/current_teams are not involved.
    const autoAssign = async () => {
        if (autoBusy) return;

        const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
        const capacityOf = (m) => Number(m.maxLoad) || 0;

        // Running load per mentor name, seeded from current assignments.
        const load = {};
        approvedMentors.forEach(m => { load[m.name] = activeLoad[m.name] || 0; });

        // Active mentors that have any capacity at all.
        const pool = approvedMentors.filter(m => capacityOf(m) > 0);
        const totalSlots = pool.reduce((s, m) => s + capacityOf(m), 0);
        if (pool.length === 0) {
            setAutoMsg({ type: 'warn', text: 'No active mentors with capacity. Add mentors or set their maxLoad first.' });
            return;
        }

        // Teams needing a mentor. Treat an empty-string mentor (from any prior
        // broken run) as unassigned so this also self-heals that corruption.
        const pending = teams.filter(t => t.assignedMentor.filter(Boolean).length === 0);
        if (pending.length === 0) {
            setAutoMsg({ type: 'success', text: 'Every team already has a mentor — nothing to assign.' });
            return;
        }

        setAutoBusy(true);
        setAutoMsg(null);

        const assignments = []; // { id, title, mentorName }
        for (const t of pending) {
            const withSlots = pool.filter(m => load[m.name] < capacityOf(m));
            if (withSlots.length === 0) break; // capacity exhausted

            const tDomain = norm(t.domain);
            const domainMatch = (tDomain && tDomain !== 'general')
                ? withSlots.filter(m => (Array.isArray(m.domains) ? m.domains : []).some(d => norm(d) === tDomain))
                : [];
            const candidates = domainMatch.length ? domainMatch : withSlots;

            // least-loaded first, then the mentor with the most spare capacity
            candidates.sort((a, b) => (load[a.name] - load[b.name]) || (capacityOf(b) - capacityOf(a)));
            const chosen = candidates[0];
            load[chosen.name] += 1;
            assignments.push({ id: t.id, title: t.title, mentorName: chosen.name });
        }

        try {
            // Persist only the teams we actually assigned, to the authoritative
            // stores — as ONE bulk upsert rather than a PATCH per team. Each
            // team update used to be its own request, so the backend's
            // mentor-assignment notifier (which groups teams by mentor within
            // a single call) only ever saw one team at a time: a mentor picked
            // up in 50 assignments still got 50 separate emails. A single
            // upsert call lets it batch them into one email per mentor.
            if (assignments.length) {
                await apiUpsertTable('teams_validation', assignments.map(a => ({ id: a.id, mentor: JSON.stringify([a.mentorName]) })), 'id');
            }
            if (assignments.length) {
                await apiUpsertTable('results', assignments.map(a => ({ team: a.id, mentor: a.mentorName })), 'team');
            }

            // Refresh the mentor load/teams counters from the final load map.
            const updatedMentors = mentors.map(m => ({ ...m, load: load[m.name] || 0, teams: load[m.name] || 0 }));
            setMentors(updatedMentors);
            await apiUpsertTable('mentors', updatedMentors, 'id');

            // Reflect the new assignments in local state immediately.
            const byId = new Map(assignments.map(a => [a.id, a.mentorName]));
            setRawTeams(prev => prev.map(t => byId.has(t.id)
                ? { ...t, mentor: JSON.stringify([byId.get(t.id)]) }
                : t));

            await AuditLogger.logMentorAction(
                getCurrentUser(),
                `Auto-assign: ${assignments.length} team(s) assigned across ${pool.length} mentor(s)`
            );

            const remaining = pending.length - assignments.length;
            setAutoMsg(remaining > 0
                ? { type: 'warn', text: `Assigned ${assignments.length} team(s). ${remaining} still unassigned — mentor capacity is exhausted (${pool.length} mentors, ${totalSlots} total slots). Add more mentors or raise maxLoad to allocate the rest.` }
                : { type: 'success', text: `Assigned all ${assignments.length} pending team(s).` });
        } catch (error) {
            console.error('Auto-assign failed:', error.message);
            setAutoMsg({ type: 'warn', text: `Auto-assign failed: ${error.message}` });
        } finally {
            setAutoBusy(false);
        }
    };

    // Mentor-team assignment never emails automatically (see
    // notification_agent.py) — this modal is the only way either side gets
    // notified, sent on demand once allocation is settled. Mentor emails are
    // always one per mentor listing every team in scope, never one per team.
    const handleSendMentorEmails = async () => {
        if (!emailNotifyMentor && !emailNotifyTeams) {
            alert('Choose at least one of "Email mentor(s)" or "Email team(s)".');
            return;
        }
        const scopeLabel = emailScopeMentor || 'every mentor with an assigned team';
        const sideLabel = emailNotifyMentor && emailNotifyTeams ? 'mentor(s) and their team(s)'
            : emailNotifyMentor ? 'mentor(s) only'
            : 'team(s)/students only';
        if (!window.confirm(`Send this email now — scope: ${scopeLabel}; recipients: ${sideLabel}?`)) return;
        setSendingMentorEmails(true);
        try {
            const result = await sendMentorAssignmentEmails({
                mentorName: emailScopeMentor || null,
                notifyMentor: emailNotifyMentor,
                notifyTeams: emailNotifyTeams,
            });
            await AuditLogger.logMentorAction(
                getCurrentUser(),
                `Dispatched manual mentor-assignment email — scope: ${scopeLabel}; recipients: ${sideLabel} `
                + `(${result.mentors_emailed?.length ?? 0} mentor(s), ${result.teams_emailed ?? 0} team(s))`
            );
            alert(result.message || 'Emails sent successfully!');
            setMentorEmailModalOpen(false);
        } catch (error) {
            console.error('Failed to send mentor assignment emails:', error.message);
            alert('Failed to send mentor assignment emails: ' + error.message);
        } finally {
            setSendingMentorEmails(false);
        }
    };

    const uniqueMentorDomains = Array.from(new Set(approvedMentors.map(m => m.domain).filter(Boolean)));

    // Domains the teams actually carry, so the filter can only offer values that
    // will match something. The hardcoded IoT / AI/ML / Web Dev options this
    // replaces matched no team at all — picking any of them emptied the table.
    // Deduped case-insensitively because the data contains near-duplicates that
    // differ only by stray whitespace or capitalisation.
    const uniqueTeamDomains = useMemo(() => {
        const seen = new Map();
        teams.forEach(t => parseDomains(t.domain).forEach(d => {
            const key = d.toLowerCase();
            if (!seen.has(key)) seen.set(key, d);
        }));
        return Array.from(seen.values()).sort((a, b) => a.localeCompare(b));
    }, [teams]);

    // Every approved mentor, not just ones with a team yet — picking a mentor
    // with zero teams should show an (correctly empty) filtered table, not be
    // impossible to select in the first place.
    const mentorFilterOptions = useMemo(() => {
        return [...approvedMentors]
            .sort((a, b) => (a.name || '').localeCompare(b.name || ''))
            .map(m => ({ name: m.name, count: activeLoad[m.name] || 0 }));
    }, [approvedMentors, activeLoad]);

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            {autoMsg && (
                <div className={`flex items-start gap-3 px-5 py-3 rounded-2xl text-sm font-semibold border ${autoMsg.type === 'warn'
                    ? 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300'
                    : 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-300'}`}>
                    <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                    <span className="flex-1">{autoMsg.text}</span>
                    <button onClick={() => setAutoMsg(null)} className="shrink-0 opacity-60 hover:opacity-100"><XIcon className="w-4 h-4" /></button>
                </div>
            )}
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
                className="bg-gradient-to-br from-indigo-700 via-indigo-800 to-slate-900 rounded-3xl p-8 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden flex flex-col md:flex-row items-center justify-between border border-indigo-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 w-full lg:w-2/3">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20 shadow-sm">
                        <UserCheck className="w-4 h-4 mr-2" /> Faculty Deployment
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Mentor Allocation</h1>
                    <p className="text-indigo-200/90 leading-relaxed text-sm md:text-base max-w-lg font-medium">Assign faculty mentors to project teams optimally. Leverage intelligent AI matching heuristics and strict workload limits to prevent supervision fatigue.</p>
                </div>
                {/* Vertically centred against the banner and flush to its right
                    edge. The title column takes lg:w-2/3, leaving too little
                    room for these side by side, so they stack. Stacking as a
                    column with `items-stretch` makes both buttons the width of
                    the wider one automatically — no hardcoded min-width to drift
                    out of date if the labels change. */}
                <div className="mt-6 md:mt-0 relative z-10 flex flex-col items-stretch justify-center gap-4 self-center md:ml-auto shrink-0">
                    <button onClick={() => setIsAddMentorOpen(true)} className="relative z-10 flex items-center justify-center whitespace-nowrap px-6 py-3 bg-emerald-600 border border-emerald-500/50 text-white rounded-xl text-sm font-black uppercase tracking-widest hover:bg-emerald-700 transition-all shadow-xl shadow-black/20 active:scale-95 group">
                        <Plus className="w-5 h-5 mr-3" /> Add Mentor
                    </button>
                    {/* Mentor-team assignment never emails automatically — this
                        opens a modal to choose who gets emailed (everyone or one
                        mentor; mentor side, team side, or both), sent once
                        allocation is finalized rather than per assignment. */}
                    <button onClick={() => setMentorEmailModalOpen(true)} disabled={sendingMentorEmails}
                        className="relative z-10 flex items-center justify-center whitespace-nowrap px-6 py-3 bg-white text-indigo-900 rounded-xl text-sm font-black uppercase tracking-widest hover:bg-indigo-50 transition-all shadow-xl shadow-black/20 active:scale-95 group disabled:opacity-50 disabled:cursor-not-allowed">
                        <Mail className={`w-5 h-5 mr-3 transition-colors ${sendingMentorEmails ? 'animate-pulse text-amber-500' : 'group-hover:text-amber-500'}`} />
                        {sendingMentorEmails ? 'Sending…' : 'Mass Email Mentors'}
                    </button>
                    {/* Opens the workload modal rather than assigning on the
                        spot: auto-assign rewrites every pending team's mentor,
                        so the capacity it is about to spend should be on screen
                        before it runs. The confirm lives inside the modal. */}
                    <button onClick={() => setWorkloadOpen(true)} aria-haspopup="dialog" aria-expanded={workloadOpen}
                        className="relative z-10 flex items-center justify-center whitespace-nowrap px-6 py-3 bg-white text-indigo-900 rounded-xl text-sm font-black uppercase tracking-widest hover:bg-indigo-50 transition-all shadow-xl shadow-black/20 active:scale-95 group">
                        <Zap className={`w-5 h-5 mr-3 transition-colors ${autoBusy ? 'animate-pulse text-amber-500' : 'group-hover:text-amber-500'}`} />
                        {autoBusy ? 'Assigning…' : 'Auto-Assign Pending'}
                    </button>
                    <div className="absolute -inset-2 bg-white/20 blur-xl rounded-full opacity-0 transition-opacity pointer-events-none"></div>
                </div>
            </motion.div>



            {/* Mentor workload — opens as a modal from Auto-Assign Pending */}
            <AnimatePresence>
            {workloadOpen && (
            <motion.div key="workload-backdrop"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                onClick={() => { if (!autoBusy) setWorkloadOpen(false); }}
                className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
            <motion.div key="workload-modal" id="mentor-workload-panel"
                initial={{ opacity: 0, scale: 0.9, y: 12 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 12 }}
                transition={{ type: 'spring', duration: 0.4, bounce: 0.18 }}
                onClick={(e) => e.stopPropagation()}
                className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-5xl border border-slate-200 dark:border-slate-700 overflow-hidden my-8 flex flex-col max-h-[90vh]">

                <div className="bg-gradient-to-r from-indigo-600 to-indigo-900 p-6 flex justify-between items-start shrink-0">
                    <div className="text-white">
                        <h3 className="font-black text-xl flex items-center"><Briefcase className="w-5 h-5 mr-3" /> Executive Workload Limits</h3>
                        <p className="text-xs text-indigo-100/90 mt-1 font-medium">Review mentor capacity before assigning pending teams · {filteredMentors.length} mentors</p>
                    </div>
                    <button onClick={() => setWorkloadOpen(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><XIcon className="w-4 h-4" /></button>
                </div>

                <div className="p-6 space-y-4 overflow-y-auto">

                {/* Pending registrations are excluded above, but saying so beats
                    letting them vanish without explanation. */}
                {pendingMentorCount > 0 && (
                    <div className="flex items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-500/30 dark:bg-amber-500/10">
                        <AlertCircle className="h-5 w-5 shrink-0 text-amber-500" />
                        <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                            {pendingMentorCount} mentor registration{pendingMentorCount === 1 ? '' : 's'} awaiting approval
                            {pendingMentorCount === 1 ? ' is' : ' are'} hidden here and cannot be allocated.
                            Approve {pendingMentorCount === 1 ? 'it' : 'them'} under Views to make {pendingMentorCount === 1 ? 'it' : 'them'} available.
                        </p>
                    </div>
                )}

                {filteredMentors.length === 0 ? (
                    <div className="bg-slate-50 dark:bg-slate-800/50 rounded-3xl p-12 text-center border border-slate-200/50 dark:border-slate-700/50">
                        <AlertCircle className="w-12 h-12 text-slate-400 mx-auto mb-4" />
                        <h3 className="text-lg font-bold text-slate-700 dark:text-slate-300">No mentors match the current search or filter criteria.</h3>
                        <div className="mt-6 flex justify-center gap-4">
                            <button onClick={() => { setMentorSearchTerm(''); setMentorDomainFilter(''); setMentorExpertiseFilter([]); setMentorWorkloadFilter('all'); }} className="px-6 py-2 bg-indigo-100 text-indigo-700 rounded-lg text-sm font-bold hover:bg-indigo-200 transition-colors">Clear Filters</button>
                        </div>
                    </div>
                ) : (
                    /* Capped at 3: these breakpoints track the viewport, not the
                       modal, so xl:grid-cols-4 squeezed four cards into a fixed
                       max-w-5xl dialog. */
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                        {filteredMentors.map((m, _i) => {
                            const statusColors = {
                                available: 'bg-emerald-500',
                                near_capacity: 'bg-amber-500',
                                full: 'bg-red-500'
                            };
                            const bgColors = {
                                available: '',
                                near_capacity: '',
                                full: 'grayscale-[50%] opacity-90'
                            };
                            const colorClasses = {
                                blue: 'bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-100 dark:border-blue-500/20',
                                emerald: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-100 dark:border-emerald-500/20',
                                rose: 'bg-rose-50 dark:bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-500/20',
                                amber: 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-500/20',
                                indigo: 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-100 dark:border-indigo-500/20',
                                purple: 'bg-purple-50 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-100 dark:border-purple-500/20'
                            };
                            const colorClass = colorClasses[m.color] || colorClasses.indigo;
                            return (
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} key={m.id}
                                    className={`bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-5 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col shadow-sm relative overflow-hidden group hover:shadow-lg transition-all ${bgColors[m.workloadStatus]}`}>

                                    {/* Name row and action buttons share a flex row rather than the
                                        buttons being absolutely positioned over a fixed `pr-10`
                                        gutter. At the modal's narrower column width that gutter was
                                        too small for two 2rem buttons, so long names ran underneath
                                        them. `min-w-0` lets the text column actually shrink, which
                                        is what makes truncation work inside a flex child. */}
                                    <div className="relative z-10 mb-4">
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="min-w-0 flex-1">
                                                <h3 className="font-black text-slate-800 dark:text-white text-lg leading-tight mb-1 break-words" title={m.name}>{m.name}</h3>
                                                {m.email && (
                                                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 flex items-center min-w-0" title={m.email}>
                                                        <Mail className="w-3 h-3 mr-1 shrink-0" />
                                                        <span className="truncate">{m.email}</span>
                                                    </p>
                                                )}
                                            </div>
                                            <div className="flex gap-1.5 shrink-0">
                                            <button onClick={() => { setIsEditingDomains(false); setEditingMentorConfig(m); }} className={`w-8 h-8 rounded-xl flex items-center justify-center shadow-inner border bg-slate-50 dark:bg-slate-900 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 ${m.workloadStatus === 'full' ? 'text-red-500 border-red-100 dark:border-red-500/20' : 'text-indigo-500 border-indigo-100 dark:border-indigo-500/20'}`} title="Edit Mentor Details">
                                                <Edit3 className="w-3.5 h-3.5" />
                                            </button>
                                            <button onClick={() => handleDeleteMentor(m.id)} className="w-8 h-8 rounded-xl flex items-center justify-center shadow-inner border bg-slate-50 dark:bg-slate-900 transition-colors hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-500/20 dark:hover:text-rose-400 border-slate-200 dark:border-slate-700" title="Delete Mentor">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                            </div>
                                        </div>

                                        {/* Tags sit below the name row so they get the card's full
                                            width instead of the leftover space beside the buttons.
                                            `whitespace-nowrap` keeps a label like "Machine Learning
                                            / AI" on one line — it was breaking mid-pill. */}
                                        <div className="flex flex-wrap gap-1 mt-3">
                                            {Array.isArray(m.domains) && m.domains.length > 0 ? (
                                                m.domains.map(d => (
                                                    <span key={d} className={`inline-flex items-center px-2 py-0.5 text-[10px] font-black uppercase tracking-widest rounded border whitespace-nowrap ${colorClass}`}>{d}</span>
                                                ))
                                            ) : (
                                                m.domain && <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-black uppercase tracking-widest rounded border whitespace-nowrap ${colorClass}`}>{m.domain}</span>
                                            )}
                                            {m.expertise && <span className="inline-flex items-center px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 text-[10px] font-black uppercase tracking-widest rounded border border-slate-200 dark:border-slate-600 truncate max-w-[150px]" title={m.expertise}>{m.expertise}</span>}
                                        </div>
                                    </div>

                                    <div className="mt-auto relative z-10 pt-4">
                                        <div className="flex justify-between items-end mb-2">
                                            <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest flex items-center"><Users className="w-3 h-3 mr-1" /> Assigned: {m.calculatedLoad}</span>
                                            <span className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest flex items-center">Slots: <strong className={`ml-1 ${m.availableSlots > 0 ? 'text-emerald-500' : 'text-red-500'}`}>{m.availableSlots}</strong>/{m.capacity}</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden shadow-inner relative">
                                            <div className={`absolute top-0 left-0 h-full rounded-full transition-all duration-1000 ease-out ${statusColors[m.workloadStatus]}`} style={{ width: `${(m.calculatedLoad / m.capacity) * 100}%` }}></div>
                                        </div>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                )}

                </div>

                {/* The confirm. Auto-assign is the one action here that rewrites
                    data, so it sits next to the capacity it will consume. */}
                <div className="shrink-0 flex flex-col sm:flex-row items-center justify-between gap-4 p-6 border-t border-slate-200 dark:border-slate-700 bg-slate-50/70 dark:bg-slate-900/30">
                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                        <strong className="text-slate-700 dark:text-slate-200">{openSlotCount}</strong> open slot{openSlotCount === 1 ? '' : 's'} across{' '}
                        <strong className="text-slate-700 dark:text-slate-200">{mentorsWithRoom}</strong> approved mentor{mentorsWithRoom === 1 ? '' : 's'}
                        {pendingTeamCount > 0 && <> · <strong className="text-slate-700 dark:text-slate-200">{pendingTeamCount}</strong> team{pendingTeamCount === 1 ? '' : 's'} awaiting a mentor</>}
                    </p>
                    <button onClick={autoAssign} disabled={autoBusy || openSlotCount === 0}
                        className="flex items-center px-6 py-3 bg-indigo-600 text-white rounded-xl text-sm font-black uppercase tracking-widest hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-500/20 active:scale-95 group disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none">
                        <Zap className={`w-5 h-5 mr-3 ${autoBusy ? 'animate-pulse' : ''}`} />
                        {autoBusy ? 'Assigning…' : 'Run Auto-Assign'}
                    </button>
                </div>
            </motion.div>
            </motion.div>
            )}
            </AnimatePresence>

            {/* Allocation Table */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.4 }} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20">
                    <div className="flex flex-col sm:flex-row gap-4">
                        <div className="relative max-w-md group flex-1">
                            <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                            <input type="text" placeholder="Search teams or projects..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full pl-11 pr-5 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow" />
                        </div>
                        <div className="flex items-center gap-3">
                            <span className="text-slate-500 dark:text-slate-400 font-bold text-sm flex items-center"><Filter className="w-4 h-4 mr-1" /> Filters:</span>
                            <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                                <option value="">All Domains{uniqueTeamDomains.length > 0 ? ` (${uniqueTeamDomains.length})` : ''}</option>
                                {uniqueTeamDomains.map(d => <option key={d} value={d}>{d}</option>)}
                            </select>
                            {/* Which teams belong to which mentor — the assign
                                modal only ever shows one team at a time, so this
                                is the one place to see a mentor's whole roster. */}
                            <select value={mentorFilter} onChange={e => setMentorFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                                <option value="">All Mentors</option>
                                <option value={UNASSIGNED_MENTOR_FILTER}>Unassigned Teams</option>
                                {mentorFilterOptions.map(m => (
                                    <option key={m.name} value={m.name}>{m.name} ({m.count} team{m.count === 1 ? '' : 's'})</option>
                                ))}
                            </select>
                        </div>
                    </div>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead className="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 backdrop-blur-md">
                            <tr>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest pl-6">Team ID</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Project Concept</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest">Status / Mentor</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest text-right pr-6">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {filtered.map(t => (
                                <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-700/20 transition-colors group">
                                    <td className="p-5 pl-6 whitespace-nowrap">
                                        <span className="inline-block whitespace-nowrap text-sm font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1.5 rounded-lg border border-indigo-100 dark:border-indigo-500/20">{teamLabel(t.id, t, semesterMap)}</span>
                                    </td>
                                    <td className="p-5 text-sm font-bold text-slate-800 dark:text-slate-200">{t.title}</td>
                                    <td className="p-5">
                                        {t.assignedMentor.length > 0 ? (
                                            <div className="flex flex-wrap gap-2 w-fit">
                                                {t.assignedMentor.map(mentor => (
                                                    <span key={mentor} className="text-xs font-black text-emerald-600 dark:text-emerald-400 flex items-center bg-emerald-50 dark:bg-emerald-500/10 px-2 py-1 rounded-lg border border-emerald-100 dark:border-emerald-500/20">
                                                        <UserCheck className="w-3 h-3 mr-1" /> {mentor}
                                                    </span>
                                                ))}
                                            </div>
                                        ) : (
                                            <span className="text-sm font-black text-amber-500 flex items-center bg-amber-50 dark:bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-100 dark:border-amber-500/20 w-fit">
                                                <AlertCircle className="w-4 h-4 mr-2" /> Pending
                                            </span>
                                        )}
                                    </td>
                                    <td className="p-5 pr-6 text-right">
                                        <button onClick={() => { setEditingTeam(t); setSelectedMentors(t.assignedMentor.length > 0 ? t.assignedMentor : []); }}
                                            className="px-4 py-2 bg-slate-100 hover:bg-indigo-50 dark:bg-slate-800 dark:hover:bg-indigo-500/20 text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 text-xs font-black uppercase tracking-widest rounded-xl transition-colors inline-flex items-center border border-transparent hover:border-indigo-200 dark:hover:border-indigo-500/30 shadow-sm opacity-60 group-hover:opacity-100">
                                            <Edit3 className="w-4 h-4 mr-2" /> {t.assignedMentor.length > 0 ? 'Reassign' : 'Allocate'}
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </motion.div>

            {/* Assignment Modal */}
            <AnimatePresence>
                {editingTeam && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-2xl border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col max-h-[90vh]">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-gradient-to-r from-indigo-50 to-white dark:from-slate-800 dark:to-slate-800">
                                <h3 className="text-xl font-black text-slate-800 dark:text-white">Allocate Mentor</h3>
                                <p className="text-sm font-bold text-slate-500 mt-1 uppercase tracking-widest">{teamLabel(editingTeam.id, editingTeam, semesterMap)} • {editingTeam.title}</p>
                                <div className="mt-3 flex gap-2">
                                    <span className="text-xs bg-white dark:bg-slate-900 px-2 py-1 rounded font-bold border dark:border-slate-700 dark:text-slate-300">Domain: {editingTeam.domain}</span>
                                </div>
                                {(() => {
                                    let rawMembers = [];
                                    if (Array.isArray(editingTeam.members)) rawMembers = editingTeam.members;
                                    else if (typeof editingTeam.members === 'string') {
                                        try { const parsed = JSON.parse(editingTeam.members); if (Array.isArray(parsed)) rawMembers = parsed; } catch { /* non-fatal: fall through to the default below */ }
                                    }
                                    if (rawMembers.length === 0) return null;
                                    return (
                                        <div className="mt-3">
                                            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Team Members</label>
                                            <div className="flex flex-wrap gap-1.5 mt-1.5">
                                                {rawMembers.map((m, idx) => {
                                                    const name = typeof m === 'string' ? m : (m.name || m.id || m.student_id || 'Unknown Member');
                                                    const isLeader = (typeof m === 'object' && (m.role === 'LEADER' || m.isLeader === true))
                                                        || (editingTeam.leader && name.trim().toLowerCase() === String(editingTeam.leader).trim().toLowerCase());
                                                    return (
                                                        <span key={idx} className={`text-xs px-2 py-1 rounded-lg font-bold border ${isLeader ? 'bg-indigo-50 border-indigo-200 text-indigo-700 dark:bg-indigo-500/10 dark:border-indigo-500/30 dark:text-indigo-300' : 'bg-white border-slate-200 text-slate-600 dark:bg-slate-900 dark:border-slate-700 dark:text-slate-300'}`}>
                                                            {name}{isLeader ? ' (Leader)' : ''}
                                                        </span>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    );
                                })()}
                            </div>

                            {/* min-h-0 overrides the flex item's default min-height:auto —
                                without it flex-1 never actually shrinks to the space
                                available, so overflow-y-auto never engages and the mentor
                                list below the fold is just clipped by the modal's
                                overflow-hidden with no way to scroll to it. */}
                            <div className="p-6 space-y-6 overflow-y-auto custom-scrollbar flex-1 min-h-0">
                                <div className="flex flex-col gap-3 mb-2">
                                    <div className="relative w-full">
                                        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <input type="text" placeholder="Search mentors by name, email, expertise, or domain..."
                                            value={mentorSearchTerm} onChange={(e) => setMentorSearchTerm(e.target.value)}
                                            className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow" />
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        <select value={mentorDomainFilter} onChange={(e) => setMentorDomainFilter(e.target.value)} className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm flex-1 min-w-[120px]">
                                            <option value="">All Domains</option>
                                            {uniqueMentorDomains.map(d => <option key={d} value={d}>{d}</option>)}
                                        </select>

                                        <select value={mentorExpertiseFilter} onChange={(e) => setMentorExpertiseFilter(e.target.value)} className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm flex-1 min-w-[120px]">
                                            <option value="">All Expertise</option>
                                            {uniqueMentorExpertise.map(s => <option key={s} value={s}>{s}</option>)}
                                        </select>

                                        <select value={mentorWorkloadFilter} onChange={(e) => setMentorWorkloadFilter(e.target.value)} className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm flex-1 min-w-[120px]">
                                            <option value="all">Any Workload</option>
                                            <option value="available">Available</option>
                                            <option value="near_capacity">Near Capacity</option>
                                            <option value="full">Full</option>
                                            <option value="available_slots">Has Slots</option>
                                        </select>

                                        <select value={mentorSortBy} onChange={(e) => setMentorSortBy(e.target.value)} className="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm flex-1 min-w-[120px]">
                                            <option value="name_asc">Sort: A-Z</option>
                                            <option value="name_desc">Sort: Z-A</option>
                                            <option value="workload_lowest">Lowest Workload</option>
                                            <option value="workload_highest">Highest Workload</option>
                                            <option value="capacity_most">Most Capacity</option>
                                        </select>
                                    </div>
                                </div>

                                {(() => {
                                    const recommendedById = new Map(modalMentors.recommended.map(sm => [sm.mentor.id, sm]));
                                    return (
                                        <div>
                                            <div className="flex justify-between items-end mb-3">
                                                <label className="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 flex items-center">
                                                    <Star className="w-4 h-4 mr-1 text-indigo-500" /> All Mentors
                                                </label>
                                                <span className="text-[10px] text-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-0.5 rounded font-bold border border-indigo-100 dark:border-indigo-500/20">{selectedMentors.length} Selected</span>
                                            </div>

                                            {filteredMentors.length === 0 ? (
                                                <div className="text-center p-6 bg-slate-50 dark:bg-slate-900 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
                                                    <p className="text-sm font-bold text-slate-500">No mentors match your search.</p>
                                                </div>
                                            ) : (
                                                <div className="space-y-2">
                                                    {filteredMentors.map(m => {
                                                        const rec = recommendedById.get(m.id);
                                                        const isSelected = selectedMentors.includes(m.name);
                                                        return (
                                                            <div key={m.id} onClick={() => {
                                                                if (isSelected) setSelectedMentors(prev => prev.filter(n => n !== m.name));
                                                                else setSelectedMentors(prev => [...prev, m.name]);
                                                            }} className={`cursor-pointer p-3 rounded-xl border transition-all flex items-center justify-between ${isSelected ? 'bg-indigo-50 border-indigo-200 dark:bg-indigo-500/20 dark:border-indigo-500/30' : rec ? 'bg-emerald-50/30 border-emerald-100 hover:bg-emerald-50 dark:bg-emerald-500/5 dark:border-emerald-500/10 dark:hover:bg-emerald-500/10' : 'bg-slate-50 border-slate-200 hover:bg-slate-100 dark:bg-slate-900 border-slate-700/50 dark:hover:bg-slate-800'}`}>
                                                                <div>
                                                                    <div className="flex items-center gap-2 flex-wrap">
                                                                        <p className={`font-bold text-sm ${isSelected ? 'text-indigo-700 dark:text-indigo-300' : 'text-slate-700 dark:text-slate-300'}`}>{m.name}</p>
                                                                        {rec && <span className="text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded font-black uppercase tracking-wide shadow-sm flex items-center gap-0.5"><Star className="w-2.5 h-2.5" /> Recommended</span>}
                                                                        {m.workloadStatus === 'full' && <span className="w-2 h-2 rounded-full bg-red-500"></span>}
                                                                        {m.workloadStatus === 'near_capacity' && <span className="w-2 h-2 rounded-full bg-amber-500"></span>}
                                                                        {m.workloadStatus === 'available' && <span className="w-2 h-2 rounded-full bg-emerald-500"></span>}
                                                                    </div>
                                                                    <p className="text-[11px] text-slate-500 mt-1">{m.domain} • Slots: {m.availableSlots}/{m.capacity}</p>
                                                                    {rec && (
                                                                        <div className="flex gap-1 mt-1.5 flex-wrap">
                                                                            <span className="text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded font-bold shadow-sm">Score: {rec.score}</span>
                                                                            {rec.reasons.map((r, i) => <span key={i} className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded font-medium shadow-sm">✓ {r}</span>)}
                                                                        </div>
                                                                    )}
                                                                    {m.expertise && <p className="text-[10px] text-slate-400 mt-1 truncate max-w-xs">{m.expertise}</p>}
                                                                </div>
                                                                <div className={`w-5 h-5 rounded flex items-center justify-center border transition-colors shrink-0 ${isSelected ? 'bg-indigo-600 border-indigo-600 text-white shadow-sm' : 'border-slate-300 dark:border-slate-600'}`}>
                                                                    {isSelected && <Check className="w-3 h-3" />}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })()}
                            </div>
                            <div className="p-5 bg-slate-50/50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex flex-col-reverse sm:flex-row justify-end space-y-3 space-y-reverse sm:space-y-0 sm:space-x-3 shrink-0">
                                <button onClick={() => setEditingTeam(null)} className="px-6 py-3 text-sm font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                {/* Enabled with nothing selected: that is how a team's
                                    mentor is removed. Only disabled when there is
                                    genuinely nothing to do -- no mentors selected and
                                    none assigned. */}
                                <button onClick={handleAssign}
                                    disabled={selectedMentors.length === 0 && (editingTeam?.assignedMentor?.length || 0) === 0}
                                    className={`px-6 py-3 text-sm font-black uppercase tracking-widest text-white rounded-xl transition-all shadow-lg flex items-center justify-center disabled:bg-slate-300 dark:disabled:bg-slate-700 disabled:text-slate-500 ${
                                        selectedMentors.length === 0
                                            ? 'bg-rose-600 hover:bg-rose-700 hover:shadow-rose-500/30'
                                            : 'bg-indigo-600 hover:bg-indigo-700 hover:shadow-indigo-500/30'}`}>
                                    <UserCheck className="w-4 h-4 mr-2" />
                                    {selectedMentors.length === 0 ? 'Remove Mentor' : 'Confirm Assignment'}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}

                {editingMentorConfig && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-50 flex items-center justify-center p-4">
                        <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col max-h-[90vh]">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-gradient-to-r from-indigo-50 to-white dark:from-slate-800 dark:to-slate-800 flex justify-between items-center shrink-0">
                                <div>
                                    <h3 className="text-xl font-black text-slate-800 dark:text-white">Edit Mentor Profile</h3>
                                    <p className="text-sm font-bold text-slate-500 mt-1 uppercase tracking-widest">{editingMentorConfig.id}</p>
                                </div>
                                <button onClick={() => setEditingMentorConfig(null)} className="p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-full transition-colors"><XIcon className="w-5 h-5" /></button>
                            </div>
                            <div className="p-6 space-y-4 overflow-y-auto custom-scrollbar">
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Mentor Name</label>
                                    <input type="text" value={editingMentorConfig.name} onChange={e => setEditingMentorConfig({ ...editingMentorConfig, name: e.target.value })} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow" />
                                </div>
                                <div>
                                    {!isEditingDomains ? (
                                        <div className="space-y-1">
                                            <div className="flex justify-between items-center">
                                                <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Domains</label>
                                                <button type="button" onClick={() => setIsEditingDomains(true)} className="text-xs font-bold text-indigo-600 hover:text-indigo-700">Edit Domains</button>
                                            </div>
                                            <p className="text-sm font-bold text-slate-700 dark:text-slate-305 bg-slate-50 dark:bg-slate-900/30 p-3.5 rounded-xl border border-slate-150 dark:border-slate-700/50">
                                                {(Array.isArray(editingMentorConfig.domains) && editingMentorConfig.domains.length > 0)
                                                    ? editingMentorConfig.domains.join(', ')
                                                    : (editingMentorConfig.domains || editingMentorConfig.domain || 'No domains specified')}
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="space-y-1.5">
                                            <div className="flex justify-between items-center">
                                                <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Edit Domains (comma-separated)</label>
                                                <button type="button" onClick={() => setIsEditingDomains(false)} className="text-xs font-bold text-indigo-600 hover:text-indigo-700">Cancel Edit</button>
                                            </div>
                                            <input
                                                type="text"
                                                value={localDomainsStr}
                                                onChange={e => setLocalDomainsStr(e.target.value)}
                                                className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow"
                                            />
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Expertise Areas (Tags)</label>
                                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                                        {(Array.isArray(editingMentorConfig.skills) ? editingMentorConfig.skills : []).map(skill => (
                                            <span key={skill} className="bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 px-2 py-1 rounded text-xs font-bold flex items-center gap-1">
                                                {skill} <button onClick={() => setEditingMentorConfig({ ...editingMentorConfig, skills: (editingMentorConfig.skills || []).filter(s => s !== skill) })}><XIcon className="w-3 h-3" /></button>
                                            </span>
                                        ))}
                                    </div>
                                    <input
                                        type="text"
                                        placeholder="Type expertise (e.g., React, TensorFlow) and press Enter..."
                                        onKeyDown={e => {
                                            if (e.key === 'Enter' && e.target.value.trim()) {
                                                e.preventDefault();
                                                const current = Array.isArray(editingMentorConfig.skills) ? editingMentorConfig.skills : [];
                                                if (!current.includes(e.target.value.trim())) {
                                                    setEditingMentorConfig({ ...editingMentorConfig, skills: [...current, e.target.value.trim()] });
                                                    e.target.value = '';
                                                }
                                            }
                                        }}
                                        className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Max Load</label>
                                    <input type="number" min="1" max="20" value={editingMentorConfig.maxLoad} onChange={e => {
                                        const load = parseInt(e.target.value) || 1;
                                        const colors = ['blue', 'emerald', 'rose', 'amber', 'indigo', 'purple'];
                                        const color = colors[(editingMentorConfig.name || '').length % colors.length];
                                        setEditingMentorConfig({ ...editingMentorConfig, maxLoad: load, color: color });
                                    }} className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow" />
                                </div>
                                {mentors.find(m => m.id === editingMentorConfig.id)?.name !== editingMentorConfig.name && (
                                    <div className="mt-4 p-4 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl flex items-start shadow-inner">
                                        <AlertCircle className="w-5 h-5 text-amber-500 mr-3 shrink-0 mt-0.5" />
                                        <p className="text-xs font-bold text-amber-700 dark:text-amber-400 leading-relaxed">Changing the mentor's name will automatically update all assigned teams, proposals, and results associated with this mentor.</p>
                                    </div>
                                )}
                            </div>
                            <div className="p-5 bg-slate-50/50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex justify-end shrink-0">
                                <button onClick={() => setEditingMentorConfig(null)} className="px-6 py-3 mr-3 text-sm font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                <button onClick={() => {
                                    const arr = localDomainsStr.split(',').map(d => d.trim()).filter(Boolean);
                                    const updated = {
                                        ...editingMentorConfig,
                                        domain: arr[0] || '',
                                        domains: arr
                                    };
                                    handleSaveMentor(updated, mentors.find(m => m.id === editingMentorConfig.id)?.name);
                                }} className="px-6 py-3 text-sm font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg hover:shadow-indigo-500/30">
                                    Save Changes
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Add Mentor Modal */}
            <AnimatePresence>
                {isAddMentorOpen && (
                    <motion.div key="add-mentor-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 shadow-2xl overflow-y-auto">
                        <motion.div key="add-mentor-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden my-8">
                            <div className="bg-gradient-to-r from-emerald-600 to-emerald-800 p-6 flex justify-between items-start">
                                <div className="text-white">
                                    <h3 className="font-black text-xl">Add New Mentor</h3>
                                    <p className="text-xs text-emerald-100/90 mt-1 font-medium">Create a single mentor record manually</p>
                                </div>
                                <button onClick={() => setIsAddMentorOpen(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><XIcon className="w-4 h-4"/></button>
                            </div>
                            <form onSubmit={handleAddMentor} className="p-6 space-y-4">
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Mentor Name</label>
                                    <input type="text" required value={newMentorForm.name} onChange={(e) => setNewMentorForm(prev => ({...prev, name: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Dr. A.K. Singh" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Email Address</label>
                                    <input type="email" required value={newMentorForm.email} onChange={(e) => setNewMentorForm(prev => ({...prev, email: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder={`e.g. ${emailPlaceholder('aksingh')}`} />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Domain</label>
                                        <input type="text" required value={newMentorForm.domain} onChange={(e) => setNewMentorForm(prev => ({...prev, domain: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. AIML" />
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Expertise / Skills</label>
                                        <input type="text" value={newMentorForm.expertise} onChange={(e) => setNewMentorForm(prev => ({...prev, expertise: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Python, NLP" />
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Max Capacity (Teams)</label>
                                    <input type="number" required value={newMentorForm.capacity} onChange={(e) => setNewMentorForm(prev => ({...prev, capacity: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" min="1" max="20" />
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 pt-4">
                                    <button type="button" onClick={() => setIsAddMentorOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" className="px-5 py-2.5 text-sm font-bold text-white bg-emerald-600 border border-emerald-500/50 hover:bg-emerald-700 rounded-xl transition-all shadow-lg shadow-emerald-500/30 active:scale-95">Add Mentor</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Mass Email Mentors Modal */}
            <AnimatePresence>
                {mentorEmailModalOpen && (
                    <motion.div key="mentor-email-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                        <motion.div key="mentor-email-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-gradient-to-r from-indigo-50 to-white dark:from-slate-800 dark:to-slate-800 flex justify-between items-start">
                                <div>
                                    <h3 className="text-xl font-black text-slate-800 dark:text-white">Mass Email Mentors</h3>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">No email fires automatically — choose who gets one below.</p>
                                </div>
                                <button onClick={() => setMentorEmailModalOpen(false)} className="p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-full transition-colors"><XIcon className="w-5 h-5" /></button>
                            </div>
                            <div className="p-6 space-y-5">
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Recipients</label>
                                    <select value={emailScopeMentor} onChange={e => setEmailScopeMentor(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                                        <option value="">Everyone (every mentor with an assigned team)</option>
                                        {mentorFilterOptions.filter(m => m.count > 0).map(m => (
                                            <option key={m.name} value={m.name}>{m.name} ({m.count} team{m.count === 1 ? '' : 's'})</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-2">Send To</label>
                                    <div className="space-y-2">
                                        <label className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 cursor-pointer">
                                            <input type="checkbox" checked={emailNotifyMentor} onChange={e => setEmailNotifyMentor(e.target.checked)} className="w-4 h-4 accent-indigo-600" />
                                            <span className="text-sm font-bold text-slate-700 dark:text-slate-300">Mentor(s) — one email each, listing every team in scope</span>
                                        </label>
                                        <label className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 cursor-pointer">
                                            <input type="checkbox" checked={emailNotifyTeams} onChange={e => setEmailNotifyTeams(e.target.checked)} className="w-4 h-4 accent-indigo-600" />
                                            <span className="text-sm font-bold text-slate-700 dark:text-slate-300">Team(s) / students — one email per team in scope</span>
                                        </label>
                                    </div>
                                </div>
                            </div>
                            <div className="p-5 bg-slate-50/50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700/50 flex justify-end gap-3">
                                <button onClick={() => setMentorEmailModalOpen(false)} className="px-6 py-3 text-sm font-black uppercase tracking-widest text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                <button onClick={handleSendMentorEmails} disabled={sendingMentorEmails || (!emailNotifyMentor && !emailNotifyTeams)}
                                    className="px-6 py-3 text-sm font-black uppercase tracking-widest text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-lg hover:shadow-indigo-500/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center">
                                    <Mail className={`w-4 h-4 mr-2 ${sendingMentorEmails ? 'animate-pulse' : ''}`} />
                                    {sendingMentorEmails ? 'Sending…' : 'Send Now'}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
