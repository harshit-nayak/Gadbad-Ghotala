/** Product areas and navigation configuration. */
import type { IconName } from '../components/ui/Icon';
import type { CallStage } from '../state/demoState';

export type ThemeName = 'employee' | 'security' | 'documents' | 'admin';

export interface ProductArea {
  id: string;
  label: string;
  basePath: string;
  theme: ThemeName;
  /** Reached from other screens, not from the top tabs */
  hidden?: boolean;
}

export const productAreas: ProductArea[] = [
  { id: 'about', label: 'About', basePath: '/about', theme: 'employee' },
  { id: 'audio', label: 'Audio', basePath: '/audio', theme: 'employee' },
  { id: 'video', label: 'Video', basePath: '/video', theme: 'employee' },
  { id: 'documents', label: 'Document', basePath: '/documents', theme: 'documents' },
  { id: 'dashboard', label: 'Dashboard', basePath: '/dashboard', theme: 'employee' },

  // Hidden legacy / demo routes (accessible via deep-links or demo flow, not in top header)
  { id: 'employee', label: 'Employee', basePath: '/employee', theme: 'employee', hidden: true },
  { id: 'security', label: 'Security Ops', basePath: '/security', theme: 'security', hidden: true },
  { id: 'admin', label: 'Administrator', basePath: '/admin', theme: 'admin', hidden: true },
  { id: 'client', label: 'Capture client', basePath: '/client', theme: 'security', hidden: true },
  { id: 'report', label: 'Incident report', basePath: '/report', theme: 'documents', hidden: true },
];

export const areaForPath = (pathname: string): ProductArea =>
  productAreas.find((area) => pathname === area.basePath || pathname.startsWith(`${area.basePath}/`)) ?? productAreas[0];

/** The call state machine decides the route, so URL and state never disagree. */
export const pathForStage: Record<CallStage, string> = {
  incoming: '/employee/incoming',
  declined: '/employee/incoming',
  live: '/employee/live',
  alert: '/employee/alert',
  verify: '/employee/verify',
  outcome: '/employee/outcome',
};

export const employeeSteps: { stages: CallStage[]; label: string }[] = [
  { stages: ['incoming', 'declined'], label: 'Incoming call' },
  { stages: ['live'], label: 'Live analysis' },
  { stages: ['alert'], label: 'Risk alert' },
  { stages: ['verify'], label: 'Verify request' },
  { stages: ['outcome'], label: 'Outcome' },
];

export interface WorkspaceLink {
  label: string;
  to: string;
  icon: IconName;
  /** Match only the exact path */
  end?: boolean;
}

export const workspaceNav: Record<'security' | 'documents' | 'admin', { title: string; links: WorkspaceLink[] }> = {
  security: {
    title: 'Dashboard',
    links: [
      { label: 'Overview', to: '/dashboard', icon: 'dashboard', end: true },
      { label: 'Incidents', to: '/security/incidents', icon: 'list' },
      { label: 'Voice profiles', to: '/security/profiles', icon: 'fingerprint' },
    ],
  },
  documents: {
    title: 'Document verification & signing',
    links: [
      { label: 'Verify', to: '/documents', icon: 'shieldCheck', end: true },
      { label: 'Sign', to: '/documents/sign', icon: 'fileText' },
      { label: 'Admin', to: '/documents/admin', icon: 'userCheck' },
      { label: 'History', to: '/documents/history', icon: 'list' },
    ],
  },
  admin: {
    title: 'Administration',
    links: [
      { label: 'Overview', to: '/admin', icon: 'dashboard', end: true },
      { label: 'Analytics', to: '/admin/analytics', icon: 'chart' },
      { label: 'Reports & audit', to: '/admin/reports', icon: 'fileText' },
    ],
  },
};
