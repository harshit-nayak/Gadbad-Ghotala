"""End-to-end verification of the live detection pipeline.

    python scripts/verify_pipeline.py              # everything
    python scripts/verify_pipeline.py --skip-model # everything except parity

Checks, in order of how much they'd hurt if they were wrong:

  1. PARITY   -- a clip scored through the live path (int16 PCM, as it arrives
                 over the WebSocket) gets the same probability as the same clip
                 scored through deepfake/xlsr_sls_infer.py's file API. If this
                 drifts, the integration has silently changed what the model
                 sees and every offline number stops applying.
  2. RESAMPLE -- content above the 8 kHz output Nyquist is filtered out rather
                 than folded back into the band, and streaming in small buffers
                 gives the same result as converting the stream in one go.
  3. VAD      -- real speech padded with silence produces segments that land on
                 the speech, and the silence is discarded.
  4. WINDOWS  -- every analysis window is exactly 64,600 samples, and windows
                 advance by exactly the configured hop.

Needs scipy + soundfile (see requirements.txt).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
CLIENT_DIR = BACKEND_DIR.parent / "client"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def load_client_module(name: str):
    """Import a client module by path.

    Deliberately not via sys.path: the client has its own top-level `app.py`,
    which would shadow the backend's `app` package.
    """
    spec = importlib.util.spec_from_file_location(f"_client_{name}", CLIENT_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


from app import config  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, PASS if ok else FAIL, detail))
    print(f"  [{PASS if ok else FAIL}] {name}" + (f"  --  {detail}" if detail else ""))
    return ok


def find_speech_clips(limit: int = 3) -> list[Path]:
    """Real 16 kHz mono speech from the ASVspoof dev set, if it's present."""
    folder = config.MODEL_CODE_DIR / "flac_D_ac" / "flac_D"
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.flac"))[:limit]


# --------------------------------------------------------------------------- #
# 1. parity
# --------------------------------------------------------------------------- #
def test_parity(clips: list[Path]) -> None:
    print("\n1. PARITY -- live int16 path vs the offline file API")
    if not clips:
        check("parity", False, "no clips found under deepfake/flac_D_ac/flac_D")
        return

    import soundfile as sf
    from app import model

    # Parity is a property of the XLSR-SLS integration specifically, so build it
    # directly rather than depending on which detectors DETECTORS enables.
    try:
        handle = model._build_xlsr()
    except Exception as e:  # noqa: BLE001
        check("parity", False, f"xlsr-sls could not load: {e}")
        return

    sys.path.insert(0, str(config.MODEL_CODE_DIR))
    from preprocess import WINDOW, fit_length
    from xlsr_sls_infer import Detector

    reference = Detector(config.MODEL_PATH, provider=config.MODEL_PROVIDER)

    worst = 0.0
    for clip in clips:
        data, sr = sf.read(str(clip), dtype="int16")
        if sr != config.SAMPLE_RATE or data.ndim != 1:
            print(f"     skipping {clip.name} ({sr} Hz, {data.ndim}ch -- want 16 kHz mono)")
            continue

        # Live path: int16 samples, exactly as they arrive over the wire.
        ours = float(handle.score(fit_length(data, WINDOW, "start")[None, :])[0][0])
        # Reference path: soundfile float32 read, straight from the CLI's API.
        theirs = reference.score_file(clip, long_audio="truncate", crop="start").p_bonafide

        delta = abs(ours - theirs)
        worst = max(worst, delta)
        print(f"     {clip.name}:  live={ours:.6f}  offline={theirs:.6f}  delta={delta:.2e}")

    check("scores match the offline API", worst < 1e-4, f"max delta {worst:.2e}")


