/**
 * Checks a recording with the detection backend's POST /analyse.
 *
 * The browser decodes the file (anything it can play: mp3, m4a, ogg, webm,
 * wav...) and resamples it to 16 kHz mono PCM16, the format the model
 * pipeline takes, so the backend needs no codecs. Results stream back as
 * NDJSON, one event per scored window.
 */
import { BACKEND_HTTP, BACKEND_TOKEN } from '../app/backend';

export const SAMPLE_RATE = 16_000;
export const MAX_SECONDS = 30 * 60;

export interface AudioWindowResult {
  index: number;
  start_ms: number;
  end_ms: number;
  /** Utterance shorter than one model window, repeated to fill it */
  padded: boolean;
  label: 'likely_real' | 'uncertain' | 'likely_synthetic' | string;
  p_bonafide: number;
  p_spoof: number;
  detector?: string;
  detail?: string;
  latency_ms?: number;
  /** Running risk over the recording up to this window, 0..1 */
  session_risk: number;
  risk_band: 'low' | 'elevated' | 'high' | string;
}

export interface AudioSegment {
  start_ms: number;
  end_ms: number;
}

export interface AudioCheckSummary {
  segments: AudioSegment[];
  analysis: {
    speech_seconds: number;
    utterances: number;
    windows_emitted: number;
    unscored_speech_seconds: number;
    utterance_min_seconds: number;
  };
  risk: {
    session_risk: number;
    risk_band: string;
    recommendation: string;
    counts: Record<string, number>;
    mean_p_bonafide: number | null;
  };
}

export type AudioCheckEvent =
  | { type: 'start'; name: string; duration_ms: number; detector: string }
  | { type: 'progress'; processed_ms: number }
  | ({ type: 'window' } & AudioWindowResult)
  | ({ type: 'summary' } & AudioCheckSummary)
  | { type: 'error'; message: string };

export async function decodeToPcm16(file: File): Promise<{ pcm: Int16Array<ArrayBuffer>; durationSec: number }> {
  const bytes = await file.arrayBuffer();
  const context = new AudioContext();
  let decoded: AudioBuffer;
  try {
    decoded = await context.decodeAudioData(bytes);
  } catch {
    throw new Error(`This browser can't decode "${file.name}". Try WAV, MP3, M4A or OGG.`);
  } finally {
    void context.close();
  }
  if (decoded.duration > MAX_SECONDS) {
    throw new Error(`Recordings are limited to ${MAX_SECONDS / 60} minutes; this one is ${Math.round(decoded.duration / 60)}.`);
  }

  // A one-channel offline context downmixes and resamples in one pass.
  const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * SAMPLE_RATE)), SAMPLE_RATE);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const samples = (await offline.startRendering()).getChannelData(0);

  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return { pcm, durationSec: decoded.duration };
}

export async function analyseAudio(
  pcm: Int16Array<ArrayBuffer>,
  name: string,
  onEvent: (event: AudioCheckEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  if (!BACKEND_HTTP) {
    throw new Error('No detection backend is configured for this deployment yet.');
  }
  let response: Response;
  try {
    response = await fetch(`${BACKEND_HTTP}/analyse?name=${encodeURIComponent(name)}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        ...(BACKEND_TOKEN ? { Authorization: `Bearer ${BACKEND_TOKEN}` } : {}),
      },
      body: pcm,
      signal,
    });
  } catch (err) {
    if (signal.aborted) throw err;
    throw new Error(`Can't reach the detection backend at ${BACKEND_HTTP}. Is run_backend.ps1 running?`);
  }
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '');
    throw new Error(`The backend refused the recording (${response.status})${detail ? `: ${detail}` : ''}`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as AudioCheckEvent);
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AudioCheckEvent);
}
