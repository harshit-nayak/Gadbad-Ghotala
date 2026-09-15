import type { ReactNode } from 'react';
import { formatClock } from '../../domain/format';
import type { Incident, TranscriptLine } from '../../domain/types';
import './incident.css';

function highlight(line: TranscriptLine): ReactNode {
  if (!line.flags?.length) return line.text;
  const parts: ReactNode[] = [];
  let rest = line.text;
  let key = 0;
  while (rest) {
    const hits = line.flags.map((f) => ({ f, i: rest.indexOf(f) })).filter((h) => h.i >= 0).sort((a, b) => a.i - b.i);
    if (!hits.length) {
      parts.push(rest);
      break;
    }
    const { f, i } = hits[0];
    if (i > 0) parts.push(rest.slice(0, i));
    parts.push(<mark key={key++} className="flagged">{f}</mark>);
    rest = rest.slice(i + f.length);
  }
  return parts;
}

interface TranscriptProps {
  incident: Incident;
  activeAt?: number;
  onSeek?: (seconds: number) => void;
  onlyFlagged?: boolean;
}

export function Transcript({ incident, activeAt, onSeek, onlyFlagged = false }: TranscriptProps) {
  const lines = onlyFlagged ? incident.transcript.filter((l) => l.flags?.length) : incident.transcript;
  const activeIndex = activeAt === undefined ? -1 : incident.transcript.filter((l) => l.at <= activeAt).length - 1;

  return (
    <ol className="transcript">
      {lines.map((line) => {
        const index = incident.transcript.indexOf(line);
        const speaker = line.speaker === 'caller' ? `Caller (claims ${incident.claimedIdentity.name.split(' ')[0]})` : incident.receiver.name;
        return (
          <li key={line.at} className={`transcript__line transcript__line--${line.speaker} ${index === activeIndex ? 'is-active' : ''}`}>
            {onSeek ? (
              <button type="button" className="transcript__time tabular" onClick={() => onSeek(line.at)} aria-label={`Jump to ${formatClock(line.at)}`}>
                {formatClock(line.at)}
              </button>
            ) : (
              <span className="transcript__time tabular">{formatClock(line.at)}</span>
            )}
            <span className="transcript__speaker">{speaker}</span>
            <p className="transcript__text">{highlight(line)}</p>
          </li>
        );
      })}
    </ol>
  );
}
