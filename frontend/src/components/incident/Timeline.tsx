import { formatDateIst, formatTimeIst, formatTimeSecIst } from '../../domain/format';
import type { TimelineEvent } from '../../domain/types';
import './incident.css';

const actorLabel: Record<TimelineEvent['actor'], string> = {
  system: 'GG',
  employee: 'Employee',
  claimed_person: 'Claimed person',
  security: 'Security',
};

export function Timeline({ events, showDate = false }: { events: TimelineEvent[]; showDate?: boolean }) {
  return (
    <ol className="timeline">
      {events.map((e, index) => (
        <li key={`${e.at}-${index}`} className={`timeline__item timeline__item--${e.tone ?? 'info'}`}>
          <span className="timeline__dot" aria-hidden="true" />
          <span className="timeline__time tabular">
            {showDate ? `${formatDateIst(e.at)}, ${formatTimeIst(e.at)}` : formatTimeSecIst(e.at)}
          </span>
          <span className="timeline__body">
            <span className="timeline__label">{e.label}</span>
            <span className="timeline__actor">{actorLabel[e.actor]}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
