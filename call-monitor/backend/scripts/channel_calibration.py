"""Does the detector separate real from synthetic *on your actual channel*?

The problem this answers
------------------------
The XLSR-SLS checkpoint scores its own training distribution (ASVspoof 2019 LA)
almost perfectly, and collapses on real captured audio: genuine human speech
recorded through a live WhatsApp call scores around -16 bona-fide log-prob,
which is where ASVspoof puts *spoofs*. Absolute thresholds are therefore
meaningless here.

But a detector can still be useful while badly miscalibrated, IF it ranks
correctly -- if real speech on your channel sits at -16 and synthetic speech on
the same channel sits at -25, a channel-specific threshold works, with no
retraining. This script measures whether that gap exists.

How to gather the inputs
------------------------
The point is that both classes must travel the SAME path (phone -> codec ->
WhatsApp -> loopback capture), so the only difference between them is whether
the voice was synthetic. Scoring a deepfake .wav from disk does NOT test this,
because it skips the channel that causes the problem.

  REAL : run the client on ordinary calls with people you know.
  FAKE : have someone play cloned-voice audio into a call to you -- from their
         phone speaker, or better, as their mic input.

A few minutes of each is enough to see whether a gap exists at all.

Usage
-----
    python scripts/channel_calibration.py \
        --real recordings/<session-id> recordings/<other-id> \
        --fake recordings/<deepfake-session-id>

Session directories or plain .wav files both work (for a session it reads
far.wav, the track that carries the other party).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402
from app.vad import FRAME_SAMPLES, VoiceActivityDetector  # noqa: E402

WINDOW = config.WINDOW_SAMPLES
SR = config.SAMPLE_RATE


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def load_detector():
    sys.path.insert(0, str(config.MODEL_CODE_DIR))
    from xlsr_sls_infer import Detector

    return Detector(config.MODEL_PATH, provider=config.MODEL_PROVIDER)


def contiguous_speech_windows(path: Path, max_windows: int = 40) -> list[np.ndarray]:
    """Unspliced windows: each comes from ONE continuous run of VAD speech.

    Deliberately avoids the live pipeline's stitching. Splicing across pauses
    is a confound here -- we want to measure the channel, not the assembly.
    """
    import soundfile as sf

    audio, sr = sf.read(str(path), dtype="int16")
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.int16)
    if sr != SR:
        raise ValueError(f"{path} is {sr} Hz; expected {SR}")

    vad = VoiceActivityDetector()
    kept: list[tuple[int, np.ndarray]] = []
    for i in range(0, len(audio), 64000):
        decisions, _ = vad.process(audio[i:i + 64000])
        kept += [(f.index, f.samples) for f, k in decisions if k]
    decisions, _ = vad.flush()
    kept += [(f.index, f.samples) for f, k in decisions if k]
    if not kept:
        return []

    runs, current = [], [kept[0]]
    for previous, item in zip(kept, kept[1:]):
        if item[0] == previous[0] + 1:
            current.append(item)
        else:
            runs.append(current)
            current = [item]
    runs.append(current)

    windows = []
    for run in runs:
        if len(run) * FRAME_SAMPLES < WINDOW:
            continue
        samples = np.concatenate([s for _, s in run])
        # Slide within a long run so one talkative stretch contributes several
        # windows rather than being reduced to a single sample.
        for start in range(0, len(samples) - WINDOW + 1, WINDOW):
            windows.append(samples[start:start + WINDOW].astype(np.float32) / 32768.0)
            if len(windows) >= max_windows:
                return windows
    return windows


def score_source(detector, path: Path, max_windows: int) -> list[float]:
    windows = contiguous_speech_windows(path, max_windows)
    if not windows:
        return []
    _, logprobs = detector.score_windows(np.stack(windows))
    return [float(v) for v in logprobs]


def resolve(target: Path) -> Path | None:
    """A session directory (use its far.wav) or a plain audio file."""
    if target.is_dir():
        far = target / "far.wav"
        return far if far.is_file() else None
    return target if target.is_file() else None


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def equal_error_rate(real: list[float], fake: list[float]) -> tuple[float, float]:
    """EER and the threshold achieving it, scoring higher = more real."""
    if not real or not fake:
        return float("nan"), float("nan")
    candidates = sorted(set(real + fake))
    best = (1.0, candidates[0], 1.0)
    for threshold in candidates:
        # false reject: real called fake. false accept: fake called real.
        far_ = sum(1 for v in fake if v >= threshold) / len(fake)
        frr = sum(1 for v in real if v < threshold) / len(real)
        if abs(far_ - frr) < best[0]:
            best = (abs(far_ - frr), threshold, (far_ + frr) / 2)
    return best[2], best[1]


def describe(label: str, values: list[float]) -> dict:
    if not values:
        print(f"  {label:<10} no speech windows found")
        return {"n": 0}
    arr = np.array(values)
    stats = {
        "n": len(values), "mean": float(arr.mean()), "std": float(arr.std()),
        "min": float(arr.min()), "max": float(arr.max()),
        "p05": float(np.percentile(arr, 5)), "p95": float(np.percentile(arr, 95)),
    }
    print(f"  {label:<10} n={stats['n']:<4} mean={stats['mean']:8.3f}  "
          f"sd={stats['std']:5.3f}  range=[{stats['min']:8.3f}, {stats['max']:8.3f}]")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", nargs="*", default=[],
                    help="sessions/wavs where the caller was a real person")
    ap.add_argument("--fake", nargs="*", default=[],
                    help="sessions/wavs where the caller was synthetic")
    ap.add_argument("--max-windows", type=int, default=40, help="cap per source")
    ap.add_argument("--json", metavar="PATH", help="write the full result here")
    args = ap.parse_args()

    if not args.real and not args.fake:
        ap.error("give at least one --real or --fake source")

    print(f"model: {config.MODEL_PATH}")
    print("scoring unspliced VAD speech windows; higher log-prob = more 'real'\n")
    detector = load_detector()

    groups: dict[str, list[float]] = {"real": [], "fake": []}
    per_source: dict[str, dict] = {}

    for label in ("real", "fake"):
        for raw in getattr(args, label):
            target = resolve(Path(raw))
            if target is None:
                print(f"  [skip] {raw}: no audio found (a session needs far.wav)")
                continue
            scores = score_source(detector, target, args.max_windows)
            groups[label] += scores
            per_source[str(target)] = {"label": label, "n": len(scores),
                                       "mean": float(np.mean(scores)) if scores else None}
            mean = f"{np.mean(scores):8.3f}" if scores else "    n/a "
            print(f"  [{label:<4}] {target.name:<24} {len(scores):>3} windows  mean={mean}")

    print("\n=== DISTRIBUTIONS ===")
    stats = {label: describe(label.upper(), values) for label, values in groups.items()}

    result = {"model": str(config.MODEL_PATH), "groups": stats, "sources": per_source}

    if groups["real"] and groups["fake"]:
        eer, threshold = equal_error_rate(groups["real"], groups["fake"])
        gap = float(np.mean(groups["real"]) - np.mean(groups["fake"]))
        overlap = not (max(groups["fake"]) < min(groups["real"])
                       or max(groups["real"]) < min(groups["fake"]))
        result.update({"eer": eer, "threshold": threshold,
                       "mean_gap": gap, "ranges_overlap": overlap})

        print("\n=== SEPARABILITY ON THIS CHANNEL ===")
        print(f"  mean gap (real - fake) : {gap:+.3f} log-prob")
        print(f"  ranges overlap         : {'yes' if overlap else 'no'}")
        print(f"  best threshold         : {threshold:.3f}")
        print(f"  EER at that threshold  : {eer:.1%}")
        print()
        if gap <= 0:
            print("  VERDICT: unusable -- synthetic speech scores as real as, or")
            print("           more real than, genuine speech. The model is not")
            print("           ranking correctly on this channel. Recalibration")
            print("           cannot help; the detector has to change.")
        elif eer < 0.10:
            print(f"  VERDICT: USABLE with a channel-specific threshold.")
            print(f"           Set THRESHOLD_SYNTHETIC/THRESHOLD_REAL from {threshold:.3f}")
            print(f"           (note these are log-probs; app/risk.py currently")
            print(f"           thresholds on probability -- switch it to score_logprob).")
        elif eer < 0.25:
            print(f"  VERDICT: weak but real signal (EER {eer:.1%}). Worth pursuing")
            print(f"           with more data before trusting, and worth reporting")
            print(f"           honestly rather than as a working detector.")
        else:
            print(f"  VERDICT: no useful separation (EER {eer:.1%}). Retraining with")
            print(f"           codec/channel augmentation, or a different checkpoint,")
            print(f"           is required.")
    else:
        missing = "fake" if not groups["fake"] else "real"
        print(f"\n  Only one class provided -- add --{missing} sources to measure")
        print("  separability. A single class only establishes its baseline.")
        if groups["real"]:
            print(f"\n  Your REAL baseline on this channel is {np.mean(groups['real']):.2f}.")
            print("  Anything a real detector calls synthetic must score well below it.")

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
