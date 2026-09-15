"""Voice activity detection for the far track.

Why this exists: a fixed 4 s slice of the far track is often mostly silence --
the other party is listening while you talk. The XLSR-SLS model is a *speech*
anti-spoofing model; scoring silence produces a number with no meaning behind
it. So the unit of analysis has to be assembled from speech, not from clock
time, and something has to decide which samples those are.

Two backends, one interface:

  silero  (preferred) -- Silero VAD as a ~2.2 MB ONNX graph, run on the same
          onnxruntime the detector already needs. Robust to the background
          noise the far track inevitably carries: it is a digital tap of what
          the other party *transmitted*, which includes their room.
  energy  (fallback)  -- adaptive noise-floor tracking in pure numpy. No
          download, no extra dependency, works offline. Weaker in noise.

`silero` degrades to `energy` automatically when the model file is missing,
and says so loudly -- a silent downgrade would quietly change what every
verdict in the session means.

Raw per-frame probabilities are never used directly. `SpeechGate` applies
hysteresis on top: speech must sustain before a segment opens (so a cough or
a line click isn't an utterance), silence must sustain before it closes (so a
pause mid-sentence doesn't split one utterance into two), and a short pad is
kept either side so onsets and offsets aren't clipped off.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import config

logger = logging.getLogger("vad")

FRAME_SAMPLES = config.VAD_FRAME_SAMPLES
FRAME_MS = FRAME_SAMPLES * 1000 // config.SAMPLE_RATE  # 32 ms at 16 kHz


@dataclass
class Frame:
    """One VAD frame: 32 ms of audio plus what the detector thought of it."""
    index: int                # global frame number within the track, from session start
    samples: np.ndarray       # int16, exactly FRAME_SAMPLES
    rms: float                # int16-scale RMS, comparable to detector.SILENCE_RMS_THRESHOLD
    prob: float               # 0..1 speech probability

    @property
    def start_ms(self) -> int:
        return self.index * FRAME_MS

    @property
    def end_ms(self) -> int:
        return (self.index + 1) * FRAME_MS


@dataclass
class SpeechSegment:
    """A contiguous stretch the gate decided was the other party speaking."""
    index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    n_frames: int
    mean_prob: float
    mean_rms: float

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "n_frames": self.n_frames,
            "mean_prob": round(self.mean_prob, 4),
            "mean_rms": round(self.mean_rms, 1),
        }


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #
_silero_session = None
_logged_silero = False


def _load_silero_session(path: Path):
    """One ONNX session shared by every track and every call.

    Sharing is safe because the recurrent state lives in Python on each
    SileroVad instance, not inside the session, and because all VAD work is
    serialised through the single analysis worker thread.
    """
    global _silero_session
    if _silero_session is None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # One frame at a time on a ~1M-param graph: extra threads cost more in
        # scheduling than they save, and we want the cores for the big model.
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        _silero_session = ort.InferenceSession(
            str(path), sess_options=so, providers=["CPUExecutionProvider"]
        )
    return _silero_session


class SileroVad:
    """Silero VAD via onnxruntime.

    The graph is recurrent -- it carries hidden state between frames -- so
    frames must be fed strictly in order, one at a time. Input names differ
    between exports (v4 carries `h`/`c`, v5 a single packed `state`), so the
    state tensors are discovered by introspection rather than hardcoded, the
    same way deepfake/xlsr_sls_infer.py:97-107 discovers its own inputs.
    """

    name = "silero"

    # v5 does NOT take a bare 512-sample frame: it expects the previous 64
    # samples prepended as context, for 576 total. The graph declares its audio
    # input as [None, None], so feeding a bare 512 does not error -- it just
    # returns near-zero probabilities for everything, including obvious speech.
    # Verified on this checkpoint: real speech scores 261/272 frames with the
    # context and 0/272 without it.
    CONTEXT_SAMPLES = 64

    def __init__(self, path: Path):
        self.sess = _load_silero_session(path)

        inputs = self.sess.get_inputs()
        self._audio_name = next((i.name for i in inputs if i.name in ("input", "audio")), inputs[0].name)
        self._sr_name = next((i.name for i in inputs if i.name in ("sr", "sample_rate")), None)
        self._state_specs = [i for i in inputs
                             if i.name not in (self._audio_name, self._sr_name)]
        self._out_names = [o.name for o in self.sess.get_outputs()]
        self.reset()
        global _logged_silero
        if not _logged_silero:
            _logged_silero = True
            logger.info(
                f"Silero VAD loaded from {path} "
                f"(audio='{self._audio_name}', state={[s.name for s in self._state_specs]})"
            )

    def reset(self) -> None:
        self._states = {
            spec.name: np.zeros(
                [d if isinstance(d, int) else 1 for d in spec.shape], dtype=np.float32
            )
            for spec in self._state_specs
        }
        self._context = np.zeros(self.CONTEXT_SAMPLES, dtype=np.float32)

    def prob(self, frame_f32: np.ndarray) -> float:
        audio = np.concatenate([self._context, frame_f32]).reshape(1, -1).astype(np.float32)
        feed = {self._audio_name: audio}
        if self._sr_name:
            feed[self._sr_name] = np.array(config.SAMPLE_RATE, dtype=np.int64)
        feed.update(self._states)

        out = self.sess.run(self._out_names, feed)
        # Outputs are [speech_prob, *new_states] in the same order as the state
        # inputs -- true for both the v4 (h/c) and v5 (state) exports.
        for spec, value in zip(self._state_specs, out[1:]):
            self._states[spec.name] = np.asarray(value, dtype=np.float32)
        self._context = frame_f32[-self.CONTEXT_SAMPLES:].astype(np.float32)
        return float(np.asarray(out[0]).reshape(-1)[0])


class EnergyVad:
    """Adaptive noise-floor VAD -- the dependency-free fallback.

    Tracks the noise floor with a fast attack / slow decay envelope so it
    settles onto the quiet parts of the line, then calls speech when a frame
    sits far enough above that floor. The frame SNR is mapped onto a 0..1
    pseudo-probability so `SpeechGate` can consume either backend unchanged.
    """

    name = "energy"

    # Frames quieter than this (int16 scale) are treated as line silence
    # outright, so a near-zero noise floor can't make digital silence "loud".
    ABSOLUTE_FLOOR_RMS = 30.0
    SNR_DB_LOW = 6.0    # prob 0 at this many dB above the floor
    SNR_DB_HIGH = 18.0  # prob 1 at this many

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._floor: float | None = None

    def prob(self, frame_f32: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(frame_f32)))) * 32768.0
        if self._floor is None:
            self._floor = max(rms, 1.0)
        # Fall to a new quiet floor quickly; rise toward a noisy one slowly, so
        # a long utterance can't drag the floor up to its own level.
        self._floor = (0.90 * self._floor + 0.10 * rms) if rms < self._floor \
            else (0.999 * self._floor + 0.001 * rms)

        if rms < self.ABSOLUTE_FLOOR_RMS:
            return 0.0
        snr_db = 20.0 * math.log10(max(rms, 1e-6) / max(self._floor, 1e-6))
        span = self.SNR_DB_HIGH - self.SNR_DB_LOW
        return float(min(1.0, max(0.0, (snr_db - self.SNR_DB_LOW) / span)))


class NullVad:
    """VAD_BACKEND=off -- every frame is speech. For A/B-ing what VAD buys."""

    name = "off"

    def reset(self) -> None:
        pass

    def prob(self, frame_f32: np.ndarray) -> float:
        return 1.0


_warned_fallback = False


def _build_backend():
    """Pick a backend, falling back audibly rather than silently."""
    global _warned_fallback
    requested = config.VAD_BACKEND

    if requested == "off":
        logger.warning("VAD disabled (VAD_BACKEND=off): every frame counts as speech")
        return NullVad()

    if requested == "silero":
        path = config.SILERO_VAD_PATH
        if not path.is_file():
            if not _warned_fallback:
                _warned_fallback = True
                logger.warning(
                    f"Silero VAD model not found at {path} -- falling back to the energy VAD. "
                    f"Run `python scripts/fetch_silero.py` to get it (~2.2 MB); the energy "
                    f"fallback is noticeably weaker when the other party is in a noisy room."
                )
            return EnergyVad()
        try:
            return SileroVad(path)
        except Exception as e:  # noqa: BLE001
            if not _warned_fallback:
                _warned_fallback = True
                logger.warning(f"Could not load Silero VAD ({e}) -- falling back to the energy VAD")
            return EnergyVad()

    if requested != "energy":
        logger.warning(f"Unknown VAD_BACKEND={requested!r}; using the energy VAD")
    return EnergyVad()


def active_backend_name() -> str:
    """Which backend a new detector would actually get -- the requested one, or
    whatever it fell back to. Reported by /health so a downgrade is visible."""
    try:
        return _build_backend().name
    except Exception:  # noqa: BLE001
        return "unavailable"


# --------------------------------------------------------------------------- #
# hysteresis
# --------------------------------------------------------------------------- #
class SpeechGate:
    """Turns per-frame probabilities into kept/dropped decisions and segments.

    A frame's fate isn't always decidable when it arrives: a frame of silence
    may still be kept as the tail pad of a segment that hasn't closed yet, and
    a frame of quiet may be retroactively kept as the head pad of a segment
    that hasn't opened yet. So frames are buffered until settled, and the
    buffer never grows past `min_speech + pad` frames of undecided history.
    """

    def __init__(self, threshold: float, min_speech_ms: int, min_silence_ms: int,
                 speech_pad_ms: int):
        self.threshold = threshold
        # Closing needs a lower bar than opening: once we believe someone is
        # talking, we keep believing it through a dip. Classic Schmitt trigger.
        self.neg_threshold = max(0.0, threshold - 0.15)
        self.min_speech_frames = max(1, round(min_speech_ms / FRAME_MS))
        self.min_silence_frames = max(1, round(min_silence_ms / FRAME_MS))
        self.pad_frames = max(0, round(speech_pad_ms / FRAME_MS))

        self._buf: deque[Frame] = deque()
        self._state = "idle"
        self._run = 0
        self._cand_pos = 0
        self._sil_pos = 0
        self._sil_run = 0
        self._seg_frames: list[Frame] = []
        self._seg_index = 0

    def push(self, frame: Frame) -> tuple[list[tuple[Frame, bool]], list[SpeechSegment]]:
        """Feed one frame. Returns (settled [(frame, kept)], closed segments)."""
        self._buf.append(frame)
        decisions: list[tuple[Frame, bool]] = []
        segments: list[SpeechSegment] = []

        is_speech = frame.prob >= self.threshold
        is_silence = frame.prob < self.neg_threshold

        if self._state == "idle":
            if is_speech:
                self._state = "maybe_speech"
                self._cand_pos = len(self._buf) - 1
                self._run = 1
            else:
                decisions += self._drop_all_but_pad()

        elif self._state == "maybe_speech":
            if is_speech:
                self._run += 1
                if self._run >= self.min_speech_frames:
                    # Confirmed. Everything before the back-pad was never speech.
                    start_pos = max(0, self._cand_pos - self.pad_frames)
                    decisions += self._pop(start_pos, kept=False)
                    self._state = "speech"
                    self._seg_frames = list(self._buf)
            else:
                self._state = "idle"
                self._run = 0
                decisions += self._drop_all_but_pad()

        elif self._state == "speech":
            self._seg_frames.append(frame)
            if is_silence:
                self._state = "maybe_silence"
                self._sil_pos = len(self._buf) - 1
                self._sil_run = 1
            else:
                decisions += self._pop(len(self._buf), kept=True)

        elif self._state == "maybe_silence":
            self._seg_frames.append(frame)
            if is_silence:
                self._sil_run += 1
                if self._sil_run >= self.min_silence_frames:
                    # Confirmed end. Keep the forward pad, drop the rest.
                    end_pos = min(len(self._buf), self._sil_pos + self.pad_frames)
                    kept = self._pop(end_pos, kept=True)
                    decisions += kept
                    last_kept = kept[-1][0].index if kept else frame.index
                    segments.append(self._close_segment(last_kept))
                    self._state = "idle"
                    self._run = 0
                    decisions += self._drop_all_but_pad()
            else:
                # False alarm -- the pause was just a pause.
                self._state = "speech"
                self._sil_run = 0
                decisions += self._pop(len(self._buf), kept=True)

        return decisions, segments

    def flush(self) -> tuple[list[tuple[Frame, bool]], list[SpeechSegment]]:
        """End of stream: settle whatever is still buffered."""
        decisions: list[tuple[Frame, bool]] = []
        segments: list[SpeechSegment] = []
        if self._state in ("speech", "maybe_silence") and self._buf:
            last = self._buf[-1].index
            decisions += self._pop(len(self._buf), kept=True)
            segments.append(self._close_segment(last))
        else:
            decisions += self._pop(len(self._buf), kept=False)
        self._state = "idle"
        self._run = 0
        self._sil_run = 0
        return decisions, segments

    # -- internals ---------------------------------------------------------

    def _pop(self, n: int, kept: bool) -> list[tuple[Frame, bool]]:
        return [(self._buf.popleft(), kept) for _ in range(min(n, len(self._buf)))]

    def _drop_all_but_pad(self) -> list[tuple[Frame, bool]]:
        """Retain just enough recent history for a future segment's back-pad."""
        excess = len(self._buf) - self.pad_frames
        return self._pop(excess, kept=False) if excess > 0 else []

    def _close_segment(self, last_kept_index: int) -> SpeechSegment:
        frames = [f for f in self._seg_frames if f.index <= last_kept_index] or self._seg_frames
        seg = SpeechSegment(
            index=self._seg_index,
            start_ms=frames[0].start_ms,
            end_ms=frames[-1].end_ms,
            duration_ms=frames[-1].end_ms - frames[0].start_ms,
            n_frames=len(frames),
            mean_prob=float(np.mean([f.prob for f in frames])),
            mean_rms=float(np.mean([f.rms for f in frames])),
        )
        self._seg_index += 1
        self._seg_frames = []
        return seg


