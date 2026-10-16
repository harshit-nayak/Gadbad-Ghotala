/**
 * Streams the browser microphone to the detection backend's /ws/audio, live.
 *
 * Speaks the same protocol as the desktop capture client (call-monitor/client):
 * a `session_start`, then per chunk an `audio_chunk` metadata frame followed by
 * a binary frame of PCM16 16 kHz mono, then `session_end`. The mic is sent as
 * the `far` track -- the one the backend scores -- so the backend needs no
 * changes: its Silero VAD, per-utterance windowing, model and risk tracker run
 * exactly as on a WhatsApp call, and verdicts come back on the same socket
 * (and go out on /ws/monitor to the live screen).
 */
import { BACKEND_HTTP, BACKEND_TOKEN } from '../app/backend';
import { StreamingResampler, floatToPcm16 } from '../lib/resampler';

const SAMPLE_RATE = 16_000;
/** 1 s chunks: the backend's VAD settles per chunk, so shorter = earlier verdicts. */
const CHUNK_SAMPLES = SAMPLE_RATE;
/** How long to wait after session_end for the backend to score what's queued. */
const SUMMARY_TIMEOUT_MS = 30_000;
const CONNECT_TIMEOUT_MS = 10_000;

export interface LiveVerdict {
  sequence: number;
  label: 'likely_real' | 'uncertain' | 'likely_synthetic' | string;
  p_bonafide: number;
  p_spoof: number;
  session_risk: number;
  risk_band: 'low' | 'elevated' | 'high' | string;
  recommendation?: string | null;
  detector?: string;
  speech_seconds?: number;
  window_start_ms?: number | null;
  window_end_ms?: number | null;
  padded?: boolean;
  latency_ms?: number;
}

export interface LiveSummary {
  detector: string;
  tracks: Record<string, {
    speech_seconds: number;
    utterances: number;
    windows_emitted: number;
    unscored_speech_seconds: number;
    utterance_min_seconds: number;
  }>;
  risk: Record<string, {
    session_risk: number;
    risk_band: string;
    recommendation: string;
  }>;
}

export type LiveMicEvent =
  | { type: 'level'; rms: number }
  | { type: 'chunk_sent'; seconds: number }
  | { type: 'verdict'; verdict: LiveVerdict }
  | { type: 'summary'; summary: LiveSummary }
  | { type: 'error'; message: string };

export interface LiveMicSession {
  sessionId: string;
  /** Stop capturing, let the backend finish scoring, resolve once it has summarised. */
  stop: () => Promise<void>;
}

/**
 * Downmixes every 128-frame render quantum to mono and posts it in 2048-frame
 * blocks (~43 ms at 48 kHz) -- fewer, larger messages to the main thread.
 * Inline as a Blob URL so it needs no separate file in the build.
 */
const WORKLET = `
class GgMicCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const input = inputs[0];
    if (input && input.length) {
      const frames = input[0].length;
      for (let i = 0; i < frames; i++) {
        let s = 0;
        for (let c = 0; c < input.length; c++) s += input[c][i];
        this.buf[this.n++] = s / input.length;
        if (this.n === this.buf.length) {
          this.port.postMessage(this.buf, [this.buf.buffer]);
          this.buf = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor('gg-mic-capture', GgMicCapture);
`;

const wsUrl = (base: string) => {
  const url = `${base.replace(/^http/, 'ws')}/ws/audio`;
  // Query string, not an Authorization header: browsers can't set headers on
  // a WebSocket handshake. The backend accepts either.
  return BACKEND_TOKEN ? `${url}?token=${encodeURIComponent(BACKEND_TOKEN)}` : url;
};

function openSocket(url: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error(`Can't reach the detection backend at ${BACKEND_HTTP} (timed out).`));
    }, CONNECT_TIMEOUT_MS);
    ws.onopen = () => {
      clearTimeout(timer);
      resolve(ws);
    };
    ws.onclose = (event) => {
      clearTimeout(timer);
      reject(new Error(
        event.code === 1008
          ? 'The detection backend rejected the connection: its auth token does not match VITE_BACKEND_TOKEN.'
          : `Can't reach the detection backend at ${BACKEND_HTTP}.`,
      ));
    };
  });
}

/**
 * Asks for the mic, connects, and starts streaming. Throws (before anything is
 * left running) if there's no backend, no mic permission, or no connection.
 */
