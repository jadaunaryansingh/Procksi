import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation, Outlet } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Users, FileBadge, Clock, Github, X, FileText } from 'lucide-react';
import { supabase } from './lib/supabase';

// Layout & Navigation
import TopNav from './components/TopNav';
import Sidebar from './components/Sidebar';
import WalkthroughOverlay from './components/Walkthrough/WalkthroughOverlay';
import { TOUR_STEPS } from './components/Walkthrough/steps';
import { useWalkthrough } from './hooks/useWalkthrough';
import ReminderWindow from './components/ReminderWindow';

// Views
import LoginView from './pages/LoginView';
import ResetPasswordView from './pages/ResetPasswordView';
import LandingPage from './pages/LandingPage';
import SignUpView from './pages/SignUpView';
import DashboardOverview from './pages/DashboardOverview';
import PmsChatView from './pages/PmsChatView';
import TeamProposalView from './pages/TeamProposalView';
import PreferencesView from './pages/PreferencesView';
import MilestonesView from './pages/MilestonesView';
import FeedbackView from './pages/FeedbackView';
import ProfileView from './pages/ProfileView';
import NotificationsView from './pages/NotificationsView';
import MentorView from './pages/MentorView';
import PresentationsView from './pages/PresentationsView';
import EvaluationsView from './pages/EvaluationsView';
import ResultsView from './pages/ResultsView';
import ExtraActivitiesView from './pages/ExtraActivitiesView';
import GitHubAnalysisView from './pages/GitHubAnalysisView';
import { useProfile, clearQueryCache } from './hooks/useStudentData';
import PmsChatRoute from './components/PmsChatRoute';
import { getApiBaseUrl } from './lib/apiBase';

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  // Read the saved theme once, during the first render, instead of setting it
  // from an effect (which would render light first and then flip to dark).
  const [isDark, setIsDark] = useState(() => {
    try {
      return localStorage.getItem('pms-theme') === 'dark';
    } catch {
      return false;   // storage blocked (private mode) -> default light
    }
  });
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const [showGuidelines, setShowGuidelines] = useState(false);

  // Theme Management -- keep the <html> class in sync with the state above.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    if (!localStorage.getItem('pms-theme')) {
      localStorage.setItem('pms-theme', isDark ? 'dark' : 'light');
    }
  }, [isDark]);



  const toggleTheme = () => {
    // The effect above applies the <html> class; here we only flip the state
    // and remember the choice.
    const next = !isDark;
    setIsDark(next);
    localStorage.setItem('pms-theme', next ? 'dark' : 'light');
  };

  // Auth monitoring
  useEffect(() => {
    const enforceDomain = async (currentSession) => {
      const email = currentSession?.user?.email?.toLowerCase() || '';
      if (currentSession && !email.endsWith('@gla.ac.in')) {
        await supabase.auth.signOut();
        navigate('/student/login?error=domain', { replace: true });
        return null;
      }
      return currentSession;
    };

    // Ask the backend whether this signed-in Google account belongs to a real
    // (pre-registered) student, and kick it out if not.
    //
    // The backend replies 200 with { registered: true | false }. We only sign the
    // user out when it explicitly says registered === false. For ANYTHING else —
    // an error status, a missing route, no internet, a timeout, an unexpected body
    // — we do nothing and let them stay. This "fail open" rule means a temporary
    // backend problem can never accidentally lock out genuine students.
    const gateOAuthSession = async (session) => {
      const API_BASE_URL = getApiBaseUrl();
      try {
        // The token proves who they are; the backend reads the e-mail from it and
        // looks it up in the students table.
        const res = await fetch(`${API_BASE_URL}/api/auth/verify`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) return;                       // couldn't check → fail open
        const body = await res.json().catch(() => null);
        if (body?.data?.registered === false) {    // the ONLY case we block on
          sessionStorage.setItem('student_oauth_gate_error',
            'This Google account is not pre-registered. Please contact your coordinator to be added.');
          await supabase.auth.signOut();
          navigate('/student/login', { replace: true });
        }
      } catch {
        // Couldn't reach the backend — fail open (do NOT sign out).
      }
    };

    supabase.auth.getSession().then(async ({ data: { session } }) => {
      const validSession = await enforceDomain(session);
      setSession(validSession);
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN') {
        const validSession = await enforceDomain(session);
        if (!validSession) {
          setLoading(false);
          return;
        }
        setSession(validSession);
        setLoading(false);
        // Only redirect to dashboard if on an unauthenticated page.
        // Supabase also fires SIGNED_IN on tab focus/token refresh — we must
        // NOT redirect mid-session or every tab switch will reset to dashboard.
        const unauthPaths = ['/student/login', '/student/signup', '/student/landing', '/student/reset-password'];
        const isOnAuthPage = unauthPaths.some(p => location.pathname.startsWith(p)) || location.pathname === '/';
        if (isOnAuthPage) {
          navigate('/student/dashboard', { replace: true });
        }
        return;
      }
      setSession(session);
      setLoading(false);
      if (event === 'SIGNED_OUT') {
        // Let the reminder window pop again on the next sign-in in this tab.
        sessionStorage.removeItem('pms-reminders-shown');
        navigate('/student/login', { replace: true });
      }
      // OAuth gate.
      // Students who sign up with a password go through /api/auth/signup, which
      // only allows e-mails the admin already uploaded (the "master data"). But
      // "Sign in with Google" skips that check, so anyone with a Google account
      // could get in. Here we catch a fresh sign-in and, if it came from Google
      // (provider is not 'email'), double-check that account is a real student.
      if (event === 'SIGNED_IN' && session) {
        const provider = session.user?.app_metadata?.provider;
        if (provider && provider !== 'email') {
          gateOAuthSession(session);
        }
      }
    });

    return () => subscription.unsubscribe();
  }, [navigate]);

  // Auth Expired Listener
  useEffect(() => {
    const handleAuthExpired = async () => {
      await supabase.auth.signOut();
      navigate('/student/login', { replace: true });
    };
    window.addEventListener('auth:expired', handleAuthExpired);
    return () => window.removeEventListener('auth:expired', handleAuthExpired);
  }, [navigate]);

  const handleLogout = async () => {
    clearQueryCache();   // drop this student's cached responses before the next login
    await supabase.auth.signOut();
    navigate('/student/login', { replace: true });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex flex-col items-center justify-center p-4 transition-colors">
        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-slate-600 dark:text-slate-400 font-semibold text-sm">Verifying Session...</p>
      </div>
    );
  }

  return (
    <>
      <Routes>
        {/* Landing Page — entry point for unauthenticated users */}
        <Route path="/student/landing" element={
          session ? <Navigate to="/student/dashboard" replace /> : 
          <LandingPage 
            onGetStarted={() => navigate('/student/login')} 
            isDark={isDark} 
            toggleTheme={toggleTheme} 
            hideLogo={false}
            forceDarkNavbar={false}
          />
        } />

        <Route path="/student/login" element={
          session ? <Navigate to="/student/dashboard" replace /> : <LoginView />
        } />
        
        <Route path="/student/signup" element={
          session ? <Navigate to="/student/dashboard" replace /> : <SignUpView />
        } />
        
        <Route path="/student/reset-password" element={<ResetPasswordView />} />
        
        <Route path="/student" element={
          session ? (
            <DashboardLayout
              session={session}
              isDark={isDark}
              toggleTheme={toggleTheme}
              sidebarCollapsed={sidebarCollapsed}
              setSidebarCollapsed={setSidebarCollapsed}
              mobileMenuOpen={mobileMenuOpen}
              setMobileMenuOpen={setMobileMenuOpen}
              notificationsOpen={notificationsOpen}
              setNotificationsOpen={setNotificationsOpen}
              profileDropdownOpen={profileDropdownOpen}
              setProfileDropdownOpen={setProfileDropdownOpen}
              handleLogout={handleLogout}
              setShowGuidelines={setShowGuidelines}
              showGuidelines={showGuidelines}
            />
          ) : <Navigate to="/student/landing" replace />
        }>
          <Route index element={<Navigate to="/student/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardOverview setShowGuidelines={setShowGuidelines} />} />
          <Route path="team" element={<TeamProposalView />} />
          <Route path="analysis" element={<GitHubAnalysisView />} />
          <Route path="preferences" element={<PreferencesView />} />
          <Route path="pms-chat" element={<PmsChatRoute><PmsChatView /></PmsChatRoute>} />
          <Route path="milestones" element={<MilestonesView />} />
          <Route path="feedback" element={<FeedbackView />} />
          <Route path="profile" element={<ProfileView />} />
          <Route path="notifications" element={<NotificationsView />} />
          <Route path="mentor" element={<MentorView />} />
          <Route path="presentations" element={<PresentationsView />} />
          <Route path="evaluations" element={<EvaluationsView />} />
          <Route path="results" element={<ResultsView />} />
          <Route path="activities" element={<ExtraActivitiesView />} />
        </Route>

        <Route path="/login" element={session ? <Navigate to="/student/dashboard" replace /> : <Navigate to="/student/login" replace />} />
        <Route path="/" element={session ? <Navigate to="/student/dashboard" replace /> : <Navigate to="/student/landing" replace />} />
        <Route path="*" element={session ? <Navigate to="/student/dashboard" replace /> : <Navigate to="/student/landing" replace />} />
      </Routes>
    </>
  );
}