# --------------------------------------------------------------------------- #
# public wrapper
# --------------------------------------------------------------------------- #
class VoiceActivityDetector:
    """Per-track VAD: framing + backend + hysteresis, stateful across chunks.

    Chunk boundaries are an artifact of network transport, not of the audio,
    so leftover samples that don't fill a frame are carried into the next
    chunk rather than being zero-padded into a fake frame.
    """

    def __init__(self, backend=None):
        self.backend = backend if backend is not None else _build_backend()
        self.gate = SpeechGate(
            threshold=config.VAD_THRESHOLD,
            min_speech_ms=config.VAD_MIN_SPEECH_MS,
            min_silence_ms=config.VAD_MIN_SILENCE_MS,
            speech_pad_ms=config.VAD_SPEECH_PAD_MS,
        )
        self._carry = np.zeros(0, dtype=np.int16)
        self._next_frame_index = 0

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def process(self, pcm_int16: np.ndarray):
        """Feed one chunk's samples. Returns (decisions, segments)."""
        buf = np.concatenate([self._carry, pcm_int16]) if self._carry.size else pcm_int16
        n_frames = len(buf) // FRAME_SAMPLES
        self._carry = buf[n_frames * FRAME_SAMPLES:].copy()

        decisions: list[tuple[Frame, bool]] = []
        segments: list[SpeechSegment] = []
        for i in range(n_frames):
            samples = buf[i * FRAME_SAMPLES:(i + 1) * FRAME_SAMPLES]
            as_float = samples.astype(np.float32) / 32768.0
            frame = Frame(
                index=self._next_frame_index,
                samples=samples,
                rms=float(np.sqrt(np.mean(np.square(as_float)))) * 32768.0,
                prob=self.backend.prob(as_float),
            )
            self._next_frame_index += 1
            d, s = self.gate.push(frame)
            decisions += d
            segments += s
        return decisions, segments

    def flush(self):
        """End of session: settle buffered frames. Trailing partial frame is
        dropped -- under 32 ms, it cannot change any verdict."""
        return self.gate.flush()