# --------------------------------------------------------------------------- #
# 2. resampler
# --------------------------------------------------------------------------- #
def test_resampler() -> None:
    print("\n2. RESAMPLE -- anti-aliasing and streaming continuity")
    resample = load_client_module("resample")
    HAVE_SCIPY, StreamingResampler = resample.HAVE_SCIPY, resample.StreamingResampler

    if not check("scipy available", HAVE_SCIPY, "" if HAVE_SCIPY else "pip install scipy"):
        return

    in_rate, seconds = 48000, 1.0
    t = np.arange(int(in_rate * seconds)) / in_rate

    def band_energy(pcm: bytes, low: float, high: float) -> float:
        x = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
        spec = np.abs(np.fft.rfft(x))
        freqs = np.fft.rfftfreq(len(x), 1 / config.SAMPLE_RATE)
        band = spec[(freqs >= low) & (freqs <= high)]
        return float(np.sum(band ** 2))

    # A 15 kHz tone cannot exist below the 8 kHz output Nyquist. Decimated
    # without a lowpass it reappears at |15000 - 16000| = 1 kHz.
    tone_15k = (0.5 * np.sin(2 * np.pi * 15000 * t) * 32767).astype("<i2").tobytes()
    out = StreamingResampler(in_rate, 1).process(tone_15k)
    aliased = band_energy(out, 500, 1500)

    # Same amplitude at 1 kHz, which legitimately survives -- the yardstick for
    # "how big would the alias be if it were there".
    tone_1k = (0.5 * np.sin(2 * np.pi * 1000 * t) * 32767).astype("<i2").tobytes()
    legit = band_energy(StreamingResampler(in_rate, 1).process(tone_1k), 500, 1500)

    ratio = aliased / legit if legit else float("inf")
    check("15 kHz does not fold back into the band",
          ratio < 1e-4, f"alias energy is {ratio:.2e} of a real 1 kHz tone")
    check("1 kHz passes through", legit > 0, f"energy {legit:.3e}")

    # Streaming in device-sized reads must equal converting the stream at once.
    speechish = ((np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 1750 * t))
                 * 0.3 * 32767).astype("<i2")
    one_shot = StreamingResampler(in_rate, 1).process(speechish.tobytes())
    streamer = StreamingResampler(in_rate, 1)
    pieces = [streamer.process(speechish[i:i + 1024].tobytes())
              for i in range(0, len(speechish), 1024)]
    streamed = b"".join(pieces)

    n = min(len(one_shot), len(streamed)) // 2
    a = np.frombuffer(one_shot, dtype="<i2")[:n].astype(np.float64)
    b = np.frombuffer(streamed, dtype="<i2")[:n].astype(np.float64)
    max_diff = float(np.max(np.abs(a - b))) if n else float("inf")
    check("1024-frame streaming == one-shot conversion",
          max_diff <= 1.0, f"max sample difference {max_diff:.1f} LSB over {n} samples")


