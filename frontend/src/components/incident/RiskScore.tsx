import type { RiskLevel } from '../../domain/types';
import { riskColor, riskLevelLabel } from './labels';
import './incident.css';

/** Compact score with a proportional bar, for tables. */
export function RiskScore({ score, level }: { score: number; level: RiskLevel }) {
  return (
    <span className="risk-score" aria-label={`Risk ${score}, ${riskLevelLabel[level]}`}>
      <span className="risk-score__value tabular">{score}</span>
      <span className="risk-score__track" aria-hidden="true">
        <span style={{ width: `${score}%`, background: riskColor[level] }} />
      </span>
    </span>
  );
}
