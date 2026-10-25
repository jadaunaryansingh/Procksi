import React, { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from "recharts";
import {
  GitCommit, TrendingUp, ChevronDown, ExternalLink, Loader2,
  RefreshCw, Code, Award, AlertOctagon, AlertTriangle, BrainCircuit,
  GraduationCap, Shield, GitBranch, Cpu, Zap, CheckCircle2,
  XCircle, Eye, FileText, Flame, Activity, Users,
} from "lucide-react";
import { useProfile, fetchWithAuth } from "../hooks/useStudentData";

/* ── helpers ─────────────────────────────────────────────────── */
const Tooltip2 = ({ active, payload, label }) => {
  if (active && payload?.length)
    return (
      <div className="bg-slate-800 p-3 rounded-lg border border-slate-700 text-sm text-white font-bold shadow-xl">
        {label}: {payload[0].value} commits
      </div>
    );
  return null;
};

const ScoreBar = ({ value = 0 }) => {
  const color = value >= 75 ? "bg-emerald-500" : value >= 45 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden mt-2">
      <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
    </div>
  );
};

const ScoreCircle = ({ value = 0, size = "md" }) => {
  const cls = value >= 75 ? "text-emerald-500 border-emerald-400" : value >= 45 ? "text-amber-500 border-amber-400" : "text-rose-500 border-rose-400";
  const dim = size === "lg" ? "w-28 h-28 text-4xl" : "w-16 h-16 text-2xl";
  return (
    <div className={`rounded-full border-4 flex flex-col items-center justify-center ${cls} ${dim} bg-white dark:bg-slate-800`}>
      <span className="font-black">{Math.round(value)}</span>
      {size === "lg" && <span className="text-[10px] opacity-60 font-bold">/100</span>}
    </div>
  );
};

const Chip = ({ children, color = "slate" }) => {
  const map = {
    slate:   "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300",
    indigo:  "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-300",
    emerald: "bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300",
    rose:    "bg-rose-50 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300",
    amber:   "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300",
  };
  return <span className={`inline-block px-3 py-1 rounded text-[11px] font-bold ${map[color] || map.slate}`}>{children}</span>;
};

const Card = ({ children, className = "" }) => (
  <div className={`bg-white/50 dark:bg-slate-800/50 backdrop-blur-md rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm ${className}`}>
    {children}
  </div>
);

const SectionHead = ({ icon: Icon, label }) => (
  <h3 className="font-bold text-slate-900 dark:text-slate-100 flex items-center gap-3 text-base mb-4">
    <Icon size={16} className="text-emerald-500" /> {label}
  </h3>
);

const SevBadge = ({ sev }) => {
  const map = {
    critical:     "bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300",
    high:         "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300",
    medium:       "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300",
    low:          "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300",
    info:         "bg-slate-100 dark:bg-slate-700 text-slate-500",
    implemented:  "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300",
    partial:      "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300",
    missing:      "bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300",
  };
  const key = (sev || "info").toLowerCase();
  return <span className={`px-3 py-1 rounded text-[10px] font-black uppercase ${map[key] || map.info}`}>{sev || "info"}</span>;
};

