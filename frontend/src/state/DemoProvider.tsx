import { createContext, useContext, useMemo, useReducer, type ReactNode } from 'react';
import { currentAnalyst } from '../data/people';
import type { AuditCategory, CallOutcome, DocumentAnalysis, IncidentStatus, VerificationMethod } from '../domain/types';
import { incidentService } from '../services/incidentService';
import { demoNowIso, uid } from './clock';
import { createInitialState, demoReducer, type DemoState } from './demoState';

interface DemoActions {
  acceptCall: () => void;
  /** A call the capture client picked up on its own; `at` is when it started */
  joinLiveCall: (at: number) => void;
  declineCall: () => void;
  /** Leave a call that ended without risk, without creating an incident */
  hangUp: () => void;
  showAlert: () => void;
  startVerify: () => void;
  resolveCall: (outcome: CallOutcome, method: VerificationMethod) => void;
  setIncidentStatus: (id: string, status: IncidentStatus, label: string) => void;
  assignIncident: (id: string) => void;
  addDocument: (document: DocumentAnalysis) => void;
  updateDocument: (id: string, patch: Partial<DocumentAnalysis>) => void;
  logAudit: (category: AuditCategory, actor: string, action: string, target: string) => void;
  resetDemo: () => void;
}

const DemoContext = createContext<{ state: DemoState; actions: DemoActions } | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(demoReducer, undefined, createInitialState);

  const actions = useMemo<DemoActions>(
    () => ({
      acceptCall: () => dispatch({ type: 'accept', at: Date.now() }),
      joinLiveCall: (at) => dispatch({ type: 'accept', at }),
      declineCall: () => dispatch({ type: 'decline' }),
      hangUp: () => dispatch({ type: 'hangUp' }),
      showAlert: () => dispatch({ type: 'showAlert' }),
      startVerify: () => dispatch({ type: 'startVerify' }),
      resolveCall: (outcome, method) =>
        dispatch({ type: 'resolve', outcome, incident: incidentService.reportCallOutcome(outcome, method) }),
      setIncidentStatus: (id, status, label) =>
        dispatch({
          type: 'updateIncident',
          id,
          status,
          event: { at: demoNowIso(), actor: 'security', label: `${label} by ${currentAnalyst}`, tone: status === 'closed' || status === 'contained' ? 'safe' : 'info' },
        }),
      assignIncident: (id) =>
        dispatch({
          type: 'updateIncident',
          id,
          status: 'investigating',
          assignee: currentAnalyst,
          event: { at: demoNowIso(), actor: 'security', label: `Assigned to ${currentAnalyst}`, tone: 'info' },
        }),
      addDocument: (document) => dispatch({ type: 'addDocument', document }),
      updateDocument: (id, patch) => dispatch({ type: 'updateDocument', id, patch }),
      logAudit: (category, actor, action, target) =>
        dispatch({ type: 'audit', event: { id: uid('audit'), at: demoNowIso(), category, actor, action, target } }),
      resetDemo: () => dispatch({ type: 'reset' }),
    }),
    [],
  );

  const value = useMemo(() => ({ state, actions }), [state, actions]);
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo() {
  const ctx = useContext(DemoContext);
  if (!ctx) throw new Error('useDemo must be used inside <DemoProvider>');
  return ctx;
}
