/**
 * Live feed from the detection backend (call-monitor/backend).
 *
 * The desktop capture client streams the WhatsApp call audio to /ws/audio; the
 * backend runs VAD and the deepfake model and publishes every session event on
 * /ws/monitor, which this module subscribes to. The UI reads it through
 * useDetectionFeed(). When the backend isn't reachable the store stays
 * 'offline' and the employee flow falls back to the simulated demo.
 *
 * Only the far track (the other party) drives risk; the backend scores the
 * near track too if DETECT_TRACKS includes it, but that is the employee's own voice.
 */
import { useSyncExternalStore } from 'react';
import { BACKEND_HTTP } from '../app/backend';
import type { RiskLevel } from '../domain/types';

export type FeedConnection = 'connecting' | 'open' | 'offline';

/** One scored window, as sent by the backend (app/models.py VerdictMessage). */
export interface Verdict {
  session_id: string;
  track: 'far' | 'near';
  sequence: number;
  /** P(spoof), 0..1 */
  score: number;
  label: 'likely_real' | 'uncertain' | 'likely_synthetic' | string;
  p_bonafide?: number | null;
  detector?: string | null;
  /** EMA of P(spoof) across the session, 0..1 */
  session_risk?: number | null;
  risk_band?: 'low' | 'elevated' | 'high' | string | null;
  recommendation?: string | null;
  speech_seconds?: number | null;
  /** Where the window's speech sits on the call timeline */
  window_start_ms?: number | null;
  window_end_ms?: number | null;
  padded?: boolean | null;
  latency_ms?: number | null;
}

export interface DetectionSession {
  id: string;
  source: string;
  /** Epoch ms */
  startedAt: number;
  detector: string;
  verdicts: Verdict[];
  ended: boolean;
}

export interface DetectionFeedState {
  connection: FeedConnection;
  /** Primary detector reported by /health; 'placeholder' means no real model loaded */
  detector: string | null;
  session: DetectionSession | null;
  /** Session the employee flow has already picked up, so a reset doesn't re-open it */
  handledSessionId: string | null;
}

const FEED_URL: string = import.meta.env.VITE_DETECTION_WS || `${BACKEND_HTTP.replace(/^http/, 'ws')}/ws/monitor`;
const RETRY_MS = [1000, 2000, 5000];

let state: DetectionFeedState = { connection: 'connecting', detector: null, session: null, handledSessionId: null };
const listeners = new Set<() => void>();
let socket: WebSocket | null = null;
let attempt = 0;

function set(patch: Partial<DetectionFeedState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

type SessionStart = { session_id: string; source?: string; started_at?: number; detector?: string };

const sessionFrom = (start: SessionStart, verdicts: Verdict[] = []): DetectionSession => ({
  id: start.session_id,
  source: start.source ?? '',
  startedAt: start.started_at ? start.started_at * 1000 : Date.now(),
  detector: start.detector ?? state.detector ?? 'unknown',
  verdicts: verdicts.filter((v) => v.track === 'far'),
  ended: false,
});

function handle(message: { type?: string; [key: string]: unknown }) {
  switch (message.type) {
    case 'hello': {
      const health = message.health as { detector?: string } | undefined;
      const active = (message.active as { session: SessionStart; verdicts: Verdict[] }[] | undefined) ?? [];
      const latest = active.at(-1);
      set({
        detector: health?.detector ?? null,
        // A session the backend no longer lists (it restarted mid-call) is over; keep it on screen as ended.
        session: latest
          ? sessionFrom(latest.session, latest.verdicts)
          : state.session && { ...state.session, ended: true },
      });
      break;
    }
    case 'session_start':
      set({ session: sessionFrom(message as unknown as SessionStart) });
      break;
    case 'verdict': {
      const verdict = message as unknown as Verdict;
      if (verdict.track !== 'far' || verdict.session_id !== state.session?.id) return;
      set({ session: { ...state.session, verdicts: [...state.session.verdicts, verdict] } });
      break;
    }
    case 'session_summary': {
      const { session } = state;
      if (session && message.session_id === session.id) set({ session: { ...session, ended: true } });
      break;
    }
  }
}

function connect() {
  set({ connection: attempt === 0 ? 'connecting' : state.connection });
  const ws = new WebSocket(FEED_URL);
  socket = ws;
  ws.onopen = () => {
    attempt = 0;
    set({ connection: 'open' });
  };
  ws.onmessage = (event) => {
    try {
      handle(JSON.parse(event.data as string));
    } catch {
      // A malformed frame is not worth tearing the feed down for.
    }
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    socket = null;
    set({ connection: 'offline' });
    window.setTimeout(connect, RETRY_MS[Math.min(attempt++, RETRY_MS.length - 1)]);
  };
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!socket) connect();
  return () => listeners.delete(listener);
}

export const detectionFeed = {
  url: FEED_URL,
  getSnapshot: () => state,
  subscribe,
  markHandled: (sessionId: string) => set({ handledSessionId: sessionId }),
};

export function useDetectionFeed(): DetectionFeedState {
  return useSyncExternalStore(subscribe, detectionFeed.getSnapshot);
}

/** True when the backend, not the scripted simulation, should drive the call screens. */
export const isLiveFeed = (feed: DetectionFeedState) => feed.connection === 'open' || feed.session !== null;

const levelForBand: Record<string, RiskLevel> = { low: 'low', elevated: 'medium', high: 'high' };

export interface SessionReadout {
  /** 0..100, session risk from the backend */
  score: number;
  level: RiskLevel;
  windows: number;
  synthetic: number;
  uncertain: number;
  speechSeconds: number;
  last: Verdict | null;
  recommendation: string | null;
  reasons: string[];
}

/** Plain summary of what the detector has said so far in a session. */
export function readSession(session: DetectionSession | null): SessionReadout {
  const verdicts = session?.verdicts ?? [];
  const last = verdicts.at(-1) ?? null;
  const synthetic = verdicts.filter((v) => v.label === 'likely_synthetic').length;
  const uncertain = verdicts.filter((v) => v.label === 'uncertain').length;
  const score = last ? Math.round((last.session_risk ?? last.score) * 100) : 0;
  const level = last?.risk_band ? (levelForBand[last.risk_band] ?? 'low') : 'low';

  const reasons: string[] = [];
  if (synthetic) {
    reasons.push(`${synthetic} of ${verdicts.length} stretches of the caller's speech sounded computer-generated.`);
  }
  if (uncertain) {
    reasons.push(`${uncertain} more ${uncertain === 1 ? 'stretch was' : 'stretches were'} unclear, neither clearly real nor synthetic.`);
  }
  if (last) reasons.push(`Overall synthetic-voice risk for this call is ${score}%.`);

  return {
    score,
    level,
    windows: verdicts.length,
    synthetic,
    uncertain,
    speechSeconds: last?.speech_seconds ?? 0,
    last,
    recommendation: last?.recommendation ?? null,
    reasons,
  };
}
