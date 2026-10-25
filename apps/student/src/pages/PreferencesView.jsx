import React, { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    ClipboardList, Clock, Plus, Minus, ArrowUp, ArrowDown, CheckCircle, Info, Hash, Lock,
    FileText, UploadCloud, X, ExternalLink, AlertCircle, Calendar, MessageSquare, Sparkles,
    Github, Code, Tag, Save, Users, Search, Filter, Eye, BrainCircuit, Activity, Target, Star
} from 'lucide-react';
import {
    useProblemStatements, usePreferences, useProposals, useTeam, useProfile, useDeadlines, fetchWithAuth
} from '../hooks/useStudentData';
import { supabase } from '../lib/supabase';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';
import PsArchitecturePlanModal from '../components/PsArchitecturePlanModal';

const formatDateUTC = (dateStr) => {
    if (!dateStr) return '';
    if (dateStr.includes('T')) {
        const [dPart, tPart] = dateStr.split('T');
        const [yyyy, mm, dd] = dPart.split('-');
        const timeClean = tPart.substring(0, 5);
        return `${dd}-${mm}-${yyyy} at ${timeClean}`;
    }
    const date = new Date(dateStr);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    return `${day}-${month}-${year}`;
};


function formatDescriptionSummary(text) {
    if (!text) return '';
    let str = text;
    if (typeof text === 'object') {
        str = text.overview || text.summary || text.main_description || text.description || text.introduction || '';
    }
    if (typeof str !== 'string') return String(str);

    let trimmed = str.trim();
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
            const parsed = JSON.parse(trimmed);
            if (parsed && typeof parsed === 'object') {
                return formatDescriptionSummary(parsed.overview || parsed.summary || parsed.main_description || parsed.description || parsed.introduction);
            }
        } catch { /* non-fatal: fall through to the default below */ }
    }

    // Match Project Overview section if markdown structured
    const overviewMatch = trimmed.match(/###?\s*(?:Project\s*)?(?:Overview|Summary|Vision)\s*([\s\S]*?)(?=###?|$)/i);
    if (overviewMatch && overviewMatch[1]?.trim()) {
        trimmed = overviewMatch[1].trim();
    }

    return trimmed.replace(/\*\*/g, '').replace(/\*/g, '').trim();
}