# --------------------------------------------------------------------------- #
# 3 + 4. VAD and windows
# --------------------------------------------------------------------------- #
def test_vad_and_windows(clips: list[Path]) -> None:
    print("\n3. VAD -- speech kept, silence discarded")
    if not clips:
        check("vad", False, "no speech clips available")
        return

    import soundfile as sf
    from app.analysis import TrackAnalyzer
    from app.vad import VoiceActivityDetector

    sr = config.SAMPLE_RATE
    silence = np.zeros(int(1.5 * sr), dtype=np.int16)

    speech_parts = []
    for clip in clips:
        data, clip_sr = sf.read(str(clip), dtype="int16")
        if clip_sr == sr and data.ndim == 1:
            speech_parts.append(data)
    if not speech_parts:
        check("vad", False, "no 16 kHz mono clips")
        return

    # silence, speech, silence, speech, ... so a correct VAD keeps roughly the
    # speech duration and drops roughly the silence.
    timeline, expected_speech = [], 0
    for part in speech_parts:
        timeline.append(silence)
        timeline.append(part)
        expected_speech += len(part)
    timeline.append(silence)
    audio = np.concatenate(timeline)
    total_silence = len(audio) - expected_speech

    detector_ = VoiceActivityDetector()
    analyzer = TrackAnalyzer("far", detector_)
    print(f"     VAD backend: {detector_.backend_name}")
    print(f"     built {len(audio)/sr:.1f}s: {expected_speech/sr:.1f}s speech, "
          f"{total_silence/sr:.1f}s silence")

    all_windows = []
    for i in range(0, len(audio), 64000):  # 4 s chunks, as the client sends
        _, _, windows = analyzer.push_chunk(audio[i:i + 64000])
        all_windows += windows
    _, _, windows = analyzer.flush()
    all_windows += windows

    kept = analyzer.total_speech_samples
    recall = kept / expected_speech if expected_speech else 0
    leak = max(0, kept - expected_speech) / total_silence if total_silence else 0
    print(f"     kept {kept/sr:.1f}s  ({analyzer.speech_frames}/{analyzer.total_frames} frames)")

    check("keeps most of the speech", 0.70 <= recall <= 1.30, f"kept/speech = {recall:.2f}")
    check("discards most of the silence", leak < 0.35, f"at most {leak:.0%} of silence retained")

    print("\n4. WINDOWS -- exact model input length and hop")
    check("at least one window emitted", len(all_windows) > 0, f"{len(all_windows)} windows")
    if not all_windows:
        return

    lengths = {len(w.samples) for w in all_windows}
    check("every window is exactly 64,600 samples",
          lengths == {config.WINDOW_SAMPLES}, f"lengths seen: {sorted(lengths)}")
    check("windows are int16", all(w.samples.dtype == np.int16 for w in all_windows),
          str(all_windows[0].samples.dtype))
    check("window indices are contiguous from 0",
          [w.index for w in all_windows] == list(range(len(all_windows))))

    check("provenance recorded for every window",
          all(w.source_ranges for w in all_windows))

    # Windows are cut per utterance and never glued across a pause, so every
    # window maps to exactly one contiguous stretch of the call.
    glued = [w.index for w in all_windows
             if len(w.source_ranges) != 1 or w.spans_discontinuity]
    check("no window spans a pause (one utterance each)",
          not glued, f"glued windows {glued[:8]}" if glued else "")

    floor = int(config.UTTERANCE_MIN_SECONDS * config.SAMPLE_RATE)
    padded = [w for w in all_windows if w.padded]
    print(f"     {len(padded)}/{len(all_windows)} windows are short utterances "
          f"tile-padded to the model's input length; "
          f"{analyzer.unscored_speech_samples / config.SAMPLE_RATE:.1f}s of speech "
          f"fell under the {config.UTTERANCE_MIN_SECONDS}s floor, unscored")
    check("padded windows carry at least the floor of real speech",
          all(floor <= w.real_samples < config.WINDOW_SAMPLES for w in padded))
    check("padding repeats the utterance itself (model-card tiling)",
          all(np.array_equal(w.samples[w.real_samples:],
                             w.samples[:len(w.samples) - w.real_samples])
              for w in padded))

    # Within one long utterance, full windows advance by exactly the hop.
    # NullVad keeps every frame, so the whole timeline is a single utterance
    # starting at sample 0 and window k must equal audio[k*hop : k*hop + window].
    from app.vad import NullVad
    unbroken = TrackAnalyzer("far", VoiceActivityDetector(backend=NullVad()))
    unbroken_windows = []
    for i in range(0, len(audio), 64000):
        unbroken_windows += unbroken.push_chunk(audio[i:i + 64000])[2]
    hop, win = config.WINDOW_HOP_SAMPLES, config.WINDOW_SAMPLES
    misplaced = [k for k, w in enumerate(unbroken_windows)
                 if not np.array_equal(w.samples, audio[k * hop:k * hop + win])]
    check(f"a long utterance slides by exactly {hop} samples",
          bool(unbroken_windows) and not misplaced,
          f"misplaced windows {misplaced[:8]}" if misplaced
          else f"{len(unbroken_windows)} windows, sample-exact")

    # The labelled audio above may contain no 3-4 s utterance at all, which
    # leaves both padding checks passing vacuously. Force one: a single 3.5 s
    # utterance must become exactly one padded window whose real part is the
    # input verbatim and whose remainder tiles it.
    short = TrackAnalyzer("far", VoiceActivityDetector(backend=NullVad()))
    clip = audio[int(1.5 * config.SAMPLE_RATE):int(5.0 * config.SAMPLE_RATE)]  # speech, past the lead-in
    got = short.push_chunk(clip)[2] + short.flush()[2]
    w0 = got[0] if got else None
    check("a 3.5 s utterance becomes one tile-padded window",
          len(got) == 1 and w0.padded
          and np.array_equal(w0.samples[:w0.real_samples], clip[:w0.real_samples])
          and np.array_equal(w0.samples[w0.real_samples:],
                             w0.samples[:len(w0.samples) - w0.real_samples]),
          f"{len(got)} window(s), padded={[w.padded for w in got]}, "
          f"real={[round(w.real_samples / config.SAMPLE_RATE, 2) for w in got]}s")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-model", action="store_true",
                    help="skip the parity check (avoids loading the 1.36 GB model)")
    args = ap.parse_args()

    print(f"model : {config.MODEL_PATH}")
    print(f"vad   : {config.SILERO_VAD_PATH}")
    print(f"window: {config.WINDOW_SAMPLES} samples, hop {config.WINDOW_HOP_SAMPLES}")

    clips = find_speech_clips()
    test_resampler()
    test_vad_and_windows(clips)
    if args.skip_model:
        print("\n1. PARITY -- skipped (--skip-model)")
    else:
        test_parity(clips)

    failed = [r for r in results if r[1] == FAIL]
    print(f"\n{'=' * 62}")
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name}  --  {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