/* ═══════════════════════════════════════════════════════════════ */
const GithubReportView = () => {
  const { data: profile, loading: profileLoading } = useProfile();
  const selectedTeamId = profile?.team?.id;
  const selectedTeam = profile?.team;

  const [githubData, setGithubData]     = useState(null);
  const [dataLoading, setDataLoading]   = useState(true);
  const [triggering, setTriggering]     = useState(false);
  const [triggerMsg, setTriggerMsg]     = useState("");
  const [activeTab, setActiveTab]       = useState("overview");

  const [demoRepoUrl, setDemoRepoUrl] = useState('');
  const [isDemoAdded, setIsDemoAdded] = useState(false);

  useEffect(() => {
    // Check if we are meant to print automatically
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('print') === 'true' && githubData && !dataLoading) {
      setTimeout(() => {
        window.print();
        // Remove the query param so it doesn't print repeatedly on refresh
        window.history.replaceState({}, document.title, window.location.pathname);
      }, 1000);
    }
  }, [githubData, dataLoading]);

  const fetchGithub = async (silent = false) => {
    if (!selectedTeamId) {
      if (!silent) Promise.resolve().then(() => setDataLoading(false));
      return;
    }
    
    // Do not fetch or mock if no repo is added yet
    if (!selectedTeam?.github?.repository_url && !isDemoAdded) {
      if (!silent) Promise.resolve().then(() => setDataLoading(false));
      return;
    }

    try {
      const data = await fetchWithAuth(`/api/teams/${selectedTeamId}/github`);
      const payload = data?.data !== undefined ? data.data : data;
      
      if (!payload || !payload.analysisResults) {
        setGithubData(null);
      } else {
        setGithubData(payload);
      }
    } catch {
      setGithubData(null);
    }
    finally { if (!silent) setDataLoading(false); }
  };

  useEffect(() => {
    if (!profileLoading) {
      Promise.resolve().then(() => fetchGithub());
      const interval = setInterval(() => {
        fetchGithub(true);
      }, 30000);
      return () => clearInterval(interval);
    }
  }, [selectedTeamId, profileLoading, isDemoAdded]);

  const handleRefresh = async () => {
    if (!selectedTeamId || triggering) return;
    setTriggering(true);
    setTriggerMsg("");
    try {
      const data = await fetchWithAuth(`/api/teams/${selectedTeamId}/github/analyze`, { method: 'POST' });
      setTriggerMsg(data?.message || "Done");
      await fetchGithub();
    } catch (e) {
      setTriggerMsg(e.message || "Error");
    } finally { setTriggering(false); }
  };

  /* ── data extraction — wired to full agent report structure ── */
  const repoName     = githubData?.repositoryName || "";
  const status       = githubData?.analysisStatus || "pending";
  const isRunning    = ["queued","running"].includes(status);
  const contributors = githubData?.contributors || [];
  const commitChart  = githubData?.weeklyActivity || [];

  const ar = githubData?.analysisResults || {};
  const rr = ar.raw_report || {};

  // Scores (raw_report.analysis)
  const analysis   = rr.analysis || {};
  const totalScore = analysis.totalScore ?? ar.scores?.quality ?? 0;
  const scores9 = [
    { label: "Quality",        value: analysis.qualityScore        ?? ar.scores?.quality        ?? 0 },
    { label: "Security",       value: analysis.securityScore       ?? ar.scores?.security       ?? 0 },
    { label: "Originality",    value: analysis.originalityScore    ?? ar.scores?.originality    ?? 0 },
    { label: "Architecture",   value: analysis.architectureScore   ?? ar.scores?.architecture   ?? 0 },
    { label: "Documentation",  value: analysis.documentationScore  ?? ar.scores?.documentation  ?? 0 },
    { label: "Implementation", value: analysis.implementationScore ?? 0 },
    { label: "Engineering",    value: analysis.engineeringScore    ?? 0 },
    { label: "Effort",         value: analysis.effortScore         ?? 0 },
  ];

  // Commits (raw_report.commits)
  const commitsBlock    = rr.commits || {};
  const totalCommits    = commitsBlock.total ?? githubData?.commitCount ?? 0;
  const lastWeekCommits = commitsBlock.lastWeek ?? 0;
  const contribDist     = commitsBlock.contributionDistribution || [];

  const weeklyChart = (() => {
    if (commitChart.length > 0) return commitChart;
    const tl = commitsBlock.timeline || [];
    if (tl.length > 0) return tl.map(t => ({ name: t.date || t.week || "", commits: t.commits || 0 }));
    return [];
  })();

  // Code metrics (raw_report.codeMetrics)
  const cm = rr.codeMetrics || {};
  const languages = (() => {
    const lwp = cm.languagesWithPct;
    if (lwp && typeof lwp === "object" && !Array.isArray(lwp))
      return Object.entries(lwp).map(([name, pct]) => ({ name, percentage: pct }));
    if (Array.isArray(lwp)) return lwp;
    if (Array.isArray(cm.languages)) {
      return cm.languages.map(n => {
        if (n && typeof n === "object") {
          return {
            name: n.name || n.language || "",
            percentage: n.percentage ?? n.pct ?? 0
          };
        }
        return { name: String(n), percentage: 0 };
      });
    }
    return [];
  })();
  const techStack = cm.techStack || cm.frameworks || ar.tech_stack || [];

  // Security (raw_report.security)
  const sec           = rr.security || {};
  const secIssues     = [...(sec.issues || []), ...(sec.leaks || []), ...(sec.hardcodedValues || [])];
  const bestPractices = sec.bestPractices || [];
  const secRecommends = sec.recommendations || [];

  // AI analysis (raw_report.aiAnalysis)
  const ai                    = rr.aiAnalysis || {};
  const strengths             = ai.strengths || [];
  const improvements          = ai.improvements || [];
  const prod                  = rr.productAnalysis || {};
  const features              = ai.features || [];
  const featureAnalysis       = ai.featureAnalysis || [];
  const suggestedFeatures     = ai.suggestedFeatures || [];
  const overallRecommendation = ai.overallRecommendation || "";

  // Commit quality (raw_report.commitQuality)
  const cq                 = rr.commitQuality || {};
  const exampleFakeCommits = cq.exampleFakeCommits || [];

  // Branch tracking (raw_report.branchTracking)
  const bt      = rr.branchTracking || {};
  const branches = bt.branchDetails || bt.branches || [];

  // Maturity (raw_report.maturity)
  const mat = rr.maturity || {};

  // Health / risk
  const healthStatus = rr.healthStatus || "";
  const riskFlags    = rr.riskFlags || [];

  // Marks deduction (raw_report.marksDeduction)
  const md = rr.marksDeduction || {};

  // Student grades (raw_report.individualStudentScores mapped to selectedTeam.members)
  const studentScores = (() => {
    const rawScores = rr.individualStudentScores || [];
    const teamMembers = selectedTeam?.members || [];
    if (teamMembers.length === 0) return rawScores;

    return teamMembers.map(member => {
      const roll = String(member.roll || member.id || "").trim().toLowerCase();
      const name = String(member.name || "").trim().toLowerCase();

      // Find matching score object from rawScores
      let match = rawScores.find(s => {
        const sId = String(s.id || "").trim().toLowerCase();
        const sName = String(s.name || "").trim().toLowerCase();
        const sGithub = String(s.github || "").trim().toLowerCase();

        // Match by roll number / id
        if (roll && sId && roll === sId) return true;
        // Match by exact email or handle
        if (sGithub && roll.includes(sGithub)) return true;
        // Match by name similarity or match by GitHub handle substrings
        if (name && sName && (name.includes(sName) || sName.includes(name))) return true;
        
        // Fallback matching substring for GitHub username (e.g. jadaunaryansingh has aryansingh)
        const cleanName = name.replace(/\s+/g, "");
        const cleanSName = sName.replace(/\s+/g, "");
        if (cleanName && cleanSName && (cleanName.includes(cleanSName) || cleanSName.includes(cleanName))) return true;
        
        return false;
      });

      if (match) {
        return {
          ...match,
          id: member.roll || member.id,
          name: member.name, // Use the actual clean student name instead of raw github handle
        };
      }

      // If no match found (student did not commit / has 0 commits), return a clean default score object
      return {
        id: member.roll || member.id,
        name: member.name,
        commits: 0,
        contributionPercentage: 0,
        contributionScore: 0,
        effortScore: 0,
        qualityScore: 0,
        deductions: 0,
        finalScore: 0,
        linesAdded: 0,
        linesDeleted: 0,
        github: ""
      };
    });
  })();

  // Project metadata
  const projectType = rr.projectType || "";
  const projectName = rr.projectName || "";

  // Score insights (raw_report.scoreInsights)
  const scoreInsights = rr.scoreInsights || [];

  const tabs = [
    { id: "overview", label: "Overview",        Icon: Code },
    { id: "code",     label: "Code & Security", Icon: Shield },
    { id: "commits",  label: "Commits",         Icon: GitCommit },
    { id: "ai",       label: "AI Analysis",     Icon: BrainCircuit },
    { id: "grading",  label: "Student Grading", Icon: GraduationCap },
  ];

  if (!selectedTeam?.github?.repository_url && !isDemoAdded) {
    return (
      <div className="max-w-xl mx-auto mt-20">
        <Card className="p-8 text-center space-y-6">
          <div className="w-16 h-16 bg-emerald-500/10 rounded-2xl flex items-center justify-center mx-auto">
            <Code className="w-8 h-8 text-emerald-500" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 mb-2">Connect GitHub Repository</h2>
            <p className="text-slate-500">Please provide the link to your project's GitHub repository to view analytics and AI insights.</p>
          </div>
          <div className="space-y-4 pt-4">
            <input 
              type="text" 
              placeholder="https://github.com/username/repo" 
              className="w-full p-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-100 focus:outline-none focus:border-emerald-500 transition-colors"
              value={demoRepoUrl}
              onChange={(e) => setDemoRepoUrl(e.target.value)}
            />
            <button 
              onClick={() => {
                if (demoRepoUrl) setIsDemoAdded(true);
              }}
              className="w-full bg-emerald-500 hover:bg-emerald-600 text-white font-bold py-3 px-4 rounded-xl transition-all active:scale-95"
            >
              Analyze Repository
            </button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="print:hidden space-y-6">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-3">
            <BrainCircuit className="text-indigo-500 w-6 h-6" />
            GitHub Analytics Hub
          </h2>
          <p className="text-sm text-slate-400 mt-0.5">AI-powered repository analysis</p>
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          {/* Team label instead of selector */}
          <div className="flex items-center gap-3 bg-white/50 dark:bg-slate-800/50 backdrop-blur-md border border-slate-200 dark:border-slate-700/50 rounded-lg px-4 py-2 text-base font-bold text-slate-700 dark:text-slate-200 shadow-sm select-none">
            Team: {selectedTeam?.name || selectedTeam?.id || "N/A"}
          </div>
          {/* Repo link */}
          {repoName && (
            <a href={`https://${repoName}`} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-slate-400 hover:text-indigo-500 font-mono bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 truncate max-w-[180px]">
              <ExternalLink size={11} />
              {repoName.replace("github.com/", "")}
            </a>
          )}
          {/* Refresh */}
          <button onClick={handleRefresh} disabled={triggering || isRunning}
            className="flex items-center gap-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-lg px-4 py-2 text-base font-bold shadow-sm transition-all">
            {triggering || isRunning ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            {isRunning ? "Analyzing..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Banners */}
      {triggerMsg && (
        <div className="bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 rounded-xl p-4 text-base font-medium text-indigo-700 dark:text-indigo-300">
          {triggerMsg}
        </div>
      )}
      {isRunning && (
        <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-4 flex items-center gap-3 text-base font-medium text-amber-700 dark:text-amber-300">
          <Loader2 size={14} className="animate-spin shrink-0" />
          Analysis running - page will refresh automatically.
          {githubData?.progress !== undefined && githubData.progress > 0 && (
            <span className="ml-2 font-bold text-indigo-600 dark:text-indigo-400">
              ({githubData.progress}% {githubData.currentStage ? `- Stage ${githubData.currentStage}` : ""})
            </span>
          )}
        </div>
      )}

      {(status === "failed" || status === "dlq") && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-xl p-4 flex items-center gap-3 text-base font-medium text-rose-700 dark:text-rose-300">
          <AlertOctagon size={14} className="shrink-0" />
          Analysis failed: {githubData?.errorMessage || "An error occurred during repository analysis. Please check your repository URL or credentials."}
        </div>
      )}

      {dataLoading && (
        <div className="flex justify-center py-24">
          <Loader2 className="w-10 h-10 animate-spin text-indigo-500" />
        </div>
      )}

      {!dataLoading && !githubData && (
        <Card className="p-12 text-center text-slate-400">
          <AlertOctagon className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p className="font-bold text-base">No analysis data yet. Click Refresh to pull from the remote analyzer.</p>
        </Card>
      )}

      {!dataLoading && githubData && isRunning && (
        <Card className="p-10 text-center flex flex-col items-center justify-center min-h-[400px]">
          <div className="w-16 h-16 rounded-full bg-indigo-50 dark:bg-indigo-950/30 flex items-center justify-center mb-6 border-2 border-dashed border-indigo-500 animate-spin" style={{ animationDuration: '8s' }}>
            <BrainCircuit className="w-8 h-8 text-indigo-600 dark:text-indigo-400" />
          </div>
          <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">Repository Analysis in Progress</h3>
          <p className="text-slate-500 text-sm max-w-md mb-6 leading-relaxed">
            The AI agent is currently cloning the repository, auditing security best practices, and calculating code quality scores.
          </p>
          <div className="inline-flex items-center gap-3 px-3 py-1.5.5 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 text-[10px] font-black uppercase rounded-full tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-ping" />
            Status: {status}
          </div>
          <p className="text-slate-400 text-[10px] mt-8">This page will automatically refresh as soon as the results are ready.</p>
        </Card>
      )}

      {!dataLoading && githubData && !isRunning && (<>

        {/* Project meta strip */}
        {(projectName || projectType || status) && (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {projectName && <span className="font-semibold text-slate-700 dark:text-slate-200">{projectName}</span>}
            {projectType && <Chip color="indigo">{projectType}</Chip>}
            <Chip color={status === "completed" ? "emerald" : ["failed", "dlq"].includes(status) ? "rose" : status === "pending" ? "amber" : "slate"}>{status}</Chip>
          </div>
        )}

        {/* Tab bar */}
        <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-700/60 pb-2 overflow-x-auto">
          {tabs.map(({ id, label, Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-3 py-1.5.5 rounded-lg text-sm font-bold whitespace-nowrap transition-all ${activeTab === id ? "bg-indigo-600 text-white shadow" : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        {/* ══ TAB: OVERVIEW ══ */}
        {activeTab === "overview" && (
          <div className="space-y-5">
            {/* Hero */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Card className="p-6 flex flex-col items-center text-center">
                <ScoreCircle value={totalScore} size="lg" />
                <span className="text-sm font-black text-slate-400 uppercase tracking-wider mt-3">Overall Score</span>
                {projectType && <Chip color="indigo" className="mt-1">{projectType}</Chip>}
              </Card>
              <div className="sm:col-span-2 grid grid-cols-2 gap-4">
                <Card className="p-4">
                  <SectionHead icon={Activity} label="Health" />
                  <div className={`text-3xl font-black capitalize ${healthStatus === "healthy" ? "text-emerald-500" : healthStatus === "warning" ? "text-amber-500" : "text-rose-500"}`}>
                    {healthStatus || "N/A"}
                  </div>
                  <div className="mt-2 space-y-1">
                    {riskFlags.slice(0, 3).map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-sm text-slate-500">
                        <AlertTriangle size={10} className="text-amber-400 shrink-0" />
                        {f.replace(/_/g, " ")}
                      </div>
                    ))}
                  </div>
                </Card>
                <Card className="p-4">
                  <SectionHead icon={CheckCircle2} label="Maturity" />
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { label: "Tests",  val: mat.hasTests  },
                      { label: "CI/CD",  val: mat.hasCI    },
                      { label: "Docker", val: mat.hasDocker },
                      { label: "README", val: mat.hasReadme },
                    ].map(({ label, val }) => (
                      <div key={label} className="flex items-center gap-2 text-sm font-semibold text-slate-600 dark:text-slate-400">
                        {val ? <CheckCircle2 size={13} className="text-emerald-500" /> : <XCircle size={13} className="text-slate-300 dark:text-slate-600" />}
                        {label}
                      </div>
                    ))}
                    {mat.testFiles > 0 && <div className="col-span-2 text-[10px] text-slate-400">{mat.testFiles} test files</div>}
                  </div>
                </Card>
                <Card className="p-4">
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">Total Commits</span>
                  <span className="text-3xl font-black text-slate-800 dark:text-slate-100">{totalCommits}</span>
                </Card>
                <Card className="p-4">
                  <SectionHead icon={AlertTriangle} label="Marks Ded." />
                  {md.applied ? (
                    <>
                      <div className="text-2xl font-black text-rose-500">-{md.marksDeductedPercentage ?? 0}%</div>
                      <p className="text-[11px] text-slate-500">{md.reason || ""}</p>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-emerald-500 text-sm font-bold">
                      <CheckCircle2 size={14} /> No deductions
                    </div>
                  )}
                </Card>
              </div>
            </div>

            {/* 8-score grid */}
            <Card className="p-5">
              <SectionHead icon={Award} label="AI Score Breakdown (8 dimensions)" />
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {scores9.map(({ label, value }) => (
                  <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 text-center border border-slate-100 dark:border-slate-700/30">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                    <span className={`text-2xl font-black ${value >= 75 ? "text-emerald-500" : value >= 45 ? "text-amber-500" : "text-rose-500"}`}>
                      {Math.round(value)}
                    </span>
                    <ScoreBar value={Math.round(value)} />
                  </div>
                ))}
              </div>
            </Card>

            {/* Tech + Languages */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <Card className="p-5">
                <SectionHead icon={Cpu} label="Tech Stack" />
                {techStack.length > 0 ? (
                  <div className="flex flex-wrap gap-3">
                    {techStack.map((t, i) => (
                      <Chip key={i} color="indigo">{typeof t === "string" ? t : t.technology || t.name || t}</Chip>
                    ))}
                  </div>
                ) : <p className="text-sm text-slate-400">No tech stack data.</p>}
                {cm.architecturePattern && (
                  <p className="text-sm text-slate-400 mt-3">
                    <span className="font-bold text-slate-600 dark:text-slate-300">Architecture: </span>
                    {cm.architecturePattern}
                  </p>
                )}
              </Card>
              <Card className="p-5">
                <SectionHead icon={FileText} label="Language Breakdown" />
                {languages.length > 0 ? (
                  <div className="space-y-2">
                    {languages.slice(0, 6).map((l, i) => {
                      const name = l.name || l.language || l;
                      const pct  = l.percentage ?? 0;
                      return (
                        <div key={i}>
                          <div className="flex justify-between text-sm font-bold text-slate-600 dark:text-slate-300 mb-1">
                            <span>{name}</span>
                            <span>{typeof pct === "number" ? pct.toFixed(1) : pct}%</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : <p className="text-sm text-slate-400">No language data.</p>}
                {cm.totalLinesOfCode > 0 && (
                  <p className="text-sm text-slate-400 mt-3">
                    <span className="font-bold text-slate-600 dark:text-slate-300">Total LOC: </span>
                    {cm.totalLinesOfCode.toLocaleString()} across {cm.totalFiles} files
                  </p>
                )}
              </Card>
            </div>

            {/* Contributors */}
            {contributors.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={Users} label="Contributors" />
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {contributors.map((dev, i) => (
                    <div key={i} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30">
                      <div className="flex items-center gap-4 mb-3">
                        <div className="w-9 h-9 rounded-full bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center font-black text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-500/20">
                          {(dev.name || "?")[0].toUpperCase()}
                        </div>
                        <div>
                          <p className="font-bold text-base text-slate-800 dark:text-slate-100">{dev.name}</p>
                          <p className="text-[11px] text-slate-400">{dev.handle}</p>
                        </div>
                      </div>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between font-semibold text-slate-600 dark:text-slate-400">
                          <span>Commits</span><span className="font-black text-slate-800 dark:text-slate-200">{dev.commits}</span>
                        </div>
                        <div>
                          <div className="flex justify-between font-semibold text-slate-600 dark:text-slate-400 mb-1">
                            <span>Contribution</span><span className="font-black text-slate-800 dark:text-slate-200">{dev.contribution}%</span>
                          </div>
                          <div className="h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${dev.contribution}%` }} />
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Insights - Score Analysis & Improvement Guide */}
            {scoreInsights && scoreInsights.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={AlertOctagon} label="Insights - Score Analysis & Improvement Guide" />
                <div className="space-y-4">
                  {scoreInsights.map((insight, idx) => {
                    const scoreVal = insight.score ?? 0;
                    const name = insight.dimension || "Dimension";
                    const severity = insight.severity || "info";
                    const reasons = insight.likely_reasons || insight.reasons || [];
                    const steps = insight.improvement_steps || insight.steps || [];
                    return (
                      <div key={idx} className="border-l-4 border-rose-500 bg-rose-50/30 dark:bg-rose-900/5 p-4 rounded-r-xl">
                        <div className="flex items-center justify-between flex-wrap gap-3 mb-2">
                          <span className="font-bold text-slate-800 dark:text-slate-100 text-base">
                            {name} &mdash; <span className="text-rose-500">{scoreVal}/100</span> [{severity.toUpperCase()}]
                          </span>
                        </div>
                        {reasons.length > 0 && (
                          <div className="mb-2">
                            <span className="text-sm font-bold text-slate-500 dark:text-slate-400 block mb-1">Why this score is low:</span>
                            <ul className="list-disc list-inside text-sm text-rose-600/90 dark:text-rose-400 space-y-0.5 pl-1">
                              {reasons.map((r, i) => <li key={i}>{r}</li>)}
                            </ul>
                          </div>
                        )}
                        {steps.length > 0 && (
                          <div>
                            <span className="text-sm font-bold text-slate-500 dark:text-slate-400 block mb-1">How to improve:</span>
                            <ul className="text-sm text-emerald-600 dark:text-emerald-400 space-y-1 pl-1">
                              {steps.map((s, i) => (
                                <li key={i} className="flex items-start gap-1">
                                  <span className="font-bold text-emerald-500 shrink-0">+</span>
                                  <span>{s}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}
          </div>
        )}

        {/* ══ TAB: CODE & SECURITY ══ */}
        {activeTab === "code" && (
          <div className="space-y-5">
            {/* Security score strip */}
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: "Overall Security", value: sec.score ?? 0 },
                { label: "Secrets Score",    value: sec.secretsScore ?? 0 },
                { label: "Practices Score",  value: sec.practicesScore ?? 0 },
              ].map(({ label, value }) => (
                <Card key={label} className="p-4 text-center">
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-2">{label}</span>
                  <ScoreCircle value={Math.round(value)} />
                </Card>
              ))}
            </div>

            {/* Code metrics */}
            {cm.totalFiles > 0 && (
              <Card className="p-5">
                <SectionHead icon={FileText} label="Code Metrics" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                  {[
                    { label: "Total Files",   val: cm.totalFiles?.toLocaleString() },
                    { label: "Lines of Code", val: cm.totalLinesOfCode?.toLocaleString() },
                    { label: "Architecture",  val: cm.architecturePattern },
                    { label: "Languages",     val: languages.length },
                  ].map(({ label, val }) => (
                    <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30">
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                      <span className="text-base font-black text-slate-800 dark:text-slate-100 mt-1 block">{val || "?"}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Security findings (issues + leaks) */}
            <Card className="p-5">
              <SectionHead icon={Shield} label={`Security Findings (${secIssues.length})`} />
              {secIssues.length > 0 ? (
                <div className="space-y-3">
                  {secIssues.map((iss, i) => (
                    <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-4">
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                          {iss.title || iss.type || "Issue"}
                        </span>
                        <SevBadge sev={iss.severity} />
                      </div>
                      {iss.description && <p className="text-[11px] text-slate-500 mb-1">{iss.description}</p>}
                      {iss.snippet && (
                        <p className="text-[10px] text-slate-400 font-mono bg-slate-50 dark:bg-slate-900/40 px-3 py-1.5 rounded mt-1 truncate">{iss.snippet}</p>
                      )}
                      {(iss.file || iss.file_path || iss.path) && (
                        <code className="text-[10px] text-indigo-500 font-mono bg-indigo-50 dark:bg-indigo-900/20 px-2 py-1 rounded block mt-1">
                          {iss.file || iss.file_path || iss.path}{iss.line_number ? `:${iss.line_number}` : ""}
                        </code>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-3 text-emerald-500 text-base font-bold">
                  <CheckCircle2 size={16} /> No security issues found.
                </div>
              )}
            </Card>

            {/* Security recommendations */}
            {secRecommends.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={AlertTriangle} label="Security Recommendations" />
                <div className="space-y-3">
                  {secRecommends.map((rec, i) => (
                    <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-4">
                      <div className="flex items-start justify-between gap-3 mb-1">
                        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">{rec.title}</span>
                        <SevBadge sev={rec.severity} />
                      </div>
                      {rec.description && <p className="text-[11px] text-slate-500 mb-2">{rec.description}</p>}
                      {rec.action_items?.length > 0 && (
                        <ul className="space-y-1">
                          {rec.action_items.slice(0, 3).map((a, j) => (
                            <li key={j} className="text-[10px] text-slate-500 flex items-start gap-2">
                              <span className="text-indigo-400 mt-0.5 shrink-0">&#8250;</span> {a}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Best practices */}
            {bestPractices.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={Eye} label="Best Practices Audit" />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  {/* Clean checklist list (Column 1) */}
                  <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30 space-y-2">
                    <span className="text-sm font-black text-slate-400 uppercase tracking-wider block mb-2">Checklist Summary</span>
                    {bestPractices.map((bp, i) => {
                      const name = bp.practice_name || bp.title || bp.name || "Practice";
                      const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                      return (
                        <div key={i} className="flex items-center gap-3 text-sm font-bold">
                          {ok ? (
                            <span className="text-emerald-500 flex items-center gap-1 font-black"><CheckCircle2 size={13} /> OK</span>
                          ) : (
                            <span className="text-rose-500 flex items-center gap-1 font-black"><XCircle size={13} /> NO</span>
                          )}
                          <span className="text-slate-700 dark:text-slate-300">{name}</span>
                        </div>
                      );
                    })}
                  </div>
                  {/* Detailed descriptions (Columns 2 & 3) */}
                  <div className="md:col-span-2 space-y-3 max-h-[400px] overflow-y-auto pr-1">
                    {bestPractices.map((bp, i) => {
                      const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                      return (
                        <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-4 bg-white dark:bg-slate-800">
                          <div className="flex items-start justify-between gap-3 mb-1">
                            <div className="flex items-center gap-2 font-bold text-sm text-slate-800 dark:text-slate-200">
                              {ok ? <CheckCircle2 size={12} className="text-emerald-500" /> : <XCircle size={12} className="text-rose-500" />}
                              {bp.practice_name || bp.title || bp.name || "Practice"}
                            </div>
                            <SevBadge sev={ok ? "implemented" : bp.severity} />
                          </div>
                          {bp.recommendation && <p className="text-[11px] text-slate-500">{bp.recommendation}</p>}
                          {bp.files_found?.length > 0 && (
                            <p className="text-[10px] text-slate-400 mt-1 font-mono">
                              Found in: {bp.files_found.join(", ")}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </Card>
            )}
          </div>
        )}

        {/* ══ TAB: COMMITS ══ */}
        {activeTab === "commits" && (
          <div className="space-y-5">
            {/* Stat strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: "Total Commits",  value: totalCommits,                                       color: "text-slate-800 dark:text-slate-100" },
                { label: "Last 7 Days",    value: lastWeekCommits,                                    color: "text-indigo-600 dark:text-indigo-400" },
                { label: "Real Commits",   value: cq.realCommits  != null ? cq.realCommits  : "-",   color: "text-emerald-600" },
                { label: "Fake / Inflated",value: cq.fakeCommits  != null ? cq.fakeCommits  : "-",   color: "text-rose-500" },
              ].map(({ label, value, color }) => (
                <Card key={label} className="p-4 text-center">
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">{label}</span>
                  <span className={`text-3xl font-black ${color}`}>{value}</span>
                </Card>
              ))}
            </div>

            {/* Chart */}
            <Card className="p-5" style={{ height: 280 }}>
              <SectionHead icon={TrendingUp} label="Weekly Commit Activity" />
              <div style={{ height: 210 }}>
                {weeklyChart.length > 0 ? (
                  <ResponsiveContainer width="100%" height={210}>
                    <BarChart data={weeklyChart}>
                      <Tooltip content={<Tooltip2 />} cursor={{ fill: "rgba(99,102,241,0.05)" }} />
                      <XAxis dataKey="name" stroke="#94a3b8" tick={{ fill: "#64748b", fontSize: 10, fontWeight: "bold" }} axisLine={false} tickLine={false} dy={8} />
                      <Bar dataKey="commits" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex items-center justify-center h-full text-slate-400 text-base font-bold">No weekly timeline data.</div>
                )}
              </div>
            </Card>

            {/* Commit quality */}
            {Object.keys(cq).length > 0 && (
              <Card className="p-5">
                <SectionHead icon={Flame} label="Commit Quality Analysis" />
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-center mb-4">
                  {[
                    { label: "Health",          val: cq.healthStatus },
                    { label: "Real Commits",    val: cq.realCommits },
                    { label: "Fake Commits",    val: cq.fakeCommits },
                    { label: "Fake %",          val: cq.fakeCommitPercentage != null ? `${cq.fakeCommitPercentage}%` : null },
                    { label: "Inflation Ratio", val: cq.inflationRatio },
                    { label: "AI Tools Found",  val: cq.aiToolsDetectedCount },
                  ].filter(x => x.val != null).map(({ label, val }) => (
                    <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30">
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                      <span className="text-base font-black text-slate-800 dark:text-slate-100">{String(val)}</span>
                    </div>
                  ))}
                </div>
                {cq.aiToolsDetected?.length > 0 && (
                  <p className="text-sm text-slate-500 mb-2">
                    <span className="font-bold">AI tools detected: </span>{cq.aiToolsDetected.join(", ")}
                  </p>
                )}
                {Array.isArray(cq.detectedIssues) && cq.detectedIssues.length > 0 && (
                  <div className="space-y-1">
                    {cq.detectedIssues.slice(0, 5).map((iss, i) => (
                      <div key={i} className="text-sm text-slate-500 flex items-start gap-2">
                        <AlertTriangle size={10} className="text-amber-400 mt-0.5 shrink-0" />
                        {typeof iss === "string" ? iss : `${iss.type}: ${iss.count ?? ""}`}
                      </div>
                    ))}
                  </div>
                )}
                {/* Example Flagged Commits */}
                {exampleFakeCommits.length > 0 && (
                  <div className="mt-4 border-t border-slate-100 dark:border-slate-700/40 pt-4">
                    <span className="text-sm font-black text-slate-400 uppercase tracking-wider block mb-2">Example Flagged Commits</span>
                    <div className="space-y-2">
                      {exampleFakeCommits.map((item, idx) => (
                        <div key={idx} className="bg-rose-50/20 dark:bg-rose-900/5 border border-rose-100 dark:border-rose-900/20 rounded-xl p-4 text-sm">
                          <div className="flex justify-between items-center gap-3 mb-1 flex-wrap">
                            <span className="font-mono text-indigo-500 font-bold">{item.sha} &mdash; {item.message || "No message"}</span>
                            <Chip color="rose">Flagged</Chip>
                          </div>
                          {item.reason && <p className="text-[11px] text-rose-600 dark:text-rose-400 font-medium">Reason: {item.reason}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* Contribution distribution */}
            {contribDist.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={GitCommit} label="Contribution Distribution" />
                <div className="space-y-3">
                  {contribDist.map((c, i) => {
                    const name = c.contributorName || c.name || "Unknown";
                    const pct  = typeof c.percentage === "number" ? c.percentage : (c.commits / Math.max(1, totalCommits)) * 100;
                    return (
                      <div key={i}>
                        <div className="flex justify-between text-sm font-bold text-slate-600 dark:text-slate-300 mb-1">
                          <span>{name}</span>
                          <span>{c.commits} commits &middot; {pct.toFixed(1)}%</span>
                        </div>
                        <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${pct >= 20 ? "bg-indigo-500" : pct >= 5 ? "bg-amber-400" : "bg-rose-400"}`}
                            style={{ width: `${Math.min(pct, 100)}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* Branch tracking */}
            {branches.length > 0 && (
              <Card className="p-5">
                <SectionHead icon={GitBranch} label={`Branch Tracking (${bt.totalBranches ?? branches.length} branches)`} />
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 dark:border-slate-700 text-slate-400 font-black uppercase tracking-wider">
                        <th className="py-2">Branch</th>
                        <th className="py-2 text-right">Commits</th>
                        <th className="py-2 text-right">Primary Author</th>
                        <th className="py-2 text-right">Last Commit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {branches.map((b, i) => {
                        const bname = typeof b === "string" ? b : (b.name || b.branch || "");
                        const isMain = bname === bt.mainBranch;
                        return (
                          <tr key={i} className="border-b border-slate-50 dark:border-slate-700/30">
                            <td className="py-2 font-mono text-slate-700 dark:text-slate-300">
                              <div className="flex items-center gap-2">
                                <GitBranch size={11} className="text-indigo-400 shrink-0" />
                                {bname}
                                {isMain && <Chip color="emerald">main</Chip>}
                              </div>
                            </td>
                            <td className="py-2 text-right font-black text-slate-800 dark:text-slate-200">{b.totalCommits ?? "?"}</td>
                            <td className="py-2 text-right text-slate-500">{b.primaryAuthor || "?"}</td>
                            <td className="py-2 text-right text-slate-400 text-[11px]">
                              {b.lastCommitDate ? new Date(b.lastCommitDate).toLocaleDateString() : "?"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            {/* Member summary */}
            {contributors.length > 0 && (
              <Card className="p-5 overflow-x-auto">
                <SectionHead icon={Users} label="Member Commit Summary" />
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-700 text-slate-400 font-black uppercase tracking-wider">
                      <th className="py-2">Name</th>
                      <th className="py-2 text-right">Commits</th>
                      <th className="py-2 text-right">Contribution</th>
                      <th className="py-2 text-right">Last Commit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contributors.map((dev, i) => (
                      <tr key={i} className="border-b border-slate-50 dark:border-slate-700/30 text-slate-600 dark:text-slate-300">
                        <td className="py-2 font-bold text-slate-800 dark:text-slate-200">{dev.name}</td>
                        <td className="py-2 text-right font-black">{dev.commits ?? 0}</td>
                        <td className="py-2 text-right">{dev.contribution ?? 0}%</td>
                        <td className="py-2 text-right text-slate-400">{dev.lastCommit || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        )}

        {/* ══ TAB: AI ANALYSIS ══ */}
        {activeTab === "ai" && (
          <div className="space-y-5">
            {Object.keys(ai).length === 0 ? (
              <Card className="p-10 text-center text-slate-400">
                <BrainCircuit className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-bold text-base">No AI analysis data. Click Refresh to pull latest from remote.</p>
              </Card>
            ) : (<>
              {/* Verdict */}
              <Card className="p-5">
                <SectionHead icon={BrainCircuit} label="AI Verdict" />
                <div className="flex items-start gap-4 flex-wrap">
                  <div className={`px-4 py-2 rounded-xl font-black text-base uppercase ${
                    (ai.verdict || "").toLowerCase().includes("high") || (ai.verdict || "").toLowerCase() === "excellent"
                      ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400"
                      : (ai.verdict || "").toLowerCase() === "mvp" || (ai.verdict || "").toLowerCase().includes("medium")
                      ? "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400"
                      : "bg-rose-50 text-rose-600 dark:bg-rose-900/20 dark:text-rose-400"
                  }`}>{ai.verdict || "N/A"}</div>
                  {ai.aiGeneratedPercentage != null && (
                    <div className="text-center">
                      <span className="text-[10px] font-black text-slate-400 uppercase block">AI-Generated %</span>
                      <span className="text-3xl font-black text-indigo-600 dark:text-indigo-400">{ai.aiGeneratedPercentage}%</span>
                    </div>
                  )}
                </div>
                {ai.verdictReasoning && (
                  <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-900/40 rounded-lg p-4">
                    {ai.verdictReasoning}
                  </p>
                )}
              </Card>

              {/* Strengths / Improvements */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {strengths.length > 0 && (
                  <Card className="p-5">
                    <SectionHead icon={CheckCircle2} label="Strengths" />
                    <ul className="space-y-2">
                      {strengths.map((s, i) => (
                        <li key={i} className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-300">
                          <CheckCircle2 size={13} className="text-emerald-500 mt-0.5 shrink-0" />
                          {typeof s === "string" ? s : s.point || s.text || JSON.stringify(s)}
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
                {improvements.length > 0 && (
                  <Card className="p-5">
                    <SectionHead icon={Zap} label="Improvements" />
                    <ul className="space-y-2">
                      {improvements.map((s, i) => (
                        <li key={i} className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-300">
                          <Zap size={13} className="text-amber-500 mt-0.5 shrink-0" />
                          {typeof s === "string" ? s : s.point || s.text || JSON.stringify(s)}
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
              </div>

              {/* Product analysis */}
              {Object.keys(prod).length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Eye} label="Product Analysis" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {[
                      { label: "Core Value",           val: prod.core_value_proposition },
                      { label: "Target Users",          val: prod.target_users },
                      { label: "Competitive Advantage", val: prod.competitive_advantage },
                      { label: "Market Readiness",      val: prod.market_readiness },
                      { label: "Usability",             val: prod.usability_assessment },
                      { label: "Scalability",           val: prod.scalability_concerns },
                    ].filter(({ val }) => val).map(({ label, val }) => (
                      <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">{label}</span>
                        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{val}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Features Implemented */}
              {features.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={CheckCircle2} label="Features Implemented" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                    {features.map((feat, idx) => (
                      <div key={idx} className="flex items-center gap-3 bg-slate-50 dark:bg-slate-900/40 px-3 py-2 rounded-lg border border-slate-100 dark:border-slate-700/30 text-sm font-semibold text-slate-700 dark:text-slate-300">
                        <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                        {feat}
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Feature-by-Feature Analysis */}
              {featureAnalysis.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Cpu} label="Feature-by-Feature Analysis" />
                  <div className="space-y-3">
                    {featureAnalysis.map((fa, idx) => {
                      const name = fa.feature || fa.name || "Feature";
                      const status = fa.status || "N/A";
                      const quality = fa.quality || "N/A";
                      const details = fa.details || "";
                      return (
                        <div key={idx} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-4">
                          <div className="flex items-center gap-3 flex-wrap mb-2">
                            <span className="font-bold text-slate-800 dark:text-slate-200 text-base">{name}</span>
                            <span className="px-3 py-1 rounded text-[10px] font-black uppercase bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300">{status}</span>
                            <span className={`px-3 py-1 rounded text-[10px] font-black uppercase ${
                              quality.toLowerCase().includes("good") || quality.toLowerCase().includes("high")
                                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                                : "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
                            }`}>Quality: {quality}</span>
                          </div>
                          {details && <p className="text-sm text-slate-500 leading-relaxed">{details}</p>}
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Suggested New Features */}
              {suggestedFeatures.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Zap} label="Suggested New Features" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {suggestedFeatures.map((sf, idx) => {
                      const name = sf.feature || sf.name || "Feature";
                      const priority = sf.priority || "Medium";
                      const desc = sf.description || "";
                      return (
                        <div key={idx} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30 flex flex-col justify-between">
                          <div>
                            <div className="flex justify-between items-start gap-3 mb-2">
                              <span className="font-bold text-slate-800 dark:text-slate-100 text-sm">{name}</span>
                              <span className={`px-2 py-1 rounded text-[9px] font-black uppercase ${
                                priority.toLowerCase() === "critical"
                                  ? "bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300"
                                  : priority.toLowerCase() === "high"
                                  ? "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300"
                                  : "bg-slate-100 text-slate-500"
                              }`}>{priority}</span>
                            </div>
                            {desc && <p className="text-[11px] text-slate-500 leading-relaxed">{desc}</p>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Overall Recommendation */}
              {overallRecommendation && (
                <Card className="p-5 border-l-4 border-indigo-500 bg-indigo-50/10 dark:bg-indigo-950/10">
                  <SectionHead icon={Award} label="Overall Recommendation" />
                  <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{overallRecommendation}</p>
                </Card>
              )}
            </>)}
          </div>
        )}

        {/* ══ TAB: STUDENT GRADING ══ */}
        {activeTab === "grading" && (
          <div className="space-y-5">
            {studentScores.length === 0 ? (
              <Card className="p-12 text-center text-slate-400">
                <GraduationCap className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="font-bold text-base">No student grading data. Click Refresh.</p>
              </Card>
            ) : (<>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {studentScores.map((s, i) => (
                  <Card key={i} className="p-5">
                    <div className="flex justify-between items-start mb-4 pb-3 border-b border-slate-100 dark:border-slate-700/40">
                      <div>
                        <h4 className="font-bold text-slate-800 dark:text-slate-100">{s.name}</h4>
                        {s.email  && <p className="text-[11px] text-slate-400">{s.email}</p>}
                        {s.github && <p className="text-[11px] text-indigo-400 font-mono">@{s.github}</p>}
                        <p className="text-[11px] text-slate-400 mt-0.5">ID: {s.id}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-[10px] font-black text-slate-400 uppercase block">Final Score</span>
                        <span className={`text-3xl font-black ${(s.finalScore ?? 0) >= 75 ? "text-emerald-500" : (s.finalScore ?? 0) >= 45 ? "text-amber-500" : "text-rose-500"}`}>
                          {(s.finalScore ?? 0).toFixed(1)}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      {[
                        { label: "Commits",        val: s.commits ?? 0 },
                        { label: "Contribution",   val: `${(s.contributionPercentage ?? 0).toFixed(1)}%` },
                        { label: "Quality Score",  val: s.qualityScore ?? 0 },
                        { label: "Effort Score",   val: s.effortScore ?? 0 },
                        { label: "Lines Added",    val: (s.linesAdded ?? 0).toLocaleString() },
                        { label: "Lines Deleted",  val: (s.linesDeleted ?? 0).toLocaleString() },
                        { label: "Contrib. Score", val: s.contributionScore ?? 0 },
                        { label: "Deductions",     val: s.deductions ?? 0 },
                      ].map(({ label, val }) => (
                        <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-lg p-3">
                          <span className="text-[9px] font-black text-slate-400 uppercase block">{label}</span>
                          <span className="font-black text-slate-800 dark:text-slate-200">{val}</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3">
                      <div className="flex justify-between text-[11px] font-bold text-slate-500 mb-1">
                        <span>Share</span><span>{(s.contributionPercentage ?? 0).toFixed(1)}%</span>
                      </div>
                      <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${(s.contributionPercentage ?? 0) >= 20 ? "bg-emerald-500" : "bg-rose-400"}`}
                          style={{ width: `${s.contributionPercentage ?? 0}%` }} />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>

              <Card className="p-5 overflow-x-auto">
                <SectionHead icon={Award} label="Grade Comparison" />
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-700 text-slate-400 font-black uppercase tracking-wider">
                      <th className="py-2">Student</th>
                      <th className="py-2 text-right">Commits</th>
                      <th className="py-2 text-right">Share</th>
                      <th className="py-2 text-right">Quality</th>
                      <th className="py-2 text-right">Effort</th>
                      <th className="py-2 text-right">Lines +/-</th>
                      <th className="py-2 text-right">Ded.</th>
                      <th className="py-2 text-right">Final</th>
                    </tr>
                  </thead>
                  <tbody>
                    {studentScores.map((s, i) => (
                      <tr key={i} className="border-b border-slate-50 dark:border-slate-700/30 text-slate-600 dark:text-slate-300">
                        <td className="py-2 font-bold text-slate-800 dark:text-slate-200">{s.name}</td>
                        <td className="py-2 text-right font-black">{s.commits ?? 0}</td>
                        <td className="py-2 text-right">{(s.contributionPercentage ?? 0).toFixed(1)}%</td>
                        <td className="py-2 text-right">{s.qualityScore ?? 0}</td>
                        <td className="py-2 text-right">{s.effortScore ?? 0}</td>
                        <td className="py-2 text-right">
                          <span className="text-emerald-600">+{(s.linesAdded ?? 0).toLocaleString()}</span>
                          <span className="text-rose-500 ml-1">-{(s.linesDeleted ?? 0).toLocaleString()}</span>
                        </td>
                        <td className="py-2 text-right text-rose-500">-{s.deductions ?? 0}</td>
                        <td className="py-2 text-right">
                          <span className={`font-black text-lg ${(s.finalScore ?? 0) >= 75 ? "text-emerald-500" : (s.finalScore ?? 0) >= 45 ? "text-amber-500" : "text-rose-500"}`}>
                            {(s.finalScore ?? 0).toFixed(1)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>)}
          </div>
        )}

      </>)}
      </div>

      {/* ───────────────────────────────────────────────────────────── */}
      {/* PRINTABLE PDF LAYOUT (@media print) */}
      {/* ───────────────────────────────────────────────────────────── */}
      <div className="hidden print:block print:w-full print:bg-white print:text-slate-900 bg-white">
        <style>{`
          @media print {
            @page { size: A4; margin: 12mm; }
            body { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; background: white; }
          }
        `}</style>
        
        {/* Print Header */}
        <div className="flex justify-between items-start border-b-2 border-slate-200 pb-4 mb-6">
          <div>
            <h1 className="text-2xl font-black text-indigo-900 uppercase tracking-wide flex items-center gap-3">
              GITHUB TEAM ANALYTICS REPORT — {selectedTeam?.name || selectedTeam?.id}
              <span className="text-[10px] bg-rose-100 text-rose-700 px-3 py-1 rounded-full">{status}</span>
            </h1>
            <p className="text-base font-bold text-slate-800 mt-2">Project: {projectName || repoName}</p>
            {repoName && <p className="text-sm text-slate-500 font-mono mt-1 flex items-center gap-1"><ExternalLink size={10} /> https://{repoName}</p>}
          </div>
          <div className="text-right text-[10px] text-slate-500 space-y-1">
            <p>Generated: {new Date().toLocaleString()}</p>
            <p>Engine: ProjectFlow - GitHub Analytics Engine v2.4</p>
          </div>
        </div>

        {/* Scores Matrix Breakdown */}
        <div className="mb-6">
          <div className="flex justify-between items-end mb-2">
            <h2 className="text-sm font-black text-slate-700 uppercase">Scores Matrix Breakdown</h2>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              Team Members: {selectedTeam?.members?.map(m => m.name).join(', ') || "N/A"}
            </p>
          </div>
          <div className="grid grid-cols-8 gap-3 border border-slate-200 rounded-xl p-4 bg-slate-50/50">
            {/* Total Score Highlight */}
            <div className="border border-rose-200 bg-rose-50 rounded-lg p-3 text-center flex flex-col items-center justify-center">
              <span className="text-[9px] font-bold text-rose-600 uppercase">Total</span>
              <span className="text-2xl font-black text-rose-700 leading-none my-1">{Math.round(totalScore)}</span>
              <span className="text-[8px] font-bold bg-rose-200 text-rose-800 px-2 py-1 rounded">Needs Work</span>
            </div>
            {scores9.map((s, i) => {
              // Ignore Effort and specific duplicates to fit 8 boxes perfectly like screenshots
              if(i > 6) return null; 
              let col = "slate";
              if (s.value >= 75) col = "emerald";
              else if (s.value >= 45) col = "amber";
              else col = "rose";

              return (
                <div key={i} className={`border border-${col}-200 bg-${col}-50 rounded-lg p-3 text-center flex flex-col items-center justify-center`}>
                  <span className={`text-[9px] font-bold text-${col}-600 uppercase truncate w-full`}>{s.label}</span>
                  <span className={`text-2xl font-black text-${col}-700 leading-none my-1`}>{Math.round(s.value)}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Repo Metrics & Maturity */}
        <div className="mb-6 border border-slate-200 rounded-xl p-4 bg-slate-50/30">
          <h2 className="text-sm font-black text-slate-700 uppercase mb-3">Repo Metrics & Maturity</h2>
          <div className="flex justify-between text-sm font-medium text-slate-600 mb-3">
            <span>Files: <span className="font-bold text-slate-900">{cm.totalFiles || 0}</span></span>
            <span>Lines of Code: <span className="font-bold text-slate-900">{(cm.linesOfCode || 0).toLocaleString()}</span></span>
          </div>
          <div className="flex justify-between text-sm font-medium text-slate-600 mb-3">
            <span>Architecture: <span className="font-bold text-orange-600">{mat.architectureType || 'Monolithic / Unstructured'}</span></span>
          </div>
          <div className="flex justify-between text-sm font-medium text-slate-600 mb-3">
            <span>Maturity: <span className="font-bold text-rose-600">{mat.engineeringMaturity || 'No tests'}</span></span>
            <span>CI: <span className="font-bold text-rose-600">Failing</span></span>
          </div>
          <div className="text-[10px] text-slate-500 truncate">
            Stack: {techStack.join(', ')}
          </div>
        </div>

        {/* Individual Student Scores */}
        <div className="mb-6">
          <div className="flex justify-between items-end mb-2">
            <h2 className="text-sm font-black text-indigo-700 uppercase">Individual Student Scores</h2>
            <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">(Contribution, Effort, Quality)</p>
          </div>
          <table className="w-full text-left text-[11px] border border-slate-200 rounded-xl overflow-hidden">
            <thead className="bg-slate-50">
              <tr className="border-b border-slate-200 text-slate-500 font-bold uppercase">
                <th className="py-2 px-3">Student</th>
                <th className="py-2 px-3 text-right">Commits</th>
                <th className="py-2 px-3 text-right">Share</th>
                <th className="py-2 px-3 text-right">Effort</th>
                <th className="py-2 px-3 text-right">Quality</th>
                <th className="py-2 px-3 text-right text-indigo-900">Score</th>
              </tr>
            </thead>
            <tbody>
              {studentScores.map((s, i) => (
                <tr key={i} className="border-b border-slate-100 text-slate-700">
                  <td className="py-2 px-3 font-bold">{s.name}</td>
                  <td className="py-2 px-3 text-right">{s.commits}</td>
                  <td className="py-2 px-3 text-right">{(s.contributionPercentage || 0).toFixed(0)}%</td>
                  <td className="py-2 px-3 text-right">{s.effortScore || 0}</td>
                  <td className="py-2 px-3 text-right">{s.qualityScore || 0}</td>
                  <td className="py-2 px-3 text-right font-black text-indigo-600">{Math.round(s.finalScore || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer for Page 1 / Page 2 break can be handled automatically by browser, but we ensure gap */}
        <div className="h-6"></div>

        {/* Security & Risk Analysis */}
        <div className="mb-6 border border-slate-200 rounded-xl p-4 bg-slate-50/30">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-sm font-black text-emerald-700 uppercase">Security Analysis & Risk Flags</h2>
            <span className="text-[10px] bg-emerald-100 text-emerald-800 font-bold px-3 py-1 rounded">Score: {analysis.securityScore || 0}/100</span>
          </div>
          <p className="text-[11px] font-bold text-slate-700 mb-3">Secrets: {sec.secretsScore || 100} ({sec.secretsDetected || 0} Detected)</p>
          
          <div className="mb-3">
            <p className="text-[10px] font-bold text-slate-500 uppercase mb-1">Risk Flags:</p>
            <div className="flex gap-3 flex-wrap">
              {riskFlags.map((rf, i) => (
                <span key={i} className="text-[9px] font-bold bg-amber-100 text-amber-700 px-2 py-1 rounded uppercase flex items-center gap-1">
                  <AlertTriangle size={10} /> {rf}
                </span>
              ))}
            </div>
          </div>
          
          <div className="mb-2">
             <p className="text-[10px] font-bold text-slate-500 uppercase mb-1">Missing Security Practices:</p>
             <div className="grid grid-cols-4 gap-3">
               {bestPractices.filter(bp => bp.status !== 'implemented').map((bp, i) => (
                 <div key={i} className="bg-rose-50 border border-rose-100 rounded p-2 text-center">
                   <p className="text-[8px] font-black text-rose-400 uppercase tracking-wider">Missing</p>
                   <p className="text-[9px] font-bold text-slate-700 truncate">{bp.name}</p>
                 </div>
               ))}
             </div>
          </div>
        </div>

        {/* Suggested Actionable Features */}
        {suggestedFeatures.length > 0 && (
          <div className="mb-6 border border-slate-200 rounded-xl p-4">
            <h2 className="text-sm font-black text-amber-700 uppercase mb-3">Suggested Actionable Features & Summary Recommendation</h2>
            <div className="space-y-3">
              {suggestedFeatures.map((sf, i) => (
                <div key={i} className="border border-slate-100 rounded-lg p-4 bg-slate-50/50">
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-[11px] font-bold text-slate-800">{i+1}. {sf.title}</h3>
                    <span className="text-[9px] bg-amber-100 text-amber-800 font-bold px-2 py-1 rounded">Priority: {sf.priority}</span>
                  </div>
                  <p className="text-[10px] text-slate-600 mb-1"><span className="font-bold text-slate-700">Why:</span> {sf.why || sf.why_needed}</p>
                  <p className="text-[10px] text-slate-600"><span className="font-bold text-slate-700">How:</span> {sf.how || sf.implementation_strategy}</p>
                </div>
              ))}
            </div>
            {overallRecommendation && (
              <div className="mt-4 p-4 bg-indigo-50 border border-indigo-100 rounded-lg">
                <p className="text-[9px] font-black text-indigo-700 uppercase mb-1">Summary Recommendation:</p>
                <p className="text-[10px] text-slate-700">{overallRecommendation}</p>
              </div>
            )}
          </div>
        )}

        {/* Footer Print */}
        <div className="fixed bottom-4 left-4 right-4 text-[9px] font-mono text-slate-400 flex justify-between border-t border-slate-200 pt-2">
          <span>Generated by ProjectFlow - GitHub Analytics Engine v2.4</span>
          <span>Confidential Student Evaluation Report</span>
        </div>

      </div>
    </div>
  );
};

export default GithubReportView;
