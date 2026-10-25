import { Routes, Route, Navigate } from 'react-router-dom';
import { useState, Suspense, lazy } from 'react';
import PanelLayout from './components/Panel/PanelLayout';
import { GlobalFilterProvider } from './context/GlobalFilterContext';
import PmsChatRoute from './components/PmsChatRoute';

// Lazy-load all page components — each page becomes a separate JS chunk that
// is only downloaded when the user navigates to that route for the first time.
const PanelHome            = lazy(() => import('./pages/Panel/PanelHome'));
const SlotTeamList         = lazy(() => import('./pages/Panel/SlotTeamList'));
const EvaluationParameters = lazy(() => import('./pages/Panel/EvaluationParameters'));
const TimeBoundEvaluation  = lazy(() => import('./pages/Panel/TimeBoundEvaluation'));
const MissedSubmissions    = lazy(() => import('./pages/Panel/MissedSubmissions'));
const SecureSubmissionReceipt = lazy(() => import('./pages/Panel/SecureSubmissionReceipt'));
const MentorTeams          = lazy(() => import('./pages/Panel/MentorTeams'));
const SlotManagement       = lazy(() => import('./pages/Panel/SlotManagement'));
const PmsChat              = lazy(() => import('./pages/Panel/PmsChat'));
const Login                = lazy(() => import('./pages/Login'));
const Signup               = lazy(() => import('./pages/Signup'));
const ResetPassword        = lazy(() => import('./pages/ResetPassword'));

// Shared loading fallback shown while a lazy chunk is downloading
const PageLoader = () => (
  <div className="flex items-center justify-center h-64">
    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-emerald-500" />
  </div>
);

// Module scope so it keeps one identity across renders. Declared inside App
// it was a new component type every render, which remounted the whole
// routed subtree — losing its state — whenever App re-rendered. It can no
// longer close over isAuthenticated, so that arrives as a prop.
const AuthRoute = ({ isAuthenticated, children }) =>
  isAuthenticated ? children : <Navigate to="/login" replace />;

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(localStorage.getItem('auth_token')));

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_info');
    setIsAuthenticated(false);
  };

  return (
    <GlobalFilterProvider>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<Login onLogin={() => setIsAuthenticated(true)} />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          
          {/* Root redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />

          {/* Panel Routes */}
          <Route path="/panel" element={<AuthRoute isAuthenticated={isAuthenticated}><PanelLayout onLogout={handleLogout} /></AuthRoute>}>
            <Route index element={<PanelHome />} />
            <Route path="slots" element={<SlotTeamList />} />
            <Route path="my-teams" element={<MentorTeams />} />
            <Route path="parameters" element={<EvaluationParameters />} />
            <Route path="pms-chat" element={<PmsChatRoute><PmsChat /></PmsChatRoute>} />
            <Route path="evaluation/:teamId" element={<TimeBoundEvaluation />} />
            <Route path="missed" element={<MissedSubmissions />} />
            <Route path="receipt/:teamId" element={<SecureSubmissionReceipt />} />
            <Route path="secure-receipt" element={<SecureSubmissionReceipt />} />
          </Route>

          {/* Redirect trailing /mentor traffic back to root safely just in case */}
          <Route path="/mentor/*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </GlobalFilterProvider>
  );
}

export default App;
