import type { DetectionSignal } from '../../domain/types';
import { riskColor } from './labels';
import { riskLevelFor } from '../../domain/risk';
import { signalColor, signalShortLabel } from './labels';
import './incident.css';

/**
 * Shows how each signal contributes to the weighted score:
 * contribution = weight × signal risk / total weight.
 */
export function SignalBreakdown({ signals, score }: { signals: DetectionSignal[]; score: number }) {
  const scored = signals.filter((s) => s.weight > 0);
  const totalWeight = scored.reduce((sum, s) => sum + s.weight, 0);
  const rows = scored
    .map((s) => ({ signal: s, contribution: (s.weight * s.risk) / totalWeight }))
    .sort((a, b) => b.contribution - a.contribution);
  const context = signals.filter((s) => s.weight === 0);

  return (
    <div className="breakdown">
      <div className="breakdown__composition">
        <div className="breakdown__bar" role="img" aria-label={`Score ${score} made up of weighted signal contributions`}>
          {rows.map(({ signal, contribution }) => (
            <span key={signal.id} style={{ width: `${contribution}%`, background: signalColor[signal.id] }} title={`${signalShortLabel[signal.id]}: ${contribution.toFixed(1)} points`} />
          ))}
        </div>
        <p className="breakdown__caption">
          <span className="tabular">{score}</span> of 100, sum of weighted signal contributions
        </p>
      </div>

      <table className="table table--signals">
        <caption className="visually-hidden">Detection signals and weighted contributions</caption>
        <thead>
          <tr>
            <th scope="col">Signal</th>
            <th scope="col" className="num">Weight</th>
            <th scope="col">Signal risk</th>
            <th scope="col" className="num">Contribution</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ signal, contribution }) => {
            const level = riskLevelFor(signal.risk);
            return (
              <tr key={signal.id}>
                <td>
                  <span className="signal-name">
                    <span className="legend__swatch" style={{ background: signalColor[signal.id] }} />
                    {signal.label}
                    {!signal.conclusive && <span className="signal-flag">Inconclusive</span>}
                  </span>
                  <span className="cell-sub">{signal.reading}</span>
                </td>
                <td className="num tabular muted">{signal.weight.toFixed(2)}</td>
                <td>
                  <span className="risk-score">
                    <span className="risk-score__value tabular">{signal.risk}</span>
                    <span className="risk-score__track risk-score__track--wide" aria-hidden="true">
                      <span style={{ width: `${signal.risk}%`, background: signal.conclusive ? riskColor[level] : 'var(--ink-subtle)' }} />
                    </span>
                  </span>
                </td>
                <td className="num tabular td-strong">+{contribution.toFixed(1)}</td>
              </tr>
            );
          })}
          {context.map((signal) => (
            <tr key={signal.id} className="table__row--context">
              <td>
                <span className="signal-name">{signal.label}</span>
                <span className="cell-sub">{signal.reading}</span>
              </td>
              <td className="num tabular muted">Context</td>
              <td className="muted">Confidence input, not scored</td>
              <td className="num muted">n/a</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
