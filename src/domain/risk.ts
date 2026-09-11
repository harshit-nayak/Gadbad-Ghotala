import type { DetectionSignal, RiskLevel } from './types';

/**
 * Score bands. Placeholder values for the prototype: the research team
 * should replace these with calibrated thresholds.
 */
export const RISK_THRESHOLDS = { medium: 40, high: 70 } as const;

export function riskLevelFor(score: number): RiskLevel {
  if (score >= RISK_THRESHOLDS.high) return 'high';
  if (score >= RISK_THRESHOLDS.medium) return 'medium';
  return 'low';
}

/** Weighted average of signal risks, normalised by total weight. */
export function weightedRiskScore(signals: Pick<DetectionSignal, 'weight' | 'risk'>[]): number {
  const totalWeight = signals.reduce((sum, s) => sum + s.weight, 0);
  if (totalWeight === 0) return 0;
  const weighted = signals.reduce((sum, s) => sum + s.weight * s.risk, 0);
  return Math.round(weighted / totalWeight);
}

export type Recommendation = 'stop' | 'verify' | 'continue';

export function recommendationFor(level: RiskLevel, hasSensitiveRequest: boolean): Recommendation {
  if (level === 'high') return 'stop';
  if (level === 'medium' || hasSensitiveRequest) return 'verify';
  return 'continue';
}
