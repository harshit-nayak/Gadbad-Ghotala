/**
 * Service seam between UI and data.
 * The caller identity, request and transcript are still mock data. When the
 * detection backend has scored the call, the incident's risk and its
 * synthetic-speech signal come from the model instead of the script.
 */
import { createIncident78421, liveAnalysisScript, liveCall } from '../data/incident78421';
import type { CallOutcome, Incident, VerificationMethod } from '../domain/types';
import { detectionFeed, readSession } from './detectionFeed';

export const incidentService = {
  /** The active call on this employee's work device */
  getActiveCall: () => liveCall,

  /** Drives the simulated real-time analysis when the backend is offline */
  getLiveAnalysisScript: () => liveAnalysisScript,

  /** Called when the employee's call reaches an outcome */
  reportCallOutcome: (outcome: CallOutcome, method: VerificationMethod): Incident => {
    const incident = createIncident78421(outcome, method);
    const { session } = detectionFeed.getSnapshot();
    const readout = readSession(session);
    if (!session || readout.windows === 0) return incident;

    return {
      ...incident,
      riskScore: readout.score,
      riskLevel: readout.level,
      reasons: readout.reasons,
      signals: incident.signals.map((signal) =>
        signal.id === 'syntheticSpeech'
          ? {
              ...signal,
              risk: readout.score,
              reading: `${session.detector}: ${readout.synthetic} of ${readout.windows} speech windows likely synthetic, session risk ${readout.score}%.`,
              evidence: [
                `${readout.speechSeconds.toFixed(1)} s of caller speech analysed`,
                `Last window P(real) ${readout.last?.p_bonafide?.toFixed(3) ?? 'n/a'}`,
                `Backend session ${session.id.slice(0, 8)}`,
              ],
            }
          : signal,
      ),
    };
  },
};
