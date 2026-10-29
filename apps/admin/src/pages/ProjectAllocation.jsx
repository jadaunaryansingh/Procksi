import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Activity, Clock, Lock, UserMinus, RefreshCcw, Users, Zap, Send,
    ScrollText, CheckCircle, Search, Edit, Trash2, Plus, Info, X, Check, Filter, AlertCircle, Eye, BrainCircuit, Target, Tag, Sparkles, ChevronRight
} from 'lucide-react';

import { api } from '../services/api';
import { apiUpsertTable, apiDeleteRows, clearTableCache } from '../lib/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamLabel } from '../lib/teamUtils';
import { normalizeYearToNumber, resolveCollegeYear, formatAcademicYear } from '../lib/globalFilters';
import PsArchitecturePlanModal from '../components/PsArchitecturePlanModal';
import NotifyPendingModal from '../components/NotifyPendingModal';
import { PS_TEAM_CAPACITY, normalizePsTitle, buildAllocationsByTitle, isPsAvailableForTeam, computeBulkAllocations } from '../lib/psAllocation';



// teams_validation.members is jsonb, but some rows hold it as a JSON *string*
// ("[{...}]") or as null/an object. `(team.members || []).map` crashed the whole
// page on the first such row, so every read goes through this.
function memberList(members) {
    if (Array.isArray(members)) return members;
    if (typeof members === 'string') {
        try {
            const parsed = JSON.parse(members);
            return Array.isArray(parsed) ? parsed : [];
        } catch {
            return [];
        }
    }
    return [];
}

function isHardwarePs(ps) {
    if (!ps) return false;
    const code = String(ps.ps_code || ps.id || '').trim().toUpperCase();
    if (code.startsWith('PS-HW-') || code.startsWith('HW-') || code.includes('-HW-')) return true;
    if (code.startsWith('PS-SW-') || code.startsWith('SW-') || code.includes('-SW-')) return false;

    const type = String(ps.ps_type || '').trim().toLowerCase();
    if (type === 'hardware' || type === 'hw') return true;
    if (type === 'software' || type === 'sw') return false;

    const rawDomain = (ps.domain || '').trim().toLowerCase();
    if (rawDomain.includes('hardware')) return true;
    if (rawDomain.includes('software')) return false;

    const fullText = ((ps.title || '') + ' ' + (ps.description || '')).toLowerCase();
    return ['hardware', 'iot', 'esp32', 'arduino', 'raspberry', 'microcontroller', 'circuit', 'embedded', 'gearbox', 'inductive', 'coil', 'actuator', 'fpga', 'rfid', 'granulometry', 'wifi sensing'].some(k => fullText.includes(k));
}

function getDomainCategoryBadge(ps) {
    const isHw = isHardwarePs(ps);
    if (isHw) {
        return {
            label: '🛠️ HARDWARE',
            style: 'bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 border-amber-200 dark:border-amber-800/60 font-black'
        };
    }
    return {
        label: '💻 SOFTWARE',
        style: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800/60 font-black'
    };
}

