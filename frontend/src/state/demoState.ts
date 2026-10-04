import { incidentHistory } from '../data/incidentHistory';
import type { AuditEvent, CallOutcome, Incident, IncidentStatus, TimelineEvent } from '../domain/types';

export type CallStage = 'incoming' | 'declined' | 'live' | 'alert' | 'verify' | 'outcome';

export interface DemoState {
  stage: CallStage;
  /** Epoch ms when the call was accepted, drives the call timer */
  acceptedAt: number | null;
  outcome: CallOutcome | null;
  /** Newest first. Seeded history plus anything created this session. */
  incidents: Incident[];
  /** Audit entries for actions taken this session that are not incident timeline events */
  sessionAudit: AuditEvent[];
}

export type DemoAction =
  | { type: 'accept'; at: number }
  | { type: 'decline' }
  | { type: 'hangUp' }
  | { type: 'showAlert' }
  | { type: 'startVerify' }
  | { type: 'resolve'; outcome: CallOutcome; incident: Incident }
  | { type: 'updateIncident'; id: string; status?: IncidentStatus; assignee?: string; event: TimelineEvent }
  | { type: 'audit'; event: AuditEvent }
  | { type: 'reset' };

export const createInitialState = (): DemoState => ({
  stage: 'incoming',
  acceptedAt: null,
  outcome: null,
  incidents: [...incidentHistory].reverse(),
  sessionAudit: [],
});

export function demoReducer(state: DemoState, action: DemoAction): DemoState {
  switch (action.type) {
    case 'accept':
      return { ...state, stage: 'live', acceptedAt: action.at };
    case 'decline':
      return { ...state, stage: 'declined' };
    case 'hangUp':
      return { ...state, stage: 'incoming', acceptedAt: null, outcome: null };
    case 'showAlert':
      return { ...state, stage: 'alert' };
    case 'startVerify':
      return { ...state, stage: 'verify' };
    case 'resolve':
      return {
        ...state,
        stage: 'outcome',
        outcome: action.outcome,
        incidents: [action.incident, ...state.incidents.filter((i) => i.id !== action.incident.id)],
      };
    case 'updateIncident':
      return {
        ...state,
        incidents: state.incidents.map((i) =>
          i.id === action.id
            ? {
                ...i,
                status: action.status ?? i.status,
                assignee: action.assignee ?? i.assignee,
                timeline: [...i.timeline, action.event],
              }
            : i,
        ),
      };
    case 'audit':
      return { ...state, sessionAudit: [action.event, ...state.sessionAudit] };
    case 'reset':
      return createInitialState();
  }
}
