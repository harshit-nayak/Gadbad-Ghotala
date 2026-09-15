import { HashRouter, MemoryRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ToastProvider } from './components/ui/Toast';
import { Login } from './features/auth/Login';
import { Landing } from './features/landing/Landing';
import { AdminLayout } from './features/admin/AdminLayout';
import { Analytics } from './features/admin/Analytics';
import { OrganisationOverview } from './features/admin/OrganisationOverview';
import { ReportsAudit } from './features/admin/ReportsAudit';
import { DocumentAnalysisView } from './features/documents/DocumentAnalysisView';
import { DocumentHistory } from './features/documents/DocumentHistory';
import { DocumentReport } from './features/documents/DocumentReport';
import { DocumentSecurity } from './features/documents/DocumentSecurity';
import { DocumentsLayout } from './features/documents/DocumentsLayout';
import { CallOutcomeScreen } from './features/employee/CallOutcomeScreen';
import { EmployeeLayout } from './features/employee/EmployeeLayout';
import { HighRiskAlert } from './features/employee/HighRiskAlert';
import { IncomingCall } from './features/employee/IncomingCall';
import { LiveAnalysis } from './features/employee/LiveAnalysis';
import { VerifyRequest } from './features/employee/VerifyRequest';
import { IncidentAnalysis } from './features/security/IncidentAnalysis';
import { IncidentDetail } from './features/security/IncidentDetail';
import { IncidentList } from './features/security/IncidentList';
import { SecurityDashboard } from './features/security/SecurityDashboard';
import { SecurityLayout } from './features/security/SecurityLayout';
import { VoiceProfileDetail } from './features/security/VoiceProfileDetail';
import { VoiceProfiles } from './features/security/VoiceProfiles';
import { AuthProvider, useAuth } from './state/AuthProvider';
import { DemoProvider } from './state/DemoProvider';

/**
 * HashRouter keeps the prototype working on any static host without server
 * rewrites. Sandboxed previews (srcdoc/blob frames, such as file viewers) have
 * no usable URL, so there we fall back to in-memory routing. Swap to
 * BrowserRouter if the team deploys somewhere with SPA fallback configured.
 */
const hasUrlRouting = ['http:', 'https:', 'file:'].includes(window.location.protocol);
const Router = hasUrlRouting ? HashRouter : MemoryRouter;

/** Gate for the authenticated application; sends visitors to the login page. */
function RequireAuth() {
  const { isAuthenticated, status } = useAuth();
  const location = useLocation();
  if (!isAuthenticated) {
    // Signing out returns to the public site; a deep link goes to the login page.
    if (status === 'signed-out') return <Navigate to="/" replace />;
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <Outlet />;
}

export default function App() {
  return (
    <Router>
      <AuthProvider>
        <DemoProvider>
          <ToastProvider>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />

              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route path="employee" element={<EmployeeLayout />}>
                    <Route index element={null} />
                    <Route path="incoming" element={<IncomingCall />} />
                    <Route path="live" element={<LiveAnalysis />} />
                    <Route path="alert" element={<HighRiskAlert />} />
                    <Route path="verify" element={<VerifyRequest />} />
                    <Route path="outcome" element={<CallOutcomeScreen />} />
                  </Route>

                  <Route path="security" element={<SecurityLayout />}>
                    <Route index element={<SecurityDashboard />} />
                    <Route path="incidents" element={<IncidentList />} />
                    <Route path="incidents/:incidentId" element={<IncidentDetail />} />
                    <Route path="incidents/:incidentId/analysis" element={<IncidentAnalysis />} />
                    <Route path="profiles" element={<VoiceProfiles />} />
                    <Route path="profiles/:personId" element={<VoiceProfileDetail />} />
                  </Route>

                  <Route path="documents" element={<DocumentsLayout />}>
                    <Route index element={<DocumentSecurity />} />
                    <Route path="history" element={<DocumentHistory />} />
                    <Route path=":documentId" element={<DocumentReport />} />
                    <Route path=":documentId/analysis" element={<DocumentAnalysisView />} />
                  </Route>

                  <Route path="admin" element={<AdminLayout />}>
                    <Route index element={<OrganisationOverview />} />
                    <Route path="analytics" element={<Analytics />} />
                    <Route path="reports" element={<ReportsAudit />} />
                  </Route>

                  <Route path="*" element={<Navigate to="/employee" replace />} />
                </Route>
              </Route>
            </Routes>
          </ToastProvider>
        </DemoProvider>
      </AuthProvider>
    </Router>
  );
}
