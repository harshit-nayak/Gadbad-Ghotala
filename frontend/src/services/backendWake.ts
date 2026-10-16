/**
 * Wakes a detection backend that sleeps between uses (call-monitor/deploy/aws).
 *
 * The hosted backend powers its machine off after a stretch with no analysis,
 * so on a quiet day the first check finds it asleep. When VITE_WAKE_URL is set,
 * that's not an error: ask the wake function to start the machine, then poll
 * /health until the model has loaded (it only answers once it has), and carry
 * on with the check. Locally, with no VITE_WAKE_URL, this is a quick no-op.
 */
import { BACKEND_HTTP, BACKEND_TOKEN } from '../app/backend';

export const WAKE_URL: string | null = import.meta.env.VITE_WAKE_URL
  ? import.meta.env.VITE_WAKE_URL.replace(/\/$/, '')
  : null;

/** Measured on EC2: ~37 s from start to answering over HTTPS. Allow for a slow day. */
const WAKE_TIMEOUT_MS = 5 * 60_000;
const POLL_MS = 5_000;

async function isAwake(): Promise<boolean> {
  if (!BACKEND_HTTP) return false;
  try {
    const response = await fetch(`${BACKEND_HTTP}/health`, { cache: 'no-store', signal: AbortSignal.timeout(8_000) });
    return response.ok;
  } catch {
    return false;
  }
}

async function requestWake(): Promise<void> {
  if (!WAKE_URL) return;
  const url = BACKEND_TOKEN ? `${WAKE_URL}?token=${encodeURIComponent(BACKEND_TOKEN)}` : WAKE_URL;
  try {
    await fetch(url, { method: 'POST', signal: AbortSignal.timeout(15_000) });
  } catch {
    // Retried on the next poll.
  }
}

/**
 * Resolves once the backend answers. Reports progress through onStatus while
 * waking. Without a wake URL it returns straight away and lets the caller's own
 * request fail with its usual "can't reach the backend" message.
 */
export async function ensureBackendAwake(onStatus: (message: string) => void, signal?: AbortSignal): Promise<void> {
  if (!BACKEND_HTTP || !WAKE_URL || (await isAwake())) return;

  const startedAt = Date.now();
  while (Date.now() - startedAt < WAKE_TIMEOUT_MS) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    // Re-sent each round: harmless while starting, and it catches a machine
    // that was still shutting down (which can't be started until it stops).
    await requestWake();
    const seconds = Math.round((Date.now() - startedAt) / 1000);
    onStatus(`The detector sleeps when unused to save cost. Waking it up, usually under a minute (${seconds} s so far)…`);
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    if (await isAwake()) return;
  }
  throw new Error('The detector did not wake up within 5 minutes. Try again, or check the server.');
}
