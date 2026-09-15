/**
 * Service seam between UI and data.
 * The prototype returns mock data synchronously. When the backend exists,
 * replace these bodies with API calls and keep the signatures (or make them
 * async and move the calls into effects / a query library).
 */
import { createIncident78421, liveAnalysisScript, liveCall } from '../data/incident78421';
import type { CallOutcome, Incident, VerificationMethod } from '../domain/types';

export const incidentService = {
  /** The active call on this employee's work device */
  getActiveCall: () => liveCall,

  /** Drives the simulated real-time analysis in the prototype only */
  getLiveAnalysisScript: () => liveAnalysisScript,

  /** Called when the employee's call reaches an outcome */
  reportCallOutcome: (outcome: CallOutcome, method: VerificationMethod): Incident =>
    createIncident78421(outcome, method),
};
