import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AdminLayout from './components/AdminLayout';

// Developed Pages
import Login from './pages/Login';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import StudentList from './pages/StudentList';
import StudentUpload from './pages/StudentUpload';
import MentorMasterData from './pages/MentorMasterData';
import SemesterSettings from './pages/SemesterSettings';
import ProposalList from './pages/ProposalList';
import ProposalViewer from './pages/ProposalViewer';
import TeamValidation from './pages/TeamValidation';
import MilestonesManager from './pages/MilestonesManager';
import Analysis from './pages/Analysis';
import ProjectAllocation from './pages/ProjectAllocation';
import MentorAllocation from './pages/MentorAllocation';
import Schedule from './pages/Schedule';
import PresentationCycles from './pages/PresentationCycles';
import Evaluations from './pages/Evaluations';
import Results from './pages/Results';
import Communication from './pages/Communication';
import PerTeamMail from './pages/PerTeamMail';
import Governance from './pages/Governance';
import Views from './pages/Views';
import AbsentStudents from './pages/AbsentStudents';
import ExtraActivities from './pages/ExtraActivities';
import GoogleAuthCallback from './pages/GoogleAuthCallback';
import RepoAnalysis from './pages/RepoAnalysis';
import ProcksiChat from './pages/ProcksiChat';
import { apiLogout, clearSession, getStoredSession, storeSession, setSessionExpiredHandler } from './lib/api';
import { GlobalFilterProvider } from './context/GlobalFilterContext';
import { PROCKSI_CHAT_ENABLED } from './config/features';

function App() {
  const [isAuthenticated, setIsAuthenticated] = React.useState(() => Boolean(getStoredSession()?.user));
  const [authUser, setAuthUser] = React.useState(() => getStoredSession()?.user || null);
  const [isCheckingAuth, setIsCheckingAuth] = React.useState(true);

  React.useEffect(() => {
    setIsCheckingAuth(false);
  }, []);

  // A session that cannot be renewed ends at the login screen. Without this the
  // app kept the dead token and every component retried with it, which is why
  // one expiry produced a wall of repeating 401s.
  React.useEffect(() => {
    setSessionExpiredHandler(() => {
      clearSession();
      setIsAuthenticated(false);
      setAuthUser(null);
    });
    return () => setSessionExpiredHandler(null);
  }, []);

  const handleLogin = (sessionPayload) => {
    storeSession(sessionPayload);
    setIsAuthenticated(Boolean(sessionPayload?.user));
    setAuthUser(sessionPayload?.user ?? null);
  };

  const handleLogout = async () => {
    const existingSession = getStoredSession();

    try {
      await apiLogout(existingSession?.access_token || null);
    } catch (error) {
      console.error('Logout endpoint failed:', error.message);
    }

    clearSession();
    setIsAuthenticated(false);
    setAuthUser(null);
  };

  if (isCheckingAuth) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-900 text-slate-600 dark:text-slate-300 font-semibold">
        Verifying session...
      </div>
    );
  }

  return (
    <GlobalFilterProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to={isAuthenticated ? "/admin/dashboard" : "/admin/login"} replace />} />
          
          <Route path="/auth/google/callback" element={<GoogleAuthCallback />} />

          <Route path="/admin/login" element={
            !isAuthenticated ? <Login onLogin={handleLogin} /> : <Navigate to="/admin/dashboard" replace />
          } />

          <Route path="/admin/reset-password" element={<ResetPassword />} />

          <Route path="/admin" element={
            isAuthenticated ? <AdminLayout onLogout={handleLogout} adminUser={authUser} /> : <Navigate to="/admin/login" replace />
          }>
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            
            <Route path="students" element={<StudentList />} />
            <Route path="students/upload" element={<StudentUpload />} />
            <Route path="mentor-master" element={<MentorMasterData />} />
            <Route path="semester-settings" element={<SemesterSettings />} />
            
            <Route path="proposals" element={<ProposalList />} />
            <Route path="proposals/view/:id" element={<ProposalViewer />} />
            <Route path="teams" element={<TeamValidation />} />
            <Route path="milestones" element={<MilestonesManager />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="project-allocations" element={<ProjectAllocation />} />
            
            <Route path="mentors" element={<MentorAllocation />} />
            <Route path="schedule" element={<Schedule />} />
            <Route path="presentation-cycles" element={<PresentationCycles />} />
            <Route path="procksi-chat" element={PROCKSI_CHAT_ENABLED ? <ProcksiChat /> : <Navigate to="/admin/dashboard" replace />} />
            <Route path="evaluations" element={<Evaluations />} />
            
            <Route path="results" element={<Results />} />
            <Route path="communication" element={<Communication />} />
            <Route path="communication/per-team" element={<PerTeamMail />} />
            <Route path="governance" element={<Governance />} />
            <Route path="views" element={<Views />} />
            <Route path="absent-students" element={<AbsentStudents />} />
            <Route path="extra-activities" element={<ExtraActivities />} />
            <Route path="repo-analysis" element={<RepoAnalysis />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </GlobalFilterProvider>
  );
}

export default App;
