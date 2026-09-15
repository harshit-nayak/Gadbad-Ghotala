"""
Audio preprocessing pipeline for XLSR-SLS.

The model accepts exactly one shape: 16 kHz, mono, float32, **64,600 samples**
(~4.04 s). `fc1` expects a 22,847-d flatten, so the window length is fixed —
this module is the funnel that turns any input clip into that.

    load (wav/flac/mp3/ogg/opus/...)
      -> downmix to mono
      -> resample to 16 kHz
      -> limit length to 64,600 samples   (crop long clips / tile-repeat short ones)
      -> [optional] peak-normalize

Use as a library:

    from preprocess import preprocess_file, WINDOW, SAMPLE_RATE
    x = preprocess_file("clip.mp3", crop="loudest")   # -> float32 (64600,)

or as a CLI to materialise the clip:

    python preprocess.py clip.mp3                        # -> clip_16k_64600.wav
    python preprocess.py *.flac --outdir prepared/ --crop loudest
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
WINDOW = 64_600            # samples the model requires — do not change
CLIP_SECONDS = WINDOW / SAMPLE_RATE   # 4.0375 s


# --------------------------------------------------------------------------- #
# individual steps
# --------------------------------------------------------------------------- #
def load(path: str | Path) -> tuple[np.ndarray, int]:
    """Read an audio file -> (float32 samples, sample_rate). May be multi-channel."""
    import soundfile as sf

    p = Path(path)
    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception as e:  # noqa: BLE001
        extra = "" if p.exists() else "  (file does not exist)"
        raise RuntimeError(
            f"could not read {path!r}: {e}{extra}\n"
            "soundfile reads wav/flac/ogg/opus/mp3. For anything else convert first:\n"
            f'  ffmpeg -i "{path}" -ar 16000 -ac 1 "{p.with_name(p.stem + "_16k.wav")}"'
        ) from e
    return data, sr


def to_mono(data: np.ndarray) -> np.ndarray:
    """(frames, channels) -> (frames,) by averaging channels."""
    return data if data.ndim == 1 else data.mean(axis=1)


def resample(audio: np.ndarray, sr_in: int, sr_out: int = SAMPLE_RATE) -> np.ndarray:
    if sr_in == sr_out:
        return audio
    from scipy.signal import resample_poly

    g = math.gcd(sr_in, sr_out)
    return resample_poly(audio, sr_out // g, sr_in // g).astype(np.float32)


def fit_length(audio: np.ndarray, length: int = WINDOW, crop: str = "start") -> np.ndarray:
    """Force the clip to exactly `length` samples.

    Short clips  -> tile-repeat up to `length` (matches the model card's pad).
    Long clips   -> keep one `length`-sample window:
        start    first window (deterministic; matches ASVspoof protocol scoring)
        center   middle window
        loudest  highest-energy window (skips leading/trailing silence)
    """
    n = len(audio)
    if n == length:
        return audio
    if n < length:
        return np.tile(audio, math.ceil(length / n))[:length]
    if crop == "start":
        s = 0
    elif crop == "center":
        s = (n - length) // 2
    elif crop == "loudest":
        power = np.concatenate([[0.0], np.cumsum(audio.astype(np.float64) ** 2)])
        s = int(np.argmax(power[length:] - power[:-length]))
    else:
        raise ValueError(f"unknown crop mode {crop!r} (start|center|loudest)")
    return audio[s:s + length]


def peak_normalize(audio: np.ndarray, target: float = 0.97) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    return audio * (target / peak) if peak > 0 else audio


# --------------------------------------------------------------------------- #
# full pipeline
# --------------------------------------------------------------------------- #
def preprocess_array(audio: np.ndarray, sr: int, crop: str = "start",
                     normalize: bool = False) -> np.ndarray:
    audio = to_mono(np.asarray(audio, dtype=np.float32))
    audio = resample(audio, sr, SAMPLE_RATE)
    audio = fit_length(audio, WINDOW, crop)
    if normalize:
        audio = peak_normalize(audio)
    return np.ascontiguousarray(audio, dtype=np.float32)


def preprocess_file(path: str | Path, crop: str = "start",
                    normalize: bool = False) -> np.ndarray:
    """Any audio file -> float32 (64600,) ready for the model."""
    data, sr = load(path)
    return preprocess_array(data, sr, crop=crop, normalize=normalize)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="+")
    ap.add_argument("-o", "--out", help="output wav (single input only)")
    ap.add_argument("--outdir", help="output directory for batch mode")
    ap.add_argument("--crop", default="start", choices=["start", "center", "loudest"])
    ap.add_argument("--normalize", action="store_true", help="peak-normalize to -0.3 dBFS")
    args = ap.parse_args(argv)

    import soundfile as sf

    if args.out and len(args.audio) > 1:
        ap.error("-o/--out takes one input; use --outdir for batches")

    for src in map(Path, args.audio):
        clip = preprocess_file(src, crop=args.crop, normalize=args.normalize)
        if args.out:
            dst = Path(args.out)
        else:
            name = f"{src.stem}_16k_64600.wav"
            dst = (Path(args.outdir) / name) if args.outdir else src.with_name(name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dst), clip, SAMPLE_RATE, subtype="PCM_16")
        print(f"{src.name}  ->  {dst}   ({len(clip)} samples / {len(clip)/SAMPLE_RATE:.2f}s, crop={args.crop})")


if __name__ == "__main__":
    _main()
