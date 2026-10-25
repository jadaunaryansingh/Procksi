import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
    Users, Eye, Search, UserCheck, Mail, Calendar, Clock, BookOpen,
    CheckCircle, AlertCircle, X, ShieldAlert, Award, FileText, ChevronRight,
    User, Hash, GraduationCap, MapPin, Loader2, Sparkles, Shield, Key,
    Github, Code, ExternalLink, Lock, ClipboardList, ArrowRight, Plus, Trash2
} from 'lucide-react';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { apiFetchTable, apiPatchRow, apiDeleteRows, apiUpsertTable, getAuthHeaders } from '../lib/api';
import { upsertPanel } from '../services/panelSync';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamDisplayLabel, resolveTeamNumber } from '../lib/globalFilters';
import { sameTeam } from '../lib/teamUid';
import { getApiBaseUrl } from '../lib/apiBase';

export default function Views() {
    const { semesterMap, filterRows } = useGlobalFilters();
    const { data: mentorsData, setData: setMentorsData } = useSupabaseTableState('mentors', [], { orderBy: 'name' });
    const { data: panelsData, setData: setPanelsData } = useSupabaseTableState('panels', [], { orderBy: 'name' });
    const [activeTab, setActiveTab] = useState('Mentors');

    // Add Mentor State
    const [isAddMentorOpen, setIsAddMentorOpen] = useState(false);
    const [newMentorForm, setNewMentorForm] = useState({
        name: '',
        email: '',
        domains: '',
        is_active: true
    });

    // Add Panel State
    const [isAddPanelOpen, setIsAddPanelOpen] = useState(false);
    const [newPanelForm, setNewPanelForm] = useState({
        name: '',
        description: '',
        members: ''
    });

    const handleAddMentor = async (e) => {
        e.preventDefault();
        try {
            const domainArray = newMentorForm.domains.split(',').map(d => d.trim()).filter(Boolean);
            const row = {
                id: 'M-' + Date.now().toString().slice(-6),
                name: newMentorForm.name.trim(),
                email: newMentorForm.email.trim(),
                domains: domainArray,
                is_active: newMentorForm.is_active
            };
            const response = await apiUpsertTable('mentors', [row]);
            const saved = response?.[0] || row;
            setMentorsData(prev => [...prev, saved]);
            setIsAddMentorOpen(false);
            setNewMentorForm({ name: '', email: '', domains: '', is_active: true });
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
            setMentorsData(prev => prev.filter(m => m.id !== mentorId));
            alert("Mentor deleted successfully.");
        } catch (err) {
            console.error(err);
            alert("Error deleting mentor: " + err.message);
        }
    };

    const handleAddPanel = async (e) => {
        e.preventDefault();
        try {
            const membersArray = newPanelForm.members.split(',').map(m => m.trim()).filter(Boolean);
            const row = {
                id: 'P-' + Date.now().toString().slice(-6),
                name: newPanelForm.name.trim(),
                description: newPanelForm.description.trim(),
                members: membersArray
            };
            const response = await apiUpsertTable('panels', [row]);
            const saved = response?.[0] || row;
            setPanelsData(prev => [...prev, saved]);
            setIsAddPanelOpen(false);
            setNewPanelForm({ name: '', description: '', members: '' });
            alert('Panel added successfully!');
        } catch (err) {
            console.error(err);
            alert('Error adding panel: ' + err.message);
        }
    };

    const handleDeletePanel = async (panelId) => {
        if (!confirm("Are you sure you want to delete this panel?")) return;
        try {
            await apiDeleteRows('panels', { id: panelId });
            setPanelsData(prev => prev.filter(p => p.id !== panelId));
            alert("Panel deleted successfully.");
        } catch (err) {
            console.error(err);
            alert("Error deleting panel: " + err.message);
        }
    };
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedFilter, setSelectedFilter] = useState('AIML + IOT 6th Semester (3rd Year) 2026');

    const navigate = useNavigate();

    // Workspace Submissions states
    const [workspaceTeams, setWorkspaceTeams] = useState([]);
    const [workspaceGithub, setWorkspaceGithub] = useState([]);
    const [workspaceProposals, setWorkspaceProposals] = useState([]);
    const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);
    const [workspaceFilter, setWorkspaceFilter] = useState('All'); // 'All', 'Submitted', 'Pending'
    const [remindingPending, setRemindingPending] = useState(false);

    const handleRemindPending = async () => {
        if (!confirm("Are you sure you want to send email and portal reminders to all team members of pending workspace submissions?")) {
            return;
        }
        setRemindingPending(true);
        try {
            const API_BASE = getApiBaseUrl();
            const response = await fetch(`${API_BASE}/api/admin/communication/remind-pending`, {
                method: 'POST',
                headers: getAuthHeaders({ 'Content-Type': 'application/json' })
            });
            const data = await response.json();
            if (response.ok) {
                alert(`✅ Reminders Sent!\n\n` +
                      `• Pending Teams Emailed: ${data.pending_teams_count}\n` +
                      `• Portal Notifications Pushed: ${data.portal_notifications_sent}\n` +
                      `• Emails Dispatched via SMTP: ${data.emails_sent} (SMTP Delivered: ${data.smtp_delivered ? 'Yes' : 'No'})\n\n` +
                      `Note: If SMTP is not configured on the server, emails are logged in the database history.`);
            } else {
                alert(`❌ Failed to send reminders: ${data.detail || 'Unknown error'}`);
            }
        } catch (err) {
            console.error("Error sending reminders:", err);
            alert(`❌ Error connecting to server: ${err.message}`);
        } finally {
            setRemindingPending(false);
        }
    };

    useEffect(() => {
        if (activeTab === 'Workspace Submissions') {
            setLoadingWorkspaces(true);
            const API_BASE = getApiBaseUrl();
            
            Promise.all([
                apiFetchTable('teams_validation'),
                fetch(`${API_BASE}/api/data/github_data`, { headers: getAuthHeaders() })
                    .then(r => r.json())
                    .then(j => j.data || [])
                    .catch(() => []),
                apiFetchTable('proposals')
            ]).then(([teams, github, proposals]) => {
                setWorkspaceTeams(teams || []);
                setWorkspaceGithub(github || []);
                setWorkspaceProposals(proposals || []);
                setLoadingWorkspaces(false);
            }).catch(err => {
                console.error("Error loading workspace data:", err);
                setLoadingWorkspaces(false);
            });
        }
    }, [activeTab]);

    // Simulation states
    const [simulating, setSimulating] = useState(null); // { type: 'Mentor' | 'Panel', entity: {...} }
    const [simLoading, setSimLoading] = useState(false);
    const [simData, setSimData] = useState({ teams: [], proposals: [], slots: [] });

    // Portal approval modal
    const [approvalModal, setApprovalModal] = useState(null); // { mentor }
    const [approvalPortals, setApprovalPortals] = useState({ mentor: true, panel: false });
    const [approvalLoading, setApprovalLoading] = useState(false);

    const openApprovalModal = (mentor) => {
        setApprovalModal({ mentor });
        setApprovalPortals({ mentor: true, panel: false });
    };

    const handleConfirmApproval = async () => {
        if (!approvalModal) return;
        const { mentor } = approvalModal;
        if (!approvalPortals.mentor && !approvalPortals.panel) {
            alert('Please select at least one portal to grant access to.');
            return;
        }
        setApprovalLoading(true);
        try {
            const portalAccess = approvalPortals.mentor && approvalPortals.panel ? 'both'
                : approvalPortals.panel ? 'panel'
                : 'mentor';

            // Always activate in Supabase mentors table
            await apiPatchRow('mentors', mentor.id, {
                is_active: true,
                portal_access: portalAccess,
                panel_access: approvalPortals.panel,
            });
            setMentorsData(prev => prev.map(m =>
                m.id === mentor.id
                    ? { ...m, is_active: true, portal_access: portalAccess, panel_access: approvalPortals.panel }
                    : m
            ));

            if (approvalPortals.panel) {
                // Create/update panel account in panel portal backend using the signup password
                const panelId = (mentor.name || mentor.id)
                    .toUpperCase()
                    .replace(/[^A-Z0-9]+/g, '-')
                    .replace(/^-+|-+$/g, '');
                try {
                    await upsertPanel(panelId, {
                        display_name: mentor.name,
                        round_name: 'Mid-Term Evaluation',
                        is_active: true,
                        email: mentor.email,
                    });
                    alert(
                        `✅ Access granted!\n\n` +
                        `• Mentor Portal: ${approvalPortals.mentor ? 'Yes (' + mentor.email + ')' : 'No'}\n` +
                        `• Panel Portal: Yes\n\n` +
                        `Panel login email: ${mentor.email || 'N/A'}\n` +
                        `Password: [User's Signup Password]\n\n` +
                        `Please inform ${mentor.name} that they can log in using their signup credentials.`
                    );
                } catch (panelErr) {
                    console.warn('Panel portal sync failed:', panelErr.message);
                    alert(
                        `✅ Mentor portal access granted.\n` +
                        `⚠️ Panel portal sync failed: ${panelErr.message}\n\n` +
                        `You can manually set up the panel account in the Panels tab.`
                    );
                }
            } else {
                alert(`✅ ${mentor.name} approved for Mentor Portal access!`);
            }

            setApprovalModal(null);
        } catch (err) {
            alert('Approval failed: ' + err.message);
        } finally {
            setApprovalLoading(false);
        }
    };


    const handleRejectMentor = async (mentorId) => {
        if (!confirm("Are you sure you want to reject and delete this registration request?")) return;
        try {
            await apiDeleteRows('mentors', { id: mentorId });
            setMentorsData(prev => prev.filter(m => m.id !== mentorId));
            alert("Registration rejected and deleted.");
        } catch (err) {
            console.error("Failed to reject:", err);
            alert("Error rejecting registration.");
        }
    };

    const handleViewAs = async (type, entity) => {
        setSimulating({ type, entity });
        setSimLoading(true);
        try {
            const [teams, proposals, slots] = await Promise.all([
                apiFetchTable('teams_validation'),
                apiFetchTable('proposals'),
                apiFetchTable('schedule_slots')
            ]);
            setSimData({ teams, proposals, slots });
        } catch (err) {
            console.error("Failed to load simulation data:", err);
            alert("Error loading simulation details.");
        } finally {
            setSimLoading(false);
        }
    };

    const handleCloseSimulation = () => {
        setSimulating(null);
        setSimData({ teams: [], proposals: [], slots: [] });
    };

    const activeMentors = useMemo(() => {
        return mentorsData.filter(m => m.is_active !== false && m.name.toLowerCase().includes(searchTerm.toLowerCase()));
    }, [mentorsData, searchTerm]);

    const pendingMentors = useMemo(() => {
        return mentorsData.filter(m => m.is_active === false && m.name.toLowerCase().includes(searchTerm.toLowerCase()));
    }, [mentorsData, searchTerm]);

    const panels = useMemo(() => {
        return panelsData.filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()));
    }, [panelsData, searchTerm]);

    // Filter simulation data for the simulating mentor/panel
    const simulatedMentorData = useMemo(() => {
        if (!simulating || simulating.type !== 'Mentor') return null;
        const mentorName = String(simulating.entity.name || '').trim();
        const mentorId = String(simulating.entity.id || '').trim();
        
        // Find teams assigned to this mentor
        const assignedTeams = simData.teams.filter(t => {
            if (!t.mentor) return false;
            try {
                const parsed = typeof t.mentor === 'string' && (t.mentor.startsWith('[') || t.mentor.startsWith('{'))
                    ? JSON.parse(t.mentor)
                    : t.mentor;
                if (Array.isArray(parsed)) {
                    return parsed.some(m => {
                        if (typeof m === 'string') return m.trim().toLowerCase() === mentorName.toLowerCase();
                        if (m && typeof m === 'object') return (m.name && String(m.name).trim().toLowerCase() === mentorName.toLowerCase()) || (m.id && String(m.id).trim() === mentorId);
                        return false;
                    });
                }
                if (parsed && typeof parsed === 'object') {
                    return (parsed.name && String(parsed.name).trim().toLowerCase() === mentorName.toLowerCase()) || (parsed.id && String(parsed.id).trim() === mentorId);
                }
                return String(parsed).trim().toLowerCase() === mentorName.toLowerCase() || String(parsed).toLowerCase().includes(mentorName.toLowerCase());
            } catch {
                return String(t.mentor).toLowerCase().includes(mentorName.toLowerCase());
            }
        });

        // Get proposals for those teams — prefer canonical team_uid, fall back to id/number
        const teamIds = assignedTeams.map(t => String(t.id));
        const relatedProposals = simData.proposals.filter(p =>
            assignedTeams.some(t => sameTeam(p, t)) ||
            teamIds.includes(String(p.team_id || p.teamId || p.team_number || p.teamNumber))
        );

        // Count students
        let studentCount = 0;
        assignedTeams.forEach(t => {
            if (t.members) {
                try {
                    const parsedMembers = Array.isArray(t.members) ? t.members : JSON.parse(t.members);
                    studentCount += parsedMembers.length;
                } catch {
                    studentCount += 1;
                }
            }
        });

        return {
            assignedTeams,
            relatedProposals,
            studentCount
        };
    }, [simulating, simData]);

    const simulatedPanelData = useMemo(() => {
        if (!simulating || simulating.type !== 'Panel') return null;
        const panelName = String(simulating.entity.name || '').trim();
        const panelId = String(simulating.entity.id || '').trim();

        // Find slots scheduled for this panel
        const assignedSlots = simData.slots.filter(s => {
            const slotPanel = String(s.panel || s.panel_name || s.panel_id || s.panelId || '').trim();
            if (!slotPanel) return false;
            return slotPanel.toLowerCase() === panelName.toLowerCase() ||
                   (panelId && slotPanel.toLowerCase() === panelId.toLowerCase()) ||
                   slotPanel.toLowerCase().includes(panelName.toLowerCase());
        });
        
        // Find panel members
        let membersList = [];
        if (simulating.entity.members) {
            try {
                membersList = Array.isArray(simulating.entity.members)
                    ? simulating.entity.members
                    : JSON.parse(simulating.entity.members);
            } catch {
                membersList = [simulating.entity.name];
            }
        }

        return {
            assignedSlots,
            membersList
        };
    }, [simulating, simData]);

    const findTeamGithub = (team, githubList) => {
        if (!team || !Array.isArray(githubList)) return null;
        const tIdStr = String(team.id || '');
        const tUidStr = String(team.uid || '');
        const tNo = resolveTeamNumber(team.id, team);
        const tNoStr = tNo ? String(tNo) : '';

        // team_uid is the designated canonical, globally-unique key for all
        // team-scoped data; team_ref is a fallback for rows that predate the uid
        // backfill. team_id (team number) is only unique per semester, so two
        // different semesters can both have a "Team 5" — matching (or the "-T5"
        // suffix check below) on it alone can pull a different semester's team's
        // repo. Try the safe identifiers first, and only fall back to the
        // ambiguous number-based match for a team that has no uid at all (so the
        // fallback can't misfire for any team that does).
        const strict = githubList.find(g => {
            if (!g) return false;
            const gUid = g.team_uid ? String(g.team_uid) : '';
            const gRef = g.team_ref ? String(g.team_ref) : '';
            if (gUid && tUidStr && gUid === tUidStr) return true;
            if (gRef && gRef === tIdStr) return true;
            return false;
        });
        if (strict) return strict;
        if (tUidStr) return null; // has a uid but no matching row -> genuinely none, don't guess

        return githubList.find(g => {
            if (!g) return false;
            const gTid = g.team_id !== null && g.team_id !== undefined ? String(g.team_id) : '';
            const gRef = g.team_ref ? String(g.team_ref) : '';
            if (gTid && (gTid === tIdStr || (tNoStr && gTid === tNoStr))) return true;
            if (gRef && tNoStr && gRef.endsWith(`-T${tNoStr}`)) return true;
            return false;
        });
    };

    const workspaceStats = useMemo(() => {
        if (activeTab !== 'Workspace Submissions') return { total: 0, submitted: 0, pending: 0, percent: 0 };
        const filteredTeamsList = filterRows(workspaceTeams);
        const total = filteredTeamsList.length;
        const submitted = filteredTeamsList.filter(t => {
            const gh = findTeamGithub(t, workspaceGithub);
            // team_uid is the only safe match: team_number repeats across semesters,
            // so falling back to a number match here pulled a different semester's
            // team's proposal into this team's submission status.
            const prop = workspaceProposals.find(p => sameTeam(p, t));
            return !!((gh && gh.repository_url && gh.repository_url.trim()) || (prop && prop.technology_stack && prop.technology_stack.trim()));
        }).length;
        const pending = total - submitted;
        const percent = total > 0 ? Math.round((submitted / total) * 100) : 0;
        return { total, submitted, pending, percent };
    }, [activeTab, workspaceTeams, workspaceGithub, workspaceProposals, filterRows]);

    const filteredWorkspaces = useMemo(() => {
        if (activeTab !== 'Workspace Submissions') return [];
        const filteredTeamsList = filterRows(workspaceTeams);
        return filteredTeamsList.map(t => {
            const tNo = resolveTeamNumber(t.id, t);
            const gh = findTeamGithub(t, workspaceGithub);
            // team_uid is the only safe match: team_number repeats across semesters
            // (two different semesters can both have a "Team 5"), so falling back to
            // a number match here pulled a different semester's team's proposal
            // (and its technology_stack) into this team's submission status.
            const prop = workspaceProposals.find(p => sameTeam(p, t));
            const isSubmitted = !!((gh && gh.repository_url && gh.repository_url.trim()) || (prop && prop.technology_stack && prop.technology_stack.trim()));
            return {
                ...t,
                teamNo: tNo,
                repository_url: gh?.repository_url || '',
                tech_stack: prop?.technology_stack || '',
                isSubmitted
            };
        }).filter(t => {
            // Search filter
            const label = teamDisplayLabel(t.id, t, semesterMap).toLowerCase();
            const title = String(t.title || '').toLowerCase();
            const leader = String(t.leader || '').toLowerCase();
            let membersStr = '';
            if (t.members) {
                try {
                    const parsed = Array.isArray(t.members) ? t.members : JSON.parse(t.members);
                    membersStr = parsed.map(m => (m.name || '') + ' ' + (m.roll || '')).join(' ').toLowerCase();
                } catch { /* non-fatal: fall through to the default below */ }
            }
            
            const matchSearch = searchTerm
                ? label.includes(searchTerm.toLowerCase())
                  || title.includes(searchTerm.toLowerCase())
                  || leader.includes(searchTerm.toLowerCase())
                  || membersStr.includes(searchTerm.toLowerCase())
                : true;
            
            // Tab filter
            const matchFilter = workspaceFilter === 'All'
                ? true
                : workspaceFilter === 'Submitted'
                ? t.isSubmitted
                : !t.isSubmitted;
                
            return matchSearch && matchFilter;
        }).sort((a, b) => (a.teamNo || 0) - (b.teamNo || 0));
    }, [activeTab, workspaceTeams, workspaceGithub, workspaceProposals, searchTerm, workspaceFilter, semesterMap]);

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header and Controls */}
            <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-6 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm">
                
                {/* Tabs */}
                <div className="flex items-center space-x-2 bg-slate-100/50 dark:bg-slate-900/50 p-1.5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50">
                    <button 
                        onClick={() => setActiveTab('Mentors')} 
                        className={`px-6 py-2.5 rounded-xl text-sm font-black tracking-wide transition-all ${
                            activeTab === 'Mentors' 
                                ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                        }`}
                    >
                        Mentors
                    </button>
                    <button 
                        onClick={() => setActiveTab('Pending Approvals')} 
                        className={`px-6 py-2.5 rounded-xl text-sm font-black tracking-wide transition-all ${
                            activeTab === 'Pending Approvals' 
                                ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                        }`}
                    >
                        Pending Approvals
                    </button>
                    <button 
                        onClick={() => setActiveTab('Panels')} 
                        className={`px-6 py-2.5 rounded-xl text-sm font-black tracking-wide transition-all ${
                            activeTab === 'Panels' 
                                ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                        }`}
                    >
                        Panels
                    </button>
                    <button 
                        onClick={() => setActiveTab('Workspace Submissions')} 
                        className={`px-6 py-2.5 rounded-xl text-sm font-black tracking-wide transition-all ${
                            activeTab === 'Workspace Submissions' 
                                ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                        }`}
                    >
                        Workspace Submissions
                    </button>
                </div>

                {/* Filters and View controls */}
                <div className="flex flex-col sm:flex-row items-center gap-4 w-full xl:w-auto">
                    <div className="flex items-center space-x-3 w-full sm:w-auto p-2 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-200/50 dark:border-slate-700/50">
                        <span className="text-xs font-bold text-slate-500 hidden sm:block ml-2">Switch Context:</span>
                        <select 
                            className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm font-bold text-slate-700 dark:text-slate-300 rounded-xl px-4 py-2 outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                            value={selectedFilter}
                            onChange={(e) => setSelectedFilter(e.target.value)}
                        >
                            <option value="AIML + IOT 6th Semester (3rd Year) 2026">AIML + IOT 6th Semester (3rd Year) 2026</option>
                            <option value="Core CS 6th Semester 2026">Core CS 6th Semester 2026</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Main Info Banner */}
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-slate-800/80 dark:to-indigo-900/20 rounded-3xl p-6 sm:p-8 border border-blue-100/50 dark:border-indigo-500/20 flex items-center justify-between shadow-inner">
                <div className="flex items-center space-x-6">
                    <div className="w-16 h-16 bg-blue-100 dark:bg-indigo-500/20 rounded-2xl flex items-center justify-center text-blue-500 dark:text-indigo-400 shrink-0">
                        {activeTab === 'Mentors' ? (
                            <UserCheck className="w-8 h-8" />
                        ) : activeTab === 'Pending Approvals' ? (
                            <ShieldAlert className="w-8 h-8 text-amber-500" />
                        ) : activeTab === 'Workspace Submissions' ? (
                            <ClipboardList className="w-8 h-8 text-indigo-500" />
                        ) : (
                            <Users className="w-8 h-8" />
                        )}
                    </div>
                    <div>
                        <div className="flex items-center space-x-3 mb-2">
                            <h2 className="text-2xl font-black text-blue-900 dark:text-white capitalize">{activeTab}</h2>
                            <span className="px-3 py-1 bg-white/50 dark:bg-white/10 rounded-full text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-indigo-300 backdrop-blur-sm border border-blue-200/50 dark:border-indigo-500/30">
                                {selectedFilter}
                            </span>
                        </div>
                        <p className="text-sm font-medium text-blue-700/80 dark:text-indigo-200/80">
                            {activeTab === 'Mentors' 
                                ? `${activeMentors.length} active mentors registered in the system` 
                                : activeTab === 'Pending Approvals'
                                ? `${pendingMentors.length} registrations pending approval`
                                : activeTab === 'Workspace Submissions'
                                ? `${workspaceTeams.length} formed teams tracked in validation`
                                : `${panelsData.length} panels registered in the system`}
                        </p>
                    </div>
                </div>
                <div className="hidden md:flex flex-col items-end">
                    <div className="text-[10px] font-black uppercase tracking-widest text-blue-400 dark:text-indigo-500/50 mb-1">Total Registry</div>
                    <div className="px-4 py-1.5 bg-blue-100 dark:bg-indigo-500/20 text-blue-700 dark:text-indigo-300 font-black rounded-xl">Active Cohorts</div>
                </div>
            </div>

            {/* Search & Actions */}
            <div className="flex flex-col md:flex-row items-center gap-4">
                <div className="relative flex-1 w-full">
                    <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input 
                        type="text" 
                        placeholder={`Search ${activeTab.toLowerCase()} by name...`} 
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-12 pr-6 py-4 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl border border-slate-200/50 dark:border-slate-700/50 rounded-2xl text-sm font-bold text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm transition-all"
                    />
                </div>
                {activeTab === 'Mentors' && (
                    <button onClick={() => setIsAddMentorOpen(true)} className="w-full md:w-auto px-6 py-4 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-2xl flex items-center justify-center gap-2 shadow-lg shadow-indigo-500/20 active:scale-95 transition-all shrink-0">
                        <Plus className="w-4 h-4" /> Add Mentor
                    </button>
                )}
                {activeTab === 'Panels' && (
                    <button onClick={() => setIsAddPanelOpen(true)} className="w-full md:w-auto px-6 py-4 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-2xl flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 active:scale-95 transition-all shrink-0">
                        <Plus className="w-4 h-4" /> Add Panel
                    </button>
                )}
            </div>

            {/* Grid List */}
            <AnimatePresence mode="wait">
                <motion.div 
                    key={activeTab}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.98 }}
                    transition={{ duration: 0.3 }}
                    className={activeTab === 'Workspace Submissions' 
                        ? "flex flex-col space-y-6 w-full col-span-full" 
                        : "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6"
                    }
                >
                    {activeTab === 'Mentors' ? (
                        activeMentors.map(m => (
                            <div key={m.id} className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-xl hover:border-indigo-200 dark:hover:border-indigo-500/50 transition-all group flex flex-col">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <h3 className="text-lg font-black text-slate-800 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">{m.name}</h3>
                                        <p className="text-xs font-medium text-slate-500 flex items-center mt-1">
                                            <Mail className="w-3 h-3 mr-1" /> {m.email || 'No email registered'}
                                        </p>
                                    </div>
                                </div>
                                <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2">
                                    <button 
                                        onClick={() => handleViewAs('Mentor', m)}
                                        className="flex-1 flex items-center justify-center px-4 py-2.5 bg-slate-50 hover:bg-indigo-50 text-indigo-600 dark:bg-slate-900/50 dark:hover:bg-indigo-500/20 dark:text-indigo-400 rounded-xl text-sm font-bold transition-colors border border-slate-200 dark:border-slate-700 hover:border-indigo-200 dark:hover:border-indigo-500/50"
                                    >
                                        <Eye className="w-4 h-4 mr-2" /> View as Mentor
                                    </button>
                                    <button 
                                        onClick={() => handleDeleteMentor(m.id)}
                                        className="p-2.5 text-slate-400 hover:text-rose-650 dark:hover:text-rose-400 rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10 border border-slate-200 dark:border-slate-700 transition-colors"
                                        title="Delete Mentor"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))
                    ) : activeTab === 'Pending Approvals' ? (
                        pendingMentors.length === 0 ? (
                            <div className="col-span-full bg-white dark:bg-slate-800 rounded-3xl p-12 text-center border border-slate-200 dark:border-slate-700">
                                <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-500/10 rounded-2xl flex items-center justify-center text-emerald-500 dark:text-emerald-400 mx-auto mb-4">
                                    <CheckCircle className="w-8 h-8" />
                                </div>
                                <h3 className="text-lg font-black text-slate-800 dark:text-white mb-1">All Registrations Reviewed</h3>
                                <p className="text-sm font-medium text-slate-500 dark:text-slate-400">There are no pending registrations waiting for review.</p>
                            </div>
                        ) : (
                            pendingMentors.map(m => (
                                <div key={m.id} className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-xl hover:border-indigo-200 dark:hover:border-indigo-500/50 transition-all group flex flex-col">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="space-y-1.5 w-full">
                                            <div className="flex items-center justify-between">
                                                <span className="text-[9px] font-black uppercase tracking-wider bg-amber-500/10 text-amber-500 px-2 py-0.5 rounded">
                                                    Pending Approval
                                                </span>
                                                {m.created_at && (
                                                    <span className="text-[10px] font-bold text-slate-400">
                                                        {new Date(m.created_at).toLocaleDateString()}
                                                    </span>
                                                )}
                                            </div>
                                            <h3 className="text-lg font-black text-slate-800 dark:text-white transition-colors">{m.name}</h3>
                                            <p className="text-xs font-medium text-slate-500 flex items-center">
                                                <Mail className="w-3.5 h-3.5 mr-1 text-slate-400" /> {m.email || 'No email registered'}
                                            </p>
                                        </div>
                                    </div>
                                    {m.domains && m.domains.length > 0 && (
                                        <div className="mb-4">
                                            <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2">Expertise Domains</div>
                                            <div className="flex flex-wrap gap-1.5">
                                                {m.domains.map(d => (
                                                    <span key={d} className="text-[10px] font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2 py-0.5 rounded">
                                                        {d}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    {/* Portal access badges if already set */}
                                    {m.portal_access && (
                                        <div className="mb-3 flex items-center gap-2">
                                            <Key className="w-3 h-3 text-slate-400" />
                                            <span className="text-[10px] font-black text-slate-500 uppercase tracking-widest">Access:</span>
                                            <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 px-2 py-0.5 rounded capitalize">{m.portal_access}</span>
                                        </div>
                                    )}
                                    <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700/50 grid grid-cols-2 gap-3">
                                        <button
                                            onClick={() => handleRejectMentor(m.id)}
                                            className="flex items-center justify-center px-4 py-2.5 bg-white hover:bg-red-50 text-red-650 dark:bg-slate-900/50 dark:hover:bg-red-500/10 dark:text-red-400 rounded-xl text-xs font-black uppercase tracking-widest transition-all border border-red-200 dark:border-red-500/30 hover:border-red-300"
                                        >
                                            Reject
                                        </button>
                                        <button
                                            onClick={() => openApprovalModal(m)}
                                            className="flex items-center justify-center gap-1.5 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-md shadow-emerald-500/15 hover:shadow-emerald-500/30 border border-emerald-600 hover:border-emerald-700"
                                        >
                                            <Shield className="w-3 h-3" /> Approve
                                        </button>
                                    </div>
                                </div>
                            ))
                        )
                    ) : activeTab === 'Workspace Submissions' ? (
                        <div className="w-full flex flex-col space-y-6">
                            {/* Summary Metrics Cards */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full">
                                <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm flex items-center justify-between group hover:shadow-md transition-shadow">
                                    <div className="space-y-1">
                                        <p className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Total Teams</p>
                                        <h4 className="text-3xl font-black text-slate-800 dark:text-white">{workspaceStats.total}</h4>
                                        <p className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">Registered in cohort</p>
                                    </div>
                                    <div className="p-4 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 rounded-2xl border border-indigo-100/50 dark:border-indigo-900/30">
                                        <ClipboardList className="w-6 h-6" />
                                    </div>
                                </div>

                                <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm flex items-center justify-between group hover:shadow-md transition-shadow">
                                    <div className="space-y-1">
                                        <p className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Submitted Workspaces</p>
                                        <h4 className="text-3xl font-black text-emerald-600 dark:text-emerald-500">{workspaceStats.submitted}</h4>
                                        <p className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">Configurations locked</p>
                                    </div>
                                    <div className="p-4 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 rounded-2xl border border-emerald-100/50 dark:border-emerald-900/30">
                                        <Github className="w-6 h-6" />
                                    </div>
                                </div>

                                <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm flex items-center justify-between group hover:shadow-md transition-shadow">
                                    <div className="space-y-1">
                                        <p className="text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">Pending Submissions</p>
                                        <h4 className="text-3xl font-black text-amber-500 dark:text-amber-500">{workspaceStats.pending}</h4>
                                        <p className="text-[11px] text-slate-400 dark:text-slate-500 font-bold">Awaiting team leader</p>
                                    </div>
                                    <div className="p-4 bg-amber-50 dark:bg-amber-950/40 text-amber-500 dark:text-amber-400 rounded-2xl border border-amber-100/50 dark:border-amber-900/30">
                                        <Clock className="w-6 h-6 animate-pulse" />
                                    </div>
                                </div>
                            </div>

                            {/* Progress Bar Container */}
                            <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-6 rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm flex flex-col space-y-3 w-full">
                                <div className="flex justify-between items-center text-xs font-black">
                                    <span className="text-slate-500 dark:text-slate-400 uppercase tracking-widest">Overall Workspace Roster Submission Progress</span>
                                    <span className="text-indigo-600 dark:text-indigo-400">{workspaceStats.percent}% Completed</span>
                                </div>
                                <div className="w-full h-3 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden border border-slate-200/50 dark:border-slate-800 shadow-inner">
                                    <motion.div 
                                        className="h-full bg-gradient-to-r from-emerald-500 via-indigo-500 to-violet-600"
                                        initial={{ width: 0 }}
                                        animate={{ width: `${workspaceStats.percent}%` }}
                                        transition={{ duration: 1, ease: "easeOut" }}
                                    />
                                </div>
                            </div>

                            {/* Roster Filters Bar */}
                            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-200/30 dark:border-slate-750/30 pb-4 w-full">
                                <div className="flex items-center space-x-2 bg-slate-100/50 dark:bg-slate-900/50 p-1 rounded-xl border border-slate-200/50 dark:border-slate-800">
                                    {['All', 'Submitted', 'Pending'].map((filterVal) => {
                                        const isActive = workspaceFilter === filterVal;
                                        const count = filterVal === 'All' 
                                            ? workspaceStats.total 
                                            : filterVal === 'Submitted' 
                                            ? workspaceStats.submitted 
                                            : workspaceStats.pending;
                                        return (
                                            <button
                                                key={filterVal}
                                                onClick={() => setWorkspaceFilter(filterVal)}
                                                className={`px-4 py-2 rounded-lg text-xs font-black uppercase tracking-wider transition-all flex items-center space-x-2 ${
                                                    isActive 
                                                        ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm border border-slate-200/30 dark:border-slate-700/30' 
                                                        : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-350'
                                                }`}
                                            >
                                                <span>{filterVal}</span>
                                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                                    isActive
                                                        ? 'bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400'
                                                        : 'bg-slate-205 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                                                }`}>
                                                    {count}
                                                </span>
                                            </button>
                                        );
                                    })}
                                </div>
                                
                                <div className="flex flex-col sm:flex-row items-center gap-4">
                                    {workspaceStats.pending > 0 && (
                                        <button
                                            onClick={handleRemindPending}
                                            disabled={remindingPending}
                                            className="flex items-center gap-1.5 px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all active:scale-[0.98] shadow-md shadow-amber-500/10 hover:shadow-amber-500/20 border border-amber-600 shrink-0"
                                        >
                                            {remindingPending ? (
                                                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Reminding...</>
                                            ) : (
                                                <><Mail className="w-3.5 h-3.5" /> Remind Pending ({workspaceStats.pending})</>
                                            )}
                                        </button>
                                    )}
                                    <div className="text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                                        Showing {filteredWorkspaces.length} of {workspaceStats.total} teams
                                    </div>
                                </div>
                            </div>

                            {/* Detailed Roster List */}
                            {loadingWorkspaces ? (
                                <div className="py-12 flex flex-col items-center justify-center space-y-3 w-full">
                                    <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
                                    <p className="text-xs text-slate-500 dark:text-slate-400 font-black uppercase tracking-widest">Querying workspace submissions...</p>
                                </div>
                            ) : filteredWorkspaces.length === 0 ? (
                                <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl p-12 text-center border border-slate-200 dark:border-slate-700 w-full shadow-sm">
                                    <div className="w-16 h-16 bg-slate-105 dark:bg-slate-900 rounded-2xl flex items-center justify-center text-slate-400 mx-auto mb-4 border border-slate-200/30 dark:border-slate-800">
                                        <ClipboardList className="w-8 h-8" />
                                    </div>
                                    <h3 className="text-lg font-black text-slate-800 dark:text-white mb-1">No Teams Found</h3>
                                    <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                                        {searchTerm ? "No teams matched your search text." : `There are no workspace submissions currently in the "${workspaceFilter}" queue.`}
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-4 w-full">
                                    {filteredWorkspaces.map(t => {
                                        let membersList = [];
                                        if (t.members) {
                                            try {
                                                membersList = Array.isArray(t.members) ? t.members : JSON.parse(t.members);
                                            } catch { /* non-fatal: fall through to the default below */ }
                                        }
                                        return (
                                            <div 
                                                key={t.id} 
                                                className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-2xl p-6 border border-slate-200/50 dark:border-slate-700/50 shadow-sm hover:shadow-md hover:border-indigo-200 dark:hover:border-indigo-500/30 transition-all flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 w-full"
                                            >
                                                {/* Left Column: Team Identity & Members */}
                                                <div className="w-full lg:w-1/4 space-y-2">
                                                    <div className="flex items-center gap-2">
                                                        <span className="px-2.5 py-1 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg text-xs font-black text-indigo-600 dark:text-indigo-400 border border-indigo-100/30 dark:border-indigo-500/20">
                                                            {teamDisplayLabel(t.id, t, semesterMap)}
                                                        </span>
                                                        <span className="text-[10px] text-slate-400 dark:text-slate-500 font-mono">
                                                            #{t.teamNo || 'N/A'}
                                                        </span>
                                                    </div>
                                                    <div>
                                                        <div className="text-[10px] font-black text-slate-450 dark:text-slate-500 uppercase tracking-widest mb-1">Leader & Roster</div>
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-6 h-6 rounded-full bg-amber-100 dark:bg-amber-955/40 flex items-center justify-center text-amber-600 dark:text-amber-400 shrink-0">
                                                                <User className="w-3.5 h-3.5" />
                                                            </div>
                                                            <span className="text-sm font-black text-slate-800 dark:text-slate-250 truncate">{t.leader || 'N/A'}</span>
                                                        </div>
                                                    </div>
                                                    {membersList.length > 0 && (
                                                        <div className="flex flex-wrap gap-1">
                                                            {membersList.map((m, idx) => (
                                                                <span 
                                                                    key={idx} 
                                                                    className="text-[9px] font-black text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800/80 px-2 py-0.5 rounded"
                                                                    title={m.roll || m.rollNumber || ''}
                                                                >
                                                                    {m.name}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>

                                                {/* Middle Column: Project Settings & Workspace Submission */}
                                                <div className="w-full lg:w-5/12 space-y-3 min-w-0">
                                                    <div>
                                                        <h4 className="text-sm font-black text-slate-800 dark:text-white leading-tight truncate">
                                                            {(!t.title || t.title === t.name || /^team\s*-?\s*\d+$/i.test(String(t.title).trim()) || String(t.title).toLowerCase().startsWith('admin-team')) ? (
                                                                <span className="text-slate-400 font-normal italic">No Problem Statement Reserved</span>
                                                            ) : (
                                                                t.title
                                                            )}
                                                        </h4>
                                                        {t.domain && (
                                                            <p className="text-[11px] text-slate-500 dark:text-slate-405 font-bold mt-1">
                                                                Domain: <span className="text-indigo-650 dark:text-indigo-400">{Array.isArray(t.domain) ? t.domain.join(', ') : String(t.domain)}</span>
                                                            </p>
                                                        )}
                                                    </div>

                                                    {/* Submission details */}
                                                    <div className="space-y-1.5 min-w-0">
                                                        {t.isSubmitted ? (
                                                            <div className="space-y-1.5 min-w-0">
                                                                {/* Github url */}
                                                                <div className="flex items-center gap-2 text-xs min-w-0">
                                                                    <Github className="w-4 h-4 text-slate-400 shrink-0" />
                                                                    <a 
                                                                        href={t.repository_url}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 dark:hover:text-indigo-300 font-bold truncate flex items-center gap-1 shrink"
                                                                    >
                                                                        <span className="truncate max-w-[320px]">{t.repository_url}</span>
                                                                        <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                                                                    </a>
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <div className="text-xs text-amber-600 dark:text-amber-500 font-black italic flex items-center gap-1.5 uppercase tracking-wider">
                                                                <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" /> Awaiting submission
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Right Column: Status Lock Badge & Action to Editor */}
                                                <div className="w-full lg:w-1/4 flex flex-row lg:flex-col items-center lg:items-end justify-between lg:justify-center gap-4 shrink-0">
                                                    {/* Status Badge */}
                                                    <div>
                                                        {t.isSubmitted ? (
                                                            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-200/30 dark:border-emerald-500/20 rounded-xl text-[10px] font-black uppercase tracking-widest">
                                                                <Lock className="w-3.5 h-3.5 text-emerald-500" />
                                                                <span>Submitted (Locked)</span>
                                                            </div>
                                                        ) : (
                                                            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50/70 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200/30 dark:border-amber-500/20 rounded-xl text-[10px] font-black uppercase tracking-widest">
                                                                <Clock className="w-3.5 h-3.5 animate-pulse text-amber-500" />
                                                                <span>Pending Submission</span>
                                                            </div>
                                                        )}
                                                    </div>

                                                    {/* Editor action button */}
                                                    <button
                                                        onClick={() => navigate(`/admin/teams?teamId=${t.id}`)}
                                                        className="flex items-center gap-1.5 px-4.5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest transition-all active:scale-[0.98] shadow-md shadow-indigo-500/10 hover:shadow-indigo-500/25 border border-indigo-600"
                                                    >
                                                        <span>Go to Editor</span>
                                                        <ArrowRight className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    ) : (
                        panels.map(p => {
                            let membersList = [];
                            try {
                                membersList = Array.isArray(p.members) ? p.members : JSON.parse(p.members || '[]');
                            } catch {
                                membersList = [];
                            }
                            return (
                                <div key={p.id} className="bg-white dark:bg-slate-800 rounded-3xl p-6 border border-slate-200 dark:border-slate-700 shadow-sm hover:shadow-xl hover:border-emerald-200 dark:hover:border-emerald-500/50 transition-all group flex flex-col">
                                    <div className="flex justify-between items-start mb-4">
                                        <div>
                                            <h3 className="text-lg font-black text-slate-800 dark:text-white group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">{p.name}</h3>
                                            <p className="text-xs font-medium text-slate-500 mt-1">{p.description || 'Evaluation Panel'}</p>
                                        </div>
                                    </div>
                                    <div className="mb-6 flex flex-wrap gap-2">
                                        {membersList.map(member => (
                                            <span key={member} className="text-[10px] font-bold text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-900 px-2 py-1 rounded">
                                                {member}
                                            </span>
                                        ))}
                                    </div>
                                    <div className="mt-auto pt-4 border-t border-slate-100 dark:border-slate-700/50 flex gap-2">
                                        <button 
                                            onClick={() => handleViewAs('Panel', p)}
                                            className="flex-1 flex items-center justify-center px-4 py-2.5 bg-slate-50 hover:bg-emerald-50 text-emerald-600 dark:bg-slate-900/50 dark:hover:bg-emerald-500/20 dark:text-emerald-400 rounded-xl text-sm font-bold transition-colors border border-slate-200 dark:border-slate-700 hover:border-emerald-200 dark:hover:border-emerald-500/50"
                                        >
                                            <Eye className="w-4 h-4 mr-2" /> View as Panel
                                        </button>
                                        <button 
                                            onClick={() => handleDeletePanel(p.id)}
                                            className="p-2.5 text-slate-400 hover:text-rose-650 dark:hover:text-rose-400 rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10 border border-slate-200 dark:border-slate-700 transition-colors"
                                            title="Delete Panel"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </motion.div>
            </AnimatePresence>

            {/* Simulation Overlay Modal */}
            <AnimatePresence>
                {simulating && (
                    <motion.div 
                        initial={{ opacity: 0 }} 
                        animate={{ opacity: 1 }} 
                        exit={{ opacity: 0 }} 
                        className="fixed inset-0 bg-slate-900/70 backdrop-blur-md z-50 flex items-center justify-center p-4"
                    >
                        <motion.div 
                            initial={{ scale: 0.95, y: 20 }} 
                            animate={{ scale: 1, y: 0 }} 
                            exit={{ scale: 0.95, y: 20 }} 
                            className="bg-slate-50 dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden"
                        >
                            {/* Modal Header */}
                            <div className="bg-slate-900 p-6 flex items-center justify-between text-white border-b border-slate-800">
                                <div className="flex items-center space-x-3">
                                    <div className="p-2 bg-amber-500/10 rounded-lg text-amber-500 animate-pulse"><Sparkles className="w-5 h-5" /></div>
                                    <div>
                                        <div className="flex items-center space-x-2">
                                            <span className="text-xs font-black uppercase tracking-wider bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded">
                                                Simulated View
                                            </span>
                                            <span className="text-xs font-semibold text-slate-400">• Proxy simulation mode</span>
                                        </div>
                                        <h3 className="text-lg font-black tracking-tight">{simulating.type}: {simulating.entity.name}</h3>
                                    </div>
                                </div>
                                <button 
                                    onClick={handleCloseSimulation} 
                                    className="p-2 bg-slate-800 hover:bg-slate-700 rounded-full transition-colors text-slate-300"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>

                            {/* Modal Content */}
                            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                                {simLoading ? (
                                    <div className="h-full flex flex-col items-center justify-center space-y-3">
                                        <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
                                        <p className="text-sm text-slate-500 dark:text-slate-400 font-bold">Querying proxy database states...</p>
                                    </div>
                                ) : simulating.type === 'Mentor' ? (
                                    // MENTOR SIMULATION VIEW
                                    <div className="space-y-6">
                                        
                                        {/* Metric Cards */}
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                            <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between shadow-sm">
                                                <div>
                                                    <p className="text-[10px] uppercase font-black text-slate-400 tracking-wider">Assigned Teams</p>
                                                    <h4 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{simulatedMentorData.assignedTeams.length}</h4>
                                                </div>
                                                <div className="p-3 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500 rounded-xl"><Users className="w-6 h-6"/></div>
                                            </div>
                                            <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between shadow-sm">
                                                <div>
                                                    <p className="text-[10px] uppercase font-black text-slate-400 tracking-wider">Total Students Under Mentor</p>
                                                    <h4 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{simulatedMentorData.studentCount}</h4>
                                                </div>
                                                <div className="p-3 bg-violet-50 dark:bg-violet-500/10 text-violet-500 rounded-xl"><GraduationCap className="w-6 h-6"/></div>
                                            </div>
                                            <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between shadow-sm">
                                                <div>
                                                    <p className="text-[10px] uppercase font-black text-slate-400 tracking-wider">Active Proposals</p>
                                                    <h4 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{simulatedMentorData.relatedProposals.length}</h4>
                                                </div>
                                                <div className="p-3 bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500 rounded-xl"><FileText className="w-6 h-6"/></div>
                                            </div>
                                        </div>

                                        {/* Assigned Teams Table */}
                                        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-4">
                                            <h4 className="text-sm font-black text-slate-800 dark:text-white flex items-center gap-2">
                                                <UserCheck className="w-4 h-4 text-indigo-500" />
                                                Allocated Roster & Project Overview
                                            </h4>
                                            
                                            {simulatedMentorData.assignedTeams.length === 0 ? (
                                                <p className="text-xs text-slate-400 font-bold py-6 text-center">No teams currently allocated to this mentor.</p>
                                            ) : (
                                                <div className="overflow-x-auto">
                                                    <table className="w-full text-left border-collapse text-xs">
                                                        <thead>
                                                            <tr className="border-b border-slate-100 dark:border-slate-800 text-[10px] uppercase tracking-wider font-black text-slate-400">
                                                                <th className="pb-2">Team ID</th>
                                                                <th className="pb-2">Project Title</th>
                                                                <th className="pb-2">Domain</th>
                                                                <th className="pb-2">Members Roster</th>
                                                                <th className="pb-2 text-right">Status</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-semibold text-slate-600 dark:text-slate-300">
                                                            {simulatedMentorData.assignedTeams.map(team => {
                                                                let membersList = [];
                                                                try {
                                                                    membersList = Array.isArray(team.members) ? team.members : JSON.parse(team.members || '[]');
                                                                } catch { /* non-fatal: fall through to the default below */ }
                                                                return (
                                                                    <tr key={team.id}>
                                                                        <td className="py-3 font-black text-slate-800 dark:text-white whitespace-nowrap">{teamDisplayLabel(team.id, team, semesterMap)}</td>
                                                                        <td className="py-3 font-black">{team.title || 'Untitled Project'}</td>
                                                                        <td className="py-3">{team.domain || 'N/A'}</td>
                                                                        <td className="py-3">
                                                                            <div className="flex gap-1.5 flex-wrap">
                                                                                {membersList.map(m => (
                                                                                    <span key={m.id || m.rollNumber} className="bg-slate-100 dark:bg-slate-900 px-2 py-0.5 rounded text-[10px]" title={m.rollNumber}>
                                                                                        {m.name}
                                                                                    </span>
                                                                                ))}
                                                                            </div>
                                                                        </td>
                                                                        <td className="py-3 text-right">
                                                                            <span className={`px-2 py-0.5 rounded-full text-[9px] font-black uppercase ${
                                                                                team.validationStatus === 'Valid' ? 'bg-emerald-500 text-white' : 'bg-amber-500 text-white'
                                                                            }`}>
                                                                                {team.validationStatus || 'Pending'}
                                                                            </span>
                                                                        </td>
                                                                    </tr>
                                                                );
                                                            })}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </div>

                                        {/* Proposals */}
                                        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-4">
                                            <h4 className="text-sm font-black text-slate-800 dark:text-white flex items-center gap-2">
                                                <BookOpen className="w-4 h-4 text-violet-500" />
                                                Team Proposal Drafts
                                            </h4>

                                            {simulatedMentorData.relatedProposals.length === 0 ? (
                                                <p className="text-xs text-slate-400 font-bold py-6 text-center">No proposals submitted by assigned teams.</p>
                                            ) : (
                                                <div className="space-y-4">
                                                    {simulatedMentorData.relatedProposals.map(prop => (
                                                        <div key={prop.id} className="p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-800 rounded-xl flex justify-between items-start gap-4">
                                                            <div className="space-y-1.5">
                                                                <h5 className="font-black text-slate-800 dark:text-white">{prop.title}</h5>
                                                                <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">{prop.description}</p>
                                                                <span className="inline-block px-2 py-0.5 bg-slate-100 dark:bg-slate-900 rounded text-[9px] font-bold text-slate-400">
                                                                    Submitted by Team: {teamDisplayLabel(prop.team_id, simData.teams.find(t => t.id === prop.team_id), semesterMap)}
                                                                </span>
                                                            </div>
                                                            <span className={`shrink-0 px-2 py-0.5 rounded-full text-[9px] font-black uppercase ${
                                                                prop.status === 'Approved' ? 'bg-emerald-500 text-white' : 'bg-amber-500 text-white'
                                                            }`}>
                                                                {prop.status || 'Pending'}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>

                                    </div>
                                ) : (
                                    // PANEL SIMULATION VIEW
                                    <div className="space-y-6">
                                        
                                        {/* Panel Info & Members */}
                                        <div className="bg-white dark:bg-slate-800 p-6 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 space-y-4 shadow-sm">
                                            <h4 className="text-sm font-black text-slate-800 dark:text-white flex items-center gap-2">
                                                <Award className="w-4 h-4 text-emerald-500" />
                                                Panel Configuration & Jurors
                                            </h4>
                                            <div className="flex flex-wrap gap-2 pt-1">
                                                {simulatedPanelData.membersList.map(member => (
                                                    <div key={member} className="flex items-center gap-2 bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 px-3.5 py-2 rounded-xl text-xs font-bold">
                                                        <User className="w-3.5 h-3.5 text-indigo-500" />
                                                        <span>{member}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Metric Cards */}
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                            <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between shadow-sm">
                                                <div>
                                                    <p className="text-[10px] uppercase font-black text-slate-400 tracking-wider">Assigned Presentation Slots</p>
                                                    <h4 className="text-2xl font-black text-slate-800 dark:text-white mt-1">{simulatedPanelData.assignedSlots.length}</h4>
                                                </div>
                                                <div className="p-3 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500 rounded-xl"><Calendar className="w-6 h-6"/></div>
                                            </div>
                                            <div className="bg-white dark:bg-slate-800 p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between shadow-sm">
                                                <div>
                                                    <p className="text-[10px] uppercase font-black text-slate-400 tracking-wider">Evaluation Venues</p>
                                                    <h4 className="text-2xl font-black text-slate-800 dark:text-white mt-1">
                                                        {[...new Set(simulatedPanelData.assignedSlots.map(s => s.room).filter(Boolean))].length || 1} Rooms
                                                    </h4>
                                                </div>
                                                <div className="p-3 bg-violet-50 dark:bg-violet-500/10 text-violet-500 rounded-xl"><MapPin className="w-6 h-6"/></div>
                                            </div>
                                        </div>

                                        {/* Scheduled Slots */}
                                        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 p-6 space-y-4">
                                            <h4 className="text-sm font-black text-slate-800 dark:text-white flex items-center gap-2">
                                                <Clock className="w-4 h-4 text-indigo-500" />
                                                Assigned Jury Presentations & Slots
                                            </h4>

                                            {simulatedPanelData.assignedSlots.length === 0 ? (
                                                <p className="text-xs text-slate-400 font-bold py-6 text-center">No presentation slots scheduled for this panel.</p>
                                            ) : (
                                                <div className="overflow-x-auto">
                                                    <table className="w-full text-left border-collapse text-xs">
                                                        <thead>
                                                            <tr className="border-b border-slate-100 dark:border-slate-800 text-[10px] uppercase tracking-wider font-black text-slate-400">
                                                                <th className="pb-2">Date</th>
                                                                <th className="pb-2">Time Slot</th>
                                                                <th className="pb-2">Room / Mode</th>
                                                                <th className="pb-2">Evaluating Team</th>
                                                                <th className="pb-2 text-right">Action Simulated</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-semibold text-slate-600 dark:text-slate-300">
                                                            {simulatedPanelData.assignedSlots.map(slot => (
                                                                <tr key={slot.id || slot.date + slot.time}>
                                                                    <td className="py-3 font-bold flex items-center gap-1.5">
                                                                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                                                                        {slot.date}
                                                                    </td>
                                                                    <td className="py-3 font-bold">
                                                                        <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-900 rounded font-mono">
                                                                            {slot.time}
                                                                        </span>
                                                                    </td>
                                                                    <td className="py-3">
                                                                        <div className="flex items-center gap-1">
                                                                            <MapPin className="w-3.5 h-3.5 text-indigo-500" />
                                                                            <span>{slot.room || 'Virtual'}</span>
                                                                            <span className="text-[9px] bg-slate-100 dark:bg-slate-900 px-1 rounded uppercase font-bold ml-1">
                                                                                {slot.mode || 'Offline'}
                                                                            </span>
                                                                        </div>
                                                                    </td>
                                                                    <td className="py-3 font-black text-slate-800 dark:text-white">
                                                                        {teamDisplayLabel(slot.team, simData.teams.find(t => t.id === slot.team), semesterMap)}
                                                                    </td>
                                                                    <td className="py-3 text-right">
                                                                        <button 
                                                                            disabled
                                                                            className="px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 rounded-lg text-[10px] font-black uppercase tracking-wider cursor-not-allowed"
                                                                        >
                                                                            Evaluate Team
                                                                        </button>
                                                                    </td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            )}
                                        </div>

                                    </div>
                                )}
                            </div>

                            {/* Modal Footer */}
                            <div className="bg-slate-100 dark:bg-slate-800/80 px-6 py-4 flex justify-between items-center border-t border-slate-200 dark:border-slate-800">
                                <div className="text-[10px] font-bold text-slate-400 flex items-center gap-1">
                                    <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
                                    Read-only dashboard proxy view.
                                </div>
                                <button 
                                    onClick={handleCloseSimulation}
                                    className="px-5 py-2 bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 font-bold rounded-xl text-xs uppercase tracking-widest transition-all"
                                >
                                    Dismiss View
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Portal Access Approval Modal ─────────────────────────── */}
            <AnimatePresence>
                {approvalModal && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                        onClick={() => !approvalLoading && setApprovalModal(null)}
                    >
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden"
                            onClick={e => e.stopPropagation()}
                        >
                            {/* Header */}
                            <div className="bg-gradient-to-r from-emerald-600 to-teal-700 p-6 flex justify-between items-center text-white">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-white/20 rounded-xl">
                                        <Shield className="w-5 h-5" />
                                    </div>
                                    <div>
                                        <h3 className="font-black text-lg">Grant Portal Access</h3>
                                        <p className="text-emerald-100 text-xs font-medium mt-0.5">{approvalModal.mentor.name}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => !approvalLoading && setApprovalModal(null)}
                                    className="p-1.5 bg-black/10 hover:bg-black/20 rounded-full transition-colors"
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            {/* Body */}
                            <div className="p-6 space-y-5">
                                <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
                                    Select which portal(s) <span className="font-black text-slate-800 dark:text-white">{approvalModal.mentor.name}</span> should be able to log into:
                                </p>

                                {/* Email info */}
                                <div className="flex items-center gap-2 p-3 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
                                    <Mail className="w-4 h-4 text-slate-400 shrink-0" />
                                    <span className="text-sm font-bold text-slate-700 dark:text-slate-300">
                                        {approvalModal.mentor.email || 'No email on file'}
                                    </span>
                                </div>

                                {/* Portal checkboxes */}
                                <div className="space-y-3">
                                    {/* Mentor Portal */}
                                    <label className={`flex items-center gap-4 p-4 rounded-2xl border-2 cursor-pointer transition-all ${approvalPortals.mentor ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-indigo-300'}`}>
                                        <input
                                            type="checkbox"
                                            checked={approvalPortals.mentor}
                                            onChange={e => setApprovalPortals(p => ({ ...p, mentor: e.target.checked }))}
                                            className="w-4 h-4 text-indigo-600 rounded"
                                        />
                                        <div className="flex-1">
                                            <div className="font-black text-sm text-slate-800 dark:text-white">Mentor Portal</div>
                                            <div className="text-xs text-slate-500 mt-0.5">Manage teams, view proposals, track milestones</div>
                                        </div>
                                        <div className="p-2 bg-indigo-100 dark:bg-indigo-500/20 rounded-lg text-indigo-600 dark:text-indigo-400">
                                            <User className="w-4 h-4" />
                                        </div>
                                    </label>

                                    {/* Panel Portal */}
                                    <label className={`flex items-center gap-4 p-4 rounded-2xl border-2 cursor-pointer transition-all ${approvalPortals.panel ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-emerald-300'}`}>
                                        <input
                                            type="checkbox"
                                            checked={approvalPortals.panel}
                                            onChange={e => setApprovalPortals(p => ({ ...p, panel: e.target.checked }))}
                                            className="w-4 h-4 text-emerald-600 rounded"
                                        />
                                        <div className="flex-1">
                                            <div className="font-black text-sm text-slate-800 dark:text-white">Panel Portal</div>
                                            <div className="text-xs text-slate-500 mt-0.5">Conduct evaluations, submit scores, view slots</div>
                                        </div>
                                        <div className="p-2 bg-emerald-100 dark:bg-emerald-500/20 rounded-lg text-emerald-600 dark:text-emerald-400">
                                            <Award className="w-4 h-4" />
                                        </div>
                                    </label>

                                    {/* Information alert confirming signup password usage */}
                                    {approvalPortals.panel && (
                                        <div className="mt-1 px-1">
                                            <p className="text-[11px] font-bold text-slate-500 dark:text-slate-400">
                                                * Access will be configured using the password they chose during registration.
                                            </p>
                                        </div>
                                    )}
                                </div>

                                {!approvalPortals.mentor && !approvalPortals.panel && (
                                    <p className="text-xs font-bold text-red-500 flex items-center gap-1">
                                        <AlertCircle className="w-3.5 h-3.5" /> Select at least one portal.
                                    </p>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="p-5 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex gap-3">
                                <button
                                    onClick={() => setApprovalModal(null)}
                                    disabled={approvalLoading}
                                    className="flex-1 px-4 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleConfirmApproval}
                                    disabled={approvalLoading || (!approvalPortals.mentor && !approvalPortals.panel)}
                                    className="flex-1 px-4 py-2.5 text-sm font-black text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl transition-all shadow-lg shadow-emerald-500/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                >
                                    {approvalLoading ? (
                                        <><Loader2 className="w-4 h-4 animate-spin" /> Granting...</>
                                    ) : (
                                        <><CheckCircle className="w-4 h-4" /> Grant Access</>
                                    )}
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
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-start">
                                <div className="text-white">
                                    <h3 className="font-black text-xl">Add New Mentor</h3>
                                    <p className="text-xs text-indigo-100/90 mt-1 font-medium">Create a single mentor record manually</p>
                                </div>
                                <button onClick={() => setIsAddMentorOpen(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-4 h-4"/></button>
                            </div>
                            <form onSubmit={handleAddMentor} className="p-6 space-y-4">
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Mentor Name</label>
                                    <input type="text" required value={newMentorForm.name} onChange={(e) => setNewMentorForm(prev => ({...prev, name: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Dr. A.K. Singh" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Email Address</label>
                                    <input type="email" required value={newMentorForm.email} onChange={(e) => setNewMentorForm(prev => ({...prev, email: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. aksingh@gla.ac.in" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Expertise Domains (Comma Separated)</label>
                                    <input type="text" value={newMentorForm.domains} onChange={(e) => setNewMentorForm(prev => ({...prev, domains: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Web, Cloud, AI" />
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 pt-4">
                                    <button type="button" onClick={() => setIsAddMentorOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" className="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 border border-indigo-500/50 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/30 active:scale-95">Add Mentor</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Add Panel Modal */}
            <AnimatePresence>
                {isAddPanelOpen && (
                    <motion.div key="add-panel-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 shadow-2xl overflow-y-auto">
                        <motion.div key="add-panel-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden my-8">
                            <div className="bg-gradient-to-r from-emerald-600 to-emerald-800 p-6 flex justify-between items-start">
                                <div className="text-white">
                                    <h3 className="font-black text-xl">Add New Panel</h3>
                                    <p className="text-xs text-emerald-100/90 mt-1 font-medium">Create a single evaluation panel manually</p>
                                </div>
                                <button onClick={() => setIsAddPanelOpen(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-4 h-4"/></button>
                            </div>
                            <form onSubmit={handleAddPanel} className="p-6 space-y-4">
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Panel Name</label>
                                    <input type="text" required value={newPanelForm.name} onChange={(e) => setNewPanelForm(prev => ({...prev, name: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. PANEL-A" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Description</label>
                                    <input type="text" value={newPanelForm.description} onChange={(e) => setNewPanelForm(prev => ({...prev, description: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Evaluation Panel for CSE AIML" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Professors Names (Comma Separated)</label>
                                    <input type="text" required value={newPanelForm.members} onChange={(e) => setNewPanelForm(prev => ({...prev, members: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Dr. A.K. Singh, Prof. Verma" />
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 pt-4">
                                    <button type="button" onClick={() => setIsAddPanelOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" className="px-5 py-2.5 text-sm font-bold text-white bg-emerald-600 border border-emerald-500/50 hover:bg-emerald-700 rounded-xl transition-all shadow-lg shadow-emerald-500/30 active:scale-95">Add Panel</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
