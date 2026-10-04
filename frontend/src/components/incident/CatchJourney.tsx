import type { CSSProperties } from 'react';
import { formatInr, formatTimeIst } from '../../domain/format';
import type { Incident } from '../../domain/types';
import { attackTypeLabel, outcomeShort } from './labels';
import './incident.css';

interface Step {
  label: string;
  detail: string;
  at?: string;
  done: boolean;
}

/** Four-stage read of an incident's own data, not a separate model of "what should happen". */
function stepsFor(incident: Incident): Step[] {
  const alerted = incident.timeline.find((e) => e.actor === 'system' || e.actor === 'employee');
  const verified = incident.verification;
  const resolved = incident.status === 'contained' || incident.status === 'closed';

  return [
    {
      label: 'Detected',
      detail: `${incident.riskScore}% risk · ${attackTypeLabel[incident.attackType]}`,
      at: incident.createdAt,
      done: true,
    },
    {
      label: 'Alerted',
      detail: `${incident.receiver.name} warned mid-call`,
      at: alerted?.at,
      done: Boolean(alerted),
    },
    {
      label: 'Verified',
      detail: verified.summary,
      at: verified.at,
      done: Boolean(verified.at),
    },
    {
      label: resolved ? 'Blocked' : 'Resolving',
      detail: resolved
        ? outcomeShort[incident.outcome] + (incident.request.amountInr ? ` · ${formatInr(incident.request.amountInr)} stopped` : '')
        : 'Still with the security team',
      done: resolved,
    },
  ];
}

/** Animated 4-stage read of how a call was caught: Detected -> Alerted -> Verified -> Blocked. */
export function CatchJourney({ incident }: { incident: Incident }) {
  const steps = stepsFor(incident);
  return (
    <ol className="catch-journey" aria-label="How this call was caught">
      {steps.map((s, i) => (
        <li
          key={s.label}
          className={`catch-journey__step ${s.done ? 'is-done' : 'is-pending'}`}
          style={{ '--i': i } as CSSProperties}
        >
          <span className="catch-journey__node" aria-hidden="true">
            {s.done ? '✓' : i + 1}
          </span>
          <span className="catch-journey__text">
            <span className="catch-journey__label">{s.label}</span>
            <span className="catch-journey__detail">{s.detail}</span>
            {s.at && <span className="catch-journey__time tabular">{formatTimeIst(s.at)}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
