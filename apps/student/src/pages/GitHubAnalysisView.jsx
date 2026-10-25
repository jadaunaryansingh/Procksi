import React, { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, Tooltip, ResponsiveContainer } from "recharts";
import {
  GitCommit, TrendingUp, ChevronDown, ExternalLink, Loader2,
  Code, Award, AlertOctagon, AlertTriangle, BrainCircuit,
  GraduationCap, Shield, GitBranch, Cpu, Zap, CheckCircle2,
  XCircle, Eye, FileText, Flame, Activity, Users, Lock
} from "lucide-react";
import { getTeamGithub } from "../lib/api";

const Tooltip2 = ({ active, payload, label }) => {
  if (active && payload?.length)
    return (
      <div className="bg-slate-800 p-2 rounded-lg border border-slate-700 text-xs text-white font-bold shadow-xl">
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
  const dim = size === "lg" ? "w-28 h-28 text-3xl" : "w-16 h-16 text-xl";
  return (
    <div className={`rounded-full border-4 flex flex-col items-center justify-center ${cls} ${dim}`}>
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
  return <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold ${map[color] || map.slate}`}>{children}</span>;
};

const Card = ({ children, className = "" }) => (
  <div className={`bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm ${className}`}>
    {children}
  </div>
);

const SectionHead = ({ icon: Icon, label }) => (
  <h3 className="font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2 text-sm mb-4">
    <Icon size={16} className="text-indigo-500" /> {label}
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
  return <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${map[key] || map.info}`}>{sev || "info"}</span>;
};

export default function GitHubAnalysisView() {
  const [githubData, setGithubData]     = useState(null);
  const [dataLoading, setDataLoading]   = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [activeTab, setActiveTab]       = useState("overview");

  const fetchGithub = async (silent = false) => {
    try {
      const data = await getTeamGithub();
      if (!silent) setErrorMessage("");
      setGithubData(data);
    } catch (err) {
      if (!silent) {
        setErrorMessage(err.message || "Failed to fetch GitHub repository analysis data.");
        setGithubData(null);
      }
    } finally {
      if (!silent) {
        setDataLoading(false);
      }
    }
  };

  useEffect(() => {
    Promise.resolve().then(() => fetchGithub());
    const interval = setInterval(() => {
      fetchGithub(true);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Poll while analysis is queued or running
  useEffect(() => {
    if (!githubData) return;
    const st = githubData.analysisStatus;
    if (st === "queued" || st === "running") {
      const iv = setInterval(async () => {
        try {
          const data = await getTeamGithub();
          setGithubData(data);
          if (!["queued", "running"].includes(data?.analysisStatus)) {
            clearInterval(iv);
          }
        } catch { /* non-fatal: fall through to the default below */ }
      }, 3000);
      return () => clearInterval(iv);
    }
  }, [githubData]);

  const repoName     = githubData?.repositoryUrl || "";
  const status       = githubData?.analysisStatus || "pending";
  const isRunning    = ["queued", "running"].includes(status);
  const progress     = githubData?.progress || 0;
  const currentStage = githubData?.currentStage || "";
  
  const ar = githubData?.analysisResults || {};
  const rr = ar.raw_report || {};

  // Overview metrics
  const analysis   = rr.analysis || {};
  const totalScore = analysis.totalScore ?? ar.scores?.quality ?? 0;
  const healthStatus = rr.healthStatus || ar.healthStatus || "";
  const riskFlags = rr.riskFlags || ar.riskFlags || [];
  
  const mat = rr.maturity || {};
  const md = rr.marksDeduction || {};
  const totalCommits = githubData?.commitCount ?? 0;

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

  // Tech stack & languages — ar.techStack can be a string ("React,Node") or already an array.
  const techStack = rr.techStack || (() => {
    const ts = ar.techStack;
    if (!ts) return [];
    if (Array.isArray(ts)) return ts;
    if (typeof ts === 'string') return ts.split(',').map(t => t.trim()).filter(Boolean);
    return [];
  })();
  const cm = rr.codeMetrics || {};
  const languages = rr.languages || [];

  // Contributors
  const contributors = (() => {
    const rawDevs = githubData?.analysisResults?.contributors || [];
    if (rawDevs.length > 0) return rawDevs;
    const rd = rr.commits?.contributionDistribution || [];
    return rd.map(c => ({
      name: c.contributorName || c.name || "Unknown",
      handle: c.name || "Unknown",
      commits: c.commits || 0,
      contribution: Math.round(c.percentage || 0),
      lastCommit: "-"
    }));
  })();

  // Code & Security findings
  const sec = rr.security || {};
  const secIssues = sec.findings || sec.issues || [];
  const bestPractices = rr.bestPractices || [];
  const scoreInsights = rr.scoreInsights || [];

  // Commits / Timeline
  const cq = rr.commitQuality || {};
  const exampleFakeCommits = cq.exampleFlaggedCommits || [];
  const weeklyChart = (() => {
    const timeline = rr.commits?.timeline || [];
    if (timeline.length > 0) return timeline.map(t => ({ name: t.date || t.week || "", commits: t.commits || 0 }));
    const weeklyActivity = githubData?.analysisResults?.weeklyActivity || [];
    return weeklyActivity.map(w => ({ name: w.week || "", commits: w.commits || 0 }));
  })();
  const contribDist = rr.commits?.contributionDistribution || [];

  // AI Verdict
  const ai = rr.aiAnalysis || {};
  const strengths = ai.strengths || [];
  const improvements = ai.improvements || [];
  const prod = rr.productAnalysis || {};
  const features = ai.featuresImplemented || [];
  const featureAnalysis = ai.featureAnalysis || [];
  const suggestedFeatures = ai.suggestedNewFeatures || [];
  const overallRecommendation = ai.overallRecommendation || "";

  // Student Grading
  const studentScores = (() => {
    const grades = rr.studentGrading || [];
    return grades.map(g => ({
      id: g.studentId || g.id || "",
      name: g.studentName || g.name || "Unknown",
      email: g.email || "",
      github: g.githubUsername || g.github || "",
      commits: g.commitsCount || g.commits || 0,
      contributionPercentage: g.contributionPercentage || g.contributionShare || 0,
      qualityScore: g.qualityScore || 0,
      effortScore: g.effortScore || 0,
      linesAdded: g.linesAdded || 0,
      linesDeleted: g.linesDeleted || 0,
      contributionScore: g.contributionScore || 0,
      deductions: g.deductionsCount || g.deductions || 0,
      finalScore: g.finalScore || g.totalScore || 0
    }));
  })();

  const tabs = [
    { id: "overview", label: "Overview",        Icon: Code },
    { id: "code",     label: "Code & Security", Icon: Shield },
    { id: "commits",  label: "Commits",         Icon: GitCommit },
    { id: "ai",       label: "AI Analysis",     Icon: BrainCircuit },
    { id: "grading",  label: "Student Grading", Icon: GraduationCap },
  ];

  if (dataLoading && !githubData) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <Loader2 className="w-10 h-10 text-indigo-500 animate-spin mb-4" />
        <p className="text-sm font-semibold text-slate-500">Loading repository analysis...</p>
      </div>
    );
  }

  if (errorMessage && !githubData) {
    return (
      <Card className="p-8 text-center max-w-lg mx-auto mt-10 border-red-200 dark:border-red-900/50 bg-red-50/20 dark:bg-red-950/10">
        <AlertTriangle className="w-12 h-12 text-rose-500 mx-auto mb-4" />
        <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-2">GitHub Analysis Not Available</h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">{errorMessage}</p>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          Please note that repository analysis is synced with the admin portal. Once the admin triggers analysis on your team's repository, the results will display here automatically.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <BrainCircuit className="text-indigo-500 w-5 h-5" />
            Repository Analysis
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">AI-powered repository insights for your team</p>
        </div>
        {repoName && (
          <a href={repoName} target="_blank" rel="noopener noreferrer" 
             className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-bold text-slate-600 dark:text-slate-300 rounded-lg shadow-sm border dark:border-slate-700 transition-colors">
            <ExternalLink size={13} /> View Repository
          </a>
        )}
      </div>

      {isRunning ? (
        <Card className="p-8 text-center max-w-xl mx-auto border-indigo-200 dark:border-indigo-900/50 bg-indigo-50/10">
          <Loader2 className="w-12 h-12 text-indigo-500 animate-spin mx-auto mb-4" />
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-1">Repository Analysis in Progress</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">The AI agent is currently analyzing commits, code complexity, security findings, and member contributions.</p>
          <div className="max-w-xs mx-auto">
            <div className="flex justify-between text-[10px] font-bold text-indigo-600 dark:text-indigo-400 mb-1 uppercase tracking-wider">
              <span>{currentStage || "Analyzing Repository"}</span>
              <span>{progress}%</span>
            </div>
            <div className="h-2 w-full bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </Card>
      ) : !githubData?.analysisResults || Object.keys(githubData.analysisResults).length === 0 ? (
        <Card className="p-10 text-center max-w-lg mx-auto border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
          <Activity className="w-12 h-12 text-indigo-500 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 mb-2">No Analysis Run Yet</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
            The Git agent repository analysis has not been executed for your team yet. 
            The system will display dashboard statistics here once your coordinator triggers the analysis on the Admin portal.
          </p>
        </Card>
      ) : (
        <>
          {/* Tab Switcher */}
          <div className="flex gap-2 border-b border-slate-200 dark:border-slate-700 pb-2 overflow-x-auto">
            {tabs.map(({ id, label, Icon }) => (
              <button key={id} onClick={() => setActiveTab(id)}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-black whitespace-nowrap transition-all ${
                  activeTab === id 
                    ? "bg-indigo-600 text-white shadow-sm" 
                    : "text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                }`}>
                <Icon size={14} /> {label}
              </button>
            ))}
          </div>

          {/* ══ TAB: OVERVIEW ══ */}
          {activeTab === "overview" && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="p-6 flex flex-col items-center justify-center text-center">
                  <ScoreCircle value={totalScore} size="lg" />
                  <span className="text-xs font-black text-slate-400 uppercase tracking-wider mt-4">Overall Score</span>
                  {rr.projectType && <Chip color="indigo" className="mt-2">{rr.projectType}</Chip>}
                </Card>
                
                <div className="sm:col-span-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <Card className="p-5 flex flex-col justify-between">
                    <div>
                      <SectionHead icon={Activity} label="Health Status" />
                      <div className={`text-2xl font-black capitalize ${healthStatus === "healthy" ? "text-emerald-500" : healthStatus === "warning" ? "text-amber-500" : "text-rose-500"}`}>
                        {healthStatus || "Healthy"}
                      </div>
                    </div>
                    <div className="mt-2 space-y-1">
                      {riskFlags.slice(0, 3).map((f, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-xs text-slate-500">
                          <AlertTriangle size={10} className="text-amber-400 shrink-0" />
                          {f.replace(/_/g, " ")}
                        </div>
                      ))}
                    </div>
                  </Card>

                  <Card className="p-5 flex flex-col justify-between">
                    <div>
                      <SectionHead icon={CheckCircle2} label="Maturity Check" />
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        {[
                          { label: "Tests",  val: mat.hasTests  },
                          { label: "CI/CD",  val: mat.hasCI    },
                          { label: "Docker", val: mat.hasDocker },
                          { label: "README", val: mat.hasReadme },
                        ].map(({ label, val }) => (
                          <div key={label} className="flex items-center gap-1.5 text-xs font-bold text-slate-600 dark:text-slate-400">
                            {val ? <CheckCircle2 size={13} className="text-emerald-500" /> : <XCircle size={13} className="text-slate-300 dark:text-slate-600" />}
                            {label}
                          </div>
                        ))}
                      </div>
                    </div>
                    {mat.testFiles > 0 && <div className="text-[10px] text-slate-400 mt-2 font-bold">{mat.testFiles} test files found</div>}
                  </Card>
                  
                  <Card className="p-4 flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">Total Commits</span>
                      <span className="text-2xl font-black text-slate-800 dark:text-slate-100">{totalCommits}</span>
                    </div>
                  </Card>

                  <Card className="p-4 flex items-center justify-between">
                    <div>
                      <SectionHead icon={AlertTriangle} label="Marks Deductions" />
                      {md.applied ? (
                        <>
                          <div className="text-xl font-black text-rose-500">-{md.marksDeductedPercentage ?? 0}%</div>
                          <p className="text-[10px] text-slate-500 font-medium">{md.reason || ""}</p>
                        </>
                      ) : (
                        <div className="flex items-center gap-1.5 text-emerald-500 text-xs font-black">
                          <CheckCircle2 size={14} /> No deductions applied
                        </div>
                      )}
                    </div>
                  </Card>
                </div>
              </div>

              {/* 8-score grid */}
              <Card className="p-5">
                <SectionHead icon={Award} label="AI Score Breakdown (8 Dimensions)" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {scores9.map(({ label, value }) => (
                    <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3 border border-slate-100 dark:border-slate-700/30">
                      <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                      <span className={`text-xl font-black block mt-0.5 ${value >= 75 ? "text-emerald-500" : value >= 45 ? "text-amber-500" : "text-rose-500"}`}>
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
                  <SectionHead icon={Cpu} label="Detected Technologies" />
                  {techStack.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {techStack.map((t, i) => (
                        <Chip key={i} color="indigo">{typeof t === "string" ? t : t.technology || t.name || t}</Chip>
                      ))}
                    </div>
                  ) : <p className="text-xs text-slate-400 font-bold">No tech stack data.</p>}
                  {cm.architecturePattern && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-4 leading-relaxed">
                      <span className="font-black text-slate-600 dark:text-slate-300">Architecture: </span>
                      {cm.architecturePattern}
                    </p>
                  )}
                </Card>

                <Card className="p-5">
                  <SectionHead icon={FileText} label="Languages Breakdown" />
                  {languages.length > 0 ? (
                    <div className="space-y-3">
                      {languages.slice(0, 6).map((l, i) => {
                        const name = l.name || l.language || l;
                        const pct  = l.percentage ?? 0;
                        return (
                          <div key={i}>
                            <div className="flex justify-between text-xs font-bold text-slate-600 dark:text-slate-300 mb-1">
                              <span>{name}</span>
                              <span>{typeof pct === "number" ? pct.toFixed(1) : pct}%</span>
                            </div>
                            <div className="h-1.5 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                              <div className="h-full bg-indigo-500 rounded-full animate-pulse-slow" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : <p className="text-xs text-slate-400 font-bold">No language breakdown data.</p>}
                  {cm.totalLinesOfCode > 0 && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-4 leading-relaxed">
                      <span className="font-black text-slate-600 dark:text-slate-300">Total Code size: </span>
                      {cm.totalLinesOfCode.toLocaleString()} lines across {cm.totalFiles} files
                    </p>
                  )}
                </Card>
              </div>

              {/* Contributors list */}
              {contributors.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Users} label="Team Contributors" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {contributors.map((dev, i) => (
                      <div key={i} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30">
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-9 h-9 rounded-full bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center font-black text-indigo-600 dark:text-indigo-400 border border-indigo-100 dark:border-indigo-500/20">
                            {(dev.name || "?")[0].toUpperCase()}
                          </div>
                          <div>
                            <p className="font-bold text-sm text-slate-800 dark:text-slate-100 leading-none">{dev.name}</p>
                            {dev.handle && <p className="text-[11px] text-slate-400 font-medium mt-1">@{dev.handle}</p>}
                          </div>
                        </div>
                        <div className="space-y-2 text-xs">
                          <div className="flex justify-between font-bold text-slate-600 dark:text-slate-400">
                            <span>Commits</span>
                            <span className="font-black text-slate-800 dark:text-slate-200">{dev.commits}</span>
                          </div>
                          <div>
                            <div className="flex justify-between font-bold text-slate-600 dark:text-slate-400 mb-1">
                              <span>Contribution Share</span>
                              <span className="font-black text-slate-800 dark:text-slate-200">{dev.contribution}%</span>
                            </div>
                            <div className="h-1.5 w-full bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                              <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${dev.contribution}%` }} />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Insights */}
              {scoreInsights && scoreInsights.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={AlertOctagon} label="Improvement Guide & Score Insights" />
                  <div className="space-y-4">
                    {scoreInsights.map((insight, idx) => {
                      const scoreVal = insight.score ?? 0;
                      const name = insight.dimension || "Dimension";
                      const severity = insight.severity || "info";
                      const reasons = insight.likely_reasons || insight.reasons || [];
                      const steps = insight.improvement_steps || insight.steps || [];
                      return (
                        <div key={idx} className="border-l-4 border-rose-500 bg-rose-50/20 dark:bg-rose-900/5 p-4 rounded-r-xl">
                          <span className="font-bold text-slate-800 dark:text-slate-100 text-xs block mb-2">
                            {name} &mdash; <span className="text-rose-500 font-black">{scoreVal}/100</span> [{severity.toUpperCase()}]
                          </span>
                          {reasons.length > 0 && (
                            <div className="mb-2">
                              <span className="text-[10px] font-black text-slate-400 uppercase block mb-1">Low Score Reasons:</span>
                              <ul className="list-disc list-inside text-xs text-rose-600/90 dark:text-rose-400 space-y-0.5 pl-1">
                                {reasons.map((r, i) => <li key={i}>{r}</li>)}
                              </ul>
                            </div>
                          )}
                          {steps.length > 0 && (
                            <div>
                              <span className="text-[10px] font-black text-slate-400 uppercase block mb-1">Recommended Fixes:</span>
                              <ul className="text-xs text-emerald-600 dark:text-emerald-400 space-y-1 pl-1 font-semibold">
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
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: "Overall Security", value: sec.score ?? 100 },
                  { label: "Secrets Leak Score", value: sec.secretsScore ?? 100 },
                  { label: "Practices Score", value: sec.practicesScore ?? 100 },
                ].map(({ label, value }) => (
                  <Card key={label} className="p-4 flex flex-col items-center justify-center text-center">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-2">{label}</span>
                    <ScoreCircle value={Math.round(value)} />
                  </Card>
                ))}
              </div>

              {cm.totalFiles > 0 && (
                <Card className="p-5">
                  <SectionHead icon={FileText} label="Repository Code Metrics" />
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                    {[
                      { label: "Total Files", val: cm.totalFiles?.toLocaleString() },
                      { label: "Lines of Code", val: cm.totalLinesOfCode?.toLocaleString() },
                      { label: "Architecture Pattern", val: cm.architecturePattern },
                      { label: "Unique Languages", val: languages.length },
                    ].map(({ label, val }) => (
                      <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3 border border-slate-100 dark:border-slate-700/30">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                        <span className="text-sm font-black text-slate-800 dark:text-slate-100 mt-1 block">{val || "?"}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {/* Security Findings */}
              <Card className="p-5">
                <SectionHead icon={Shield} label={`Vulnerability Findings (${secIssues.length})`} />
                {secIssues.length > 0 ? (
                  <div className="space-y-3">
                    {secIssues.map((iss, i) => (
                      <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-3 bg-white dark:bg-slate-850">
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                            {iss.title || iss.type || "Security Leak"}
                          </span>
                          <SevBadge sev={iss.severity} />
                        </div>
                        {iss.description && <p className="text-[11px] text-slate-500 mb-1 leading-relaxed">{iss.description}</p>}
                        {iss.snippet && (
                          <p className="text-[10px] text-slate-400 font-mono bg-slate-50 dark:bg-slate-900/40 px-2 py-1 rounded mt-1 truncate">{iss.snippet}</p>
                        )}
                        {(iss.file || iss.file_path || iss.path) && (
                          <code className="text-[9px] text-indigo-500 font-mono bg-indigo-50 dark:bg-indigo-900/20 px-1.5 py-0.5 rounded block mt-1.5 w-fit">
                            {iss.file || iss.file_path || iss.path}{iss.line_number ? `:${iss.line_number}` : ""}
                          </code>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-emerald-500 text-sm font-bold">
                    <CheckCircle2 size={16} /> No security issues found in analysis.
                  </div>
                )}
              </Card>

              {/* Best practices checklist */}
              {bestPractices.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Eye} label="Best Practices Audit Summary" />
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30 space-y-2.5 h-fit">
                      <span className="text-xs font-black text-slate-400 uppercase tracking-wider block mb-2">Checklist Summary</span>
                      {bestPractices.map((bp, i) => {
                        const name = bp.practice_name || bp.title || bp.name || "Practice";
                        const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                        return (
                          <div key={i} className="flex items-center gap-2 text-xs font-bold">
                            {ok ? (
                              <span className="text-emerald-500 flex items-center gap-1 font-black shrink-0"><CheckCircle2 size={13} /> OK</span>
                            ) : (
                              <span className="text-rose-500 flex items-center gap-1 font-black shrink-0"><XCircle size={13} /> NO</span>
                            )}
                            <span className="text-slate-700 dark:text-slate-300 truncate">{name}</span>
                          </div>
                        );
                      })}
                    </div>
                    
                    <div className="md:col-span-2 space-y-3 max-h-[400px] overflow-y-auto pr-1">
                      {bestPractices.map((bp, i) => {
                        const ok = bp.status === "implemented" || bp.status === "pass" || bp.status === true || String(bp.status).toLowerCase() === "ok";
                        return (
                          <div key={i} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-3 bg-white dark:bg-slate-800">
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <div className="flex items-center gap-1.5 font-bold text-xs text-slate-800 dark:text-slate-200">
                                {ok ? <CheckCircle2 size={12} className="text-emerald-500" /> : <XCircle size={12} className="text-rose-500" />}
                                {bp.practice_name || bp.title || bp.name || "Practice"}
                              </div>
                              <SevBadge sev={ok ? "implemented" : bp.severity} />
                            </div>
                            {bp.recommendation && <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">{bp.recommendation}</p>}
                            {bp.files_found?.length > 0 && (
                              <p className="text-[10px] text-slate-400 mt-1.5 font-mono">
                                Files: {bp.files_found.join(", ")}
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Total Commits",  value: totalCommits, color: "text-slate-800 dark:text-slate-100" },
                  { label: "Last 7 Days",    value: githubData?.analysisResults?.raw_report?.commits?.lastWeek ?? 0, color: "text-indigo-600 dark:text-indigo-400" },
                  { label: "Authentic Commits",   value: cq.realCommits ?? "-", color: "text-emerald-600" },
                  { label: "Suspicious / Inflated", value: cq.fakeCommits ?? "-", color: "text-rose-500" },
                ].map(({ label, value, color }) => (
                  <Card key={label} className="p-4 text-center">
                    <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">{label}</span>
                    <span className={`text-2xl font-black ${color}`}>{value}</span>
                  </Card>
                ))}
              </div>

              {/* Chart */}
              <Card className="p-5" style={{ height: 280 }}>
                <SectionHead icon={TrendingUp} label="Commit Frequency (Weekly Timeline)" />
                <div style={{ height: 210 }} className="w-full">
                  {weeklyChart.length > 0 ? (
                    <ResponsiveContainer width="100%" height={210}>
                      <BarChart data={weeklyChart}>
                        <Tooltip content={<Tooltip2 />} cursor={{ fill: "rgba(99,102,241,0.05)" }} />
                        <XAxis dataKey="name" stroke="#94a3b8" tick={{ fill: "#64748b", fontSize: 10, fontWeight: "bold" }} axisLine={false} tickLine={false} dy={8} />
                        <Bar dataKey="commits" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-slate-400 text-sm font-bold">No weekly timeline data.</div>
                  )}
                </div>
              </Card>

              {/* Commit Quality */}
              {Object.keys(cq).length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Flame} label="Commit Sincerity & Sizing" />
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-center mb-4">
                    {[
                      { label: "Health Status", val: cq.healthStatus },
                      { label: "Real Commits", val: cq.realCommits },
                      { label: "Fake Commits", val: cq.fakeCommits },
                      { label: "Fake Commits Share", val: cq.fakeCommitPercentage != null ? `${cq.fakeCommitPercentage}%` : null },
                      { label: "Inflation Factor", val: cq.inflationRatio },
                      { label: "AI tools used", val: cq.aiToolsDetectedCount },
                    ].filter(x => x.val != null).map(({ label, val }) => (
                      <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3 border border-slate-100 dark:border-slate-700/30">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block">{label}</span>
                        <span className="text-sm font-black text-slate-800 dark:text-slate-100 block mt-0.5">{String(val)}</span>
                      </div>
                    ))}
                  </div>
                  
                  {cq.aiToolsDetected?.length > 0 && (
                    <p className="text-xs text-slate-500 mb-3 leading-relaxed">
                      <span className="font-bold">AI generation signatures: </span>{cq.aiToolsDetected.join(", ")}
                    </p>
                  )}
                  {cq.detectedIssues?.length > 0 && (
                    <div className="space-y-1 bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border dark:border-slate-700/30">
                      <span className="text-xs font-black text-slate-400 uppercase tracking-wider block mb-2">Warnings & Alerts</span>
                      {cq.detectedIssues.slice(0, 5).map((iss, i) => (
                        <div key={i} className="text-xs text-slate-500 flex items-start gap-1.5 font-medium">
                          <AlertTriangle size={12} className="text-amber-500 mt-0.5 shrink-0" />
                          <span>{typeof iss === "string" ? iss : `${iss.type}: ${iss.count ?? ""}`}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {exampleFakeCommits.length > 0 && (
                    <div className="mt-4 border-t border-slate-100 dark:border-slate-700/40 pt-4">
                      <span className="text-xs font-black text-slate-400 uppercase tracking-wider block mb-2">Commits Flagged as Inflated</span>
                      <div className="space-y-2">
                        {exampleFakeCommits.map((item, idx) => (
                          <div key={idx} className="bg-rose-50/20 dark:bg-rose-900/5 border border-rose-100 dark:border-rose-900/20 rounded-xl p-3 text-xs">
                            <div className="flex justify-between items-center gap-2 mb-1 flex-wrap">
                              <span className="font-mono text-indigo-500 font-bold">{item.sha} &mdash; {item.message || "No message"}</span>
                              <Chip color="rose">Flagged</Chip>
                            </div>
                            {item.reason && <p className="text-[11px] text-rose-600 dark:text-rose-400 font-semibold mt-1">Reason: {item.reason}</p>}
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
                  <SectionHead icon={GitCommit} label="Author Contribution Distribution" />
                  <div className="space-y-4">
                    {contribDist.map((c, i) => {
                      const name = c.contributorName || c.name || "Unknown";
                      const pct  = typeof c.percentage === "number" ? c.percentage : (c.commits / Math.max(1, totalCommits)) * 100;
                      return (
                        <div key={i}>
                          <div className="flex justify-between text-xs font-bold text-slate-600 dark:text-slate-300 mb-1">
                            <span>{name}</span>
                            <span>{c.commits} commits &middot; {pct.toFixed(1)}%</span>
                          </div>
                          <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden animate-pulse-slow">
                            <div className={`h-full rounded-full ${pct >= 20 ? "bg-indigo-500" : pct >= 5 ? "bg-amber-400" : "bg-rose-400"}`}
                              style={{ width: `${Math.min(pct, 100)}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}
            </div>
          )}

          {/* ══ TAB: AI ANALYSIS ══ */}
          {activeTab === "ai" && (
            <div className="space-y-5">
              <Card className="p-5">
                <SectionHead icon={BrainCircuit} label="AI Verdict" />
                <div className="flex items-start gap-4 flex-wrap">
                  <div className={`px-4 py-2 rounded-xl font-black text-sm uppercase ${
                    (ai.verdict || "").toLowerCase().includes("high") || (ai.verdict || "").toLowerCase() === "excellent"
                      ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400"
                      : (ai.verdict || "").toLowerCase() === "mvp" || (ai.verdict || "").toLowerCase().includes("medium")
                      ? "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400"
                      : "bg-rose-50 text-rose-600 dark:bg-rose-900/20 dark:text-rose-400"
                  }`}>{ai.verdict || "N/A"}</div>
                  {ai.aiGeneratedPercentage != null && (
                    <div>
                      <span className="text-[10px] font-black text-slate-400 uppercase block">AI Code Percentage</span>
                      <span className="text-2xl font-black text-indigo-600 dark:text-indigo-400 mt-0.5 block">{ai.aiGeneratedPercentage}%</span>
                    </div>
                  )}
                </div>
                {ai.verdictReasoning && (
                  <p className="mt-4 text-xs text-slate-600 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-900/40 rounded-lg p-3 font-medium">
                    {ai.verdictReasoning}
                  </p>
                )}
              </Card>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {strengths.length > 0 && (
                  <Card className="p-5">
                    <SectionHead icon={CheckCircle2} label="Key Strengths" />
                    <ul className="space-y-2">
                      {strengths.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 font-medium">
                          <CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" />
                          <span>{typeof s === "string" ? s : s.point || s.text || JSON.stringify(s)}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
                
                {improvements.length > 0 && (
                  <Card className="p-5">
                    <SectionHead icon={Zap} label="Suggested Improvements" />
                    <ul className="space-y-2">
                      {improvements.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 font-medium">
                          <Zap size={14} className="text-amber-500 mt-0.5 shrink-0" />
                          <span>{typeof s === "string" ? s : s.point || s.text || JSON.stringify(s)}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
              </div>

              {Object.keys(prod).length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Eye} label="Product Architecture & Feasibility" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {[
                      { label: "Core Value Proposition", val: prod.core_value_proposition },
                      { label: "Target Users",          val: prod.target_users },
                      { label: "Competitive Edge",      val: prod.competitive_advantage },
                      { label: "Market Readiness",      val: prod.market_readiness },
                      { label: "Usability Assessment",  val: prod.usability_assessment },
                      { label: "Scalability Concerns",  val: prod.scalability_concerns },
                    ].filter(({ val }) => val).map(({ label, val }) => (
                      <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-3 border dark:border-slate-750">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider block mb-1">{label}</span>
                        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-semibold">{val}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {features.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={CheckCircle2} label="Detected Product Features" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                    {features.map((feat, idx) => (
                      <div key={idx} className="flex items-center gap-2 bg-slate-50 dark:bg-slate-900/40 px-3 py-2 rounded-lg border border-slate-100 dark:border-slate-700/30 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        <CheckCircle2 size={13} className="text-emerald-500 shrink-0" />
                        <span>{feat}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              {featureAnalysis.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Cpu} label="Detailed Feature Quality Breakdown" />
                  <div className="space-y-3">
                    {featureAnalysis.map((fa, idx) => {
                      const name = fa.feature || fa.name || "Feature";
                      const fStatus = fa.status || "N/A";
                      const quality = fa.quality || "N/A";
                      const details = fa.details || "";
                      return (
                        <div key={idx} className="border border-slate-100 dark:border-slate-700/40 rounded-xl p-4 bg-white dark:bg-slate-800">
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <span className="font-bold text-slate-800 dark:text-slate-200 text-xs">{name}</span>
                            <span className="px-2 py-0.5 rounded text-[9px] font-black uppercase bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300">{fStatus}</span>
                            <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase ${
                              quality.toLowerCase().includes("good") || quality.toLowerCase().includes("high")
                                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                                : "bg-amber-50 text-amber-700 dark:bg-amber-900/30 text-amber-300"
                            }`}>Quality: {quality}</span>
                          </div>
                          {details && <p className="text-xs text-slate-500 leading-relaxed font-semibold">{details}</p>}
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {suggestedFeatures.length > 0 && (
                <Card className="p-5">
                  <SectionHead icon={Zap} label="AI Recommended New Features" />
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {suggestedFeatures.map((sf, idx) => {
                      const name = sf.feature || sf.name || "Feature";
                      const priority = sf.priority || "Medium";
                      const desc = sf.description || "";
                      return (
                        <div key={idx} className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-4 border border-slate-100 dark:border-slate-700/30 flex flex-col justify-between">
                          <div>
                            <div className="flex justify-between items-start gap-2 mb-2">
                              <span className="font-bold text-slate-800 dark:text-slate-100 text-xs">{name}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-black uppercase ${
                                priority.toLowerCase() === "critical"
                                  ? "bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300"
                                  : priority.toLowerCase() === "high"
                                  ? "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300"
                                  : "bg-slate-100 text-slate-500"
                              }`}>{priority}</span>
                            </div>
                            {desc && <p className="text-[11px] text-slate-500 leading-relaxed font-medium">{desc}</p>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {overallRecommendation && (
                <Card className="p-5 border-l-4 border-indigo-500 bg-indigo-50/10 dark:bg-indigo-950/10">
                  <SectionHead icon={Award} label="Overall Recommendation" />
                  <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-semibold">{overallRecommendation}</p>
                </Card>
              )}
            </div>
          )}

          {/* ══ TAB: STUDENT GRADING ══ */}
          {activeTab === "grading" && (
            <div className="space-y-5">
              {studentScores.length === 0 ? (
                <Card className="p-12 text-center text-slate-400">
                  <GraduationCap className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p className="font-bold text-sm">No student grading details available for this run.</p>
                </Card>
              ) : (
                <>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {studentScores.map((s, i) => (
                      <Card key={i} className="p-5">
                        <div className="flex justify-between items-start mb-4 pb-3 border-b border-slate-100 dark:border-slate-700/40">
                          <div>
                            <h4 className="font-bold text-slate-800 dark:text-slate-100 leading-none">{s.name}</h4>
                            {s.email  && <p className="text-[11px] text-slate-450 mt-1">{s.email}</p>}
                            {s.github && <p className="text-[11px] text-indigo-400 font-mono mt-0.5">@{s.github}</p>}
                            <p className="text-[10px] text-slate-400 mt-1">Roll / ID: {s.id}</p>
                          </div>
                          <div className="text-right">
                            <span className="text-[9px] font-black text-slate-400 uppercase block">Calculated Grade</span>
                            <span className={`text-2xl font-black block mt-0.5 ${(s.finalScore ?? 0) >= 75 ? "text-emerald-500" : (s.finalScore ?? 0) >= 45 ? "text-amber-500" : "text-rose-500"}`}>
                              {(s.finalScore ?? 0).toFixed(1)}
                            </span>
                          </div>
                        </div>
                        
                        <div className="grid grid-cols-2 gap-2 text-xs font-semibold">
                          {[
                            { label: "Commits",        val: s.commits ?? 0 },
                            { label: "Contrib. Share", val: `${(s.contributionPercentage ?? 0).toFixed(1)}%` },
                            { label: "Quality Score",  val: s.qualityScore ?? 0 },
                            { label: "Effort Score",   val: s.effortScore ?? 0 },
                            { label: "Lines Added",    val: (s.linesAdded ?? 0).toLocaleString() },
                            { label: "Lines Deleted",  val: (s.linesDeleted ?? 0).toLocaleString() },
                            { label: "Contrib. Score", val: s.contributionScore ?? 0 },
                            { label: "Deductions",     val: s.deductions ?? 0 },
                          ].map(({ label, val }) => (
                            <div key={label} className="bg-slate-50 dark:bg-slate-900/40 rounded-lg p-2 border dark:border-slate-750">
                              <span className="text-[9px] font-black text-slate-400 uppercase block">{label}</span>
                              <span className="font-black text-slate-800 dark:text-slate-200 mt-0.5 block">{val}</span>
                            </div>
                          ))}
                        </div>
                        <div className="mt-3">
                          <div className="flex justify-between text-[11px] font-bold text-slate-500 mb-1">
                            <span>Contribution share</span>
                            <span>{(s.contributionPercentage ?? 0).toFixed(1)}%</span>
                          </div>
                          <div className="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${(s.contributionPercentage ?? 0) >= 20 ? "bg-emerald-500" : "bg-rose-450"}`}
                              style={{ width: `${s.contributionPercentage ?? 0}%` }} />
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>

                  <Card className="p-5 overflow-x-auto">
                    <SectionHead icon={Award} label="Grade Distribution Table" />
                    <table className="w-full text-left text-xs font-bold">
                      <thead>
                        <tr className="border-b border-slate-100 dark:border-slate-700 text-slate-400 font-black uppercase tracking-wider">
                          <th className="py-2">Student</th>
                          <th className="py-2 text-right">Commits</th>
                          <th className="py-2 text-right">Share</th>
                          <th className="py-2 text-right">Quality</th>
                          <th className="py-2 text-right">Effort</th>
                          <th className="py-2 text-right">Lines +/-</th>
                          <th className="py-2 text-right">Deductions</th>
                          <th className="py-2 text-right">Final Grade</th>
                        </tr>
                      </thead>
                      <tbody>
                        {studentScores.map((s, i) => (
                          <tr key={i} className="border-b border-slate-50 dark:border-slate-700/30 text-slate-650 dark:text-slate-300 font-medium">
                            <td className="py-3 font-bold text-slate-800 dark:text-slate-200">{s.name}</td>
                            <td className="py-3 text-right font-black">{s.commits ?? 0}</td>
                            <td className="py-3 text-right">{(s.contributionPercentage ?? 0).toFixed(1)}%</td>
                            <td className="py-3 text-right">{s.qualityScore ?? 0}</td>
                            <td className="py-3 text-right">{s.effortScore ?? 0}</td>
                            <td className="py-3 text-right">
                              <span className="text-emerald-600 font-black">+{(s.linesAdded ?? 0).toLocaleString()}</span>
                              <span className="text-rose-500 font-black ml-1.5">-{(s.linesDeleted ?? 0).toLocaleString()}</span>
                            </td>
                            <td className="py-3 text-right text-rose-500">-{s.deductions ?? 0}</td>
                            <td className="py-3 text-right">
                              <span className={`font-black text-sm ${(s.finalScore ?? 0) >= 75 ? "text-emerald-500" : (s.finalScore ?? 0) >= 45 ? "text-amber-500" : "text-rose-500"}`}>
                                {(s.finalScore ?? 0).toFixed(1)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Card>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
