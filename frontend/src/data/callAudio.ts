/** Deterministic amplitude envelope for a call, shaped by who speaks when. */
import type { Incident } from '../domain/types';
import { hashString, seeded } from './seed';

export const SAMPLES_PER_SECOND = 4;

export interface SpeechTurn {
  start: number;
  end: number;
  speaker: 'caller' | 'employee';
}

export function speechTurns(incident: Incident): SpeechTurn[] {
  const lines = incident.transcript;
  return lines.map((line, i) => {
    const spoken = Math.max(2.5, line.text.length / 13);
    const next = lines[i + 1]?.at ?? incident.metadata.durationSec;
    return { start: line.at, end: Math.min(line.at + spoken, next - 0.6), speaker: line.speaker };
  });
}

export function callEnvelope(incident: Incident): number[] {
  const rng = seeded(hashString(incident.id));
  const turns = speechTurns(incident);
  const total = incident.metadata.durationSec * SAMPLES_PER_SECOND;
  const loud = incident.metadata.backgroundNoise.toLowerCase().includes('repeat');
  return Array.from({ length: total }, (_, i) => {
    const t = i / SAMPLES_PER_SECOND;
    const turn = turns.find((u) => t >= u.start && t <= u.end);
    // Repeating noise floor when a background loop was detected
    const floor = loud ? 0.06 + 0.03 * Math.abs(Math.sin(t * 2.3)) : 0.04 + rng.next() * 0.03;
    if (!turn) return floor;
    const syllable = 0.45 + 0.55 * Math.abs(Math.sin(t * 7.1 + rng.next()));
    const level = turn.speaker === 'caller' ? 0.95 : 0.62;
    return Math.min(1, floor + level * syllable * (0.7 + rng.next() * 0.3));
  });
}
