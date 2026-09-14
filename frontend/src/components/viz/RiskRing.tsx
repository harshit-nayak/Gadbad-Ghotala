import type { RiskLevel } from '../../domain/types';
import './viz.css';

interface RiskRingProps {
  score: number;
  level: RiskLevel;
  size?: number;
  stroke?: number;
}

export function RiskRing({ score, level, size = 72, stroke = 6 }: RiskRingProps) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(100, Math.max(0, score)) / 100);

  return (
    <div
      className={`risk-ring risk-ring--${level}`}
      style={{ width: size, height: size }}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-label={`Risk score ${score} out of 100, ${level}`}
    >
      <svg viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle className="risk-ring__track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        <circle
          className="risk-ring__value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="risk-ring__score tabular">{score}</span>
    </div>
  );
}