export default function ProjectAllocation() {
    const { filterRows, semesterMap, filters, semesters } = useGlobalFilters();

    const [lockedPS, setLockedPS] = useState([]);
    const [teams, setTeams] = useState([]);
    const [preferences, setPreferences] = useState([]);
    const [problemStatements, setProblemStatements] = useState([]);
    const [selectedPsForAnalysis, setSelectedPsForAnalysis] = useState(null);
    const [aiGenerating, setAiGenerating] = useState(false);
    const [sendingPsEmail, setSendingPsEmail] = useState(false);
    const [isNotifyModalOpen, setIsNotifyModalOpen] = useState(false);

    const handleSendPsAnnouncementEmail = async () => {
        if (!window.confirm("Are you sure you want to send a mass email announcement of Problem Statement release to all students?")) return;
        setSendingPsEmail(true);
        try {
            await api.sendPsReleasedEmail();
            alert("Problem Statement release announcement emails sent successfully!");
        } catch (e) {
            alert("Failed to send PS announcement email: " + (e.message || e));
        } finally {
            setSendingPsEmail(false);
        }
    };

    const handleGenerateOpenAISuggestions = async (psToEnrich) => {

        if (!psToEnrich || aiGenerating) return;
        setAiGenerating(true);
        try {
            const res = await api.generateAiSuggestions({
                id: psToEnrich.id,
                title: psToEnrich.title,
                description: psToEnrich.description,
                domain: psToEnrich.domain || 'General',

            });

            const payloadData = res.data || res;
            const enrichedDesc = payloadData.description || payloadData.suggested_description || psToEnrich.description;
            const enrichedDomain = payloadData.domain || payloadData.suggested_domain || psToEnrich.domain;
            const enrichedDiff = payloadData.difficulty || payloadData.suggested_difficulty || psToEnrich.difficulty;
            const costInfo = payloadData.cost_info || null;

            const updatedPs = {
                ...psToEnrich,
                description: enrichedDesc,
                domain: enrichedDomain,
                difficulty: enrichedDiff,
                cost_info: costInfo
            };

            setProblemStatements(prev => prev.map(p => p.id === psToEnrich.id ? updatedPs : p));
            setSelectedPsForAnalysis(updatedPs);
            return updatedPs;
        } catch (err) {
            console.error('Error generating AI suggestions:', err);
            alert('AI Generation error: ' + (err.message || err));
        } finally {
            setAiGenerating(false);
        }
    };

    const [psModal, setPsModal] = useState(null);
    const [psSubmitting, setPsSubmitting] = useState(false);

    const [loading, setLoading] = useState(true);
    const [importing, setImporting] = useState(false);
    const [importStatus, setImportStatus] = useState('');
    const [uploadYear, setUploadYear] = useState('');
    const [importFileName, setImportFileName] = useState('');
    const [importProgress, setImportProgress] = useState(0);
    const [importStepText, setImportStepText] = useState('');
    const [importedCount, setImportedCount] = useState(null);

    const [activeTab, setActiveTab] = useState('allotment');

    const [allotmentSearch, setAllotmentSearch] = useState('');
    const [allotmentStatusFilter, setAllotmentStatusFilter] = useState('all');

    const [psSearch, setPsSearch] = useState('');
    const [psTypeFilter, setPsTypeFilter] = useState('all');
    const [psYearFilter, setPsYearFilter] = useState('all');
    const [selectedPsIds, setSelectedPsIds] = useState([]);
    const [proposals, setProposals] = useState([]);

    const loadData = async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            setSelectedPsIds([]);
            const [conflictsRes, teamsRes, prefsRes, psRes, proposalsRes] = await Promise.all([
                api.getProjectConflicts(),
                api.getTeams(),
                api.getStudentPreferences(),
                api.getProblemStatements(),
                api.getProposals()
            ]);

            setLockedPS(conflictsRes.data || []);
            setTeams(teamsRes.data || []);
            setPreferences(prefsRes.data || []);
            setProblemStatements(psRes.data || []);
            setProposals(proposalsRes.data || []);
        } catch (err) {
            console.error("Failed to load allocation data", err);
        } finally {
            if (!silent) setLoading(false);
        }
    };

    React.useEffect(() => {
        clearTableCache();
        loadData();
        const interval = setInterval(() => {
            loadData(true);
        }, 3000);
        return () => clearInterval(interval);
    }, [filters.semesterId, filters.year, filters.branch]);

    const handleDeallocate = async (team) => {
        const teamName = teamLabel(team.id, team, semesterMap);
        if (window.confirm(`Are you sure you want to reset and de-allocate the project for ${teamName}?`)) {
            setLoading(true);
            try {
                const approvedProp = getApprovedProposal(team.id);
                if (approvedProp) {
                    await api.updateProposalStatus(approvedProp.id, 'Pending');
                }

                const teamIdStr = String(team.id);
                const match = teamIdStr.match(/-T(\d+)$/);
                const tNum = match ? match[1] : "1";
                const defaultTitle = `Team ${tNum}`;

                await api.allocateProject(team.id, defaultTitle, '', 'General');
                await api.updateTeamValidationStatus(team.id, 'Pending');

                alert("Project de-allocated successfully.");
                loadData();
            } catch (err) {
                alert("De-allocation failed: " + err.message);
            } finally {
                setLoading(false);
            }
        }
    };

    const handleAllocate = async (team, projectTitle, projectDesc, projectDomain) => {
        try {
            await api.allocateProject(team.id, projectTitle, projectDesc, projectDomain || 'General');

            try {
                const existingProp = proposals.find(p => p.teamId === team.id);
                const propId = existingProp ? existingProp.id : `PROP-ADM-${team.id.slice(-8).toUpperCase()}`;
                await apiUpsertTable('proposals', [{
                    id: propId,
                    teamId: team.id,
                    title: projectTitle,
                    description: projectDesc || '',
                    status: 'Approved',
                    submittedDate: new Date().toISOString().split('T')[0],
                }], 'id');
            } catch (propErr) {
                console.warn('Could not track proposal record:', propErr);
            }

            const teamLock = lockedPS.find(lps => String(lps.lockedBy) === String(team.id) || String(lps.id) === `LOCK-${team.id}`);
            if (teamLock && String(teamLock.title).toLowerCase() !== String(projectTitle).toLowerCase()) {
                await api.resolveConflict(teamLock.id, "Replaced on manual allocation").catch(e => console.log('Lock clear warning:', e));
            }

            const memberIds = memberList(team.members).map(m => String(m?.id || m?.student_id || m).trim());
            const leaderId = String(team.leader).trim();
            const allIds = [...new Set([leaderId, ...memberIds].filter(Boolean))];

            await Promise.all(allIds.map(sid => api.forceAssign(sid).catch(e => console.log('Stranded member clear warning:', e))));

            alert('Project successfully allocated!');
            loadData();
        } catch (err) {
            alert('Allocation failed: ' + err.message);
        }
    };

    const handleBulkAllocate = async () => {
        setLoading(true);
        try {
            const unallocatedList = unallocatedTeamsList;
            if (unallocatedList.length === 0) {
                alert("No unallocated teams to assign.");
                setLoading(false);
                return;
            }

            const titleCounts = new Map(
                Array.from(buildAllocationsByTitle(teams, getHasAllocated)).map(([title, holders]) => [title, holders.length])
            );

            const teamsWithMeta = unallocatedList.map(team => {
                const memberIds = memberList(team.members).map(m => String(m?.id || m?.student_id || m).trim());
                const leaderId = String(team.leader).trim();
                const allIds = [...new Set([leaderId, ...memberIds].filter(Boolean))];
                const prefRecord = preferences.find(p => allIds.includes(String(p.student_id).trim()));
                const teamYear = getTeamYear(team);
                return { team, prefRecord, teamYear, allIds, allocatedProject: null };
            });

            const priorityTeams = teamsWithMeta.filter(item => item.prefRecord && Array.isArray(item.prefRecord.preferences) && item.prefRecord.preferences.length > 0);
            const randomTeams = teamsWithMeta.filter(item => !item.prefRecord || !Array.isArray(item.prefRecord.preferences) || item.prefRecord.preferences.length === 0);

            priorityTeams.sort((a, b) => {
                const timeA = a.prefRecord.updated_at ? new Date(a.prefRecord.updated_at).getTime() : 0;
                const timeB = b.prefRecord.updated_at ? new Date(b.prefRecord.updated_at).getTime() : 0;
                return timeA - timeB;
            });

            const assignments = computeBulkAllocations({ priorityTeams, randomTeams, problemStatements, titleCounts });
            teamsWithMeta.forEach(item => {
                if (assignments.has(item)) item.allocatedProject = assignments.get(item);
            });

            const allocatedTeamsMeta = teamsWithMeta.filter(item => item.allocatedProject);
            if (allocatedTeamsMeta.length === 0) {
                alert("Could not allocate any teams. No available problem statements match requirements.");
                setLoading(false);
                return;
            }

            const teamsToUpsert = allocatedTeamsMeta.map(item => ({
                ...item.team,
                title: item.allocatedProject.title,
                description: item.allocatedProject.description,
                domain: item.allocatedProject.domain,
                validationStatus: 'Valid'
            }));

            await apiUpsertTable('teams_validation', teamsToUpsert, 'id');

            const cleanupPromises = [];

            const newlyAllocatedTitles = new Set(allocatedTeamsMeta.map(item => item.allocatedProject.title.trim().toLowerCase()));
            const conflictsToResolve = lockedPS.filter(lps => newlyAllocatedTitles.has(String(lps.title).toLowerCase()));
            if (conflictsToResolve.length > 0) {
                const conflictIds = conflictsToResolve.map(c => c.id);
                cleanupPromises.push(apiDeleteRows('project_locked_ps', { id: `in.(${conflictIds.join(',')})` }).catch(e => console.warn("Failed to clear conflicts", e)));
            }

            const allAllocatedStudentIds = [];
            allocatedTeamsMeta.forEach(item => allAllocatedStudentIds.push(...item.allIds));
            const uniqueStudentIds = [...new Set(allAllocatedStudentIds)];
            if (uniqueStudentIds.length > 0) {
                cleanupPromises.push(apiDeleteRows('project_unallocated_students', { id: `in.(${uniqueStudentIds.join(',')})` }).catch(e => console.warn("Failed to clear unallocated students", e)));
            }

            if (cleanupPromises.length > 0) await Promise.all(cleanupPromises);

            alert(`Bulk Allocation Completed!\nSuccessfully allocated ${allocatedTeamsMeta.length} teams.`);
            loadData();
        } catch (err) {
            console.error("Bulk allocation failed:", err);
            alert("Bulk allocation failed: " + err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleSaveProblemStatement = async (e) => {
        e.preventDefault();
        if (!psModal) return;
        setPsSubmitting(true);
        try {
            const { mode, data } = psModal;
            const targetYear = data.year === '3' ? 3 : data.year === '4' ? 4 : null;
            const row = {
                // `generateId` was never defined anywhere, so creating a problem
                // statement without an explicit id threw a ReferenceError.
                // crypto.randomUUID gives the same PS-XXXXXXXX shape the stored
                // ids already use (compare PROP-EB745B5A on proposals).
                id: data.id || `PS-${crypto.randomUUID().replace(/-/g, '').substring(0, 8).toUpperCase()}`,
                title: data.title.trim(),
                description: data.description.trim(),
                domain: data.domain.trim() || 'General',
                // The modal has always offered a Hardware/Software select, but the value
                // was dropped here, so the column kept its default and the type filters
                // could never see it.
                ps_type: String(data.ps_type).trim().toLowerCase() === 'hardware' ? 'Hardware' : 'Software',
                year: targetYear
            };
            let finalRow = { ...row };

            await apiUpsertTable('problem_statements', [finalRow], 'id');

            if (mode === 'edit') {
                const originalPs = problemStatements.find(p => p.id === row.id);
                if (originalPs) {
                    const titleChanged = originalPs.title !== row.title;
                    const descChanged = originalPs.description !== row.description;
                    const domainChanged = originalPs.domain !== row.domain;

                    if (titleChanged || descChanged || domainChanged) {
                        const affectedTeams = teams.filter(t => t.title && t.title.trim().toLowerCase() === originalPs.title.trim().toLowerCase());
                        if (affectedTeams.length > 0) {
                            await Promise.all(affectedTeams.map(t => api.allocateProject(t.id, row.title, row.description, row.domain)));
                        }
                    }
                }
            }

            alert(`Problem Statement ${mode === 'create' ? 'created' : 'updated'} successfully!`);
            setPsModal(null);
            loadData();
        } catch (err) {
            alert('Failed to save problem statement: ' + err.message);
        } finally {
            setPsSubmitting(false);
        }
    };

    const handleDeleteProblemStatement = async (psId, title) => {
        if (window.confirm(`Are you sure you want to delete the problem statement: "${title}"?`)) {
            try {
                await apiDeleteRows('problem_statements', { id: psId });
                alert('Problem Statement deleted.');
                loadData();
            } catch (err) {
                alert('Failed to delete: ' + err.message);
            }
        }
    };

    const handleDeleteSelectedProblemStatements = async () => {
        if (selectedPsIds.length === 0) return;
        const count = selectedPsIds.length;
        if (window.confirm(`Are you sure you want to delete the ${count} selected problem statement${count > 1 ? 's' : ''}?`)) {
            setLoading(true);
            try {
                const idFilterString = `in.(${selectedPsIds.join(',')})`;
                await apiDeleteRows('problem_statements', { id: idFilterString });
                alert(`Successfully deleted ${count} problem statement${count > 1 ? 's' : ''}.`);
                setSelectedPsIds([]);
                loadData();
            } catch (err) {
                alert('Failed to delete selected problem statements: ' + err.message);
            } finally {
                setLoading(false);
            }
        }
    };

    const getApprovedProposal = (teamId) => {
        return proposals.find(p => p.teamId === teamId && (p.status || '').toLowerCase() === 'approved');
    };

    const isPlaceholderTitle = (t) => {
        if (!t) return true;
        const clean = t.trim().toLowerCase();
        if (!clean || clean === 'custom team' || clean.startsWith('pending') || clean.startsWith('admin-team')) return true;
        if (/^team\s*-?\s*\d+$/i.test(clean)) return true;
        if (/^\d{4}(?:-\d{4})?[-_\s]+\d+$/i.test(clean)) return true;
        return false;
    };

    const getHasAllocated = (team) => {
        if (getApprovedProposal(team.id)) return true;
        if (!team.title) return false;
        return !isPlaceholderTitle(team.title);
    };

    const getTeamYear = (team) => {
        if (!team) return 3;
        const resolvedYear = resolveCollegeYear(team, semesterMap);
        const normalized = normalizeYearToNumber(resolvedYear);
        if (normalized) {
            const num = Number(normalized);
            if (!isNaN(num) && num > 0) return num;
        }
        if (team.year) {
            const norm = normalizeYearToNumber(team.year);
            if (norm) {
                const num = Number(norm);
                if (!isNaN(num) && num > 0) return num;
            }
        }
        const name = teamLabel(team.id, team, semesterMap).toLowerCase();
        if (name.includes("2nd year") || name.includes("4th sem") || name.includes("yr 2") || name.includes("year 2")) return 2;
        if (name.includes("3rd year") || name.includes("6th sem") || name.includes("yr 3") || name.includes("year 3")) return 3;
        if (name.includes("4th year") || name.includes("8th sem") || name.includes("yr 4") || name.includes("year 4")) return 4;
        return 3;
    };

    const filteredTeams = filterRows(teams);
    const allocatedTeamsList = filteredTeams.filter(t => getHasAllocated(t));
    const unallocatedTeamsList = filteredTeams.filter(t => !getHasAllocated(t));

    const displayedCanvasTeams = useMemo(() => {
        return filteredTeams.filter(t => {
            const isAllocated = getHasAllocated(t);
            if (allotmentStatusFilter === 'allocated' && !isAllocated) return false;
            if (allotmentStatusFilter === 'unallocated' && isAllocated) return false;

            const label = teamLabel(t.id, t, semesterMap).toLowerCase();
            const projectTitle = (t.title || '').toLowerCase();
            const members = memberList(t.members).map(m => (m?.name || '').toLowerCase()).join(' ');
            const query = allotmentSearch.toLowerCase();

            return label.includes(query) || projectTitle.includes(query) || members.includes(query);
        });
    }, [filteredTeams, allotmentStatusFilter, allotmentSearch, semesterMap]);

    const allPsTitlesPool = useMemo(() => {
        const seen = new Set();
        const pool = [];

        for (const ps of problemStatements) {
            const key = (ps.title || '').trim().toLowerCase();
            if (key && !seen.has(key)) { seen.add(key); pool.push(ps); }
        }
        return pool;
    }, [problemStatements]);

    // Import/target options are built from the *active* semesters (batches) so the
    // list always reflects the batches currently running — not a hardcoded
    // "3rd Year / 4th Year". The option value is the batch's academic year number,
    // which is exactly what problem_statements.year stores and what every portal
    // filters problem statements on, so an upload targeted here is only ever
    // visible to that batch (an empty value = common to all active batches).
    const activeBatchOptions = useMemo(() => {
        const byLevel = new Map();
        for (const sem of (semesters || [])) {
            if (!sem?.is_active) continue;
            let level = Number(sem.academic_level);
            if ((!Number.isFinite(level) || level <= 0) && sem.semester_number) {
                level = Math.ceil(Number(sem.semester_number) / 2);
            }
            if (!Number.isFinite(level) || level <= 0) continue;
            const entry = byLevel.get(level) || { value: String(level), level, branches: new Set(), years: new Set() };
            if (sem.branch) entry.branches.add(String(sem.branch));
            if (sem.year) entry.years.add(String(sem.year));
            byLevel.set(level, entry);
        }
        return [...byLevel.values()]
            .sort((a, b) => a.level - b.level)
            .map(o => ({
                value: o.value,
                label: `${formatAcademicYear(o.level)} Only`,
                title: [[...o.years].join(', '), [...o.branches].join(', ')].filter(Boolean).join(' • '),
            }));
    }, [semesters]);

    const activeGlobalYear = useMemo(() => {
        if (filters.year && filters.year !== 'all') {
            const norm = normalizeYearToNumber(filters.year);
            if (norm) return Number(norm);
        }
        if (filters.semesterId && filters.semesterId !== 'all' && semesterMap[filters.semesterId]) {
            const sem = semesterMap[filters.semesterId];
            if (sem.academic_level) return Number(sem.academic_level);
            if (sem.semester_number) return Math.ceil(Number(sem.semester_number) / 2);
        }
        return null;
    }, [filters, semesterMap]);

    const displayedProblemStatements = useMemo(() => {
        return allPsTitlesPool.filter(ps => {
            if (psTypeFilter !== 'all' && isHardwarePs(ps) !== (psTypeFilter.toLowerCase() === 'hardware')) return false;

            const psYearNum = (ps.year !== null && ps.year !== undefined && ps.year !== '') ? Number(ps.year) : null;
            if (psYearFilter !== 'all') {
                const targetYearNum = Number(psYearFilter);
                if (psYearNum !== null && psYearNum !== targetYearNum) return false;
            } else if (activeGlobalYear !== null) {
                if (psYearNum !== null && psYearNum !== activeGlobalYear) return false;
            }

            const query = psSearch.toLowerCase();
            return (
                (ps.title || '').toLowerCase().includes(query) ||
                (ps.description || '').toLowerCase().includes(query) ||
                (ps.domain || '').toLowerCase().includes(query)
            );
        });
    }, [allPsTitlesPool, psTypeFilter, psYearFilter, activeGlobalYear, psSearch]);

    const allocationsByTitle = useMemo(
        () => buildAllocationsByTitle(teams, getHasAllocated),
        [teams, proposals]
    );

    const getPsAllocations = (psTitle) => {
        const holders = allocationsByTitle.get(normalizePsTitle(psTitle)) || [];
        return holders.map(team => ({ ...team, team_label: teamLabel(team.id, team, semesterMap) }));
    };

    const enrichedPsStats = useMemo(() => {
        const total = problemStatements.length;
        const enriched = problemStatements.filter(ps => {
            const desc = (ps.description || '').trim();
            return desc.includes('###') || desc.includes('## ') || desc.length > 200;
        }).length;
        const pct = total > 0 ? Math.round((enriched / total) * 100) : 0;
        return { total, enriched, pct, pending: total - enriched };
    }, [problemStatements]);


    const teamAllowedPsMap = useMemo(() => {
        const result = new Map();
        for (const team of teams) {
            const teamYear = getTeamYear(team);
            const allowed = allPsTitlesPool.filter(ps => {
                const psYearNum = (ps.year !== null && ps.year !== undefined && ps.year !== '') ? Number(ps.year) : null;
                if (psYearNum !== null && psYearNum !== Number(teamYear)) return false;
                return isPsAvailableForTeam(allocationsByTitle, ps.title, team.id);
            });
            result.set(team.id, allowed);
        }
        return result;
    }, [teams, allPsTitlesPool, allocationsByTitle, semesterMap]);

    const handleTabChange = (tab) => {
        setActiveTab(tab);
        setSelectedPsIds([]);
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">

            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
                className="bg-gradient-to-br from-indigo-900 via-slate-900 to-indigo-950 rounded-3xl p-6 md:p-8 text-white shadow-xl shadow-indigo-950/20 relative overflow-hidden flex flex-col md:flex-row justify-between items-start md:items-center gap-6 border border-slate-800">
                <div className="absolute inset-0 opacity-10 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full text-white">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 space-y-2 max-w-2xl">
                    <div className="inline-flex items-center px-3 py-1 bg-indigo-500/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider border border-indigo-500/20 text-indigo-400">
                        <Activity className="w-3.5 h-3.5 mr-2 animate-pulse" /> Allocation Canvas
                    </div>
                    <h1 className="text-3xl md:text-4xl font-black tracking-tight bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">Project &amp; Roster Allocation</h1>
                    <p className="text-slate-400 leading-relaxed text-sm font-medium">Manage student preferences, import and edit year-specific Problem Statements, and auto-allot projects with the click of a button.</p>
                </div>

                {/* Stats Cards */}
                <div className="flex gap-4 shrink-0 w-full md:w-auto overflow-x-auto pb-2 md:pb-0">
                    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 min-w-[120px] text-center flex-1 md:flex-initial">
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">Total Teams</div>
                        <div className="text-2xl font-black text-indigo-400 mt-1">{filteredTeams.length}</div>
                    </div>
                    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 min-w-[120px] text-center flex-1 md:flex-initial">
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-widest text-emerald-400">Allocated</div>
                        <div className="text-2xl font-black text-emerald-400 mt-1">{allocatedTeamsList.length}</div>
                    </div>
                    <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-4 min-w-[120px] text-center flex-1 md:flex-initial">
                        <div className="text-xs font-bold text-slate-400 uppercase tracking-widest text-amber-500">Pending</div>
                        <div className="text-2xl font-black text-amber-500 mt-1">{unallocatedTeamsList.length}</div>
                    </div>
                    <div className="bg-gradient-to-br from-[#1E1B4B] to-[#311B92] text-white border border-indigo-500/40 rounded-2xl p-4 min-w-[180px] shadow-lg flex flex-col justify-between flex-1 md:flex-initial">
                        <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] font-mono font-bold text-indigo-300 uppercase tracking-widest flex items-center gap-1.5">
                                <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-pulse" /> AI Specs
                            </span>
                            <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 text-[10px] font-mono font-bold border border-cyan-500/30">
                                {enrichedPsStats.pct}%
                            </span>
                        </div>
                        <div className="flex items-baseline gap-1.5 mt-1">
                            <span className="text-xl font-black text-white">{enrichedPsStats.enriched}</span>
                            <span className="text-xs font-medium text-indigo-200">/ {enrichedPsStats.total} Enriched</span>
                        </div>
                        <div className="w-full h-1.5 bg-indigo-950/80 rounded-full overflow-hidden mt-1.5">
                            <div className="h-full bg-gradient-to-r from-indigo-400 via-cyan-400 to-emerald-400 transition-all duration-500 rounded-full" style={{ width: `${enrichedPsStats.pct}%` }} />
                        </div>
                    </div>
                </div>
            </motion.div>

            {/* Navigation Tabs */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-4 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                <div className="flex items-center space-x-2 bg-slate-100/50 dark:bg-slate-900/50 p-1.5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 w-full sm:w-auto">
                    <button
                        onClick={() => handleTabChange('allotment')}
                        className={`flex-1 sm:flex-initial px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${activeTab === 'allotment' ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                    >
                        <Users className="w-4 h-4" /> Allotment Board
                    </button>
                    <button
                        onClick={() => handleTabChange('statements')}
                        className={`flex-1 sm:flex-initial px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${activeTab === 'statements' ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                    >
                        <ScrollText className="w-4 h-4" /> Problem Statements
                    </button>
                    <button
                        onClick={() => handleTabChange('allocated')}
                        className={`flex-1 sm:flex-initial px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wider transition-all flex items-center justify-center gap-2 ${activeTab === 'allocated' ? 'bg-white dark:bg-slate-800 text-emerald-600 dark:text-emerald-400 shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
                    >
                        <CheckCircle className="w-4 h-4" /> Allocated ({allocatedTeamsList.length})
                    </button>
                </div>

                {activeTab === 'allotment' && (
                    <button
                        onClick={handleBulkAllocate}
                        disabled={loading || unallocatedTeamsList.length === 0}
                        className="w-full sm:w-auto flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white font-black text-xs uppercase tracking-widest rounded-2xl shadow-lg shadow-amber-500/15 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <Zap className="w-4 h-4" /> Bulk Allocate Preferences
                    </button>
                )}
            </div>

            {/* TAB CONTENTS */}
            <AnimatePresence mode="wait">
                {loading ? (
                    <div className="h-[400px] bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col items-center justify-center gap-3">
                        <div className="w-10 h-10 border-4 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin"></div>
                        <p className="text-sm font-bold text-slate-500">Querying database allocations...</p>
                    </div>
                ) : activeTab === 'allotment' ? (

                    /* ALLOTMENT CANVAS TAB */
                    <motion.div key="allotment-tab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">

                        {/* Filters Bar */}
                        <div className="flex flex-col lg:flex-row gap-4 items-center justify-between bg-slate-50 dark:bg-slate-900/30 p-4 rounded-3xl border border-slate-200/40 dark:border-slate-800">

                            {/* Search bar */}
                            <div className="relative w-full lg:max-w-md">
                                <Search className="w-4.5 h-4.5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="Search teams by ID, name, or members..."
                                    value={allotmentSearch}
                                    onChange={(e) => setAllotmentSearch(e.target.value)}
                                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl text-xs font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>

                            {/* Filters selectors */}
                            <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
                                <div className="flex items-center space-x-2 bg-white dark:bg-slate-800 p-1.5 rounded-xl border border-slate-200 dark:border-slate-700">
                                    <span className="text-[10px] font-black uppercase text-slate-400 px-2 flex items-center gap-1"><Filter className="w-3 h-3" /> Status:</span>
                                    {['all', 'unallocated', 'allocated'].map(st => (
                                        <button
                                            key={st}
                                            onClick={() => setAllotmentStatusFilter(st)}
                                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider transition-colors ${allotmentStatusFilter === st ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-700'}`}
                                        >
                                            {st}
                                        </button>
                                    ))}
                                </div>

                            </div>

                        </div>

                        {/* Teams Canvas Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                            {displayedCanvasTeams.map(team => {
                                const isAllocated = getHasAllocated(team);
                                const teamYear = getTeamYear(team);

                                const memberIds = memberList(team.members).map(m => String(m?.id || m?.student_id || m).trim());
                                const leaderId = String(team.leader).trim();
                                const allIds = [leaderId, ...memberIds];

                                const prefRecord = preferences.find(p => allIds.includes(String(p.student_id).trim()));
                                const hasPreferences = !!prefRecord;
                                const prefsList = hasPreferences && Array.isArray(prefRecord.preferences) ? prefRecord.preferences : [];

                                const allowedProblemStatements = teamAllowedPsMap.get(team.id) || [];

                                return (
                                    <div key={team.id} className={`bg-white dark:bg-slate-800 border rounded-3xl p-6 flex flex-col shadow-sm hover:shadow-xl transition-all group min-h-[300px] ${isAllocated ? 'border-emerald-500/30 hover:border-emerald-500/60 dark:border-emerald-500/20' : 'border-slate-200 dark:border-slate-700 hover:border-indigo-300'}`}>

                                        {/* Card Header */}
                                        <div className="flex justify-between items-start gap-2 mb-3">
                                            <div>
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className={`text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded ${teamYear === 3 ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' : 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'}`}>
                                                        {teamYear === 3 ? '3rd Year' : '4th Year'}
                                                    </span>
                                                    <span className={`text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded ${isAllocated ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400' : 'bg-amber-100 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'}`}>
                                                        {isAllocated ? 'Allocated' : 'Unallocated'}
                                                    </span>
                                                </div>
                                                <h3 className="text-base font-black text-slate-800 dark:text-slate-200 mt-2 whitespace-nowrap">
                                                    {teamLabel(team.id, team, semesterMap)}
                                                </h3>
                                            </div>
                                            <span className="text-[10px] font-bold text-slate-400">ID: {team.id}</span>
                                        </div>

                                        {/* Members */}
                                        <div className="mb-4">
                                            <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1.5">Roster Ranks</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {memberList(team.members).map((m, idx) => (
                                                    <span key={`${m.id || m.student_id || idx}-${idx}`} className="text-[10px] font-bold bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded" title={m.roll || m.student_id}>
                                                        {m.name}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="flex-1 flex flex-col justify-end border-t border-slate-100 dark:border-slate-800 pt-4 mt-auto">
                                            {isAllocated ? (
                                                /* ALLOCATED PROJECT VIEW */
                                                (() => {
                                                    const approvedProp = getApprovedProposal(team.id);
                                                    const displayTitle = approvedProp ? approvedProp.title : team.title;
                                                    const displayDomain = approvedProp ? (approvedProp.domain || 'Custom Proposal') : team.domain;
                                                    return (
                                                        <div className="space-y-4">
                                                            <div className="bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-100 dark:border-emerald-500/10 p-4 rounded-2xl flex items-start gap-3">
                                                                <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                                                                <div className="min-w-0 flex-1">
                                                                    <div className="text-[9px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                                                                        {approvedProp ? 'Approved Custom Proposal' : 'Approved Project'}
                                                                    </div>
                                                                    <h4 className="text-xs font-black text-slate-800 dark:text-white mt-1 break-words">{displayTitle}</h4>
                                                                    {displayDomain && (
                                                                        <span className="inline-block text-[9px] font-bold bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded mt-2">
                                                                            {displayDomain}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            <button
                                                                onClick={() => handleDeallocate(team)}
                                                                className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 hover:bg-rose-50 dark:hover:bg-rose-950/20 border border-slate-200 dark:border-slate-700 hover:border-rose-200 dark:hover:border-rose-900/30 text-slate-500 hover:text-rose-600 rounded-xl text-xs font-bold uppercase tracking-wider transition-colors"
                                                            >
                                                                <X className="w-3.5 h-3.5" /> De-allocate / Reset
                                                            </button>
                                                        </div>
                                                    );
                                                })()
                                            ) : (
                                                /* UNALLOCATED PREFERENCES VIEW */
                                                <div className="space-y-4">
                                                    {hasPreferences && prefsList.length > 0 ? (
                                                        <div className="space-y-2">
                                                            <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">Student Preferences</div>
                                                            {prefsList.map((pref, i) => {
                                                                const isTaken = !isPsAvailableForTeam(allocationsByTitle, pref.title, team.id);
                                                                return (
                                                                    <div key={pref.id || `${pref.title}-${i}`} className={`flex items-center justify-between text-xs p-2 bg-slate-50 dark:bg-slate-900/40 border rounded-xl gap-3 ${isTaken ? 'border-slate-100 dark:border-slate-800 opacity-60' : 'border-indigo-100 dark:border-indigo-900/20'}`}>
                                                                        <div className="flex items-center gap-2 min-w-0 flex-1">
                                                                            <span className={`font-black text-[9px] w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${isTaken ? 'bg-slate-200 dark:bg-slate-800 text-slate-400' : 'bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400'}`}>{i + 1}</span>
                                                                            <span className="font-bold text-slate-700 dark:text-slate-300 truncate" title={pref.title}>{pref.title}</span>
                                                                        </div>
                                                                        {isTaken ? (
                                                                            <span className="text-[9px] font-bold text-slate-400 select-none px-2 shrink-0">Taken</span>
                                                                        ) : (
                                                                            <button
                                                                                onClick={() => {
                                                                                    if (window.confirm(`Allocate Preference #${i + 1} "${pref.title}" to ${teamLabel(team.id, team, semesterMap)}?`)) {
                                                                                        handleAllocate(team, pref.title, pref.description, pref.domain);
                                                                                    }
                                                                                }}
                                                                                className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-black text-[9px] uppercase tracking-wider transition-colors shrink-0 flex items-center gap-1"
                                                                            >
                                                                                Allot <Check className="w-2.5 h-2.5" />
                                                                            </button>
                                                                        )}
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    ) : (
                                                        <div className="bg-amber-500/5 border border-amber-500/10 p-3 rounded-2xl flex items-start gap-2.5">
                                                            <Info className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                                                            <p className="text-[10px] font-bold text-amber-700 dark:text-amber-400/90 leading-normal">
                                                                No preferences submitted. Allocate a statement manually from the options below.
                                                            </p>
                                                        </div>
                                                    )}

                                                    {/* Manual Dropdown Selector */}
                                                    <div className="space-y-2">
                                                        <select
                                                            id={`manual-select-${team.id}`}
                                                            className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-xs font-bold rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 outline-none"
                                                        >
                                                            <option value="">Choose Problem Statement...</option>
                                                            {allowedProblemStatements.map(ps => (
                                                                <option key={ps.id} value={JSON.stringify(ps)}>
                                                                    {ps.title} ({ps.domain || 'General'}) {ps.year ? `[${ps.year} Year]` : '[Common]'}
                                                                </option>
                                                            ))}
                                                        </select>
                                                        <button
                                                            onClick={() => {
                                                                const selectEl = document.getElementById(`manual-select-${team.id}`);
                                                                const val = selectEl?.value;
                                                                if (!val) { alert("Please select a problem statement first."); return; }
                                                                const ps = JSON.parse(val);
                                                                if (window.confirm(`Allocate manual project "${ps.title}" to ${teamLabel(team.id, team, semesterMap)}?`)) {
                                                                    handleAllocate(team, ps.title, ps.description, ps.domain);
                                                                }
                                                            }}
                                                            className="w-full flex items-center justify-center gap-1.5 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-wider transition-colors shadow-sm"
                                                        >
                                                            Allocate Project
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>

                                    </div>
                                );
                            })}
                        </div>

                        {displayedCanvasTeams.length === 0 && (
                            <div className="h-[200px] bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-center text-sm font-bold text-slate-400 italic">
                                No teams found matching the active filters.
                            </div>
                        )}

                    </motion.div>
                ) : activeTab === 'statements' ? (

                    /* PROBLEM STATEMENTS TAB */
                    <motion.div key="statements-tab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">

                        {/* Control panel & filters */}
                        <div className="flex flex-col lg:flex-row gap-4 items-center justify-between bg-slate-50 dark:bg-slate-900/30 p-4 rounded-3xl border border-slate-200/40 dark:border-slate-800">

                            {/* Search bar */}
                            <div className="relative w-full lg:max-w-md">
                                <Search className="w-4.5 h-4.5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="Search statements by title, details, category..."
                                    value={psSearch}
                                    onChange={(e) => setPsSearch(e.target.value)}
                                    className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl text-xs font-bold outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>

                            {/* Type filter & Add buttons */}
                            <div className="flex flex-wrap items-center gap-4 w-full lg:w-auto">
                                <div className="flex items-center space-x-2 bg-white dark:bg-slate-800 p-1.5 rounded-xl border border-slate-200 dark:border-slate-700">
                                    <span className="text-[10px] font-black uppercase text-slate-400 px-2 flex items-center gap-1"><Filter className="w-3 h-3" /> Type:</span>
                                    {['all', 'Hardware', 'Software'].map(type => (
                                        <button
                                            key={type}
                                            onClick={() => setPsTypeFilter(type)}
                                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider transition-colors ${psTypeFilter === type ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-700'}`}
                                        >
                                            {type}
                                        </button>
                                    ))}
                                </div>

                                <div className="flex items-center space-x-2 bg-white dark:bg-slate-800 p-1.5 rounded-xl border border-slate-200 dark:border-slate-700">
                                    <span className="text-[10px] font-black uppercase text-slate-400 px-2 flex items-center gap-1"><Filter className="w-3 h-3" /> Year:</span>
                                    {[
                                        { id: 'all', label: 'All Years' },
                                        { id: '3', label: '3rd Year' },
                                        { id: '4', label: '4th Year' },
                                        { id: '2', label: '2nd Year' }
                                    ].map(y => (
                                        <button
                                            key={y.id}
                                            onClick={() => setPsYearFilter(y.id)}
                                            className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider transition-colors ${psYearFilter === y.id ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-700'}`}
                                        >
                                            {y.label}
                                        </button>
                                    ))}
                                </div>

                                <button
                                    onClick={() => setPsModal({ mode: 'create', data: { title: '', description: '', domain: 'General', year: '', ps_type: 'Software' } })}
                                    className="flex items-center justify-center gap-1.5 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors shadow-md shadow-indigo-500/10 cursor-pointer"
                                >
                                    <Plus className="w-4 h-4" /> Add Problem Statement
                                </button>
                                <button
                                    onClick={handleSendPsAnnouncementEmail}
                                    disabled={sendingPsEmail}
                                    className="flex items-center justify-center gap-1.5 px-4 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors shadow-md shadow-purple-500/10 cursor-pointer disabled:opacity-50"
                                    title="Manually send Problem Statement release announcement emails to all students"
                                >
                                    <Send className="w-4 h-4" /> {sendingPsEmail ? 'Sending Emails...' : 'Mass Email PS Released'}
                                </button>
                                <button
                                    onClick={() => setIsNotifyModalOpen(true)}
                                    className="flex items-center justify-center gap-1.5 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-colors shadow-md shadow-indigo-500/10 cursor-pointer"
                                    title="Send email reminders to teams pending PS selection or GitHub repository submission"
                                >
                                    <Send className="w-4 h-4" /> Email Pending Teams
                                </button>
                            </div>


                        </div>

                        {/* Compact Import Widget */}
                        <div className="bg-white dark:bg-slate-800 p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-sm">
                            <div className="space-y-1">
                                <h3 className="text-sm font-black text-slate-800 dark:text-white flex items-center gap-2">
                                    <ScrollText className="w-4 h-4 text-indigo-500" />
                                    Import Problem Statements via File
                                </h3>
                                <p className="text-xs text-slate-500">Upload Excel (.xlsx/.xls), CSV (.csv), PDF (.pdf), or Word (.docx/.doc) containing problem statements roster.</p>
                            </div>

                            <div className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900/50 p-2.5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 shrink-0 flex-wrap">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 px-2">Import Target:</span>
                                <select
                                    id="upload-year-select"
                                    value={uploadYear}
                                    onChange={(e) => setUploadYear(e.target.value)}
                                    className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-2 outline-none cursor-pointer"
                                >
                                    <option value="">Common (All Active Batches)</option>
                                    {activeBatchOptions.length > 0 ? (
                                        activeBatchOptions.map(o => (
                                            <option key={o.value} value={o.value} title={o.title}>{o.label}</option>
                                        ))
                                    ) : (
                                        <>
                                            <option value="2">2nd Year Only</option>
                                            <option value="3">3rd Year Only</option>
                                            <option value="4">4th Year Only</option>
                                        </>
                                    )}
                                </select>
                                <input
                                    type="file"
                                    id="ps-file-input"
                                    accept=".csv,.xlsx,.xls,.pdf,.docx,.doc"
                                    className="hidden"
                                    onChange={async (e) => {
                                        const file = e.target.files?.[0];
                                        if (!file) return;
                                        setImportFileName(file.name);
                                        setImporting(true);
                                        setImportProgress(10);
                                        setImportedCount(null);
                                        setImportStepText('Reading uploaded document & validating format...');

                                        let progressTimer = setInterval(() => {
                                            setImportProgress(prev => {
                                                if (prev < 40) {
                                                    setImportStepText('🤖 AI Agent parallel chunking & extracting problem statements...');
                                                    return prev + 6;
                                                } else if (prev < 85) {
                                                    setImportStepText('⚡ Structuring specs, tech stacks, deliverables & system architecture...');
                                                    return prev + 5;
                                                } else if (prev < 98) {
                                                    setImportStepText('💾 Saving parsed problem statements to database...');
                                                    return prev + 2;
                                                }
                                                return prev;
                                            });
                                        }, 400);

                                        try {
                                            const res = await api.importProblemStatements(file, uploadYear || null);
                                            clearInterval(progressTimer);
                                            setImportProgress(100);
                                            const count = (res && typeof res.count === 'number') ? res.count : (res?.data?.length || 0);
                                            setImportedCount(count);
                                            setImportStepText(`🎉 Done! Successfully parsed and saved ${count} Problem Statements to Database.`);
                                            setImportStatus(`Successfully imported ${count} Problem Statements!`);
                                            loadData();
                                            setTimeout(() => setImporting(false), 4000);
                                        } catch (err) {
                                            clearInterval(progressTimer);
                                            setImportProgress(0);
                                            setImportStepText(`❌ Error: ${err.message || 'Failed'}`);
                                            setImportStatus(`Import error: ${err.message || 'Failed'}`);
                                            setTimeout(() => setImporting(false), 3500);
                                        }
                                    }}
                                />
                                <label htmlFor="ps-file-input" className="cursor-pointer flex items-center gap-2 px-4 py-2 bg-indigo-550 dark:bg-indigo-500/20 hover:bg-indigo-600/30 hover:bg-indigo-50 dark:hover:bg-slate-700 rounded-xl transition-colors text-xs font-black uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                                    {importing ? 'Processing...' : 'Upload File'}
                                </label>
                                {importStatus && (
                                    <span className={`text-[10px] font-bold px-3 py-1.5 rounded-lg ${importStatus.includes('Error') ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/20' : 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20'}`}>
                                        {importStatus}
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Select All & Bulk Actions Sub-bar */}
                        <div className="flex items-center justify-between gap-4 bg-slate-50 dark:bg-slate-900/30 p-3 rounded-2xl border border-slate-200/50 dark:border-slate-800">
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => {
                                        const displayedIds = displayedProblemStatements.map(ps => ps.id);
                                        const allSelected = displayedIds.every(id => selectedPsIds.includes(id));
                                        if (allSelected) {
                                            setSelectedPsIds(prev => prev.filter(id => !displayedIds.includes(id)));
                                        } else {
                                            setSelectedPsIds(prev => [...new Set([...prev, ...displayedIds])]);
                                        }
                                    }}
                                    className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900 rounded-xl text-xs font-bold text-slate-650 dark:text-slate-350 transition-colors shadow-sm cursor-pointer animate-none"
                                >
                                    <input
                                        type="checkbox"
                                        checked={displayedProblemStatements.length > 0 && displayedProblemStatements.every(ps => selectedPsIds.includes(ps.id))}
                                        onChange={() => { }}
                                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5 cursor-pointer"
                                    />
                                    <span>Select All Displayed ({displayedProblemStatements.length})</span>
                                </button>
                                {selectedPsIds.length > 0 && (
                                    <span className="text-xs font-bold text-slate-500 dark:text-slate-400">
                                        {selectedPsIds.length} statement{selectedPsIds.length > 1 ? 's' : ''} selected
                                    </span>
                                )}
                            </div>

                            {selectedPsIds.length > 0 && (
                                <button
                                    onClick={handleDeleteSelectedProblemStatements}
                                    className="flex items-center justify-center gap-1.5 px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-black uppercase tracking-wider transition-colors shadow-md shadow-rose-500/10 active:scale-95 cursor-pointer"
                                >
                                    <Trash2 className="w-3.5 h-3.5" /> Delete Selected ({selectedPsIds.length})
                                </button>
                            )}
                        </div>

                        {/* Problem Statements List — reference design (horizontal rows with hover reveal) */}
                        <div className="flex flex-col gap-4">
                            {displayedProblemStatements.map((ps, index) => {
                                const psAllocations = getPsAllocations(ps.title);
                                const isPsFull = psAllocations.length >= PS_TEAM_CAPACITY;
                                const isSelected = selectedPsIds.includes(ps.id);
                                return (
                                    <motion.div
                                        layout
                                        initial={{ opacity: 0, scale: 0.98, y: 5 }}
                                        animate={{ opacity: 1, scale: 1, y: 0 }}
                                        exit={{ opacity: 0, scale: 0.98, y: -5 }}
                                        key={ps.id}
                                        onClick={() => setSelectedPsForAnalysis(ps)}
                                        className={`p-4 md:p-5 rounded-2xl transition-all duration-300 group cursor-pointer relative overflow-hidden border ${isPsFull
                                            ? 'bg-slate-50/50 dark:bg-slate-900/20 border-slate-200 dark:border-slate-800 opacity-80'
                                            : isSelected
                                                ? 'bg-indigo-50/50 dark:bg-indigo-900/10 border-indigo-300 dark:border-indigo-700 shadow-sm'
                                                : 'bg-white dark:bg-slate-800/40 hover:bg-slate-50/80 dark:hover:bg-slate-800 border-slate-200/80 dark:border-slate-700/60 hover:border-indigo-300 dark:hover:border-indigo-500 hover:shadow-lg hover:shadow-indigo-500/5'
                                            }`}
                                    >
                                        {/* Subtle gradient on hover */}
                                        {!isPsFull && (
                                            <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/0 via-indigo-500/5 to-purple-500/10 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                                        )}

                                        <div className="flex gap-4 md:gap-5 items-center relative z-10">
                                            {/* Left: Checkbox & Index number */}
                                            <div
                                                className="flex flex-col items-center justify-center gap-2 shrink-0"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onClick={(e) => e.stopPropagation()}
                                                    onChange={(e) => {
                                                        e.stopPropagation();
                                                        setSelectedPsIds(prev =>
                                                            prev.includes(ps.id)
                                                                ? prev.filter(id => id !== ps.id)
                                                                : [...prev, ps.id]
                                                        );
                                                    }}
                                                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4 cursor-pointer"
                                                />
                                                <div className="flex items-center justify-center w-8 h-8 md:w-10 md:h-10 rounded-xl bg-slate-100 dark:bg-slate-900/80 text-sm md:text-base font-bold text-slate-400 dark:text-slate-500 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 group-hover:bg-indigo-50 dark:group-hover:bg-indigo-500/20 transition-all duration-300 font-mono shadow-inner border border-transparent group-hover:border-indigo-100 dark:group-hover:border-indigo-500/30">
                                                    {String(index + 1).padStart(2, '0')}
                                                </div>
                                            </div>

                                            {/* Content Column */}
                                            <div className="flex-1 flex flex-col justify-center min-h-[3rem]">
                                                <div className="flex justify-between items-start md:items-center flex-col md:flex-row gap-2">
                                                    <div>
                                                        <h4 className="font-bold text-slate-800 dark:text-slate-100 transition-colors text-sm md:text-[16px] group-hover:text-indigo-700 dark:group-hover:text-indigo-300 leading-tight">
                                                            {ps.title}
                                                        </h4>
                                                        <p className="text-xs text-slate-400 mt-1">ID: {ps.id}</p>
                                                    </div>

                                                    {/* Badges */}
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        {(() => {
                                                            const badge = getDomainCategoryBadge(ps);
                                                            return (
                                                                <span className={`text-[9px] md:text-[10px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-lg border transition-all shadow-sm ${badge.style}`}>
                                                                    {badge.label}
                                                                </span>
                                                            );
                                                        })()}
                                                        {psAllocations.length > 0 && (
                                                            <span className="text-[9px] md:text-[10px] font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2 md:px-2.5 py-1 rounded-lg flex items-center gap-1 border border-rose-100 dark:border-rose-900/50" title={psAllocations.map(t => teamLabel(t.id, t, semesterMap)).join(', ')}>
                                                                <Lock className="w-3 h-3" /> {isPsFull ? 'Allocated' : `${psAllocations.length}/${PS_TEAM_CAPACITY} Allocated`}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Hover Action Buttons (reveal on hover) */}
                                                <div className="h-0 overflow-hidden opacity-0 group-hover:h-auto group-hover:opacity-100 group-hover:mt-4 transition-all duration-300 flex items-center gap-2 md:gap-3 flex-wrap">
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setSelectedPsForAnalysis(ps);
                                                        }}
                                                        className="justify-center bg-slate-900 hover:bg-slate-800 dark:bg-slate-100 dark:hover:bg-white text-white dark:text-slate-900 px-4 md:px-5 py-2 rounded-xl text-xs font-bold transition-transform duration-200 active:scale-95 shadow-md flex items-center gap-2"
                                                    >
                                                        <Eye className="w-3.5 h-3.5" /> View Full Details
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setPsModal({ mode: 'edit', data: { ...ps, ps_type: isHardwarePs(ps) ? 'Hardware' : 'Software', year: ps.year ? String(ps.year) : '' } });
                                                        }}
                                                        className="justify-center bg-white dark:bg-slate-800/80 hover:bg-indigo-50 dark:hover:bg-slate-700 text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-slate-600 px-4 md:px-5 py-2 rounded-xl text-xs font-bold transition-all duration-200 active:scale-95 shadow-sm flex items-center gap-2"
                                                    >
                                                        <Edit className="w-3.5 h-3.5" /> Edit PS
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleDeleteProblemStatement(ps.id, ps.title);
                                                        }}
                                                        className="justify-center bg-white dark:bg-slate-800/80 hover:bg-rose-50 dark:hover:bg-slate-700 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-slate-600 px-4 md:px-5 py-2 rounded-xl text-xs font-bold transition-all duration-200 active:scale-95 shadow-sm flex items-center gap-2"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" /> Delete
                                                    </button>
                                                </div>
                                            </div>

                                            {/* Right Chevron Arrow */}
                                            <div className="w-8 h-8 md:w-10 md:h-10 rounded-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 text-slate-400 group-hover:bg-indigo-600 group-hover:text-white dark:group-hover:bg-indigo-500 transition-all duration-300 shrink-0 transform group-hover:scale-110 shadow-sm group-hover:shadow-indigo-500/30">
                                                <ChevronRight className="w-4 h-4 md:w-5 md:h-5 transform group-hover:translate-x-0.5 transition-transform duration-300" />
                                            </div>
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </div>

                        {displayedProblemStatements.length === 0 && (
                            <div className="h-[200px] bg-white dark:bg-slate-800 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-center text-sm font-bold text-slate-400 italic">
                                No Problem Statements found. Click "Add Problem Statement" to manually create one.
                            </div>
                        )}

                    </motion.div>
                ) : (

                    /* ALLOCATED TAB */
                    <motion.div key="allocated-tab" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                        <div className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col min-h-[400px]">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 flex items-center justify-between">
                                <div>
                                    <h2 className="text-lg font-black text-slate-800 dark:text-white flex items-center">
                                        <CheckCircle className="w-5 h-5 mr-2 text-emerald-500" /> Allocated Projects
                                    </h2>
                                    <p className="text-xs text-slate-500 mt-0.5">Teams that have a problem statement allotted, with the project assigned to each.</p>
                                </div>
                                <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-200/50 dark:border-emerald-500/20">{allocatedTeamsList.length} Allocated</span>
                            </div>
                            <div className="p-6">
                                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                                    {allocatedTeamsList.map(team => {
                                        const matchedPs = allPsTitlesPool.find(ps => (ps.title || '').trim().toLowerCase() === (team.title || '').trim().toLowerCase());
                                        return (
                                            <div key={team.id} className="p-5 rounded-2xl border bg-emerald-50/50 dark:bg-emerald-500/5 border-emerald-200 dark:border-emerald-500/30 transition-all hover:shadow-md flex flex-col justify-between min-h-[180px]">
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-start mb-2 gap-2">
                                                        <h3 className="font-black text-sm text-slate-800 dark:text-slate-200 line-clamp-2">{team.title}</h3>
                                                        <span className="shrink-0 inline-flex items-center text-[9px] font-black uppercase tracking-widest text-white bg-emerald-500 px-2 py-0.5 rounded shadow-sm"><CheckCircle className="w-2.5 h-2.5 mr-1" /> Allotted</span>
                                                    </div>
                                                    <div className="text-xs font-bold text-slate-600 dark:text-slate-400">
                                                        Allotted To: <span className="text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-0.5 rounded italic">{teamLabel(team.id, team, semesterMap)}</span>
                                                    </div>
                                                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                                                        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 bg-white dark:bg-slate-800 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700">{isHardwarePs(matchedPs || team) ? 'Hardware' : 'Software'}</span>
                                                        {team.domain && team.domain !== 'General' && (
                                                            <span className="text-[9px] font-black uppercase tracking-widest text-slate-500 bg-white dark:bg-slate-800 px-2 py-0.5 rounded border border-slate-200 dark:border-slate-700 line-clamp-1">{team.domain}</span>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800/50 flex items-center justify-end gap-4">
                                                    <button
                                                        onClick={() => setSelectedPsForAnalysis(matchedPs || { id: null, title: team.title, description: team.description, domain: team.domain || 'General', difficulty: 'Medium' })}
                                                        className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:text-indigo-600 dark:hover:text-indigo-400 hover:border-indigo-200 dark:hover:border-indigo-500/30 rounded-xl transition-colors shadow-sm flex items-center gap-1.5"
                                                    >
                                                        <Eye className="w-3 h-3" /> View Blueprint
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                {allocatedTeamsList.length === 0 && (
                                    <div className="h-[250px] flex flex-col items-center justify-center gap-2 text-sm font-bold text-slate-400 py-12 italic">
                                        <Info className="w-10 h-10 opacity-50" />
                                        No projects allotted yet.
                                    </div>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* PROBLEM STATEMENT ADD/EDIT MODAL */}
            <AnimatePresence>
                {psModal && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                        onClick={() => !psSubmitting && setPsModal(null)}
                    >
                        <motion.div
                            initial={{ scale: 0.95, y: 20 }}
                            animate={{ scale: 1, y: 0 }}
                            exit={{ scale: 0.95, y: 20 }}
                            className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-2xl w-full max-w-lg overflow-hidden"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Modal Header */}
                            <div className="bg-slate-900 p-6 flex items-center justify-between text-white border-b border-slate-800">
                                <div className="flex items-center space-x-2">
                                    <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400"><ScrollText className="w-5 h-5" /></div>
                                    <div>
                                        <h3 className="text-lg font-black tracking-tight">{psModal.mode === 'create' ? 'Add Problem Statement' : 'Edit Problem Statement'}</h3>
                                        <p className="text-xs text-slate-400">Specify details and Year targeted for the problem statement</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => !psSubmitting && setPsModal(null)}
                                    className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded-full transition-colors text-slate-300"
                                >
                                    <X className="w-4.5 h-4.5" />
                                </button>
                            </div>

                            {/* Modal Form */}
                            <form onSubmit={handleSaveProblemStatement} className="p-6 space-y-4">
                                <div className="space-y-1">
                                    <label className="block text-xs font-black text-slate-600 dark:text-slate-300 uppercase tracking-wider">Title</label>
                                    <input
                                        type="text"
                                        required
                                        placeholder="e.g. Smart Traffic Management System"
                                        value={psModal.data.title}
                                        onChange={e => setPsModal(prev => ({ ...prev, data: { ...prev.data, title: e.target.value } }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-bold text-slate-800 dark:text-white"
                                    />
                                </div>

                                <div className="space-y-1">
                                    <label className="block text-xs font-black text-slate-600 dark:text-slate-300 uppercase tracking-wider">Description</label>
                                    <textarea
                                        required
                                        rows={3}
                                        placeholder="Enter details of constraints, APIs or target scopes..."
                                        value={psModal.data.description}
                                        onChange={e => setPsModal(prev => ({ ...prev, data: { ...prev.data, description: e.target.value } }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-bold text-slate-800 dark:text-white"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-1">
                                        <label className="block text-xs font-black text-slate-600 dark:text-slate-300 uppercase tracking-wider">Type (Hardware / Software)</label>
                                        <select
                                            value={psModal.data.ps_type || 'Software'}
                                            onChange={e => setPsModal(prev => ({ ...prev, data: { ...prev.data, ps_type: e.target.value } }))}
                                            className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-bold text-slate-800 dark:text-white cursor-pointer"
                                        >
                                            <option value="Software">Software</option>
                                            <option value="Hardware">Hardware</option>
                                        </select>
                                    </div>
                                </div>

                                <div className="space-y-1">
                                    <label className="block text-xs font-black text-slate-600 dark:text-slate-300 uppercase tracking-wider">Target Batch / Year</label>
                                    <select
                                        value={psModal.data.year}
                                        onChange={e => setPsModal(prev => ({ ...prev, data: { ...prev.data, year: e.target.value } }))}
                                        className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-xs font-bold text-slate-750 dark:text-slate-300 cursor-pointer"
                                    >
                                        <option value="">Common (Available for all active batches)</option>
                                        {activeBatchOptions.length > 0 ? (
                                            activeBatchOptions.map(o => (
                                                <option key={o.value} value={o.value} title={o.title}>{o.label}</option>
                                            ))
                                        ) : (
                                            <>
                                                <option value="2">2nd Year Only</option>
                                                <option value="3">3rd Year Only</option>
                                                <option value="4">4th Year Only</option>
                                            </>
                                        )}
                                    </select>
                                </div>

                                {/* Modal Footer Buttons */}
                                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex gap-3">
                                    <button
                                        type="button"
                                        disabled={psSubmitting}
                                        onClick={() => setPsModal(null)}
                                        className="flex-1 py-3 text-xs font-bold text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={psSubmitting}
                                        className="flex-1 py-3 text-xs font-black uppercase tracking-wider text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition-all shadow-md shadow-indigo-500/10 flex items-center justify-center gap-1.5"
                                    >
                                        {psSubmitting ? 'Saving...' : 'Save Statement'}
                                    </button>
                                </div>

                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Problem Statement Detailed Analysis Modal (PsArchitecturePlanModal) */}
            {selectedPsForAnalysis && (
                <PsArchitecturePlanModal
                    ps={selectedPsForAnalysis}
                    onClose={() => setSelectedPsForAnalysis(null)}
                    onGenerateAi={handleGenerateOpenAISuggestions}
                    aiGenerating={aiGenerating}
                    allocations={getPsAllocations(selectedPsForAnalysis.title)}
                />
            )}

            {/* Live AI Agent Document Import & Processing Modal */}
            <AnimatePresence>
                {importing && (
                    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 overflow-hidden">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 bg-[#060609]/85 backdrop-blur-md"
                        />
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 15 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 15 }}
                            className="relative w-full max-w-md bg-[#0A0A0F] text-[#E8E6E1] rounded-2xl shadow-[0_0_60px_rgba(108,60,225,0.35)] border border-[#FFFFFF15] p-6 z-10 space-y-5"
                        >
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#6C3CE1] to-[#06B6D4] flex items-center justify-center text-white font-black text-sm shadow-md animate-pulse">
                                    <Sparkles className="w-5 h-5 text-white animate-spin" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <h3 className="text-sm font-extrabold text-white truncate">AI Agent Document Processing</h3>
                                    <p className="text-[11px] font-mono text-slate-400 truncate">{importFileName || 'Uploading document...'}</p>
                                </div>
                                <button
                                    onClick={() => setImporting(false)}
                                    className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-[#FFFFFF10] transition-colors cursor-pointer"
                                    title="Close / Run in background"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            {/* Progress Bar & Status Text */}
                            <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs font-mono font-bold">
                                    <span className="text-[#06B6D4] flex items-center gap-1.5">
                                        <Zap className="w-3.5 h-3.5 animate-bounce" /> {importedCount !== null ? `🎉 ${importedCount} PS Saved` : 'Processing & Enriching'}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        {importedCount !== null && (
                                            <span className="px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold">
                                                {importedCount} PS Done
                                            </span>
                                        )}
                                        <span className="text-[#8B5CF6]">{importProgress}%</span>
                                    </div>
                                </div>

                                <div className="w-full h-2.5 bg-[#13131A] rounded-full overflow-hidden border border-[#FFFFFF10]">
                                    <motion.div
                                        className="h-full bg-gradient-to-r from-[#6C3CE1] via-[#06B6D4] to-[#10B981]"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${importProgress}%` }}
                                        transition={{ ease: 'easeOut', duration: 0.4 }}
                                    />
                                </div>

                                <p className="text-[11px] font-bold text-slate-300 min-h-[32px] leading-relaxed pt-1">
                                    {importStepText}
                                </p>
                            </div>

                            {/* Step Indicator Badges */}
                            <div className="grid grid-cols-4 gap-2 pt-2 border-t border-[#FFFFFF10] text-[10px] font-mono font-bold">
                                <div className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-colors ${importProgress >= 10 ? 'bg-[#6C3CE1]/20 text-[#A78BFA] border border-[#6C3CE1]/40' : 'text-slate-600'}`}>
                                    <ScrollText className="w-3.5 h-3.5" />
                                    <span>Upload</span>
                                </div>
                                <div className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-colors ${importProgress >= 30 ? 'bg-[#6C3CE1]/20 text-[#A78BFA] border border-[#6C3CE1]/40' : 'text-slate-600'}`}>
                                    <BrainCircuit className="w-3.5 h-3.5" />
                                    <span>Parsing</span>
                                </div>
                                <div className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-colors ${importProgress >= 75 ? 'bg-[#06B6D4]/20 text-[#38BDF8] border border-[#06B6D4]/40' : 'text-slate-600'}`}>
                                    <Sparkles className="w-3.5 h-3.5" />
                                    <span>OpenAI</span>
                                </div>
                                <div className={`flex flex-col items-center gap-1 p-2 rounded-xl transition-colors ${importProgress >= 100 ? 'bg-[#10B981]/20 text-[#34D399] border border-[#10B981]/40' : 'text-slate-600'}`}>
                                    <CheckCircle className="w-3.5 h-3.5" />
                                    <span>Save</span>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {/* Email Pending Teams Modal */}
            <NotifyPendingModal
                isOpen={isNotifyModalOpen}
                onClose={() => setIsNotifyModalOpen(false)}
            />
        </div>
    );
}