function DashboardLayout({
  session,
  sidebarCollapsed,
  setSidebarCollapsed,
  mobileMenuOpen,
  setMobileMenuOpen,
  handleLogout,
  isDark,
  toggleTheme,
  notificationsOpen,
  setNotificationsOpen,
  profileDropdownOpen,
  setProfileDropdownOpen,
  showGuidelines,
  setShowGuidelines
}) {
  const { data: profile } = useProfile();
  const walkthrough = useWalkthrough({
    tours: TOUR_STEPS,
    prefix: 'pms-student-walkthrough-v1',
    rootPath: '/student/dashboard',
  });
  const user = {
    name: session?.user?.user_metadata?.full_name || session?.user?.email?.split('@')[0],
    email: session?.user?.email,
    avatar: session?.user?.user_metadata?.avatar_url || `https://ui-avatars.com/api/?name=${session?.user?.email?.split('@')[0]}&background=random`
  };

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-900 font-sans overflow-hidden transition-colors selection:bg-indigo-500/30">
      <Sidebar
        user={user}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        mobileMenuOpen={mobileMenuOpen}
        setMobileMenuOpen={setMobileMenuOpen}
        handleLogout={handleLogout}
      />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <TopNav
          onReplayWalkthrough={walkthrough.restart}
          isDark={isDark}
          toggleTheme={toggleTheme}
          setMobileMenuOpen={setMobileMenuOpen}
          notificationsOpen={notificationsOpen}
          setNotificationsOpen={setNotificationsOpen}
          profileDropdownOpen={profileDropdownOpen}
          setProfileDropdownOpen={setProfileDropdownOpen}
          handleLogout={handleLogout}
        />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 scroll-smooth w-full">
          <div className="max-w-7xl mx-auto pb-20 relative px-2">
            {profile?.isLocked && (
              <div className="mb-6 px-4 py-3 bg-red-100 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 rounded-2xl flex items-center font-bold text-xs sm:text-sm shadow-sm gap-2">
                <span>⚠️</span>
                <span>The system is currently frozen by an Administrator. All data modifications are strictly prohibited.</span>
              </div>
            )}
            {profile?.lockTeams && !profile?.isLocked && (
              <div className="mb-6 px-4 py-3 bg-amber-100 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400 rounded-2xl flex items-center font-bold text-xs sm:text-sm shadow-sm gap-2">
                <span>🔒</span>
                <span>Team formation is locked for this semester. No member additions, removals, or join requests are allowed.</span>
              </div>
            )}
            <Outlet />
          </div>
        </main>
      </div>

      {/* Portals into document.body so the sidebar's stacking context cannot
          trap the spotlight behind it. */}
      <WalkthroughOverlay {...walkthrough} />

      {/* Guidelines Modal */}
      <AnimatePresence>
        {showGuidelines && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setShowGuidelines(false)} className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-[60]" />
            <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[90%] max-w-lg bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 z-[70] overflow-hidden flex flex-col max-h-[90vh]">
              <div className="p-5 border-b border-slate-100 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
                <h2 className="text-lg font-bold text-slate-800 dark:text-white flex items-center">
                  <FileText className="w-5 h-5 mr-2 text-indigo-500" /> Academic Guidelines
                </h2>
                <button onClick={() => setShowGuidelines(false)} className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 overflow-y-auto space-y-6">
                <div className="flex gap-4 items-start">
                  <div className="w-8 h-8 rounded-full bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center shrink-0 mt-0.5"><Users className="w-4 h-4 text-blue-500" /></div>
                  <div><h4 className="font-bold text-slate-800 dark:text-slate-200">Team Size limits</h4><p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">Maximum team size is 3 members. Teams must be finalized before the deadline.</p></div>
                </div>
                <div className="flex gap-4 items-start">
                  <div className="w-8 h-8 rounded-full bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center shrink-0 mt-0.5"><FileBadge className="w-4 h-4 text-indigo-500" /></div>
                  <div><h4 className="font-bold text-slate-800 dark:text-slate-200">Proposal Submission</h4><p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">Only the designated Team Leader is authorized to submit the final proposal document.</p></div>
                </div>
                <div className="flex gap-4 items-start">
                  <div className="w-8 h-8 rounded-full bg-rose-50 dark:bg-rose-500/10 flex items-center justify-center shrink-0 mt-0.5"><Clock className="w-4 h-4 text-rose-500" /></div>
                  <div><h4 className="font-bold text-slate-800 dark:text-slate-200">Strict Deadlines</h4><p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">Proposal submissions and milestone updates must be completed strictly before their deadlines. Late submissions are automatically locked.</p></div>
                </div>
                <div className="flex gap-4 items-start">
                  <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center shrink-0 mt-0.5"><Github className="w-4 h-4 text-slate-700 dark:text-slate-300" /></div>
                  <div><h4 className="font-bold text-slate-800 dark:text-slate-200">Code Repository</h4><p className="text-sm text-slate-600 dark:text-slate-400 mt-1 leading-relaxed">A valid GitHub repository link must be provided for all code submissions to track contributions.</p></div>
                </div>
              </div>
              <div className="p-5 border-t border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex justify-end">
                <button onClick={() => setShowGuidelines(false)} className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg text-sm font-semibold transition-colors shadow-md">Understood</button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Post-login reminders (deadlines + announcements) */}
      <ReminderWindow />
    </div>
  );
}
