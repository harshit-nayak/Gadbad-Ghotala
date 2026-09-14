/** Product areas and the employee call flow. Navigation UI reads from here. */
import type { IconName } from '../components/ui/Icon';
import type { CallStage } from '../state/demoState';

export type ThemeName = 'employee' | 'security' | 'documents' | 'admin';

export interface ProductArea {
  id: 'employee' | 'security' | 'documents' | 'admin';
  label: string;
  basePath: string;
  theme: ThemeName;
}

export const productAreas: ProductArea[] = [
  { id: 'employee', label: 'Employee', basePath: '/employee', theme: 'employee' },
  { id: 'security', label: 'Security', basePath: '/security', theme: 'security' },
  { id: 'documents', label: 'Documents', basePath: '/documents', theme: 'documents' },
  { id: 'admin', label: 'Administrator', basePath: '/admin', theme: 'admin' },
];

export const areaForPath = (pathname: string): ProductArea =>
  productAreas.find((area) => pathname.startsWith(area.basePath)) ?? productAreas[0];

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
    title: 'Security operations',
    links: [
      { label: 'Dashboard', to: '/security', icon: 'dashboard', end: true },
      { label: 'Incidents', to: '/security/incidents', icon: 'list' },
      { label: 'Voice profiles', to: '/security/profiles', icon: 'fingerprint' },
    ],
  },
  documents: {
    title: 'Document signing',
    links: [
      { label: 'Verify', to: '/documents', icon: 'shieldCheck', end: true },
      { label: 'Sign', to: '/documents/sign', icon: 'fileText' },
      { label: 'Admin', to: '/documents/admin', icon: 'userCheck' },
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
