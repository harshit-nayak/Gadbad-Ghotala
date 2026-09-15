"""Central configuration for the capture -> VAD -> model -> verdict pipeline.

Every knob is an environment variable with a working default, so the backend
runs out of the box and any deployment can retune it without touching code.
Set them before launching uvicorn (see ../../README.md section 5).

Kept in one module rather than scattered across the files that use them
because several settings are shared (RECORDINGS_DIR is needed by both the
WAV writers and the JSONL artifact log) and because the whole config is
snapshotted into every session manifest -- having one place to enumerate it
is what makes that snapshot trustworthy.
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
BACKEND_DIR = Path(__file__).resolve().parent.parent          # .../call-monitor/backend
PROJECT_ROOT = BACKEND_DIR.parent.parent                       # .../sih deepfake


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# audio contract -- fixed by the model, do not change
# --------------------------------------------------------------------------- #
SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2

# The XLSR-SLS model accepts exactly one input length: fc1 expects a 22,847-d
# flatten, so 64,600 samples (4.0375 s) is structural, not a tuning choice.
WINDOW_SAMPLES = 64_600

# Windows are cut per UTTERANCE -- one continuous stretch of the far party
# speaking -- and never span a pause (see app/analysis.py).
#
# Within a long utterance, how far each window advances. Default = one full
# window, i.e. no overlap. 50% overlap doubled inference load, and on a real
# 25-minute call CPU inference averaged 2.2 s per window -- slower than windows
# arrived -- so analysis fell behind and chunks were dropped. Set 32300 for 50%
# overlap on a machine that can keep up.
WINDOW_HOP_SAMPLES = _env_int("WINDOW_HOP_SAMPLES", WINDOW_SAMPLES)

# Shortest utterance that gets scored. Shorter ones are recorded to speech.wav
# but never scored. Utterances between this and one window (4.04 s) are
# tile-padded to the model's input length -- the padding its model card
# specifies -- and flagged `padded`. Capped at one window.
# Measured on real calls: 3 s scores 68-86% of speech, 2 s scores 80-92%.
UTTERANCE_MIN_SECONDS = _env_float("UTTERANCE_MIN_SECONDS", 3.0)

# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
MODEL_ENABLED = _env_bool("MODEL_ENABLED", True)
# Directory holding preprocess.py + xlsr_sls_infer.py. Added to sys.path so the
# already-tested inference code is reused rather than duplicated here.
MODEL_CODE_DIR = Path(os.getenv("MODEL_CODE_DIR") or (PROJECT_ROOT / "deepfake"))
MODEL_PATH = Path(os.getenv("MODEL_PATH") or (MODEL_CODE_DIR / "xlsr-sls.onnx"))
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "cpu").strip().lower()
MODEL_THREADS = _env_int("MODEL_THREADS", 0) or None

# --------------------------------------------------------------------------- #
# decision thresholds
#
# Three bands, not two, because the project's own constraint is that a false
# "this is a deepfake" is expensive: the middle band recommends verification
# instead of asserting fraud.
#
# THESE DEFAULTS ARE NOT CALIBRATED. Derive your own from the EER in
# deepfake/results/summary.json (produced by deepfake/eval_balanced.py) before
# putting any weight on them.
# --------------------------------------------------------------------------- #
THRESHOLD_REAL = _env_float("THRESHOLD_REAL", 0.75)        # P(bona fide) >= this -> likely_real
THRESHOLD_SYNTHETIC = _env_float("THRESHOLD_SYNTHETIC", 0.30)  # <= this -> likely_synthetic

# Session-level risk = exponential moving average of P(spoof) across windows.
# Lower alpha = smoother/slower, higher = more reactive to a single window.
RISK_EMA_ALPHA = _env_float("RISK_EMA_ALPHA", 0.4)

# Consecutive synthetic-leaning windows before the session is called high risk.
# Must be read against WINDOW_HOP_SAMPLES: at the default 50% overlap, windows
# N and N+1 share half their audio, so "2 consecutive" can be one anomalous 4 s
# stretch counted twice. 3 consecutive spans windows N and N+2, which share no
# samples at all -- i.e. the suspicion survived into independent audio. Since a
# false "deepfake" is the expensive error here, 3 is the default.
RISK_SUSTAIN_WINDOWS = _env_int("RISK_SUSTAIN_WINDOWS", 3)

# --------------------------------------------------------------------------- #
# voice activity detection
# --------------------------------------------------------------------------- #
# "silero" (preferred), "energy" (numpy fallback), "off" (treat everything as
# speech). "silero" degrades to "energy" automatically if the model file is
# missing -- always with a warning, never silently.
VAD_BACKEND = os.getenv("VAD_BACKEND", "silero").strip().lower()
SILERO_VAD_PATH = Path(os.getenv("SILERO_VAD_PATH") or (BACKEND_DIR / "models" / "silero_vad.onnx"))

# 512 samples @ 16 kHz = 32 ms. Required frame size for Silero v5, and valid
# for v4 too, so the same framing drives either backend.
VAD_FRAME_SAMPLES = 512

VAD_THRESHOLD = _env_float("VAD_THRESHOLD", 0.5)
# Speech must sustain this long to open a segment (rejects clicks and coughs).
VAD_MIN_SPEECH_MS = _env_int("VAD_MIN_SPEECH_MS", 250)
# Silence must sustain this long to close one (a pause mid-sentence shouldn't
# split an utterance into two).
VAD_MIN_SILENCE_MS = _env_int("VAD_MIN_SILENCE_MS", 400)
# Keep this much audio either side of a segment, so onsets/offsets aren't clipped.
VAD_SPEECH_PAD_MS = _env_int("VAD_SPEECH_PAD_MS", 120)

# --------------------------------------------------------------------------- #
# tracks
# --------------------------------------------------------------------------- #
# "far" = the other party (the one worth screening). Add ",near" to also score
# your own mic -- useful for sanity-checking the pipeline against a voice you
# know is genuine.
DETECT_TRACKS = {t.strip() for t in os.getenv("DETECT_TRACKS", "far").split(",") if t.strip()}

# --------------------------------------------------------------------------- #
# recording / artifacts
# --------------------------------------------------------------------------- #
RECORDINGS_DIR = Path(os.getenv("RECORDINGS_DIR", "recordings"))
RECORD_LOCALLY = _env_bool("RECORD_LOCALLY", True)      # continuous far.wav / near.wav
RECORD_CHUNKS = _env_bool("RECORD_CHUNKS", True)        # per-chunk wavs as they arrive
RECORD_SPEECH = _env_bool("RECORD_SPEECH", True)        # VAD-kept audio only
RECORD_WINDOWS = _env_bool("RECORD_WINDOWS", True)      # the exact samples the model saw
WRITE_ARTIFACTS = _env_bool("WRITE_ARTIFACTS", True)    # events/segments/verdicts JSONL

# --------------------------------------------------------------------------- #
# runtime
# --------------------------------------------------------------------------- #
# Chunks queued for analysis before the oldest is dropped. Inference is slower
# than capture in the worst case; dropping analysis of an old chunk is better
# than drifting further behind a live call. Recordings are written before
# queueing, so a drop never loses audio from disk -- only from scoring.
ANALYSIS_QUEUE_SIZE = _env_int("ANALYSIS_QUEUE_SIZE", 8)

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)
RELOAD = _env_bool("RELOAD", False)  # off by default: reload re-loads a 1.36 GB model

# --------------------------------------------------------------------------- #
# detectors
# --------------------------------------------------------------------------- #
# Which detectors score each window, in priority order. The FIRST one that
# loads is the primary: it produces the verdict and drives session risk. The
# rest score the same window and are logged beside it, for comparison. Names
# that are unknown or fail to load are skipped with a warning, so the backend
# always starts.
#
#   xlsr-mamba       XLSR-Mamba with the Indic fine-tuned head (app/xlsr_mamba.py):
#                    trained on Hindi/Bengali/Tamil real + deepfake speech, half
#                    of it WhatsApp-style Opus compressed. PyTorch.
#   xlsr-mamba-base  the same network without the Indic head (ASVspoof-trained).
#   antideepfake     AntiDeepfake MMS-300M (app/antideepfake.py), post-trained on
#                    ~74k hours in 100+ languages. PyTorch.
#   xlsr-sls         the original ASVspoof 2019 LA model, via ONNX Runtime.
#
# The default is the Indic fine-tuned XLSR-Mamba alone: the only one trained on
# Indian-language deepfakes and messaging-app compression, and on the recorded
# test calls the only one that scored the tester's own voice real (14 of 14).
# Add the others to log their scores beside it for comparison, e.g.
#   DETECTORS=xlsr-mamba,antideepfake,xlsr-sls
# Each takes ~1 s per window on CPU.
DETECTORS = [d.strip().lower() for d in
             os.getenv("DETECTORS", "xlsr-mamba").split(",") if d.strip()]
ANTIDEEPFAKE_PATH = Path(os.getenv("ANTIDEEPFAKE_PATH")
                         or (BACKEND_DIR / "models" / "mms-300m-anti-deepfake"))
# Holds model_base.safetensors (public) + conformer_head_only.safetensors (Indic head).
XLSR_MAMBA_PATH = Path(os.getenv("XLSR_MAMBA_PATH") or (BACKEND_DIR / "models" / "xlsr-mamba"))


def snapshot() -> dict:
    """The full effective config, for the session manifest."""
    return {
        "sample_rate": SAMPLE_RATE,
        "window_samples": WINDOW_SAMPLES,
        "window_hop_samples": WINDOW_HOP_SAMPLES,
        "utterance_min_seconds": UTTERANCE_MIN_SECONDS,
        "detectors": DETECTORS,
        "antideepfake_path": str(ANTIDEEPFAKE_PATH),
        "xlsr_mamba_path": str(XLSR_MAMBA_PATH),
        "model_enabled": MODEL_ENABLED,
        "model_path": str(MODEL_PATH),
        "model_provider": MODEL_PROVIDER,
        "threshold_real": THRESHOLD_REAL,
        "threshold_synthetic": THRESHOLD_SYNTHETIC,
        "risk_ema_alpha": RISK_EMA_ALPHA,
        "risk_sustain_windows": RISK_SUSTAIN_WINDOWS,
        "vad_backend": VAD_BACKEND,
        "vad_frame_samples": VAD_FRAME_SAMPLES,
        "vad_threshold": VAD_THRESHOLD,
        "vad_min_speech_ms": VAD_MIN_SPEECH_MS,
        "vad_min_silence_ms": VAD_MIN_SILENCE_MS,
        "vad_speech_pad_ms": VAD_SPEECH_PAD_MS,
        "detect_tracks": sorted(DETECT_TRACKS),
        "record_locally": RECORD_LOCALLY,
        "record_chunks": RECORD_CHUNKS,
        "record_speech": RECORD_SPEECH,
        "record_windows": RECORD_WINDOWS,
        "analysis_queue_size": ANALYSIS_QUEUE_SIZE,
    }
