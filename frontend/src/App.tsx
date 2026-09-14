import { HashRouter, MemoryRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { ToastProvider } from './components/ui/Toast';
import { AdminLayout } from './features/admin/AdminLayout';
import { Analytics } from './features/admin/Analytics';
import { OrganisationOverview } from './features/admin/OrganisationOverview';
import { ReportsAudit } from './features/admin/ReportsAudit';
import { AdminDocuments } from './features/documents/AdminDocuments';
import { DocumentsLayout } from './features/documents/DocumentsLayout';
import { SignDocument } from './features/documents/SignDocument';
import { VerifyDocument } from './features/documents/VerifyDocument';
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
import { DemoProvider } from './state/DemoProvider';

/**
 * HashRouter keeps the prototype working on any static host without server
 * rewrites. Sandboxed previews (srcdoc/blob frames, such as file viewers) have
 * no usable URL, so there we fall back to in-memory routing. Swap to
 * BrowserRouter if the team deploys somewhere with SPA fallback configured.
 */
const hasUrlRouting = ['http:', 'https:', 'file:'].includes(window.location.protocol);
const Router = hasUrlRouting ? HashRouter : MemoryRouter;

export default function App() {
  return (
    <Router>
      <DemoProvider>
        <ToastProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<Navigate to="/employee" replace />} />

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
                <Route index element={<VerifyDocument />} />
                <Route path="sign" element={<SignDocument />} />
                <Route path="admin" element={<AdminDocuments />} />
              </Route>

              <Route path="admin" element={<AdminLayout />}>
                <Route index element={<OrganisationOverview />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="reports" element={<ReportsAudit />} />
              </Route>

              <Route path="*" element={<Navigate to="/employee" replace />} />
            </Route>
          </Routes>
        </ToastProvider>
      </DemoProvider>
    </Router>
  );
}
