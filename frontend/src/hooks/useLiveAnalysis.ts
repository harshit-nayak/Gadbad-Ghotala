/**
 * Real-time call analysis.
 *
 * With the detection backend connected, readings come from the deepfake model
 * via services/detectionFeed: one real check (AI-generated voice), scored per
 * window of the caller's speech, with the backend's session risk and band.
 * The other signals (voice match, prosody, context) have no model behind them
 * yet, so they are not shown in that mode.
 *
 * Without the backend, it simulates the analysis: each signal starts at a
 * provisional reading and settles on the final value from the incident data,
 * following the schedule in liveAnalysisScript.
 */
import { useCallback, useEffect, useState } from 'react';
import { riskLevelFor, weightedRiskScore } from '../domain/risk';
import type { RiskLevel, SignalId } from '../domain/types';
import { isLiveFeed, readSession, useDetectionFeed, type DetectionSession, type SessionReadout } from '../services/detectionFeed';
import { incidentService } from '../services/incidentService';

export type SignalState = 'waiting' | 'checking' | 'settled';

export interface LiveSignalReading {
  id: SignalId;
  risk: number;
  state: SignalState;
  /** Set when the level comes from the backend's risk band rather than the risk number */
  level?: RiskLevel;
}

export interface LiveAnalysis {
  source: 'backend' | 'simulated';
  progress: number;
  readings: LiveSignalReading[];
  score: number;
  level: RiskLevel;
  requestDetected: boolean;
  complete: boolean;
  skipToEnd: () => void;
  /** Backend mode only */
  session: DetectionSession | null;
  readout: SessionReadout | null;
  detector: string | null;
}

const clamp = (n: number, min = 0, max = 1) => Math.min(max, Math.max(min, n));
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export function useLiveAnalysis({ startComplete = false } = {}): LiveAnalysis {
  const feed = useDetectionFeed();
  const live = isLiveFeed(feed);
  const script = incidentService.getLiveAnalysisScript();
  const { signals } = incidentService.getActiveCall();
  const [progress, setProgress] = useState(startComplete ? 1 : 0);
  const [skipped, setSkipped] = useState(startComplete);
  const skipToEnd = useCallback(() => setSkipped(true), []);

  useEffect(() => {
    if (live) return;
    if (skipped) {
      setProgress(1);
      return;
    }
    const startedAt = performance.now();
    const id = window.setInterval(() => {
      const p = clamp((performance.now() - startedAt) / script.durationMs);
      setProgress(p);
      if (p >= 1) window.clearInterval(id);
    }, 100);
    return () => window.clearInterval(id);
  }, [live, skipped, script.durationMs]);

  if (live) {
    const { session } = feed;
    const readout = readSession(session);
    const scoring = session !== null && !session.ended;
    return {
      source: 'backend',
      progress: readout.windows > 0 ? 1 : 0,
      readings: [
        {
          id: 'syntheticSpeech',
          risk: readout.score,
          state: readout.windows > 0 ? 'settled' : scoring ? 'checking' : 'waiting',
          level: readout.level,
        },
      ],
      score: readout.score,
      level: readout.level,
      requestDetected: false,
      // The backend's high band already requires sustained evidence, so it raises the alert directly.
      complete: readout.level === 'high',
      skipToEnd,
      session,
      readout,
      detector: session?.detector ?? feed.detector,
    };
  }

  const readings: LiveSignalReading[] = signals.map((signal, index) => {
    const plan = script.signals[signal.id];
    if (progress < plan.start) {
      return { id: signal.id, risk: script.baselineRisk, state: 'waiting' };
    }
    const local = clamp((progress - plan.start) / (plan.end - plan.start));
    if (local >= 1) return { id: signal.id, risk: signal.risk, state: 'settled' };
    const jitter = Math.sin(progress * 80 + index * 1.7) * 6 * (1 - local);
    const risk = plan.from + (signal.risk - plan.from) * easeOutCubic(local) + jitter;
    return { id: signal.id, risk: Math.round(clamp(risk, 0, 100)), state: 'checking' };
  });

  const weights = Object.fromEntries(signals.map((s) => [s.id, s.weight]));
  const score = weightedRiskScore(readings.map((r) => ({ weight: weights[r.id], risk: r.risk })));

  return {
    source: 'simulated',
    progress,
    readings,
    score,
    level: riskLevelFor(score),
    requestDetected: progress >= script.requestDetectedAt,
    complete: progress >= 1,
    skipToEnd,
    session: null,
    readout: null,
    detector: null,
  };
}
