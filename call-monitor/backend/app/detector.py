"""Scoring one analysis window with every loaded detector.

This module is the single point where "what do the detectors think of this
window" is answered, so the rest of the pipeline never has to care which
detectors are live.

The PRIMARY detector (first loaded in DETECTORS) produces the verdict: label,
P(real), and the value that drives session risk. Every other loaded detector
scores the SAME window and is reported under `secondary`, so models can be
compared on identical audio from real calls without changing the verdict.

If no detector loaded, the original placeholder heuristic (RMS + spectral
flatness) runs instead. It is NOT a deepfake classifier and its numbers mean
nothing -- it exists only so the pipeline still runs and demos. Every result
says which path produced it, and /health reports it too.
"""

import logging
import time

import numpy as np

from app import config, model, risk

logger = logging.getLogger("detector")

# Below this RMS (int16 scale) the placeholder treats audio as silence rather
# than emitting a meaningless number. The real models never see silence -- VAD
# has already removed it upstream.
SILENCE_RMS_THRESHOLD = 80.0

PLACEHOLDER_NAME = "placeholder"
PLACEHOLDER_WARNING = "PLACEHOLDER heuristic - NOT a trained deepfake model"


def active_name() -> str:
    primary = model.get()
    return primary.name if primary is not None else PLACEHOLDER_NAME


def score_window(samples: np.ndarray, real_samples: int | None = None) -> dict:
    """Score one window with every loaded detector.

    `real_samples` is how much of the window is actual speech; a short
    utterance's window is tile-padded after that point. Detectors that accept
    any length (AntiDeepfake) score only the real speech; XLSR-SLS, which needs
    exactly 64,600 samples, scores the padded window.

    Returns the primary's {p_bonafide, p_spoof, score_logprob, label, detector,
    latency_ms, detail}, plus `secondary`: the same fields for each other
    detector.
    """
    detectors = model.get_all()
    if not detectors:
        return _placeholder(samples)

    primary, *others = detectors
    result = _score_with(primary, samples, real_samples)
    if others:
        result["secondary"] = [
            {k: v for k, v in _score_with(m, samples, real_samples).items() if k != "detail"}
            for m in others
        ]
    return result


def _score_with(detector_model, samples: np.ndarray, real_samples: int | None) -> dict:
    t0 = time.perf_counter()
    p_bonafide, logprob = detector_model.score_window(samples, real_samples)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    real = real_samples or len(samples)
    # What the model actually consumed: its own input length if it tiles to one
    # (XLSR-Mamba, 66,800), else the fixed pipeline window, else the real speech.
    used = getattr(detector_model, "input_samples", None) or \
        (len(samples) if detector_model.requires_fixed_length else real)
    basis = f"{real / config.SAMPLE_RATE:.2f}s of speech"
    if used > real:
        basis += f", tile-padded to {used / config.SAMPLE_RATE:.2f}s"

    return {
        "p_bonafide": round(p_bonafide, 6),
        "p_spoof": round(1.0 - p_bonafide, 6),
        "score_logprob": round(logprob, 6),
        "label": risk.classify(p_bonafide),
        "detector": detector_model.name,
        "latency_ms": latency_ms,
        "detail": f"{detector_model.name} P(real)={p_bonafide:.3f} on {basis}",
    }


def _placeholder(samples: np.ndarray) -> dict:
    """Cheap signal statistics, kept only to keep the pipeline demonstrable."""
    arr = np.asarray(samples, dtype=np.float32)
    if arr.size == 0:
        return {
            "p_bonafide": 1.0, "p_spoof": 0.0, "label": "empty",
            "detector": PLACEHOLDER_NAME, "detail": "zero-length window",
        }

    rms = float(np.sqrt(np.mean(np.square(arr))))
    if rms < SILENCE_RMS_THRESHOLD:
        return {
            "p_bonafide": 1.0, "p_spoof": 0.0, "label": "silence",
            "detector": PLACEHOLDER_NAME, "detail": f"{PLACEHOLDER_WARNING}: rms={rms:.1f}",
        }

    spectrum = np.abs(np.fft.rfft(arr))
    spectrum = spectrum[spectrum > 1e-6]
    if spectrum.size == 0:
        flatness = 0.0
    else:
        gmean = np.exp(float(np.mean(np.log(spectrum))))
        amean = float(np.mean(spectrum))
        flatness = gmean / amean if amean > 0 else 0.0

    suspicion = float(min(1.0, flatness * 2.5))
    p_bonafide = 1.0 - suspicion
    return {
        "p_bonafide": round(p_bonafide, 6),
        "p_spoof": round(suspicion, 6),
        "label": risk.classify(p_bonafide),
        "detector": PLACEHOLDER_NAME,
        "detail": f"{PLACEHOLDER_WARNING}: rms={rms:.1f}, flatness={flatness:.3f}",
    }


def analyze_chunk(track: str, pcm: bytes, sample_rate: int) -> dict:
    """Legacy entry point: score a raw chunk with no VAD and no windowing.

    Retained so a chunk can still be scored ad hoc, but the live pipeline does
    NOT use this -- see app/analysis.py for why scoring wall-clock chunks is
    the wrong unit. Always uses the placeholder, since a raw chunk is neither
    the right length for the model nor guaranteed to contain speech.
    """
    return _placeholder(np.frombuffer(pcm, dtype="<i2").astype(np.float32))
