/**
 * Simulates real-time analysis for the prototype.
 * Each signal starts at a provisional reading and settles on the final value
 * from the incident data, following the schedule in liveAnalysisScript.
 *
 * Backend integration: replace this hook with a subscription (WebSocket/SSE)
 * that returns the same shape: { readings, score, level, requestDetected, complete }.
 */
import { useCallback, useEffect, useState } from 'react';
import { riskLevelFor, weightedRiskScore } from '../domain/risk';
import type { RiskLevel, SignalId } from '../domain/types';
import { incidentService } from '../services/incidentService';

export type SignalState = 'waiting' | 'checking' | 'settled';

export interface LiveSignalReading {
  id: SignalId;
  risk: number;
  state: SignalState;
}

export interface LiveAnalysis {
  progress: number;
  readings: LiveSignalReading[];
  score: number;
  level: RiskLevel;
  requestDetected: boolean;
  complete: boolean;
  skipToEnd: () => void;
}

const clamp = (n: number, min = 0, max = 1) => Math.min(max, Math.max(min, n));
const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export function useLiveAnalysis({ startComplete = false } = {}): LiveAnalysis {
  const script = incidentService.getLiveAnalysisScript();
  const { signals } = incidentService.getActiveCall();
  const [progress, setProgress] = useState(startComplete ? 1 : 0);
  const [skipped, setSkipped] = useState(startComplete);

  useEffect(() => {
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
  }, [skipped, script.durationMs]);

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
    progress,
    readings,
    score,
    level: riskLevelFor(score),
    requestDetected: progress >= script.requestDetectedAt,
    complete: progress >= 1,
    skipToEnd: useCallback(() => setSkipped(true), []),
  };
}