const parseProblemStatementDescription = (desc) => {
    if (!desc) return { mainDescription: '', techStack: [], deliverables: [], features: [], rawObjective: '', rawDatasets: '', rawOutcomes: '', sections: [] };

    // Standardize newlines
    const text = desc.replace(/\r\n/g, '\n');

    // Split by markdown headers like "### Header"
    const sections = [];
    const mainDescMatch = text.match(/^([\s\S]*?)(?=\n+###?\s+|$)/);
    let mainDescription = mainDescMatch ? mainDescMatch[1].trim() : '';
    mainDescription = mainDescription.replace(/^(?:Short\s*Description|Description|Overview|Project\s*Overview|Abstract|Problem\s*Statement)\s*:\s*/i, '').trim();

    // Extract bullet points helper
    const getBullets = (sectionText) => {
        if (!sectionText) return [];
        return sectionText
            .split('\n')
            .map(line => line.trim().replace(/^[-*•]\s*/, ''))
            .filter(line => line.length > 0);
    };

    // Match all headers and content
    const regex = /\n+###?\s+([^\n]+)\n+([\s\S]*?)(?=\n+###?|$)/g;
    let match;
    const seenHeaders = new Set();
    while ((match = regex.exec(text)) !== null) {
        const title = match[1].trim();
        const content = match[2].trim();
        if (content && !seenHeaders.has(title.toLowerCase())) {
            seenHeaders.add(title.toLowerCase());
            sections.push({
                title,
                content,
                bullets: getBullets(content)
            });
        }
    }

    // For backward compatibility:
    const findSectionContent = (names) => {
        const sec = sections.find(s => names.some(name => s.title.toLowerCase().includes(name)));
        return sec ? sec.content : '';
    };

    const rawObjective = findSectionContent(['objective', 'goal']);
    const rawDatasets = findSectionContent(['tech stack', 'technology', 'dataset', 'input']);
    const rawOutcomes = findSectionContent(['deliverable', 'outcome', 'expected outcome']);

    const features = getBullets(rawObjective);
    const techStack = getBullets(rawDatasets);
    const deliverables = getBullets(rawOutcomes);

    return {
        mainDescription,
        techStack,
        deliverables,
        features,
        rawObjective,
        rawDatasets,
        rawOutcomes,
        sections
    };
};


export default function PreferencesView() {
    const { data: profile, loading: profileLoading, error: profileError, refetch: refetchProfile } = useProfile();
    const { data: problemStatements = [], loading: psLoading, error: psError, refetch: refetchPs } = useProblemStatements();
    const { data: savedPrefs = [], loading: prefsLoading, error: prefsError, refetch: refetchPrefs } = usePreferences();
    const { data: proposals = [], loading: proposalsLoading, refetch: refetchProposals } = useProposals();
    const { data: team, loading: teamLoading, refetch: refetchTeam } = useTeam();
    const { data: deadlines } = useDeadlines();

    const [activeTab, setActiveTab] = useState('preferences'); // 'preferences' or 'proposal'
    const [preferences, setPreferences] = useState([]);

    // Proposal states
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [proposalFile, setProposalFile] = useState(null);
    const [uploadStatus, setUploadStatus] = useState('');
    const [isSaving, setIsSaving] = useState(false);
    const fileInputRef = useRef(null);

    // Project Details states
    const [projectDetails, setProjectDetails] = useState({
        repository_url: '',
        tech_stack: '',
        project_title: '',
        description: '',
        domain: ''
    });
    const [loadingDetails, setLoadingDetails] = useState(false);
    const [savingDetails, setSavingDetails] = useState(false);
    const [detailsError, setDetailsError] = useState(null);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [isFormSubmitted, setIsFormSubmitted] = useState(false);

    const [psSearch, setPsSearch] = useState('');
    const [selectedDomain, setSelectedDomain] = useState('All');
    
    const [selectedPsType, setSelectedPsType] = useState('All');
    // The value is never rendered — no spinner or disabled state reads it —
    // but the setter is still called around the submit, so the pair is kept
    // and the unused half is marked rather than removed.
    const [, setSubmitting] = useState(false);

    // No control calls the setter, so no row can ever expand. Kept as a
    // constant because the value is still read when rendering each row.
    const expandedPsId = null;
    const [selectedPsForAnalysis, setSelectedPsForAnalysis] = useState(null);

    const domainsList = useMemo(() => {
        const unique = new Set();
        (problemStatements || []).forEach(p => {
            if (p.domain) {
                const dom = p.domain.trim();
                if (dom && dom.toLowerCase() !== 'software' && dom.toLowerCase() !== 'hardware') {
                    unique.add(dom);
                }
            }
        });
        return ['All', ...Array.from(unique)];
    }, [problemStatements]);


    // Get active proposal if exists (latest)
    const activeProposal = proposals && proposals.length > 0 ? proposals[proposals.length - 1] : null;

    const isPlaceholderTitle = (title, teamName = '') => {
        if (!title) return true;
        const clean = title.trim().toLowerCase();
        if (!clean || clean === 'custom team' || clean.startsWith('pending') || clean.startsWith('admin-team')) return true;
        if (teamName && clean === teamName.trim().toLowerCase()) return true;
        if (/^team\s*-?\s*\d+$/i.test(clean)) return true;
        if (/^\d{4}(?:-\d{4})?[-_\s]+\d+$/i.test(clean)) return true;
        return false;
    };

    const hasApprovedProposal = proposals && proposals.some(p => String(p.status).toLowerCase() === 'approved');
    const hasAllocatedPS = team && (() => {
        if (team.allocated_ps_id) return true;
        const p_title = team.project_title;
        if (p_title && !isPlaceholderTitle(p_title, team.name)) return true;
        return false;
    })();

    const isProjectAllocated = hasApprovedProposal || hasAllocatedPS;

    const isLeader = (() => {
        const myIds = [
            String(profile?.id || '').toLowerCase(),
            String(profile?.student_id || '').toLowerCase(),
            String(profile?.roll_number || '').toLowerCase(),
            String(profile?.name || '').toLowerCase(),
            String(profile?.email || '').toLowerCase()
        ].filter(Boolean);

        if (team) {
            const leaderVal = String(team.leader || team.leader_id || team.leaderRaw || '').toLowerCase();
            if (leaderVal) {
                if (myIds.some(id => id && (leaderVal.includes(id) || id.includes(leaderVal)))) return true;
                const members = team.members || [];
                if (Array.isArray(members)) {
                    for (const m of members) {
                        if (!m) continue;
                        const mIds = [
                            String(m.id || '').toLowerCase(),
                            String(m.student_id || '').toLowerCase(),
                            String(m.roll || '').toLowerCase(),
                            String(m.name || '').toLowerCase(),
                            String(m.email || '').toLowerCase(),
                            String(m.student?.id || '').toLowerCase(),
                            String(m.student?.name || '').toLowerCase()
                        ].filter(Boolean);
                        if (mIds.some(lId => leaderVal.includes(lId) || lId.includes(leaderVal)) && !myIds.some(myId => mIds.includes(myId))) {
                            return false;
                        }
                    }
                }
            }

            const members = team.members || [];
            if (Array.isArray(members) && members.length > 0) {
                for (let idx = 0; idx < members.length; idx++) {
                    const m = members[idx];
                    if (!m) continue;
                    const mIds = [
                        String(m.id || '').toLowerCase(),
                        String(m.student_id || '').toLowerCase(),
                        String(m.roll || '').toLowerCase(),
                        String(m.name || '').toLowerCase(),
                        String(m.email || '').toLowerCase(),
                        String(m.student?.id || '').toLowerCase(),
                        String(m.student?.name || '').toLowerCase()
                    ].filter(Boolean);

                    if (myIds.some(myId => mIds.includes(myId))) {
                        const mRole = String(m.role || '').toUpperCase();
                        if (m.isLeader || mRole === 'LEADER') return true;
                        if (mRole === 'MEMBER') return false;
                        return idx === 0;
                    }
                }
            }
        }

        if (profile?.team_membership?.role) {
            return String(profile.team_membership.role).toUpperCase() === 'LEADER';
        }
        return false;
    })();

    useEffect(() => {
        if (isProjectAllocated) {
            const fetchProjectDetails = async () => {
                setLoadingDetails(true);
                setDetailsError(null);
                try {
                    const data = await fetchWithAuth('/api/student/team/project-details');
                    if (data) {
                        setProjectDetails({
                            repository_url: data.repository_url || '',
                            tech_stack: data.tech_stack || '',
                            project_title: data.project_title || team?.project_title || '',
                            description: formatDescriptionSummary(data.description) || formatDescriptionSummary(team?.description) || '',
                            domain: data.domain || (team?.domain ? team.domain.join(', ') : '')
                        });
                        setIsFormSubmitted(!!(data.repository_url && data.tech_stack));
                    }
                } catch (err) {
                    console.error("Failed to fetch project details:", err);
                    setDetailsError(err.message || "Failed to load project details");
                } finally {
                    setLoadingDetails(false);
                }
            };
            fetchProjectDetails();
        }
    }, [isProjectAllocated, team]);

    const [prevSavedPrefs, setPrevSavedPrefs] = useState(savedPrefs);
    if (savedPrefs !== prevSavedPrefs) {
        setPrevSavedPrefs(savedPrefs);
        if (savedPrefs && savedPrefs.length > 0) {
            setPreferences(savedPrefs);
        }
    }

    const [prevActiveProposal, setPrevActiveProposal] = useState(activeProposal);
    if (activeProposal !== prevActiveProposal) {
        setPrevActiveProposal(activeProposal);
        if (activeProposal) {
            setTitle(activeProposal.title || '');
            setDescription(activeProposal.aiRationale || activeProposal.description || '');
        }
    }

    const handleRetry = () => {
        refetchProfile();
        refetchPs();
        refetchPrefs();
        refetchProposals();
        refetchTeam();
    };

    if (profileLoading || psLoading || prefsLoading || proposalsLoading || teamLoading) {
        return (
            <div className="space-y-6">
                <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                    <LoadingSkeleton lines={6} />
                </div>
            </div>
        );
    }

    if (profileError || psError || prefsError) {
        return (
            <ErrorCard message={profileError || psError || prefsError} onRetry={handleRetry} />
        );
    }

    if (!team) {
        return (
            <div className="bg-white dark:bg-slate-800 rounded-3xl p-10 border border-slate-200 dark:border-slate-700/50 shadow-sm text-center flex flex-col items-center justify-center min-h-[400px]">
                <div className="p-5 bg-indigo-50 dark:bg-indigo-500/10 rounded-2xl mb-4 text-indigo-500">
                    <ClipboardList className="w-16 h-16 animate-pulse" />
                </div>
                <h3 className="text-2xl font-black text-slate-800 dark:text-slate-100">Team Pending</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-3 max-w-md">
                    You do not belong to any active project team yet. Please form or join a team first before selecting preferences or submitting proposals.
                </p>
            </div>
        );
    }

    const submitted = savedPrefs && savedPrefs.length > 0;
    const isLockedOrApproved = submitted || isProjectAllocated;

    const isHardwarePs = (ps) => {
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
    };


    // Dynamic filtering and search without calling external API
    const filteredAvailableStatements = (problemStatements || [])
        .filter(ps => !preferences.some(p => p.id === ps.id))
        .filter(ps => {
            const matchesSearch =
                !psSearch.trim() ||
                (ps.title || '').toLowerCase().includes(psSearch.toLowerCase()) ||
                (ps.description || '').toLowerCase().includes(psSearch.toLowerCase());
            const matchesDomain =
                !selectedDomain ||
                selectedDomain === 'All' ||
                String(ps.domain || '').trim().toLowerCase().includes(String(selectedDomain).trim().toLowerCase());

            const isHw = isHardwarePs(ps);
            let matchesPsType = true;
            if (selectedPsType === 'Software') {
                matchesPsType = !isHw;
            } else if (selectedPsType === 'Hardware') {
                matchesPsType = isHw;
            }

            return matchesSearch && matchesDomain && matchesPsType;
        });

    const isTeamLeader = isLeader;

    // Check deadlines

    const proposalDeadline = deadlines?.find(d => d.name === 'proposal' || d.name === 'proposalUpload' || d.id === 'deadline-proposal' || d.id === 'proposalUpload' || d.id === 'deadline-proposalUpload');
    const proposalDeadlinePassed = proposalDeadline ? proposalDeadline.is_past : false;

    const hasActiveProposal = proposals && proposals.some(p =>
        ['pending', 'approved'].includes(String(p.status).toLowerCase())
    );

    // Determine resubmission status
    const latestStatus = activeProposal ? String(activeProposal.status || '').toLowerCase() : '';
    const isRejectedOrRevision = latestStatus === 'rejected' || latestStatus === 'revision' || latestStatus === 'revision requested' || latestStatus === 'revision_requested';


    // Disable logic
    const disableProposalEdits = isProjectAllocated || !!(profile?.isLocked || (isRejectedOrRevision ? false : (proposalDeadlinePassed || hasActiveProposal)));
    const canSubmitProposal = !isProjectAllocated && !profile?.isLocked && !hasActiveProposal && (!proposalDeadlinePassed || isRejectedOrRevision);
    const isFormLocked = isFormSubmitted || !isTeamLeader;

    const handleSaveProjectDetails = async (e) => {
        if (e) e.preventDefault();
        if (!isTeamLeader || isFormSubmitted) return;

        if (!window.confirm("Are you sure you want to finalize your submission? This will lock your project workspace and submit it for coordination review. You will not be able to change these settings afterwards.")) {
            return;
        }

        setSavingDetails(true);
        setDetailsError(null);
        setSaveSuccess(false);
        try {
            await fetchWithAuth('/api/student/team/project-details', {
                method: 'POST',
                body: {
                    repository_url: projectDetails.repository_url.trim(),
                    tech_stack: projectDetails.tech_stack.trim(),
                    project_title: projectDetails.project_title.trim(),
                    description: projectDetails.description.trim(),
                    domain: projectDetails.domain.trim()
                }
            });
            setSaveSuccess(true);
            setIsFormSubmitted(true);
            refetchTeam();
            setTimeout(() => setSaveSuccess(false), 3000);
        } catch (err) {
            console.error("Failed to save project details:", err);
            setDetailsError(err.message || "Failed to save project details");
        } finally {
            setSavingDetails(false);
        }
    };

    const handleAdd = async (ps) => {
        if (!isLeader) {
            alert("Only the team leader is authorized to reserve problem statements for your team.");
            return;
        }
        if (!window.confirm(`Are you sure you want to select and reserve the topic "${ps.title}"? Once selected, other teams cannot choose this topic.`)) {
            return;
        }
        setSubmitting(true);
        try {
            await fetchWithAuth('/api/student/team/reserve-ps', {
                method: 'POST',
                body: { ps_id: ps.id }
            });
            alert("Topic reserved successfully! Now please enter your public repository URL to finalize your submission.");
            refetchTeam();
            refetchPs();
        } catch (err) {
            console.error("Failed to reserve problem statement:", err);
            alert(err.message || "Failed to reserve problem statement");
        } finally {
            setSubmitting(false);
        }
    };


    const submitProposal = async () => {
        if (!title.trim() || !description.trim()) {
            return alert("Please enter both title and description.");
        }
        setIsSaving(true);
        setUploadStatus('');
        try {
            let fileUrl = null;

            if (proposalFile) {
                setUploadStatus('Uploading file…');
                try {
                    const { data: { session } } = await supabase.auth.getSession();
                    const userId = session?.user?.id || 'unknown';
                    const ext = proposalFile.name.split('.').pop();
                    const filePath = `proposals/${userId}/${Date.now()}.${ext}`;

                    const bucket = 'PMS';
                    const uploadResult = await supabase.storage
                        .from(bucket)
                        .upload(filePath, proposalFile, { upsert: false });
                    if (!uploadResult.error) {
                        const { data: urlData } = supabase.storage.from(bucket).getPublicUrl(filePath);
                        fileUrl = urlData?.publicUrl || null;
                    } else {
                        throw uploadResult.error;
                    }
                } catch (_uploadErr) {
                    console.error("Supabase upload error:", _uploadErr);
                    alert("Failed to upload proposal PDF: " + (_uploadErr.message || _uploadErr.error_description || JSON.stringify(_uploadErr)));
                    setIsSaving(false);
                    setUploadStatus('');
                    return;
                }
                setUploadStatus('');
            }

            setUploadStatus('Submitting…');
            await fetchWithAuth('/api/student/proposals', {
                method: 'POST',
                body: {
                    title: title.trim(),
                    description: description.trim(),
                    ...(fileUrl ? { proposalFile: fileUrl } : {})
                }
            });
            alert("Proposal successfully submitted for review.");
            setProposalFile(null);
            if (fileInputRef.current) fileInputRef.current.value = '';
            refetchProposals();
            refetchTeam();
        } catch (err) {
            alert("Failed to submit proposal: " + err.message);
        } finally {
            setIsSaving(false);
            setUploadStatus('');
        }
    };

    const activeProposalStatus = activeProposal ? (activeProposal.status || 'Pending') : 'Not Submitted';

    if (isProjectAllocated) {
        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                {/* Header & Status Indicator */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
                    <div>
                        <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                            <ClipboardList className="w-6 h-6 mr-3 text-indigo-500" /> Project Workspace
                        </h2>
                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                            Manage your allocated project details, code repository, and tech stack configuration.
                        </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        <span className="flex items-center text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-3.5 py-2 rounded-xl border border-emerald-200 dark:border-emerald-500/20 shadow-sm">
                            🌟 Project Allocated
                        </span>
                        {isTeamLeader ? (
                            <span className="flex items-center text-xs font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3.5 py-2 rounded-xl border border-indigo-200 dark:border-indigo-500/20 shadow-sm">
                                👑 Team Leader
                            </span>
                        ) : (
                            <span className="flex items-center text-xs font-bold text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-500/10 px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-500/20 shadow-sm">
                                👥 Team Member
                            </span>
                        )}
                    </div>
                </div>

                {loadingDetails ? (
                    <div className="bg-white dark:bg-slate-800 rounded-3xl p-8 border border-slate-100 dark:border-slate-700/50 shadow-sm">
                        <LoadingSkeleton lines={6} />
                    </div>
                ) : (
                    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

                        {/* LEFT COLUMN: Overview & Team Roster */}
                        <div className="lg:col-span-2 space-y-6">

                            {/* Project Overview Card */}
                            <div className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 text-white rounded-3xl p-6 border border-indigo-500/20 shadow-xl relative overflow-hidden backdrop-blur-md">
                                <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-full blur-3xl -z-10"></div>
                                <div className="absolute bottom-0 left-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl -z-10"></div>

                                <div className="space-y-4">
                                    <div>
                                        <div className="flex items-center justify-between gap-2 mb-2">
                                            <span className="inline-flex items-center px-2.5 py-0.5 bg-indigo-500/20 text-indigo-300 text-[10px] rounded-lg font-bold uppercase tracking-wider border border-indigo-500/30">
                                                Allocated Topic
                                            </span>
                                            {team.allocated_ps_id && (
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        const fullPs = problemStatements.find(p =>
                                                            (p.id && team.allocated_ps_id && String(p.id) === String(team.allocated_ps_id)) ||
                                                            (p.title && team.project_title && p.title.trim().toLowerCase() === team.project_title.trim().toLowerCase())
                                                        );
                                                        setSelectedPsForAnalysis(fullPs || {
                                                            id: team.allocated_ps_id || 'allocated',
                                                            title: projectDetails.project_title || team.project_title || team.name,
                                                            description: projectDetails.description || team.description || projectDetails.project_title || team.project_title,
                                                            domain: Array.isArray(team.domain) ? team.domain.join(', ') : (team.domain || 'General'),
                                                            is_allocated: true
                                                        });
                                                    }}
                                                    className="px-3.5 py-1.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white rounded-xl transition-all shadow-lg hover:shadow-indigo-500/25 shrink-0 flex items-center gap-1.5 text-xs font-black tracking-wide cursor-pointer border border-indigo-400/30 active:scale-95"
                                                    title="View Full Architecture Plan & Specs"
                                                >
                                                    <Eye className="w-3.5 h-3.5 text-white" />
                                                    <span>View Blueprint</span>
                                                </button>
                                            )}
                                        </div>
                                        <h3 className="text-lg font-black text-white leading-tight">
                                            {team.project_title || team.name}
                                        </h3>
                                    </div>

                                    <div className="pt-3 border-t border-slate-800 space-y-3">
                                        {team.domain && team.domain.length > 0 && (
                                            <div className="flex flex-wrap gap-1.5">
                                                {team.domain.map((d, i) => (
                                                    <span key={i} className="text-[10px] font-bold bg-slate-800/60 text-slate-300 px-2.5 py-1 rounded-md border border-slate-700/50">
                                                        Domain: {d}
                                                    </span>
                                                ))}
                                            </div>
                                        )}

                                        {team.mentor && (
                                            <div className="flex items-center gap-2.5 p-2.5 bg-slate-800/30 rounded-xl border border-slate-700/30">
                                                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-xs shrink-0">
                                                    {(team.mentor.name || 'M').charAt(0).toUpperCase()}
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-[10px] font-bold text-slate-205">Mentor Assigned</p>
                                                    <p className="text-[11px] text-slate-400 truncate">{team.mentor.name} ({team.mentor.email || 'No email'})</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Team Roster Card */}
                            <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm p-6 space-y-4">
                                <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                                    <Users className="w-4 h-4 text-indigo-500" /> Team Roster
                                </h4>
                                <div className="space-y-3">
                                    {team.members && team.members.map((m) => (
                                        <div key={m.id} className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/40 rounded-2xl border border-slate-100 dark:border-slate-800">
                                            <div className="flex items-center gap-3 min-w-0">
                                                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-xs shrink-0 shadow-sm">
                                                    {(m.student?.name || 'S').charAt(0).toUpperCase()}
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-xs font-semibold text-slate-800 dark:text-slate-250 truncate">{m.student?.name}</p>
                                                    <p className="text-[10px] text-slate-400 truncate">{m.student?.email || '—'}</p>
                                                </div>
                                            </div>
                                            <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider ${m.role === 'LEADER' ? 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-450'}`}>
                                                {m.role}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* RIGHT COLUMN: Submission Form */}
                        <div className="lg:col-span-3">
                            <form onSubmit={handleSaveProjectDetails} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-xl overflow-hidden backdrop-blur-md">
                                <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20">
                                    <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                                        <Code className="w-5 h-5 text-indigo-500" /> Project Configurations
                                    </h3>
                                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                                        Provide the repository link, software stack, and details of your workspace.
                                    </p>
                                </div>

                                <div className="p-6 space-y-5">
                                    {/* Locked Banner if submitted */}
                                    {isFormSubmitted ? (
                                        <div className="p-4 bg-emerald-50 dark:bg-emerald-955/15 border border-emerald-250 dark:border-emerald-900/40 rounded-2xl flex items-start gap-3">
                                            <Lock className="w-4 h-4 text-emerald-550 shrink-0 mt-0.5" />
                                            <div>
                                                <h5 className="text-xs font-bold text-emerald-850 dark:text-emerald-355">Submission Locked</h5>
                                                <p className="text-[11px] text-emerald-600 dark:text-emerald-455 mt-0.5">
                                                    Your project workspace has been successfully submitted and is now locked. Only project coordinators or administrators have the privilege to edit these details.
                                                </p>
                                            </div>
                                        </div>
                                    ) : (
                                        /* Read Only Banner if not Leader */
                                        !isTeamLeader && (
                                            <div className="p-4 bg-amber-50 dark:bg-amber-955/20 border border-amber-200 dark:border-amber-900/50 rounded-2xl flex items-start gap-3">
                                                <Lock className="w-4 h-4 text-amber-550 shrink-0 mt-0.5" />
                                                <div>
                                                    <h5 className="text-xs font-bold text-amber-850 dark:text-amber-355">Read-Only Workspace</h5>
                                                    <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-0.5">
                                                        Only your Team Leader has write permissions to modify project details, repository link, and tech stack.
                                                    </p>
                                                </div>
                                            </div>
                                        )
                                    )}

                                    {saveSuccess && (
                                        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="p-4 bg-emerald-50 dark:bg-emerald-955/20 border border-emerald-250 dark:border-emerald-900/50 rounded-2xl flex items-center gap-2 text-emerald-700 dark:text-emerald-400 text-xs font-bold">
                                            <CheckCircle className="w-4 h-4 text-emerald-550" /> Settings updated successfully!
                                        </motion.div>
                                    )}

                                    {detailsError && (
                                        <div className="p-4 bg-rose-50 dark:bg-rose-955/20 border border-rose-200 dark:border-rose-900/50 rounded-2xl flex items-center gap-2 text-rose-700 dark:text-rose-400 text-xs font-bold">
                                            <AlertCircle className="w-4 h-4 text-rose-500" /> {detailsError}
                                        </div>
                                    )}

                                    {/* Customizable Project Title */}
                                    <div className="space-y-1.5">
                                        <label className="block text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                                            Customized Project Title
                                        </label>
                                        <input
                                            type="text"
                                            value={projectDetails.project_title}
                                            onChange={(e) => setProjectDetails({ ...projectDetails, project_title: e.target.value })}
                                            disabled={isFormLocked || savingDetails}
                                            placeholder="Enter customized title for your project"
                                            className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-xs dark:text-slate-200 font-medium transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                                        />
                                    </div>

                                    {/* Customizable Project Description */}
                                    <div className="space-y-1.5">
                                        <label className="block text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                                            Project Description / Abstract
                                        </label>
                                        <textarea
                                            rows="4"
                                            value={projectDetails.description}
                                            onChange={(e) => setProjectDetails({ ...projectDetails, description: e.target.value })}
                                            disabled={isFormLocked || savingDetails}
                                            placeholder="Provide a detailed description of the system or product you are building..."
                                            className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-xs dark:text-slate-200 font-medium transition-all resize-none leading-relaxed disabled:opacity-60 disabled:cursor-not-allowed"
                                        />
                                    </div>

                                    {/* Comma separated domains */}
                                    <div className="space-y-1.5">
                                        <label className="block text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                                            Project Domains (comma-separated)
                                        </label>
                                        <div className="relative">
                                            <Tag className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                            <input
                                                type="text"
                                                value={projectDetails.domain}
                                                onChange={(e) => setProjectDetails({ ...projectDetails, domain: e.target.value })}
                                                disabled={isFormLocked || savingDetails}
                                                placeholder="e.g. Web Development, Artificial Intelligence, Cybersecurity"
                                                className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-xs dark:text-slate-200 font-medium transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                                            />
                                        </div>
                                    </div>

                                    {/* GitHub Repository URL */}
                                    <div className="space-y-1.5">
                                        <label className="block text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest flex justify-between items-center">
                                            <span>GitHub Code Repository URL</span>
                                            {projectDetails.repository_url && (
                                                <a
                                                    href={projectDetails.repository_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-[10px] text-indigo-500 hover:underline flex items-center gap-1 font-bold lowercase normal-case tracking-normal"
                                                >
                                                    Open <ExternalLink className="w-2.5 h-2.5" />
                                                </a>
                                            )}
                                        </label>
                                        <div className="relative">
                                            <Github className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                            <input
                                                type="url"
                                                required
                                                value={projectDetails.repository_url}
                                                onChange={(e) => setProjectDetails({ ...projectDetails, repository_url: e.target.value })}
                                                disabled={isFormLocked || savingDetails}
                                                placeholder="e.g. https://github.com/username/repository"
                                                className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-xs dark:text-slate-200 font-medium transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                                            />
                                        </div>
                                    </div>

                                    {/* Tech Stack */}
                                    <div className="space-y-1.5">
                                        <label className="block text-[11px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest">
                                            Technology Stack / Core Software Components
                                        </label>
                                        <div className="relative">
                                            <Code className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                                            <input
                                                type="text"
                                                required
                                                value={projectDetails.tech_stack}
                                                onChange={(e) => setProjectDetails({ ...projectDetails, tech_stack: e.target.value })}
                                                disabled={isFormLocked || savingDetails}
                                                placeholder="e.g. React, Node.js, PostgreSQL, Docker"
                                                className="w-full pl-10 pr-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700/80 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-xs dark:text-slate-200 font-medium transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Save Button / Footer */}
                                {isFormSubmitted ? (
                                    <div className="p-6 bg-slate-50 dark:bg-slate-900/20 border-t border-slate-100 dark:border-slate-750/50 flex justify-center items-center gap-2 text-xs font-bold text-slate-500 dark:text-slate-400">
                                        <Lock className="w-4 h-4 text-slate-450" /> Locked (Only Administrators can modify)
                                    </div>
                                ) : (
                                    isTeamLeader && (
                                        <div className="p-6 bg-slate-50 dark:bg-slate-900/20 border-t border-slate-100 dark:border-slate-750/50 flex justify-end">
                                            <button
                                                type="submit"
                                                disabled={savingDetails || !projectDetails.repository_url.trim() || !projectDetails.tech_stack.trim()}
                                                className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 dark:disabled:text-slate-650 rounded-xl font-bold transition-all shadow-md active:scale-98 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-xs"
                                            >
                                                {savingDetails ? (
                                                    <><span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block"></span> Submitting...</>
                                                ) : (
                                                    <><CheckCircle className="w-3.5 h-3.5" /> Final Submit Project Workspace</>
                                                )}
                                            </button>
                                        </div>
                                    )
                                )}
                            </form>
                        </div>
                    </div>
                )}

                {/* Problem Statement Detailed Analysis Modal */}
                {selectedPsForAnalysis && (
                    <PsArchitecturePlanModal
                        ps={selectedPsForAnalysis}
                        onClose={() => setSelectedPsForAnalysis(null)}
                    />
                )}
            </motion.div>
        );
    }

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">

            {/* Header & Status Indicator */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
                <div>
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                        <ClipboardList className="w-6 h-6 mr-3 text-indigo-500" /> Project Workspace
                    </h2>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        Select topic preferences or submit a custom project proposal.
                    </p>
                </div>

                <div className="flex flex-wrap gap-2">
                    {isProjectAllocated ? (
                        <span className="flex items-center text-xs font-bold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-3.5 py-2 rounded-xl border border-emerald-200 dark:border-emerald-500/20 shadow-sm">
                            🌟 Project Allocated
                        </span>
                    ) : submitted ? (
                        <span className="flex items-center text-xs font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3.5 py-2 rounded-xl border border-indigo-200 dark:border-indigo-500/20 shadow-sm">
                            <CheckCircle className="w-4 h-4 mr-2" /> Preferences Locked
                        </span>
                    ) : null}

                    {activeProposal && !isProjectAllocated && (
                        <span className={`flex items-center text-xs font-bold px-3.5 py-2 rounded-xl border
                            ${(activeProposalStatus.toLowerCase() === 'approved' || activeProposalStatus.toLowerCase() === 'valid') ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 border-emerald-200 dark:border-emerald-800' :
                                (activeProposalStatus.toLowerCase() === 'pending' || activeProposalStatus.toLowerCase() === 'submitted') ? 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 border-amber-200 dark:border-amber-800 animate-pulse' :
                                    activeProposalStatus.toLowerCase() === 'rejected' ? 'bg-rose-50 dark:bg-rose-500/10 text-rose-600 border-rose-200 dark:border-rose-800' :
                                        'bg-orange-50 dark:bg-orange-500/10 text-orange-600 border-orange-200 dark:border-orange-850'}`}>
                            Proposal: {activeProposalStatus}
                        </span>
                    )}
                </div>
            </div>

            {/* Premium Tab Bar */}
            <div className="flex border-b border-slate-200 dark:border-slate-700/50 gap-6 shrink-0">
                <button
                    onClick={() => setActiveTab('preferences')}
                    className={`py-3 text-sm font-bold transition-all relative flex items-center gap-2 ${activeTab === 'preferences' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'}`}
                >
                    <ClipboardList className="w-4 h-4" /> Project Preferences
                    {activeTab === 'preferences' && (
                        <motion.div layoutId="activeTabIndicator" className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 dark:bg-indigo-400 rounded-full" />
                    )}
                </button>
                <button
                    onClick={() => setActiveTab('proposal')}
                    className={`py-3 text-sm font-bold transition-all relative flex items-center gap-2 ${activeTab === 'proposal' ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'}`}
                >
                    <FileText className="w-4 h-4" /> Submit Custom Proposal
                    {activeTab === 'proposal' && (
                        <motion.div layoutId="activeTabIndicator" className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 dark:bg-indigo-400 rounded-full" />
                    )}
                </button>
            </div>

            {/* Allocated Banner */}
            {isProjectAllocated && (
                <div className="bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10 border border-indigo-500/20 dark:border-indigo-500/30 rounded-3xl p-6 shadow-xl relative overflow-hidden backdrop-blur-md">
                    <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-full blur-3xl -z-10"></div>
                    <div className="absolute bottom-0 left-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl -z-10"></div>

                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                            <span className="inline-flex items-center px-3 py-1 bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-400 text-xs rounded-xl font-bold uppercase tracking-wider mb-3 border border-indigo-200 dark:border-indigo-800">
                                🌟 Allocated Project
                            </span>
                            <div className="flex items-center gap-3 flex-wrap">
                                <h3 className="text-2xl font-black text-slate-800 dark:text-white leading-tight">
                                    {team.project_title}
                                </h3>
                                {(() => {
                                    const allocatedPs = problemStatements.find(ps =>
                                        ps.title && team.project_title &&
                                        ps.title.trim().toLowerCase() === team.project_title.trim().toLowerCase()
                                    );
                                    if (!allocatedPs) return null;
                                    return (
                                        <button
                                            onClick={() => setSelectedPsForAnalysis(allocatedPs)}
                                            className="p-1.5 text-slate-450 hover:text-indigo-605 hover:bg-white dark:hover:bg-slate-800 rounded-xl transition-all border border-slate-200/40 dark:border-slate-700/40 bg-white/40 dark:bg-slate-900/40 shadow-xs"
                                            title="View Project Specifications"
                                        >
                                            <Eye className="w-4.5 h-4.5" />
                                        </button>
                                    );
                                })()}
                            </div>


                            <div className="flex flex-wrap gap-2.5 mt-4">
                                {team.domain && team.domain.length > 0 && team.domain.map((d, i) => (
                                    <span key={i} className="text-xs font-bold bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-400 px-3 py-1 rounded-lg border border-slate-200 dark:border-slate-700/50">
                                        Domain: {d}
                                    </span>
                                ))}
                                {team.mentor && (
                                    <span className="text-xs font-bold bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 px-3 py-1 rounded-lg border border-indigo-100 dark:border-indigo-900/30">
                                        Mentor: {team.mentor.name}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {activeTab === 'preferences' ? (
                /* ── TAB 1: PREFERENCES ── */
                <div className="flex flex-col gap-6 w-full">
                    {/* Header Banner */}
                    <div className="bg-gradient-to-r from-indigo-600 via-purple-700 to-indigo-850 rounded-3xl p-8 text-white shadow-xl relative overflow-hidden border border-indigo-500/20">
                        <div className="absolute inset-0 opacity-10 mix-blend-overlay pointer-events-none">
                            <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                                <path d="M0,150 C300,50 600,250 1000,100 L1000,300 L0,300 Z" fill="currentColor"></path>
                            </svg>
                        </div>
                        <div data-tour="student-pref-browse" className="relative z-10">
                            <h1 className="text-3xl font-black mb-2 tracking-tight">Browse & Reserve Topics</h1>
                            <p className="text-indigo-100/90 text-sm max-w-lg">Review and select your preferred project problem statements. Topics are reserved on a first-come, first-served basis.</p>
                        </div>
                    </div>

                    <div className="w-full space-y-6">
                        {/* Available Topics */}
                        <div className="w-full bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm flex flex-col">
                            <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/50 shrink-0">
                                <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center">
                                    Available Topics
                                </h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Review and select your preferred problem statements.</p>

                                {/* Search and Filters */}
                                <div className="mt-4 space-y-3">
                                    <div className="relative">
                                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-450 pointer-events-none" />
                                        <input
                                            type="text"
                                            placeholder="Search by topic title or description..."
                                            value={psSearch}
                                            onChange={(e) => setPsSearch(e.target.value)}
                                            className="w-full pl-9 pr-4 py-2 bg-white dark:bg-slate-900 border border-slate-250 dark:border-slate-700 rounded-xl text-xs outline-none focus:ring-2 focus:ring-indigo-500 dark:text-slate-200 transition-all"
                                        />
                                    </div>
                                    <div className="flex flex-col sm:flex-row gap-2">
                                        {/* Type Filter */}
                                        <select
                                            value={selectedPsType}
                                            onChange={(e) => setSelectedPsType(e.target.value)}
                                            className="flex-1 bg-white dark:bg-slate-900 border border-slate-250 dark:border-slate-700 rounded-xl px-3 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-indigo-500 dark:text-slate-200 shadow-sm"
                                        >
                                            <option value="All">All Types (Software & Hardware)</option>
                                            <option value="Software">💻 Software Projects</option>
                                            <option value="Hardware">🛠️ Hardware Projects</option>
                                        </select>

                                        {/* Domain Filter */}
                                        <select
                                            value={selectedDomain}
                                            onChange={(e) => setSelectedDomain(e.target.value)}
                                            className="flex-1 bg-white dark:bg-slate-900 border border-slate-250 dark:border-slate-700 rounded-xl px-3 py-2 text-xs font-bold outline-none focus:ring-2 focus:ring-indigo-500 dark:text-slate-200 shadow-sm"
                                        >
                                            <option value="All">All Specific Domains</option>
                                            {domainsList.filter(d => d !== 'All').map(d => (
                                                <option key={d} value={d}>{d}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div className="p-4 overflow-y-auto flex-1 space-y-4">
                                {filteredAvailableStatements.length === 0 ? (
                                    <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
                                        <Info className="w-12 h-12 mb-4 opacity-50" />
                                        <p className="font-medium text-slate-500 dark:text-slate-400 max-w-xs">
                                            {problemStatements.length === 0
                                                ? "No topics available or all have been selected."
                                                : "No topics match your search/filter criteria."}
                                        </p>
                                    </div>
                                ) : (
                                    <AnimatePresence>
                                        {filteredAvailableStatements.map(ps => {
                                            const parsed = parseProblemStatementDescription(ps.description);
                                            const isExpanded = expandedPsId === ps.id;
                                            const hasDetails = (parsed.sections && parsed.sections.length > 0) || parsed.techStack.length > 0 || parsed.deliverables.length > 0 || parsed.features.length > 0;

                                            return (
                                                <motion.div
                                                    layout
                                                    initial={{ opacity: 0, scale: 0.95 }}
                                                    animate={{ opacity: 1, scale: 1 }}
                                                    exit={{ opacity: 0, scale: 0.95 }}
                                                    key={ps.id}
                                                    onClick={() => {
                                                        setSelectedPsForAnalysis(ps);
                                                    }}
                                                    className={`border rounded-2xl p-5 transition-all group cursor-pointer relative ${ps.is_allocated
                                                        ? 'bg-slate-100/50 dark:bg-slate-900/20 border-slate-200 dark:border-slate-800 opacity-60'
                                                        : 'bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-600 hover:shadow-md'
                                                        }`}
                                                >
                                                    <div className="flex justify-between items-start mb-3">
                                                        <div>
                                                            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                                                                {(() => {
                                                                      const isHw = isHardwarePs(ps);
                                                                      let label = '💻 SOFTWARE';
                                                                      let style = 'bg-cyan-50 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800/60 font-black';

                                                                      if (isHw) {
                                                                          label = '🛠️ HARDWARE';
                                                                          style = 'bg-amber-50 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 border-amber-200 dark:border-amber-800/60 font-black';
                                                                      }

                                                                      return (
                                                                          <span className={`text-xs font-black uppercase tracking-wider px-2.5 py-1 rounded-md border transition-all ${style}`}>
                                                                              {label}
                                                                          </span>
                                                                      );
                                                                  })()}
                                                                {ps.is_allocated && (
                                                                    <span className="text-xs font-black uppercase tracking-wider text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-500/10 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                                                                        <Lock className="w-3 h-3" /> Fully Booked
                                                                    </span>
                                                                )}
                                                                {!ps.is_allocated && Number(ps.team_count) > 0 && (
                                                                    <span className="text-xs font-black uppercase tracking-wider text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-2.5 py-0.5 rounded-md flex items-center gap-1">
                                                                        <Users className="w-3 h-3" /> 1 Team Already Selected
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <h4 className="font-bold text-slate-800 dark:text-slate-100">{ps.title}</h4>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            <button
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setSelectedPsForAnalysis(ps);
                                                                }}
                                                                className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/20 rounded-xl transition-all opacity-0 group-hover:opacity-100 scale-90 group-hover:scale-100 shadow-sm border border-transparent hover:border-indigo-200 dark:hover:border-indigo-800"
                                                                title="View Full Detailed Plan"
                                                            >
                                                                <Eye className="w-5 h-5" />
                                                            </button>
                                                            <button
                                                                disabled={isLockedOrApproved || ps.is_allocated || !isLeader}
                                                                title={!isLeader ? "Only the team leader can reserve problem statements" : (ps.is_allocated ? "Allocated" : "Add to selection")}
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    handleAdd(ps);
                                                                }}
                                                                className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                                            >
                                                                {ps.is_allocated ? <Lock className="w-5 h-5 text-rose-500" /> : (!isLeader ? <Lock className="w-5 h-5 text-slate-400" /> : <Plus className="w-5 h-5" />)}
                                                            </button>
                                                        </div>
                                                    </div>

                                                    <p className="text-sm text-slate-650 dark:text-slate-400 leading-relaxed line-clamp-3">
                                                        {formatDescriptionSummary(parsed.mainDescription || ps.description)}
                                                    </p>

                                                    {isExpanded && (
                                                        <motion.div
                                                            initial={{ opacity: 0, height: 0 }}
                                                            animate={{ opacity: 1, height: 'auto' }}
                                                            transition={{ duration: 0.2 }}
                                                            className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-850 space-y-4"
                                                            onClick={(e) => e.stopPropagation()}
                                                        >
                                                            {parsed.techStack.length > 0 && (
                                                                <div>
                                                                    <span className="text-[10px] font-bold text-slate-450 dark:text-slate-500 uppercase tracking-wider block mb-1.5">Tech Stack</span>
                                                                    <div className="flex flex-wrap gap-1.5">
                                                                        {parsed.techStack.map(tech => (
                                                                            <span key={tech} className="px-2.5 py-0.5 bg-slate-100 dark:bg-slate-800/80 text-slate-650 dark:text-slate-300 rounded-md text-[11px] font-medium border border-slate-200/50 dark:border-slate-700/50">
                                                                                {tech}
                                                                            </span>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}

                                                            {(() => {
                                                                const nonTechSections = parsed.sections && parsed.sections.length > 0
                                                                    ? parsed.sections.filter(sec => !['tech stack', 'technology', 'dataset', 'input'].some(k => sec.title.toLowerCase().includes(k)))
                                                                    : [
                                                                        ...(parsed.rawObjective ? [{ title: 'Key Objectives / Modules', bullets: parsed.features, content: parsed.rawObjective }] : []),
                                                                        ...(parsed.rawOutcomes ? [{ title: 'Expected Outcomes & Deliverables', bullets: parsed.deliverables, content: parsed.rawOutcomes }] : [])
                                                                    ];
                                                                return nonTechSections.map((section, idx) => (
                                                                    <div key={idx}>
                                                                        <span className="text-[10px] font-bold text-slate-455 dark:text-slate-500 uppercase tracking-wider block mb-1.5">{section.title}</span>
                                                                        {section.bullets && section.bullets.length > 0 ? (
                                                                            <ul className="space-y-1 text-[11px] text-slate-650 dark:text-slate-350">
                                                                                {section.bullets.map((bullet, bIdx) => (
                                                                                    <li key={bIdx} className="flex items-start gap-1.5">
                                                                                        <span className="text-indigo-500 mt-0.5">•</span>
                                                                                        <span className="break-words">{bullet}</span>
                                                                                    </li>
                                                                                ))}
                                                                            </ul>
                                                                        ) : (
                                                                            <p className="text-[11px] leading-relaxed text-slate-650 dark:text-slate-350 pl-1 whitespace-pre-wrap">
                                                                                {section.content}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                ));
                                                            })()}
                                                        </motion.div>
                                                    )}

                                                    {hasDetails && (
                                                        <div className="mt-3 flex justify-end">
                                                            <span className="text-[10px] font-black text-indigo-600 dark:text-indigo-400 hover:underline">
                                                                {isExpanded ? 'Show Less' : 'View Details & Structure'}
                                                            </span>
                                                        </div>
                                                    )}
                                                </motion.div>
                                            );
                                        })}
                                    </AnimatePresence>
                                )}
                            </div>
                        </div>

                    </div>
                </div>
            ) : (
                /* ── TAB 2: PROPOSALS (PREMIUM) ── */
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                    {/* Proposal Form & Status Container */}
                    <div className="xl:col-span-2 bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden flex flex-col">
                        <div className="p-6 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-800/50 shrink-0 flex justify-between items-center">
                            <div>
                                <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center">
                                    <Sparkles className="w-5 h-5 mr-2 text-indigo-500" /> Pitch a Custom Project
                                </h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                                    Submit details of your own custom startup or research idea.
                                </p>
                            </div>
                        </div>

                        <div className="p-6 flex-1 space-y-6">
                            {/* Read Only or Locked Display */}
                            {disableProposalEdits && activeProposal ? (
                                <div className="space-y-6">
                                    {/* Current proposal header */}
                                    <div className="p-6 bg-slate-50 dark:bg-slate-900/30 rounded-2xl border border-slate-200 dark:border-slate-700/60">
                                        <div className="flex justify-between items-start gap-4 flex-wrap mb-3">
                                            <div data-tour="student-pref-submission">
                                                <h4 className="text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-1">Active Submission</h4>
                                                <h2 className="text-xl font-extrabold text-slate-800 dark:text-slate-100 leading-tight">
                                                    {activeProposal.title}
                                                </h2>
                                            </div>
                                        </div>

                                        <p className="text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mt-6 mb-2">Description & Rationale</p>
                                        <div className="border-l-4 border-indigo-500 bg-indigo-50/20 dark:bg-indigo-950/10 p-4 rounded-r-xl text-slate-700 dark:text-slate-300 text-sm leading-relaxed font-medium">
                                            {activeProposal.aiRationale || activeProposal.description}
                                        </div>

                                        {activeProposal.proposalFile && (
                                            <div className="mt-5 p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl flex items-center justify-between gap-4">
                                                <div className="flex items-center gap-3 min-w-0">
                                                    <FileText className="w-5 h-5 text-indigo-500 shrink-0" />
                                                    <span className="text-xs font-bold text-slate-700 dark:text-slate-350 truncate">Proposal Document PDF</span>
                                                </div>
                                                <a
                                                    href={activeProposal.proposalFile}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:hover:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-lg text-xs font-bold transition-all shadow-sm active:scale-95"
                                                >
                                                    <ExternalLink className="w-3 h-3" /> View PDF
                                                </a>
                                            </div>
                                        )}
                                    </div>

                                    {/* Warnings and help comments */}
                                    <div className="p-4 bg-slate-50 dark:bg-slate-900/30 rounded-xl border border-slate-200/60 dark:border-slate-700/40 text-xs text-slate-500 dark:text-slate-400 flex items-start gap-2.5">
                                        <Lock className="w-4 h-4 shrink-0 text-slate-400 mt-0.5" />
                                        <span>
                                            This proposal is locked and currently under evaluation. Roster editing and preference ranking will remain frozen until reviews are published by coordinators.
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                /* Editable View (Only Leader) */
                                <>
                                    {!isTeamLeader ? (
                                        <div className="flex flex-col items-center justify-center p-10 bg-slate-50 dark:bg-slate-900/20 rounded-2xl border border-slate-200 dark:border-slate-700 text-center">
                                            <Lock className="w-10 h-10 text-slate-300 dark:text-slate-650 mb-3" />
                                            <h4 className="text-slate-800 dark:text-slate-200 font-bold mb-1">Restricted Workspace</h4>
                                            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm leading-relaxed">
                                                Only the Team Leader has permissions to compose and submit custom proposals. Ask your leader to complete this workspace.
                                            </p>
                                        </div>
                                    ) : (
                                        <div className="space-y-6">
                                            {/* Feedback banner if rejected/revision */}
                                            {isRejectedOrRevision && activeProposal?.feedback && (
                                                <div className="p-4 bg-orange-50 dark:bg-orange-950/20 border border-orange-200 dark:border-orange-900/50 rounded-xl flex items-start gap-3">
                                                    <AlertCircle className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
                                                    <div>
                                                        <h4 className="text-sm font-bold text-orange-850 dark:text-orange-355">Coordinator Action Required</h4>
                                                        <p className="text-xs text-orange-600 dark:text-orange-400 mt-1">{activeProposal.feedback}</p>
                                                    </div>
                                                </div>
                                            )}

                                            <div>
                                                <label className="block text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-2">Project Title</label>
                                                <input
                                                    type="text"
                                                    placeholder="e.g., Decentralized Identity Provider using ZK-Snarks"
                                                    value={title}
                                                    onChange={(e) => setTitle(e.target.value)}
                                                    disabled={disableProposalEdits}
                                                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm dark:text-slate-200 transition-all font-medium disabled:opacity-60 disabled:cursor-not-allowed"
                                                />
                                            </div>

                                            <div>
                                                <label className="block text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-2">Project Description</label>
                                                <textarea
                                                    rows="5"
                                                    placeholder="Describe the problem you are solving, target audience, technology stack, and major modules..."
                                                    value={description}
                                                    onChange={(e) => setDescription(e.target.value)}
                                                    disabled={disableProposalEdits}
                                                    className="w-full px-4 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm dark:text-slate-200 transition-all resize-none font-medium leading-relaxed disabled:opacity-60 disabled:cursor-not-allowed"
                                                ></textarea>
                                            </div>

                                            {/* PDF file attachment */}
                                            <div>
                                                <label className="block text-xs font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest mb-2">Proposal Document (PDF)</label>
                                                <input
                                                    type="file"
                                                    ref={fileInputRef}
                                                    accept="application/pdf"
                                                    onChange={e => setProposalFile(e.target.files?.[0] || null)}
                                                    disabled={disableProposalEdits}
                                                    className="hidden"
                                                />
                                                {proposalFile ? (
                                                    <div className="flex items-center gap-3.5 p-4 bg-indigo-50/50 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-800 rounded-xl">
                                                        <FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400 shrink-0" />
                                                        <div className="min-w-0 flex-1">
                                                            <p className="text-sm font-bold text-indigo-950 dark:text-indigo-200 truncate">{proposalFile.name}</p>
                                                            <p className="text-xs text-indigo-500/80">{(proposalFile.size / (1024 * 1024)).toFixed(2)} MB</p>
                                                        </div>
                                                        {!disableProposalEdits && (
                                                            <button
                                                                onClick={() => { setProposalFile(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}
                                                                className="w-8 h-8 rounded-lg flex items-center justify-center text-indigo-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-955/30 transition-colors"
                                                            >
                                                                <X className="w-4 h-4" />
                                                            </button>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div
                                                        onClick={() => { if (!disableProposalEdits) fileInputRef.current?.click(); }}
                                                        className={`group w-full flex flex-col items-center justify-center py-8 px-4 bg-slate-50 dark:bg-slate-900/30 border-2 border-dashed border-slate-200 dark:border-slate-700/80 hover:border-indigo-500 dark:hover:border-indigo-500 rounded-xl transition-all text-center gap-2.5 hover:shadow-sm ${disableProposalEdits ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
                                                    >
                                                        <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400 group-hover:text-indigo-500 group-hover:bg-indigo-50 dark:group-hover:bg-indigo-950/30 transition-all shrink-0">
                                                            <UploadCloud className="w-6 h-6" />
                                                        </div>
                                                        <div>
                                                            <p className="text-sm font-bold text-slate-700 dark:text-slate-300">Click to upload proposal PDF</p>
                                                            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Accepts PDF format only · Max size 10MB</p>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="flex flex-col items-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700/60">
                                                {isRejectedOrRevision && (
                                                    <p className="text-xs text-orange-655 dark:text-orange-400 font-bold flex items-center gap-1.5">
                                                        <Sparkles className="w-3.5 h-3.5 animate-spin" /> Re-submitting revision — deadline bypassed.
                                                    </p>
                                                )}
                                                {proposalDeadlinePassed && !isRejectedOrRevision && (
                                                    <p className="text-xs text-rose-500 font-bold flex items-center gap-1.5 mb-1 font-sans">
                                                        <AlertCircle className="w-4 h-4" /> Proposal submission deadline has passed {proposalDeadline?.deadline_date ? `(${formatDateUTC(proposalDeadline.deadline_date)})` : ''}.
                                                    </p>
                                                )}
                                                <button
                                                    onClick={submitProposal}
                                                    disabled={isSaving || !canSubmitProposal}
                                                    className="px-8 py-3 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white rounded-xl font-bold transition-all shadow-md active:scale-98 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 text-sm"
                                                >
                                                    {isSaving ? (
                                                        <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block"></span> {uploadStatus || 'Saving…'}</>
                                                    ) : 'Submit Proposal'}
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>

                    {/* Proposal Status Timeline & Comments */}
                    <div className="bg-slate-50 dark:bg-slate-900/30 rounded-3xl border border-slate-200 dark:border-slate-700/50 shadow-sm p-6 space-y-6 flex flex-col h-[700px] overflow-hidden">
                        <div className="border-b border-slate-200 dark:border-slate-700/60 pb-4 shrink-0">
                            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center">
                                <Calendar className="w-5 h-5 mr-2 text-indigo-500" /> Pitch Timeline
                            </h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">History of proposal submissions and coordinator actions.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                            {proposals.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
                                    <Info className="w-10 h-10 mb-3 opacity-50" />
                                    <p className="text-xs font-semibold text-slate-500 max-w-[180px]">No active pitches submitted yet.</p>
                                </div>
                            ) : (
                                [...proposals].reverse().map((p, _idx) => {
                                    const pStatus = (p.status || 'Pending').toLowerCase();
                                    return (
                                        <div key={p.id} className="bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700/60 rounded-2xl p-4 space-y-3 shadow-xs">
                                            <div className="flex justify-between items-start gap-2">
                                                <div>
                                                    <span className={`inline-flex px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider
                                                        ${(pStatus === 'approved' || pStatus === 'valid') ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-400' :
                                                            (pStatus === 'pending' || pStatus === 'submitted') ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-400' :
                                                                pStatus === 'rejected' ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-400' :
                                                                    'bg-orange-105 text-orange-800 dark:bg-orange-900/40 dark:text-orange-400'}`}>
                                                        {p.status}
                                                    </span>
                                                    <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 mt-1.5 truncate max-w-[180px]" title={p.title}>
                                                        {p.title}
                                                    </h4>
                                                </div>
                                                <span className="text-[10px] text-slate-400 font-mono">
                                                    {p.submittedDate || p.submitted_at?.split('T')[0] || ''}
                                                </span>
                                            </div>

                                            <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed">
                                                {p.aiRationale || p.description}
                                            </p>

                                            {p.feedback && (
                                                <div className="bg-slate-50 dark:bg-slate-900/40 p-2.5 rounded-xl border border-slate-100 dark:border-slate-700/50 flex items-start gap-2">
                                                    <MessageSquare className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                                                    <div className="text-[10px] text-slate-600 dark:text-slate-350 leading-normal">
                                                        <span className="font-bold block text-slate-500 mb-0.5">Coordinator Remarks</span>
                                                        {p.feedback}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    </div>
                </div>
            )}



            {/* Problem Statement Detailed Analysis Modal */}
            {selectedPsForAnalysis && (
                <PsArchitecturePlanModal
                    ps={selectedPsForAnalysis}
                    onClose={() => setSelectedPsForAnalysis(null)}
                />
            )}
        </motion.div>
    );
}
