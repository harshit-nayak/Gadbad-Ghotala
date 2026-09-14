import { useEffect, useMemo, useRef, useState } from 'react';
import { callEnvelope, speechTurns } from '../../data/callAudio';
import { formatClock } from '../../domain/format';
import type { AudioRegion, Incident } from '../../domain/types';
import { useElementWidth } from '../../hooks/useElementWidth';
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion';
import { Icon } from '../ui/Icon';
import { riskColor, signalShortLabel } from './labels';
import './incident.css';

interface CallAudioProps {
  incident: Incident;
  position: number;
  onSeek: (seconds: number) => void;
  height?: number;
  showRegions?: boolean;
  selectedRegion?: AudioRegion | null;
  onSelectRegion?: (region: AudioRegion) => void;
}

/**
 * Recorded-call waveform with the regions where signals fired.
 * "Replay analysis" moves the playhead at 3x so analysts can watch the
 * signals trigger in order; it does not play audio.
 */
export function CallAudio({ incident, position, onSeek, height = 120, showRegions = true, selectedRegion, onSelectRegion }: CallAudioProps) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const [playing, setPlaying] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const positionRef = useRef(position);
  positionRef.current = position;

  const duration = incident.metadata.durationSec;
  const envelope = useMemo(() => callEnvelope(incident), [incident]);
  const turns = useMemo(() => speechTurns(incident), [incident]);
  const barW = 3;
  const gap = 1.5;
  const count = Math.max(10, Math.floor(width / (barW + gap)));
  const bars = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => {
        const from = Math.floor((i / count) * envelope.length);
        const to = Math.max(from + 1, Math.floor(((i + 1) / count) * envelope.length));
        return Math.max(...envelope.slice(from, to));
      }),
    [count, envelope],
  );
  const x = (sec: number) => (sec / duration) * width;
  const waveTop = 18;
  const waveH = height - waveTop - 22;
  const mid = waveTop + waveH / 2;

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const next = positionRef.current + ((now - last) / 1000) * (reducedMotion ? 10 : 3);
      last = now;
      if (next >= duration) {
        onSeek(duration);
        setPlaying(false);
        return;
      }
      onSeek(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, duration, onSeek, reducedMotion]);

  const seekFromEvent = (clientX: number, target: Element) => {
    const rect = target.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(duration, ((clientX - rect.left) / rect.width) * duration)));
  };
  const ticks = Array.from({ length: Math.floor(duration / 15) + 1 }, (_, i) => i * 15);

  return (
    <div className="call-audio">
      <div className="call-audio__controls">
        <button
          type="button"
          className="call-audio__play"
          onClick={() => {
            if (position >= duration) onSeek(0);
            setPlaying((p) => !p);
          }}
          aria-pressed={playing}
        >
          <Icon name={playing ? 'pause' : 'play'} size={14} />
          {playing ? 'Pause replay' : 'Replay analysis'}
        </button>
        <span className="call-audio__time tabular">
          {formatClock(position)} / {formatClock(duration)}
        </span>
        <span className="call-audio__legend">
          <span><i className="swatch swatch--caller" />Caller</span>
          <span><i className="swatch swatch--employee" />Employee</span>
        </span>
      </div>

      <div className="call-audio__stage" ref={ref}>
        <svg
          width={width}
          height={height}
          role="slider"
          tabIndex={0}
          aria-label="Call audio position"
          aria-valuemin={0}
          aria-valuemax={duration}
          aria-valuenow={Math.round(position)}
          aria-valuetext={formatClock(position)}
          onClick={(e) => seekFromEvent(e.clientX, e.currentTarget)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowRight') onSeek(Math.min(duration, position + 5));
            if (e.key === 'ArrowLeft') onSeek(Math.max(0, position - 5));
          }}
        >
          {showRegions &&
            incident.audioRegions.map((r, i) => {
              const selected = selectedRegion === r;
              const active = position >= r.start && position <= r.end;
              return (
                <rect
                  key={i}
                  x={x(r.start)}
                  y={waveTop - 4}
                  width={Math.max(2, x(r.end) - x(r.start))}
                  height={waveH + 8}
                  rx={4}
                  className={`call-audio__region ${selected || active ? 'is-active' : ''}`}
                  style={{ fill: riskColor[r.level] }}
                />
              );
            })}
          {turns.map((t, i) => (
            <rect key={`turn-${i}`} x={x(t.start)} y={4} width={Math.max(2, x(t.end) - x(t.start))} height={4} rx={2} className={`call-audio__turn call-audio__turn--${t.speaker}`} />
          ))}
          {bars.map((v, i) => {
            const sec = (i / count) * duration;
            const turn = turns.find((t) => sec >= t.start && sec <= t.end);
            const h = Math.max(2, v * waveH);
            return (
              <rect
                key={i}
                x={i * (barW + gap)}
                y={mid - h / 2}
                width={barW}
                height={h}
                rx={1.5}
                className={`call-audio__bar ${sec <= position ? 'is-played' : ''} ${turn?.speaker === 'employee' ? 'is-employee' : ''}`}
              />
            );
          })}
          <line x1={x(position)} x2={x(position)} y1={2} y2={height - 20} className="call-audio__playhead" />
          {ticks.map((t) => (
            <text key={t} x={Math.min(width - 14, x(t))} y={height - 4} className="call-audio__tick" textAnchor={t === 0 ? 'start' : 'middle'}>
              {formatClock(t)}
            </text>
          ))}
        </svg>
      </div>

      {showRegions && onSelectRegion && (
        <ul className="region-list">
          {incident.audioRegions.map((r, i) => (
            <li key={i}>
              <button
                type="button"
                className={`region-chip ${selectedRegion === r ? 'is-selected' : ''} ${position >= r.start && position <= r.end ? 'is-live' : ''}`}
                onClick={() => {
                  onSelectRegion(r);
                  onSeek(r.start);
                }}
              >
                <span className="region-chip__dot" style={{ background: riskColor[r.level] }} />
                <span className="tabular region-chip__time">
                  {formatClock(r.start)}–{formatClock(r.end)}
                </span>
                <span className="region-chip__signal">{signalShortLabel[r.signal]}</span>
                <span className="region-chip__label">{r.label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

