import { Routes, Route, Navigate } from 'react-router-dom';
import MentorLayout from './components/Mentor/MentorLayout';
import MentorHome from './pages/Mentor/MentorHome';
import AssignedTeams from './pages/Mentor/AssignedTeams';
import DetailedTeamView from './pages/Mentor/DetailedTeamView';
import GitHubAnalyzer from './pages/Mentor/GitHubAnalyzer';
import MentorEvaluationForm from './pages/Mentor/MentorEvaluationForm';
import Presentations from './pages/Mentor/Presentations';
import History from './pages/Mentor/History';
import MilestonesManager from './pages/Mentor/MilestonesManager';
import PmsChat from './pages/Mentor/PmsChat';
import Login from './pages/Login';
import Signup from './pages/Signup';
import ResetPassword from './pages/ResetPassword';
import Profile from './pages/profile/Profile';
import { AuthProvider } from './context/AuthContext';
import { GlobalFilterProvider } from './context/GlobalFilterContext';
import ProtectedRoute from './components/ProtectedRoute';
import PmsChatRoute from './components/PmsChatRoute';

function App() {
  return (
    <AuthProvider>
      <GlobalFilterProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        
        {/* Root redirect */}
        <Route path="/" element={<Navigate to="/login" replace />} />

        {/* Mentor Routes */}
        <Route path="/mentor" element={<ProtectedRoute><MentorLayout /></ProtectedRoute>}>
          <Route index element={<MentorHome />} />
          <Route path="teams" element={<AssignedTeams />} />
          <Route path="teams/:id" element={<DetailedTeamView />} />
          <Route path="analyzer" element={<GitHubAnalyzer />} />
          <Route path="evaluation" element={<MentorEvaluationForm />} />
          <Route path="presentations" element={<Presentations />} />
          <Route path="pms-chat" element={<PmsChatRoute><PmsChat /></PmsChatRoute>} />
          <Route path="history" element={<History />} />
          <Route path="milestones" element={<MilestonesManager />} />
          <Route path="profile" element={<Profile />} />
          <Route path="*" element={
            <div className="flex flex-col items-center justify-center p-12 bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm text-center m-6 min-h-[400px]">
              <h2 className="text-4xl font-black text-slate-900 dark:text-slate-100 mb-2">404</h2>
              <p className="text-slate-500 font-medium">This page could not be found.</p>
            </div>
          } />
        </Route>
        
        {/* Redirect trailing /panel traffic back to root safely just in case */}
        <Route path="/panel/*" element={<Navigate to="/login" replace />} />
      </Routes>
    </GlobalFilterProvider>
    </AuthProvider>
  );
}

export default App;
