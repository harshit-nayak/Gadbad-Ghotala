import type { ReactNode } from 'react';
import { HashRouter, MemoryRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthLoading, SignIn } from './features/auth/SignIn';
import { AuthProvider, useAuth } from './state/AuthProvider';
import { AppShell } from './components/layout/AppShell';
import { CaptureClient } from './features/client/CaptureClient';
import { ReportPage } from './features/report/ReportPage';
import { ToastProvider } from './components/ui/Toast';
import { AdminLayout } from './features/admin/AdminLayout';
import { Analytics } from './features/admin/Analytics';
import { OrganisationOverview } from './features/admin/OrganisationOverview';
import { ReportsAudit } from './features/admin/ReportsAudit';
import { AdminDocuments } from './features/documents/AdminDocuments';
import { DocumentHistory } from './features/documents/DocumentHistory';
import { DocumentsLayout } from './features/documents/DocumentsLayout';
import { SignDocument } from './features/documents/SignDocument';
import { VerifyDocument } from './features/documents/VerifyDocument';
import { CallOutcomeScreen } from './features/employee/CallOutcomeScreen';
import { EmployeeLayout } from './features/employee/EmployeeLayout';
import { HighRiskAlert } from './features/employee/HighRiskAlert';
import { IncomingCall } from './features/employee/IncomingCall';
import { LiveAnalysis } from './features/employee/LiveAnalysis';
import { VerifyRequest } from './features/employee/VerifyRequest';
import { AudioCheck } from './features/security/AudioCheck';
import { IncidentAnalysis } from './features/security/IncidentAnalysis';
import { IncidentDetail } from './features/security/IncidentDetail';
import { IncidentList } from './features/security/IncidentList';
import { SecurityDashboard } from './features/security/SecurityDashboard';
import { VoiceProfileDetail } from './features/security/VoiceProfileDetail';
import { VoiceProfiles } from './features/security/VoiceProfiles';
import { DemoProvider } from './state/DemoProvider';
import { Landing } from './features/landing/Landing';

import { VideoCheck } from './features/video/VideoCheck';

/**
 * HashRouter keeps the prototype working on any static host without server
 * rewrites. Sandboxed previews (srcdoc/blob frames, such as file viewers) have
 * no usable URL, so there we fall back to in-memory routing. Swap to
 * BrowserRouter if the team deploys somewhere with SPA fallback configured.
 */
const hasUrlRouting = ['http:', 'https:', 'file:'].includes(window.location.protocol);
const Router = hasUrlRouting ? HashRouter : MemoryRouter;

/** With Supabase configured, nothing renders until the user has signed in. Without it, the app runs open. */
function AuthGate({ children }: { children: ReactNode }) {
  const { configured, loading, session } = useAuth();
  if (!configured) return <>{children}</>;
  if (loading) return <AuthLoading />;
  if (!session) return <SignIn />;
  return <>{children}</>;
}

/** The gated console: everything behind the public landing page at "/". */
function Console() {
  return (
    <AuthGate>
      <DemoProvider>
        <ToastProvider>
          <Routes>
            <Route element={<AppShell />}>
              {/* Primary Platform Modules */}
              <Route path="audio" element={<AudioCheck />} />
              <Route path="video" element={<VideoCheck />} />
              <Route path="dashboard" element={<SecurityDashboard />} />

              <Route path="documents" element={<DocumentsLayout />}>
                <Route index element={<VerifyDocument />} />
                <Route path="sign" element={<SignDocument />} />
                <Route path="admin" element={<AdminDocuments />} />
                <Route path="history" element={<DocumentHistory />} />
              </Route>

              {/* Aliases for old /security paths */}
              <Route path="security/audio" element={<Navigate to="/audio" replace />} />
              <Route path="security" element={<Navigate to="/dashboard" replace />} />
              <Route path="security/incidents" element={<IncidentList />} />
              <Route path="security/incidents/:incidentId" element={<IncidentDetail />} />
              <Route path="security/incidents/:incidentId/analysis" element={<IncidentAnalysis />} />
              <Route path="security/profiles" element={<VoiceProfiles />} />
              <Route path="security/profiles/:personId" element={<VoiceProfileDetail />} />

              {/* Employee Call Protection Flow */}
              <Route path="employee" element={<EmployeeLayout />}>
                <Route index element={null} />
                <Route path="incoming" element={<IncomingCall />} />
                <Route path="live" element={<LiveAnalysis />} />
                <Route path="alert" element={<HighRiskAlert />} />
                <Route path="verify" element={<VerifyRequest />} />
                <Route path="outcome" element={<CallOutcomeScreen />} />
              </Route>

              {/* Administrator */}
              <Route path="admin" element={<AdminLayout />}>
                <Route index element={<OrganisationOverview />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="reports" element={<ReportsAudit />} />
              </Route>

              <Route path="client" element={<CaptureClient />} />
              <Route path="report" element={<ReportPage />} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </ToastProvider>
      </DemoProvider>
    </AuthGate>
  );
}

export default function App() {
  return (
    <Router>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/about" element={<Landing />} />
          <Route path="/signin" element={<SignIn />} />
          <Route path="/*" element={<Console />} />
        </Routes>
      </AuthProvider>
    </Router>
  );
}
