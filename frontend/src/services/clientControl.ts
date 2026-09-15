/**
 * The desktop capture client (call-monitor/client/app.py), seen through
 * its local control API. Polls while a page is subscribed and sends the same
 * commands as the client window's buttons.
 */
import { useSyncExternalStore } from 'react';
import { CLIENT_HTTP } from '../app/backend';

export interface ClientLogEntry {
  id: number;
  /** Epoch seconds */
  ts: number;
  text: string;
  /** likely_synthetic | uncertain | likely_real | error | info | silence | suspect */
  tag: string;
}

export interface ClientState {
  running: boolean;
  session_source: 'manual' | 'auto' | 'web' | null;
  session_id: string | null;
  status: string;
  server_url: string;
  token_set: boolean;
  far_devices: string[];
  near_devices: string[];
  far_device: string;
  near_device: string;
  chunk_seconds: string;
  auto_detect: boolean;
  process_names: string;
  require_speaker: boolean;
  auto_status: string;
  detector_tick: { mic: boolean; speaker: boolean } | null;
  stats: { far_sent: number; far_acked: number; near_sent: number; near_acked: number };
  risk: { value: number; band: 'low' | 'elevated' | 'high' | null; label: string; detail: string };
  log_seq: number;
}

export type ClientCommand = 'start' | 'stop' | 'auto_detect' | 'scan' | 'refresh_devices';

export interface ClientControlSnapshot {
  reachability: 'checking' | 'online' | 'offline';
  state: ClientState | null;
  log: ClientLogEntry[];
}

const POLL_MS = 700;
const LOG_KEEP = 500;

let snapshot: ClientControlSnapshot = { reachability: 'checking', state: null, log: [] };
const listeners = new Set<() => void>();
let timer: number | null = null;
let inFlight = false;

function set(patch: Partial<ClientControlSnapshot>) {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((listener) => listener());
}

async function poll() {
  if (inFlight) return;
  inFlight = true;
  const lastId = snapshot.log.at(-1)?.id ?? 0;
  try {
    const response = await fetch(`${CLIENT_HTTP}/state?since=${lastId}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(String(response.status));
    const { log, ...state } = (await response.json()) as ClientState & { log: ClientLogEntry[] };
    // The client restarted and its log ids began again: drop the old log; the next poll refetches from 0.
    const restarted = state.log_seq < lastId;
    set({ reachability: 'online', state, log: restarted ? [] : [...snapshot.log, ...log].slice(-LOG_KEEP) });
  } catch {
    if (snapshot.reachability !== 'offline') set({ reachability: 'offline', state: null });
  } finally {
    inFlight = false;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (timer === null) {
    void poll();
    timer = window.setInterval(() => void poll(), POLL_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}

export function useClientControl(): ClientControlSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot);
}

export async function sendClientCommand(command: ClientCommand, payload: Record<string, unknown> = {}): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${CLIENT_HTTP}/${command}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error(`Can't reach the capture client at ${CLIENT_HTTP}.`);
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { error?: string } | null;
    throw new Error(detail?.error ?? `The capture client refused ${command} (${response.status}).`);
  }
  // The command runs on the client's UI thread within ~100 ms; show its effect promptly.
  window.setTimeout(() => void poll(), 150);
}

export const clientControlUrl = CLIENT_HTTP;
