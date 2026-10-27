import React, { useState, useMemo, useEffect } from 'react';
import { Calculator, DownloadCloud, Trophy, CheckCircle, TableProperties, BarChart3, TrendingUp, Send, FileSpreadsheet, FileText, FileDown, Filter, AlertTriangle, Users, Layers, RefreshCw, Loader2, AlertCircle, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { useSupabaseTableState } from '../hooks/useSupabaseTableState';
import { AuditLogger, getCurrentUser } from '../lib/auditLogger';
import { getAllEvaluations } from '../services/panelSync';
import { apiUpsertTable, getActiveSemesterIds } from '../lib/api';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { teamLabel } from '../lib/teamUtils';

/* ── Scoring Range Config ─────────────────────────────────────────── */
const SCORING_RANGES = [
    { grade: 'A+', label: 'Outstanding',  min: 85, max: 100, color: 'emerald', bg: 'bg-emerald-500', text: 'text-emerald-700 dark:text-emerald-400', chip: 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30' },
    { grade: 'A',  label: 'Excellent',    min: 70, max: 84,  color: 'indigo',  bg: 'bg-indigo-500',  text: 'text-indigo-700 dark:text-indigo-400',   chip: 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/30'  },
    { grade: 'B',  label: 'Good',         min: 50, max: 69,  color: 'amber',   bg: 'bg-amber-500',   text: 'text-amber-700 dark:text-amber-400',     chip: 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/30'    },
    { grade: 'C',  label: 'Needs Work',   min: 0,  max: 49,  color: 'rose',    bg: 'bg-rose-500',    text: 'text-rose-700 dark:text-rose-400',       chip: 'bg-rose-50 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/30'      },
];

function getGradeInfo(score) {
    if (score == null) return null;
    return SCORING_RANGES.find(r => score >= r.min && score <= r.max) || SCORING_RANGES[SCORING_RANGES.length - 1];
}

const prepareDbPayload = (rows) => {
    return rows.map(r => ({
        team: r.team,
        title: r.title || null,
        domain: r.domain || null,
        branch: r.branch || null,
        proposalMarks: r.proposalMarks ?? null,
        midMarks: r.midMarks ?? null,
        finalMarks: r.finalMarks ?? null,
        totalScore: r.totalScore ?? null,
        mentor: r.mentor || null,
        semester_id: r.semester_id || null,
    }));
};

const teamIdFromRow = (row) => {
    const teamStr = row?.team;
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

const isEvalForTeam = (ev, teamRow) => {
    if (!ev || !teamRow) return false;
    const evTeamId = String(ev.team_id || ev.team || '').trim().toLowerCase();
    const targetTeamId = String(teamRow.team || teamRow.id || '').trim().toLowerCase();
    if (!evTeamId || !targetTeamId) return false;

    if (evTeamId === targetTeamId) return true;

    // Fallback: match by numeric team number
    const evNum = teamIdFromRow({ team: evTeamId });
    const targetNum = teamIdFromRow(teamRow);
    return evNum !== null && targetNum !== null && evNum === targetNum;
};

/** Merge panel evaluation scores into results rows (match by numeric team id). */
function applyEvalsToResults(currentResults, evals, activeSemesterId) {
    const scoreMap = {};
    const metaMap = {};
    for (const ev of evals) {
        const scaled = Math.round((ev.final_score_normalized / 100) * 30);
        if (scoreMap[ev.team_id] === undefined) {
            scoreMap[ev.team_id] = { sum: scaled, count: 1 };
        } else {
            scoreMap[ev.team_id].sum += scaled;
            scoreMap[ev.team_id].count += 1;
        }
        metaMap[ev.team_id] = {
            team_name: ev.team_name,
            project_title: ev.project_title,
        };
    }

    const byTeamId = new Map();
    for (const r of currentResults) {
        const tid = teamIdFromRow(r);
        if (tid) byTeamId.set(tid, r);
    }

    const updated = currentResults.map((r) => {
        const tid = teamIdFromRow(r);
        const entry = tid ? scoreMap[tid] : undefined;
        if (!entry) return r;
        const mid = Math.round(entry.sum / entry.count);
        return { ...r, midMarks: mid, totalScore: null };
    });

    for (const [tidStr, entry] of Object.entries(scoreMap)) {
        const tid = Number(tidStr);
        if (byTeamId.has(tid)) continue;
        const meta = metaMap[tid] || {};
        updated.push({
            team: meta.team_name || `TEAM-${tid}`,
            title: meta.project_title || null,
            midMarks: Math.round(entry.sum / entry.count),
            totalScore: null,
            semester_id: activeSemesterId
        });
    }

    return updated;
}

// Module scope because both the publish and unpublish handlers call it. It
// previously lived inside the publish handler, so unpublish threw a
// ReferenceError that its own catch swallowed — the student portal was left
// believing results were still published.
const getStudentApiUrl = () => {
    if (import.meta.env.VITE_STUDENT_API_URL) return import.meta.env.VITE_STUDENT_API_URL;
    return 'http://localhost:8002';
};

export default function Results() {
    const navigate = useNavigate();
    const { semesterMap, filterRows, filters, semesters, semesterOptions } = useGlobalFilters();
    const [activeSemesterId, setActiveSemesterId] = useState(null);   // primary (first) active sem id
    const [activeSemesterIds, setActiveSemesterIds] = useState([]);   // all active sem ids
    const [checkingSemester, setCheckingSemester] = useState(true);

    const activeSemConfig = useMemo(() => {
        if (!activeSemesterId || !semesters) return null;
        return semesters.find(s => s.id === activeSemesterId) || null;
    }, [activeSemesterId, semesters]);

    const { data: results, setData: setResults } = useSupabaseTableState('results', [], { orderBy: 'team' });
    const { data: teams } = useSupabaseTableState('teams_validation', []);
    const { data: cycles } = useSupabaseTableState('presentation_cycles', []);
    const { data: evals } = useSupabaseTableState('presentation_evaluations', []);
    const { data: rubrics } = useSupabaseTableState('presentation_rubrics', []);
    const [systemState, setSystemState] = useState('Pending'); // Pending -> Draft -> Published
    const [exporting, setExporting] = useState(false);
    
    // Filters
    const [searchTerm, setSearchTerm] = useState('');
    const [domainFilter, setDomainFilter] = useState('');
    const [branchFilter, setBranchFilter] = useState('');
    const [mentorFilter, setMentorFilter] = useState('');
    const [gradeFilter, setGradeFilter] = useState('');

    const [evalLoading, setEvalLoading] = useState(false);
    const [evalError, setEvalError] = useState(null);
    const [lastSynced, setLastSynced] = useState(null);
    useEffect(() => {
        let isMounted = true;
        async function checkSem() {
            try {
                const ids = await getActiveSemesterIds();
                if (isMounted) {
                    setActiveSemesterIds(ids);
                    setActiveSemesterId(ids.length > 0 ? ids[0] : 'NONE');
                }
            } catch (err) {
                console.error(err);
                if (isMounted) {
                    setActiveSemesterId('NONE');
                    setActiveSemesterIds([]);
                }
            } finally {
                if (isMounted) {
                    setCheckingSemester(false);
                }
            }
        }
        checkSem();
        return () => { isMounted = false; };
    }, []);

    useEffect(() => {
        if (checkingSemester) return;
        if (filters?.semesterId && filters.semesterId !== 'all') {
            setActiveSemesterId(filters.semesterId);
            setActiveSemesterIds([filters.semesterId]);
        } else if (!activeSemesterId || activeSemesterId === 'NONE') {
            const defaultSem = semesters.find(s => s.is_active)?.id || semesters[0]?.id || 'NONE';
            setActiveSemesterId(defaultSem);
            setActiveSemesterIds([defaultSem]);
        }
    }, [filters?.semesterId, checkingSemester, semesters]);

    /* ── Filter results by active semesters ──────────────────────────── */
    const activeResults = useMemo(() => {
        if (!activeSemesterId || activeSemesterId === 'NONE') return [];
        
        // Filter results by active semester
        const semResults = results.filter(r => r.semester_id === activeSemesterId);
        
        // Create a map of existing results by team name/ID
        const resultsMap = new Map();
        semResults.forEach(r => {
            const normalized = String(r.team || '').trim().toLowerCase();
            resultsMap.set(normalized, r);
            const numId = teamIdFromRow(r);
            if (numId) {
                resultsMap.set(`num-${numId}`, r);
            }
        });
        
        const semTeams = teams.filter(t => t.semester_id === activeSemesterId);
        const filteredTeams = filterRows(semTeams);
        // Map teams to results structure
        return filteredTeams.map(t => {
            const teamIdStr = String(t.id || '').trim().toLowerCase();
            const numId = teamIdFromRow(t);
            
            // Try to find existing result row
            let existing = resultsMap.get(teamIdStr);
            if (!existing && numId) {
                existing = resultsMap.get(`num-${numId}`);
            }
            
            // Extract branch and mentor details from team members if not present
            let branchVal = t.branch;
            if (!branchVal && t.members) {
                let parsedMembers = [];
                if (Array.isArray(t.members)) parsedMembers = t.members;
                else {
                    try { parsedMembers = JSON.parse(t.members) || []; } catch { /* non-fatal: fall through to the default below */ }
                }
                if (parsedMembers.length > 0) {
                    branchVal = parsedMembers[0].branch || parsedMembers[0].branchVal;
                }
            }
            
            return {
                team: t.id,
                title: t.title || t.project_title || (existing ? existing.title : ''),
                domain: t.domain || (existing ? existing.domain : ''),
                branch: branchVal || (existing ? existing.branch : ''),
                mentor: t.mentor || (existing ? existing.mentor : ''),
                proposalMarks: existing ? existing.proposalMarks : null,
                midMarks: existing ? existing.midMarks : null,
                finalMarks: existing ? existing.finalMarks : null,
                totalScore: existing ? existing.totalScore : null,
                grade: existing ? existing.grade : null,
                semester_id: t.semester_id || activeSemesterId
            };
        });
    }, [results, teams, activeSemesterIds, activeSemesterId, filterRows]);

    const syncPanelScores = async () => {
        if (activeSemesterId === 'NONE') return;
        setEvalLoading(true);
        setEvalError(null);
        try {
            const evals = await getAllEvaluations();
            if (!evals || evals.length === 0) {
                setEvalLoading(false);
                return;
            }

            const updated = applyEvalsToResults(activeResults, evals, activeSemesterId);

            setResults(updated);
            const dbPayload = prepareDbPayload(updated);
            await apiUpsertTable('results', dbPayload, 'team');
            setLastSynced(new Date().toLocaleTimeString());
            AuditLogger.logUserAction(getCurrentUser(), 'Synced panel evaluation scores from Panel Portal');
        } catch (e) {
            setEvalError(e.message);
        } finally {
            setEvalLoading(false);
        }
    };

    // Auto-sync panel scores shortly after page load
    useEffect(() => {
        if (checkingSemester || activeSemesterId === 'NONE') return;
        const timer = setTimeout(() => syncPanelScores(), 2000);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [checkingSemester, activeSemesterId]);

    // Keep systemState synced with database published state
    useEffect(() => {
        if (activeSemConfig) {
            if (activeSemConfig.results_published) {
                setSystemState('Published');
            } else {
                const hasComputed = activeResults.some(r => r.totalScore !== null);
                setSystemState(hasComputed ? 'Draft' : 'Pending');
            }
        }
    }, [activeSemConfig, activeResults]);

    /* ── Derived filter options from live data ─────────────────────── */
    const uniqueDomains = useMemo(() => [...new Set(activeResults.map(r => r.domain).filter(Boolean))], [activeResults]);
    const uniqueBranches = useMemo(() => [...new Set(['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)', ...activeResults.map(r => r.branch).filter(Boolean)])], [activeResults]);
    const uniqueMentors = useMemo(() => [...new Set(activeResults.map(r => r.mentor).filter(Boolean))], [activeResults]);

    /* ── Evaluation count per team ────────────────────────────────── */
    const getEvalCount = (r) => {
        const teamEvals = evals.filter(e => isEvalForTeam(e, r));
        const evaluatedCycleIds = new Set(teamEvals.map(e => e.cycle_id).filter(Boolean));
        return evaluatedCycleIds.size;
    };

    const targetEvalCount = Math.max(cycles.filter(c=>c.semester_id===activeSemesterId).length, 1);
    const allHave3Evals = activeResults.length > 0 && activeResults.every(r => getEvalCount(r) >= targetEvalCount);
    const teamsWithIncomplete = activeResults.filter(r => getEvalCount(r) < targetEvalCount);

    /* ── Calculate & Publish ──────────────────────────────────────── */
    const handleCalculate = () => {
        setSystemState('Draft');
        setTimeout(async () => {
            const updated = activeResults.map(r => {
                let total = null;
                let computed = 0;
                let hasAnyEval = false;
                const semCycles = cycles.filter(c => c.semester_id === activeSemesterId);
                semCycles.forEach(cycle => {
                    const teamEvalsForCycle = evals.filter(e => isEvalForTeam(e, r) && e.cycle_id === cycle.id);
                    if (teamEvalsForCycle.length > 0) {
                        const avgNormalized = teamEvalsForCycle.reduce((sum, e) => sum + e.total_score, 0) / teamEvalsForCycle.length;
                        computed += (avgNormalized / 100) * cycle.weightage;
                        hasAnyEval = true;
                    }
                });
                if (hasAnyEval) {
                    total = Math.round(computed);
                }
                let grade = null;
                if (total != null) {
                    if (total >= 85) grade = 'A+';
                    else if (total >= 70) grade = 'A';
                    else if (total >= 50) grade = 'B';
                    else grade = 'C';
                }
                return { ...r, totalScore: total, grade };
            });
            setResults(updated);
            try {
                const dbPayload = prepareDbPayload(updated);
                await apiUpsertTable('results', dbPayload, 'team');
                AuditLogger.logUserAction(getCurrentUser(), 'Computed metrics for all teams in Results and saved to Supabase');
            } catch (e) {
                console.error("Failed to save computed results:", e);
            }
        }, 600);
    };

    const handlePublish = async () => {
        // Allow publishing even if some scores are pending — show a warning
        if (!allHave3Evals) {
            const proceed = window.confirm(
                `Warning: ${teamsWithIncomplete.length} team(s) still have incomplete evaluations.\n\nPublishing now will show partial results. Are you sure you want to publish?`
            );
            if (!proceed) return;
        }

        // 1. Try to persist results_published flag to Supabase semester_config
        try {
            await api.updateSemesterConfig(activeSemesterId, { results_published: true });
        } catch (e) {
            // Column may not exist yet — show migration SQL to user
            console.warn('Could not update results_published in semester_config:', e);
            alert(
                `⚠️ Action required: Run this SQL in your Supabase SQL Editor, then click Publish again:\n\n` +
                `ALTER TABLE public.semester_config\n` +
                `ADD COLUMN IF NOT EXISTS results_published boolean default false;\n\n` +
                `(Dashboard → SQL Editor → New Query → paste → Run)`
            );
            return;
        }

        setSystemState('Published');
        AuditLogger.logAdminAction(getCurrentUser(), 'Published final results for all teams');

        // 2. Notify student portal backend (non-blocking, non-fatal)
        try {
            const STUDENT_API = getStudentApiUrl();
            await fetch(`${STUDENT_API}/api/student/admin/publish-results`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ published: true })
            });
        } catch (e) {
            console.warn('Could not notify student backend:', e);
        }

        alert('✅ Results published! Students can now view their results.');
    };

    const handleUnpublish = async () => {
        const confirm = window.confirm('Are you sure you want to unpublish results? Students will no longer be able to see their scores.');
        if (!confirm) return;
        try {
            await api.updateSemesterConfig(activeSemesterId, { results_published: false });
        } catch (e) {
            alert('Failed to unpublish: ' + e.message);
            return;
        }
        // Notify student backend
        try {
            const STUDENT_API = getStudentApiUrl();
            await fetch(`${STUDENT_API}/api/student/admin/publish-results`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ published: false })
            });
        } catch (e) {
            console.warn('Could not notify student backend:', e);
        }
        setSystemState('Draft');
        AuditLogger.logAdminAction(getCurrentUser(), 'Unpublished results — students can no longer view scores');
        alert('Results unpublished. Students can no longer view their scores.');
    };

    const handleExport = () => {
        setExporting(true);
        AuditLogger.logUserAction(getCurrentUser(), 'Exported consolidated Excel report');
        setTimeout(() => setExporting(false), 2000);
    };

    /* ── Enhanced PDF Export ──────────────────────────────────────── */
    const handleExportPDF = () => {
        const doc = new jsPDF({ orientation: 'landscape' });
        const now = new Date();

        // Header
        doc.setFontSize(18);
        doc.setFont('helvetica', 'bold');
        doc.text('Project Management System', 14, 15);
        doc.setFontSize(12);
        doc.setFont('helvetica', 'normal');
        doc.text('Comprehensive Evaluation Results Report', 14, 22);
        doc.setFontSize(9);
        doc.setTextColor(120);
        doc.text(`Generated: ${now.toLocaleDateString()} at ${now.toLocaleTimeString()}`, 14, 28);
        doc.text(`Total Teams: ${activeResults.length} | Evaluated: ${activeResults.filter(r => r.totalScore).length}`, 14, 33);
        doc.setTextColor(0);

        // Scoring Ranges Legend
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.text('Scoring Ranges:', 200, 15);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8);
        SCORING_RANGES.forEach((range, i) => {
            doc.text(`${range.grade} (${range.label}): ${range.min}-${range.max}`, 200, 21 + i * 5);
        });

        // Table
        const semCycles = cycles.filter(c => c.semester_id === activeSemesterId);
        const dynamicHeaders = semCycles.map(c => `${c.title} (${c.weightage})`);
        const tableColumn = ['Team', 'Title', 'Domain', 'Branch', 'Mentor', ...dynamicHeaders, 'Total (100)', 'Grade', 'Evals'];
        const tableRows = [];

        const dataToExport = displayResults.length > 0 ? displayResults : activeResults;
        dataToExport.forEach(r => {
            const info = getGradeInfo(r.totalScore);
            const baseRow = [
                r.team || '--',
                r.title || '--',
                r.domain || '--',
                r.branch || '--',
                r.mentor || '--',
            ];
            const dynamicCols = [];
            semCycles.forEach(c => {
                const teamEvals = evals.filter(e => isEvalForTeam(e, r) && e.cycle_id === c.id);
                if (teamEvals.length > 0) {
                    const avgNormalized = teamEvals.reduce((s, e) => s + e.total_score, 0) / teamEvals.length;
                    const cycleRubrics = rubrics.filter(rub => rub.cycle_id === c.id);
                    const maxScore = cycleRubrics.reduce((sum, rub) => sum + (rub.max_marks || 0), 0) || 100;
                    const rawScore = Math.round((avgNormalized / 100) * maxScore);
                    dynamicCols.push(rawScore);
                } else {
                    dynamicCols.push('--');
                }
            });
            
            tableRows.push([
                ...baseRow,
                ...dynamicCols,
                r.totalScore ?? '--',
                info ? info.grade : '--',
                `${getEvalCount(r)}/${targetEvalCount}`
            ]);
        });

        autoTable(doc, {
            head: [tableColumn],
            body: tableRows,
            startY: 40,
            theme: 'grid',
            headStyles: { fillColor: [79, 70, 229], fontSize: 8, fontStyle: 'bold' },
            bodyStyles: { fontSize: 7.5 },
            alternateRowStyles: { fillColor: [245, 245, 255] },
            columnStyles: {
                0: { fontStyle: 'bold', cellWidth: 22 },
                1: { cellWidth: 35 },
                8: { fontStyle: 'bold', halign: 'center' },
                9: { fontStyle: 'bold', halign: 'center' },
                10: { halign: 'center' },
            },
        });

        // Summary footer
        const finalY = doc.lastAutoTable.finalY + 10;
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        const evaluated = activeResults.filter(r => r.totalScore);
        const gradeBreakdown = SCORING_RANGES.map(range => {
            const count = evaluated.filter(r => r.totalScore >= range.min && r.totalScore <= range.max).length;
            return `${range.grade}: ${count}`;
        }).join('  |  ');
        doc.text(`Grade Breakdown:  ${gradeBreakdown}`, 14, finalY);

        if (branchFilter || domainFilter || mentorFilter) {
            doc.setFont('helvetica', 'normal');
            doc.text(`Filters Applied: ${[branchFilter && `Branch: ${branchFilter}`, domainFilter && `Domain: ${domainFilter}`, mentorFilter && `Mentor: ${mentorFilter}`].filter(Boolean).join(', ')}`, 14, finalY + 6);
        }

        doc.save(`PROCKSI_Results_Report_${now.toISOString().slice(0,10)}.pdf`);
        AuditLogger.logUserAction(getCurrentUser(), 'Downloaded Comprehensive Evaluation Results PDF Report');
    };

    /* ── Single Team PDF Export ────────────────────────────────────── */
    const handleExportTeamPDF = (r) => {
        const doc = new jsPDF();
        const now = new Date();
        const info = getGradeInfo(r.totalScore);
        const evalCount = getEvalCount(r);

        // Header
        doc.setFontSize(18);
        doc.setFont('helvetica', 'bold');
        doc.text('Project Management System', 14, 15);
        doc.setFontSize(13);
        doc.text('Individual Team Evaluation Report', 14, 23);
        doc.setFontSize(9);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(120);
        doc.text(`Generated: ${now.toLocaleDateString()} at ${now.toLocaleTimeString()}`, 14, 30);
        doc.setTextColor(0);

        // Divider
        doc.setDrawColor(200);
        doc.line(14, 34, 196, 34);

        // Team details
        doc.setFontSize(14);
        doc.setFont('helvetica', 'bold');
        doc.text(`${r.team || 'Unknown Team'}`, 14, 44);
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.text(`Project: ${r.title || 'N/A'}`, 14, 52);

        const details = [
            ['Domain', r.domain || 'N/A'],
            ['Branch', r.branch || 'N/A'],
            ['Mentor', r.mentor || 'N/A'],
            ['Evaluations Completed', `${evalCount} / ${targetEvalCount}`],
        ];
        let yPos = 62;
        details.forEach(([label, value]) => {
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(9);
            doc.text(`${label}:`, 14, yPos);
            doc.setFont('helvetica', 'normal');
            doc.text(value, 55, yPos);
            yPos += 7;
        });

        const semCycles = cycles.filter(c => c.semester_id === activeSemesterId);
        const tableBodyRows = semCycles.map(c => {
            const teamEvals = evals.filter(e => isEvalForTeam(e, r) && e.cycle_id === c.id);
            if (teamEvals.length > 0) {
                const avgNormalized = teamEvals.reduce((s, e) => s + e.total_score, 0) / teamEvals.length;
                const score = Math.round((avgNormalized / 100) * c.weightage);
                return [c.title, String(c.weightage), String(score), 'Completed'];
            }
            return [c.title, String(c.weightage), '--', 'Pending'];
        });

        // Scores table
        autoTable(doc, {
            startY: yPos + 5,
            head: [['Evaluation', 'Max Marks', 'Obtained', 'Status']],
            body: tableBodyRows,
            theme: 'grid',
            headStyles: { fillColor: [79, 70, 229], fontSize: 10, fontStyle: 'bold' },
            bodyStyles: { fontSize: 10 },
            columnStyles: {
                2: { fontStyle: 'bold', halign: 'center' },
                3: { halign: 'center' },
            },
        });

        // Total & Grade
        const tableEndY = doc.lastAutoTable.finalY + 10;
        doc.setFontSize(12);
        doc.setFont('helvetica', 'bold');
        doc.text(`Total Score: ${r.totalScore ?? 'N/A'} / 100`, 14, tableEndY);
        doc.text(`Final Grade: ${info ? `${info.grade} (${info.label})` : 'N/A'}`, 14, tableEndY + 8);

        // Scoring ranges reference
        doc.setFontSize(9);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(120);
        const rangeY = tableEndY + 22;
        doc.text('Scoring Ranges:', 14, rangeY);
        SCORING_RANGES.forEach((range, i) => {
            doc.text(`${range.grade} (${range.label}): ${range.min}–${range.max}`, 14, rangeY + 6 + i * 5);
        });

        doc.setTextColor(0);
        doc.save(`PROCKSI_Report_${r.team || 'team'}_${now.toISOString().slice(0,10)}.pdf`);
        AuditLogger.logUserAction(getCurrentUser(), `Downloaded individual evaluation report for team ${r.team || 'Unknown Team'}`);
    };

    /* ── Grade counts ─────────────────────────────────────────────── */
    const evaluatedTotal = activeResults.filter(r => r.totalScore).length;
    const gradeCounts = SCORING_RANGES.map(range => ({
        ...range,
        count: activeResults.filter(r => r.totalScore && r.totalScore >= range.min && r.totalScore <= range.max).length,
    }));
    
    /* ── Filtered results ─────────────────────────────────────────── */
    const displayResults = activeResults.filter(r => {
        const matchSearch = searchTerm ? (
            String(r.team || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
            String(r.title || '').toLowerCase().includes(searchTerm.toLowerCase())
        ) : true;
        const matchDomain = domainFilter ? r.domain === domainFilter : true;
        const matchBranch = branchFilter ? (() => {
            const rb = String(r.branch || '').toLowerCase();
            const bf = String(branchFilter).toLowerCase();
            return rb === bf || rb.includes(bf) || bf.includes(rb);
        })() : true;
        const matchMentor = mentorFilter ? r.mentor === mentorFilter : true;
        const matchGrade = gradeFilter ? (() => {
            const info = getGradeInfo(r.totalScore);
            return info && info.grade === gradeFilter;
        })() : true;
        return matchSearch && matchDomain && matchBranch && matchMentor && matchGrade;
    });

    if (checkingSemester) {
        return (
            <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            </div>
        );
    }

    if (activeSemesterId === 'NONE') {
        return (
            <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)] flex items-center justify-center">
                <motion.div 
                    initial={{ opacity: 0, scale: 0.95 }} 
                    animate={{ opacity: 1, scale: 1 }} 
                    className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-8 rounded-3xl shadow-xl border border-slate-200/50 dark:border-slate-700/50 max-w-lg w-full text-center space-y-6"
                >
                    <div className="mx-auto w-16 h-16 bg-amber-50 dark:bg-amber-500/10 rounded-2xl flex items-center justify-center text-amber-500">
                        <AlertTriangle className="w-8 h-8" />
                    </div>
                    <div className="space-y-2">
                        <h2 className="text-2xl font-black text-slate-800 dark:text-white tracking-tight">No Active Semester</h2>
                        <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">
                            Evaluation results and rubrics are linked to active semester data. 
                            Please configure and activate a semester to continue.
                        </p>
                    </div>
                    <button 
                        onClick={() => navigate('/admin/semester-settings')}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-black uppercase tracking-widest text-xs rounded-xl shadow-lg shadow-indigo-500/20 active:scale-95 transition-all"
                    >
                        Go to Semester Settings
                    </button>
                </motion.div>
            </div>
        );
    }
    const activeFilterCount = [domainFilter, branchFilter, mentorFilter, gradeFilter].filter(Boolean).length;

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header Title Space */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 pb-6 border-b border-slate-200/50 dark:border-slate-700/50">
                <div>
                    <h1 className="text-3xl font-black text-slate-800 dark:text-white mb-2 tracking-tight">Rubric & Results</h1>
                    <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Aggregate and compute deterministic final scores derived from modular configurations.</p>
                    {lastSynced && (
                        <p className="text-xs font-bold text-emerald-600 dark:text-emerald-400 mt-1 flex items-center">
                            <CheckCircle className="w-3 h-3 mr-1 text-emerald-500" /> Panel scores synced at {lastSynced}
                        </p>
                    )}
                    {evalError && (
                        <p className="text-xs font-bold text-red-600 dark:text-red-400 mt-1 flex items-center">
                            <AlertCircle className="w-3 h-3 mr-1 text-red-500" /> Sync error: {evalError}
                        </p>
                    )}
                </div>
                <div className="flex w-full sm:w-auto space-x-3 flex-wrap gap-y-2 items-center">
                    {semesters && semesters.length > 0 && (
                        <div className="flex items-center gap-2 bg-white dark:bg-slate-800 px-4 py-2.5 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm">
                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">Term:</span>
                            <select
                                value={activeSemesterId || ''}
                                onChange={(e) => {
                                    const selectedId = e.target.value;
                                    setActiveSemesterId(selectedId);
                                    setActiveSemesterIds([selectedId]);
                                }}
                                className="bg-transparent text-xs font-bold text-slate-700 dark:text-white border-0 p-0 focus:ring-0 outline-none cursor-pointer"
                            >
                                <option value="NONE">-- Select Semester --</option>
                                {semesterOptions.map(opt => (
                                    <option key={opt.id} value={opt.id}>
                                        {opt.label}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}
                    <button 
                        onClick={syncPanelScores} 
                        disabled={evalLoading}
                        className="flex-1 sm:flex-none justify-center px-4 py-3 bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-600 dark:text-slate-200 text-slate-700 rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-sm flex items-center disabled:opacity-50"
                    >
                        {evalLoading ? (
                            <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Syncing...</>
                        ) : (
                            <><RefreshCw className="w-4 h-4 mr-2 text-emerald-500" /> Sync Panel Scores</>
                        )}
                    </button>
                    <button onClick={handleCalculate} disabled={systemState !== 'Pending' || activeResults.length === 0} className="flex-1 sm:flex-none justify-center px-6 py-3 bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 disabled:opacity-50 dark:text-slate-900 text-white rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-xl shadow-slate-900/20 flex items-center">
                        {systemState !== 'Pending' ? <CheckCircle className="w-4 h-4 mr-2 text-emerald-500" /> : <Calculator className="w-4 h-4 mr-2" />} 
                        {systemState !== 'Pending' ? 'Computed Metrics' : 'Process Rubrics'}
                    </button>
                    {systemState === 'Draft' && (
                        <div className="flex flex-col items-center">
                            <button onClick={handlePublish} className="flex-1 sm:flex-none justify-center px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs uppercase tracking-widest font-black transition-all shadow-lg shadow-indigo-500/30 flex items-center active:scale-95">
                                <Send className="w-4 h-4 mr-2" /> Publish Final Results
                            </button>
                            {!allHave3Evals && (
                                <span className="text-[10px] text-amber-600 dark:text-amber-400 mt-1 font-bold flex items-center">
                                    <AlertTriangle className="w-3 h-3 mr-1" />
                                    {teamsWithIncomplete.length} team{teamsWithIncomplete.length !== 1 ? 's' : ''} incomplete — will warn before publish
                                </span>
                            )}
                        </div>
                    )}
                    {systemState === 'Published' && (
                        <div className="flex items-center gap-2">
                            <div className="flex items-center gap-2 px-4 py-3 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30 rounded-xl text-xs font-black uppercase tracking-widest">
                                <CheckCircle className="w-4 h-4" /> Results Published
                            </div>
                            <button
                                onClick={handleUnpublish}
                                className="px-4 py-3 bg-white hover:bg-red-50 dark:bg-slate-800 dark:hover:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/30 rounded-xl text-xs font-black uppercase tracking-widest transition-all flex items-center gap-2 active:scale-95"
                                title="Hide results from students"
                            >
                                <Send className="w-4 h-4 rotate-180" /> Unpublish
                            </button>
                        </div>
                    )}
                </div>
            </motion.div>

            {/* Scoring Ranges Reference Card */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-5">
                <div className="flex items-center space-x-3 mb-4">
                    <div className="p-2 bg-violet-50 dark:bg-violet-500/10 rounded-lg text-violet-500"><Layers className="w-5 h-5" /></div>
                    <h3 className="font-black text-slate-800 dark:text-white text-sm">Scoring Ranges & Grade Bands</h3>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {SCORING_RANGES.map(range => (
                        <div key={range.grade} className={`flex items-center justify-between p-3 rounded-2xl border ${range.chip} transition-all hover:shadow-md`}>
                            <div className="flex items-center space-x-3">
                                <div className={`w-3 h-8 rounded-full ${range.bg}`}></div>
                                <div>
                                    <div className={`text-sm font-black ${range.text}`}>{range.grade}</div>
                                    <div className="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">{range.label}</div>
                                </div>
                            </div>
                            <div className="text-right">
                                <div className="text-xs font-black text-slate-600 dark:text-slate-300">{range.min}–{range.max}</div>
                                <div className="text-[10px] font-bold text-slate-400">out of 100</div>
                            </div>
                        </div>
                    ))}
                </div>
            </motion.div>

            {/* Stats Panel (visible after calculation) */}
            <AnimatePresence>
                {systemState !== 'Pending' && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                        {/* Grade Distribution */}
                        <div className="lg:col-span-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6 flex flex-col justify-center">
                            <div className="flex items-center space-x-3 mb-4">
                                <div className="p-2 bg-indigo-50 dark:bg-indigo-500/10 rounded-lg text-indigo-500"><BarChart3 className="w-5 h-5" /></div>
                                <h3 className="font-black text-slate-800 dark:text-white">Grade Distribution</h3>
                            </div>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center text-xs font-bold text-slate-500 uppercase tracking-widest">
                                    <span>{evaluatedTotal} Processed</span>
                                    <span>{results.length - evaluatedTotal} Pending</span>
                                </div>
                                {evaluatedTotal > 0 && (
                                    <div className="h-6 w-full flex rounded-xl overflow-hidden shadow-inner bg-slate-100 dark:bg-slate-900">
                                        {gradeCounts.map(gc => (
                                            <div key={gc.grade} className={`${gc.bg} hover:brightness-110 transition-all border-l border-white/20 first:border-l-0 group relative`} style={{width: `${(gc.count / evaluatedTotal) * 100}%`}}>
                                                <div className="absolute inset-0 flex items-center justify-center text-[10px] text-white font-black opacity-0 group-hover:opacity-100">{gc.grade}</div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                <div className="grid grid-cols-4 gap-2 text-center text-[10px] font-black uppercase tracking-widest">
                                    {gradeCounts.map(gc => (
                                        <div key={gc.grade} className={gc.text}>{gc.grade} ({gc.count})</div>
                                    ))}
                                </div>
                            </div>
                        </div>
                        
                        {/* Leaderboard */}
                        <div className="lg:col-span-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6">
                            <div className="flex items-center space-x-3 mb-4">
                                <div className="p-2 bg-amber-50 dark:bg-amber-500/10 rounded-lg text-amber-500"><Trophy className="w-5 h-5" /></div>
                                <h3 className="font-black text-slate-800 dark:text-white">Top Performers</h3>
                            </div>
                            <div className="space-y-3">
                                {[...activeResults].sort((a, b) => (b.totalScore || 0) - (a.totalScore || 0)).slice(0, 3).map((team, idx) => {
                                    const info = getGradeInfo(team.totalScore);
                                    return (
                                        <div key={team.team || idx} className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-900/50 rounded-2xl border border-slate-100 dark:border-slate-700/50 group hover:border-amber-300 dark:hover:border-amber-500/50 transition-colors">
                                            <div className="flex items-center space-x-3">
                                                <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-black ${idx === 0 ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}`}>
                                                    #{idx + 1}
                                                </div>
                                                <div>
                                                    <div className="font-black text-sm text-slate-800 dark:text-slate-100">{teamLabel(team.team, team, semesterMap)}</div>
                                                    <div className="text-[10px] text-slate-400 font-bold truncate max-w-[120px]">{team.title}</div>
                                                </div>
                                            </div>
                                            <div className="flex items-center space-x-2">
                                                {info && <span className={`text-[10px] font-black px-2 py-0.5 rounded border ${info.chip} ${info.text}`}>{info.grade}</span>}
                                                <span className="font-black text-lg text-slate-800 dark:text-white">{team.totalScore ?? '--'}</span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Evaluation Completion Status */}
                        <div className="lg:col-span-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 p-6">
                            <div className="flex items-center space-x-3 mb-4">
                                <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-lg text-blue-500"><Users className="w-5 h-5" /></div>
                                <h3 className="font-black text-slate-800 dark:text-white">Evaluation Status</h3>
                            </div>
                            <div className="space-y-3">
                                {[
                                    { label: `All ${targetEvalCount} Complete`, count: activeResults.filter(r => getEvalCount(r) >= targetEvalCount).length, color: 'emerald' },
                                    { label: 'Partially Done', count: activeResults.filter(r => { const c = getEvalCount(r); return c > 0 && c < targetEvalCount; }).length, color: 'amber' },
                                    { label: 'No Evaluations', count: activeResults.filter(r => getEvalCount(r) === 0).length, color: 'rose' },
                                ].map(item => (
                                    <div key={item.label} className="flex items-center justify-between">
                                        <div className="flex items-center space-x-2">
                                            <div className={`w-2 h-2 rounded-full bg-${item.color}-500`}></div>
                                            <span className="text-xs font-bold text-slate-600 dark:text-slate-400">{item.label}</span>
                                        </div>
                                        <span className="text-sm font-black text-slate-800 dark:text-white">{item.count}</span>
                                    </div>
                                ))}
                            </div>
                            <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700/50">
                                <div className="flex justify-between items-center text-xs font-bold text-slate-500 mb-2 uppercase tracking-widest">
                                    <span>Overall Progress</span>
                                    <span>{activeResults.length > 0 ? Math.round((activeResults.filter(r => getEvalCount(r) >= targetEvalCount).length / activeResults.length) * 100) : 0}%</span>
                                </div>
                                <div className="h-3 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden shadow-inner">
                                    <div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all duration-700" 
                                        style={{ width: `${activeResults.length > 0 ? (activeResults.filter(r => getEvalCount(r) >= targetEvalCount).length / activeResults.length) * 100 : 0}%` }}></div>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Data Table */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden flex flex-col relative z-20">
                
                {/* Filter Bar */}
                <div className="p-4 border-b border-slate-100 dark:border-slate-700/50 bg-slate-50/50 dark:bg-slate-900/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div className="flex items-center space-x-3">
                        <div className="p-2.5 bg-indigo-50 dark:bg-indigo-500/10 rounded-xl text-indigo-500"><TableProperties className="w-5 h-5" /></div>
                        <div>
                            <h2 className="text-xl font-black text-slate-800 dark:text-white">Cohort Evaluation Sheet</h2>
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{displayResults.length} of {activeResults.length} teams shown</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                        <div className="relative group max-w-xs mr-2">
                            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                            <input
                                type="text"
                                placeholder="Search team or title..."
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                className="pl-8 pr-4 py-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-semibold focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow w-44 focus:w-56"
                            />
                        </div>
                        <span className="text-slate-500 dark:text-slate-400 font-bold text-sm flex items-center">
                            <Filter className="w-4 h-4 mr-1" />
                            {activeFilterCount > 0 && <span className="w-5 h-5 bg-indigo-500 text-white text-[10px] font-black rounded-full flex items-center justify-center ml-1">{activeFilterCount}</span>}
                        </span>
                        <select value={branchFilter} onChange={e => setBranchFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Branches</option>
                            {uniqueBranches.map(b => <option key={b} value={b}>{b}</option>)}
                        </select>
                        <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Domains</option>
                            {uniqueDomains.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                        <select value={mentorFilter} onChange={e => setMentorFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Mentors</option>
                            {uniqueMentors.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                        <select value={gradeFilter} onChange={e => setGradeFilter(e.target.value)} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-300 rounded-xl px-3 py-1.5 outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm">
                            <option value="">All Grades</option>
                            {SCORING_RANGES.map(r => <option key={r.grade} value={r.grade}>{r.grade} ({r.label})</option>)}
                        </select>
                        {(activeFilterCount > 0 || searchTerm) && (
                            <button onClick={() => { setSearchTerm(''); setBranchFilter(''); setDomainFilter(''); setMentorFilter(''); setGradeFilter(''); }} className="text-[10px] font-black text-red-500 hover:text-red-600 uppercase tracking-widest px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
                                Clear
                            </button>
                        )}
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead className="bg-white/40 dark:bg-slate-800/40 border-b border-slate-200 dark:border-slate-700 backdrop-blur-md sticky top-0 z-10">
                            <tr>
                                <th className="p-5 pl-6 text-[10px] font-black underline decoration-2 decoration-indigo-500/30 text-slate-500 dark:text-slate-400 uppercase tracking-widest">Team Identifier</th>
                                <th className="p-5 text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest border-l border-slate-100 dark:border-slate-700/50">Mentor</th>
                                {cycles.filter(c => c.semester_id === activeSemesterId).map(c => {
                                    const cycleRubrics = rubrics.filter(rub => rub.cycle_id === c.id);
                                    const maxScore = cycleRubrics.reduce((sum, rub) => sum + (rub.max_marks || 0), 0) || 100;
                                    return (
                                        <th key={c.id} className="p-5 text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest text-center border-l border-slate-100 dark:border-slate-700/50">
                                            {c.title} ({c.weightage}%)<br/><span className="text-slate-400 dark:text-slate-500">Max: {maxScore}</span>
                                        </th>
                                    );
                                })}
                                <th className="p-5 text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest text-center border-l border-slate-100 dark:border-slate-700/50">Evals</th>
                                <th className="p-5 text-xs font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-widest text-center border-l-2 border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/30">Total</th>
                                <th className="p-5 text-xs font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-widest text-center border-l border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/30">Grade</th>
                                <th className="p-5 pr-6 text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest text-center border-l border-slate-100 dark:border-slate-700/50">Report</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {displayResults.length > 0 ? displayResults.map((r, idx) => {
                                const gradeInfo = getGradeInfo(r.totalScore);
                                const evalCount = getEvalCount(r);
                                return (
                                <tr key={r.team || idx} className="hover:bg-slate-50/80 dark:hover:bg-slate-700/30 transition-colors group">
                                    <td className="p-5 pl-6 whitespace-nowrap">
                                        <div className="text-sm font-black text-slate-800 dark:text-slate-200 flex items-center whitespace-nowrap">
                                            {teamLabel(r.team, r, semesterMap)} {r.totalScore >= 90 && <Trophy className="w-4 h-4 ml-2 text-amber-500 drop-shadow-sm" />}
                                        </div>
                                        <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400 mt-1">{r.title}</div>
                                    </td>
                                    <td className="p-5 border-l border-slate-100 dark:border-slate-700/50">
                                        <span className="text-xs font-bold text-slate-600 dark:text-slate-400">{r.mentor || '--'}</span>
                                    </td>
                                    {cycles.filter(c => c.semester_id === activeSemesterId).map(c => {
                                        const teamEvals = evals.filter(e => isEvalForTeam(e, r) && e.cycle_id === c.id);
                                        let score = '--';
                                        if (teamEvals.length > 0) {
                                            const avgNormalized = teamEvals.reduce((s, e) => s + e.total_score, 0) / teamEvals.length;
                                            const cycleRubrics = rubrics.filter(rub => rub.cycle_id === c.id);
                                            const maxScore = cycleRubrics.reduce((sum, rub) => sum + (rub.max_marks || 0), 0) || 100;
                                            score = Math.round((avgNormalized / 100) * maxScore);
                                        }
                                        return (
                                            <td key={c.id} className="p-5 text-center text-sm font-black text-slate-600 dark:text-slate-300 border-l border-slate-100 dark:border-slate-700/50">
                                                {score}
                                            </td>
                                        );
                                    })}
                                    <td className="p-5 text-center border-l border-slate-100 dark:border-slate-700/50">
                                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-xl text-xs font-black ${
                                            evalCount >= targetEvalCount ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-500/30' :
                                            evalCount >= 1 ? 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30' :
                                            'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500 border border-slate-200 dark:border-slate-700'
                                        }`}>{evalCount}/{targetEvalCount}</span>
                                    </td>
                                    <td className="p-5 text-center border-l-2 border-slate-200 dark:border-slate-700 bg-slate-50/20 dark:bg-slate-900/10">
                                        <AnimatePresence mode="wait">
                                            {r.totalScore ? (
                                                <motion.span 
                                                    key="calculated"
                                                    initial={{ opacity: 0, scale: 0.5, rotate: -20 }} 
                                                    animate={{ opacity: 1, scale: 1, rotate: 0 }} 
                                                    transition={{ type: "spring", stiffness: 200, damping: 10, delay: idx * 0.05 }}
                                                    className="inline-flex items-center justify-center w-10 h-10 rounded-2xl font-black text-lg border-b-2 bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-400 dark:border-indigo-500/30">
                                                    {r.totalScore}
                                                </motion.span>
                                            ) : (
                                                <motion.span key="empty" className="inline-flex items-center justify-center w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-600 text-xs font-black font-mono border border-slate-200 dark:border-slate-700">
                                                    --
                                                </motion.span>
                                            )}
                                        </AnimatePresence>
                                    </td>
                                    <td className="p-5 text-center border-l border-slate-200 dark:border-slate-700 bg-slate-50/20 dark:bg-slate-900/10 pr-6">
                                        {gradeInfo ? (
                                            <span className={`inline-flex items-center justify-center px-4 py-1.5 rounded-xl font-black text-sm uppercase tracking-widest border ${gradeInfo.chip} ${gradeInfo.text}`}>
                                                {gradeInfo.grade}
                                            </span>
                                        ) : (
                                            <span className="text-slate-400 font-black">--</span>
                                        )}
                                    </td>
                                    <td className="p-5 text-center border-l border-slate-100 dark:border-slate-700/50 pr-6">
                                        <button onClick={() => handleExportTeamPDF(r)} title={`Download report for ${r.team}`} className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-slate-50 hover:bg-indigo-50 dark:bg-slate-800 dark:hover:bg-indigo-500/20 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 border border-slate-200 dark:border-slate-700 hover:border-indigo-200 dark:hover:border-indigo-500/30 transition-all active:scale-95 shadow-sm">
                                            <FileDown className="w-4 h-4" />
                                        </button>
                                    </td>
                                </tr>
                            )}) : (
                                <tr>
                                    <td colSpan="9" className="p-12 text-center">
                                        <div className="text-sm font-bold text-slate-400 dark:text-slate-500">
                                            {activeResults.length === 0 ? 'No results data available. Data will appear when teams are evaluated.' : 'No results match the selected filters.'}
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </motion.div>

            {/* Generate Formal Reports Block */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="grid grid-cols-1 md:grid-cols-3 gap-6">
                 <button onClick={handleExport} disabled={exporting || activeResults.length === 0} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl p-6 border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between group hover:shadow-lg hover:border-emerald-300 dark:hover:border-emerald-500/30 transition-all text-left disabled:opacity-50 disabled:hover:shadow-none">
                    <div className="flex items-center">
                        <div className="p-3 bg-emerald-50 dark:bg-emerald-500/10 rounded-2xl text-emerald-500 group-hover:scale-110 transition-transform mr-4"><FileSpreadsheet className="w-6 h-6" /></div>
                        <div>
                            <h4 className="font-black text-slate-800 dark:text-slate-200">Consolidated Excel</h4>
                            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-widest">Full Cohort Data</p>
                        </div>
                    </div>
                    <DownloadCloud className="w-5 h-5 text-slate-400 group-hover:text-emerald-500 opacity-50 group-hover:opacity-100 transition-all" />
                 </button>

                 <button onClick={handleExportPDF} disabled={activeResults.length === 0} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl p-6 border border-slate-200/50 dark:border-slate-700/50 flex items-center justify-between group hover:shadow-lg hover:border-indigo-300 dark:hover:border-indigo-500/30 transition-all text-left disabled:opacity-50 disabled:hover:shadow-none">
                    <div className="flex items-center">
                        <div className="p-3 bg-indigo-50 dark:bg-indigo-500/10 rounded-2xl text-indigo-500 group-hover:scale-110 transition-transform mr-4"><FileDown className="w-6 h-6" /></div>
                        <div>
                            <h4 className="font-black text-slate-800 dark:text-slate-200">Download PDF</h4>
                            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-widest">Complete Report with Team Details</p>
                        </div>
                    </div>
                    <DownloadCloud className="w-5 h-5 text-slate-400 group-hover:text-indigo-500 opacity-50 group-hover:opacity-100 transition-all" />
                 </button>

                 <div className={`bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl p-6 border flex items-center justify-between ${allHave3Evals ? 'border-emerald-300 dark:border-emerald-500/30' : 'border-slate-200/50 dark:border-slate-700/50'}`}>
                    <div className="flex items-center">
                        <div className={`p-3 rounded-2xl mr-4 ${allHave3Evals ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500' : 'bg-slate-100 dark:bg-slate-700 text-slate-400'}`}>
                            <CheckCircle className="w-6 h-6" />
                        </div>
                        <div>
                            <h4 className={`font-black ${allHave3Evals ? 'text-emerald-700 dark:text-emerald-400' : 'text-slate-500 dark:text-slate-400'}`}>
                                {allHave3Evals ? 'Ready to Publish' : 'Awaiting Evaluations'}
                            </h4>
                            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-widest">
                                {activeResults.filter(r => getEvalCount(r) >= targetEvalCount).length}/{activeResults.length} teams complete
                            </p>
                        </div>
                    </div>
                    {allHave3Evals ? (
                        <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-200 dark:border-emerald-500/30">All Clear</span>
                    ) : (
                        <span className="text-[10px] font-black uppercase tracking-widest text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 px-3 py-1 rounded-full border border-amber-200 dark:border-amber-500/30">{teamsWithIncomplete.length} Pending</span>
                    )}
                 </div>
            </motion.div>
        </div>
    );
}