export async function startLiveMic(onEvent: (event: LiveMicEvent) => void): Promise<LiveMicSession> {
  if (!BACKEND_HTTP) {
    throw new Error('No detection backend is configured for this deployment yet (VITE_BACKEND_URL).');
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        // The browser's call processing rewrites the voice -- denoising and
        // gain riding are exactly the artefacts a spoof detector keys on, and
        // the laptop's own DSP already cost one detector the tester's real
        // voice. Ask for the raw signal.
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
        channelCount: 1,
      },
    });
  } catch (err) {
    const denied = err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'SecurityError');
    throw new Error(denied
      ? 'Microphone access was denied. Allow it in the browser\'s site permissions, then try again.'
      : 'No usable microphone was found.');
  }
  const stopMic = () => stream.getTracks().forEach((t) => t.stop());

  let ws: WebSocket;
  try {
    ws = await openSocket(wsUrl(BACKEND_HTTP));
  } catch (err) {
    stopMic();
    throw err;
  }

  const sessionId = crypto.randomUUID();
  ws.send(JSON.stringify({
    type: 'session_start',
    session_id: sessionId,
    sample_rate: SAMPLE_RATE,
    channels: 1,
    encoding: 'pcm_s16le',
    source: 'browser_mic',
  }));

  // ---- capture graph: mic -> worklet -> (silent) destination ----
  const context = new AudioContext();
  let source: MediaStreamAudioSourceNode;
  let capture: AudioWorkletNode;
  const workletUrl = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }));
  try {
    await context.audioWorklet.addModule(workletUrl);
    source = context.createMediaStreamSource(stream);
    capture = new AudioWorkletNode(context, 'gg-mic-capture', { numberOfOutputs: 1, outputChannelCount: [1] });
    // Some engines only pull nodes that reach the destination; a zero gain
    // keeps the graph running without playing the mic back into the room.
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(capture).connect(mute).connect(context.destination);
    await context.resume();
  } catch (err) {
    stopMic();
    ws.onclose = null;
    ws.close();
    void context.close();
    throw new Error(`This browser couldn't start audio capture: ${err instanceof Error ? err.message : String(err)}`);
  } finally {
    URL.revokeObjectURL(workletUrl);
  }

  const resampler = new StreamingResampler(context.sampleRate, SAMPLE_RATE);
  let pending = new Float32Array(0);
  let sequence = 0;
  let sentSamples = 0;
  let stopping = false;
  let finished = false;

  const sendChunk = (samples: Float32Array) => {
    if (ws.readyState !== WebSocket.OPEN || samples.length === 0) return;
    const pcm = floatToPcm16(samples);
    ws.send(JSON.stringify({
      type: 'audio_chunk',
      session_id: sessionId,
      track: 'far',
      sequence: sequence++,
      timestamp: Date.now(),
      duration_ms: Math.round((pcm.length / SAMPLE_RATE) * 1000),
      sample_rate: SAMPLE_RATE,
      channels: 1,
      encoding: 'pcm_s16le',
      payload_size: pcm.byteLength,
    }));
    ws.send(pcm.buffer);
    sentSamples += pcm.length;
    onEvent({ type: 'chunk_sent', seconds: sentSamples / SAMPLE_RATE });
  };

  capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
    if (stopping) return;
    const block = event.data;
    let sum = 0;
    for (let i = 0; i < block.length; i++) sum += block[i] * block[i];
    onEvent({ type: 'level', rms: Math.sqrt(sum / block.length) });

    const out = resampler.push(block);
    const joined = new Float32Array(pending.length + out.length);
    joined.set(pending);
    joined.set(out, pending.length);
    let offset = 0;
    while (joined.length - offset >= CHUNK_SAMPLES) {
      sendChunk(joined.subarray(offset, offset + CHUNK_SAMPLES));
      offset += CHUNK_SAMPLES;
    }
    pending = joined.slice(offset);
  };

  const teardownAudio = () => {
    capture.port.onmessage = null;
    source.disconnect();
    capture.disconnect();
    stopMic();
    void context.close();
  };

  let resolveSummary: () => void = () => {};
  const summaryArrived = new Promise<void>((resolve) => { resolveSummary = resolve; });

  ws.onmessage = (event) => {
    if (typeof event.data !== 'string') return;
    let message: { type?: string; [key: string]: unknown };
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message.type === 'verdict' && message.track === 'far') {
      onEvent({ type: 'verdict', verdict: message as unknown as LiveVerdict });
    } else if (message.type === 'session_summary' && message.session_id === sessionId) {
      onEvent({ type: 'summary', summary: message as unknown as LiveSummary });
      resolveSummary();
    } else if (message.type === 'error') {
      onEvent({ type: 'error', message: String(message.message ?? 'The backend reported an error.') });
    }
  };
  ws.onclose = () => {
    if (!stopping) {
      stopping = true;
      teardownAudio();
      onEvent({ type: 'error', message: 'Lost the connection to the detection backend. Scoring stopped.' });
    }
    resolveSummary();
  };

  const stop = async () => {
    if (finished) return;
    finished = true;
    if (!stopping) {
      stopping = true;
      teardownAudio();
      // Whatever the resampler can still produce, plus the part-filled chunk.
      sendChunk(pending);
      pending = new Float32Array(0);
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'session_end', session_id: sessionId }));
      }
    }
    // The backend scores everything still queued before summarising; give it
    // time, but never hang the UI on a backend that has gone quiet.
    await Promise.race([summaryArrived, new Promise((r) => setTimeout(r, SUMMARY_TIMEOUT_MS))]);
    ws.onclose = null;
    ws.close();
  };

  return { sessionId, stop };
}
