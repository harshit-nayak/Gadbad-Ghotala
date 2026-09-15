"""
XLSR-SLS audio deepfake detector — ONNX inference.

Model: "Audio Deepfake Detection with Self-Supervised XLS-R and SLS Classifier"
       (Zhang, Wen, Hu — ACM MM 2024).  Checkpoint: xlsr-sls.onnx
       repo: https://huggingface.co/SpeechAntiSpoofingBenchmarks/XLSR-SLS

Contract (from the model card):
  - input : raw waveform, 16 kHz mono, float32, EXACTLY 64,600 samples (~4.04 s)
  - pad   : if shorter, tile-repeat to length; if longer, take the first 64,600
  - output: 2-class log-softmax; index 1 = bona fide (real), index 0 = spoof (fake)
            higher score at index 1  ->  more likely genuine

Usage:
  python xlsr_sls_infer.py clip1.wav clip2.flac
  python xlsr_sls_infer.py clip.wav --provider openvino
  python xlsr_sls_infer.py long.wav --long-audio window --agg min
  python xlsr_sls_infer.py *.wav --json out.json --threshold 0.5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from preprocess import (  # the preprocessing pipeline lives in preprocess.py
    SAMPLE_RATE,
    WINDOW,
    fit_length as crop_window,
    load,
    resample,
    to_mono,
)


def load_audio(path: str | Path) -> np.ndarray:
    """Any audio file -> float32 mono @ 16 kHz (no length limiting yet)."""
    data, sr = load(path)
    return np.ascontiguousarray(resample(to_mono(data), sr, SAMPLE_RATE), dtype=np.float32)


def sliding_windows(audio: np.ndarray, length: int = WINDOW, overlap: float = 0.5):
    """Yield fixed-length windows over a long clip (last one tile-padded)."""
    if len(audio) <= length:
        yield crop_window(audio, length, "start")
        return
    hop = max(1, int(length * (1.0 - overlap)))
    for start in range(0, len(audio) - length + hop, hop):
        chunk = audio[start:start + length]
        yield crop_window(chunk, length, "start") if len(chunk) < length else chunk


# --------------------------------------------------------------------------- #
# model
# --------------------------------------------------------------------------- #
PROVIDER_MAP = {
    "cpu": ["CPUExecutionProvider"],
    "openvino": ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    "dml": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
}


class Detector:
    def __init__(self, onnx_path: str | Path, provider: str = "cpu", threads: int | None = None):
        import onnxruntime as ort

        onnx_path = Path(onnx_path)
        if not onnx_path.is_file():
            raise FileNotFoundError(
                f"{onnx_path} not found. Download it with:\n"
                '  python -c "from huggingface_hub import hf_hub_download as d; '
                "d('SpeechAntiSpoofingBenchmarks/XLSR-SLS','xlsr-sls.onnx',local_dir='.')\""
            )

        want = PROVIDER_MAP.get(provider)
        if want is None:
            raise ValueError(f"unknown provider {provider!r}; choose from {list(PROVIDER_MAP)}")
        available = ort.get_available_providers()
        use = [p for p in want if p in available] or ["CPUExecutionProvider"]
        if use[0] != want[0]:
            print(f"[warn] {want[0]} unavailable, falling back to {use[0]}", file=sys.stderr)

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if threads:
            so.intra_op_num_threads = threads

        self.sess = ort.InferenceSession(str(onnx_path), sess_options=so, providers=use)
        self.provider = self.sess.get_providers()[0]

        ins = self.sess.get_inputs()
        # primary waveform input = the float tensor whose shape can hold WINDOW
        self.wave_in = next(
            (i for i in ins if "float" in i.type and (len(i.shape) <= 3)), ins[0]
        )
        self.wave_rank = len(self.wave_in.shape)
        # optional fairseq padding_mask input (bool, True = padded); we never pad -> all False
        self.mask_in = next(
            (i for i in ins if i is not self.wave_in and ("mask" in i.name.lower())), None
        )
        self.out_name = self.sess.get_outputs()[0].name

    def _feed(self, windows: np.ndarray) -> dict:
        """windows: (N, WINDOW) float32 -> onnx feed dict."""
        x = windows.astype(np.float32)
        # match the exported rank: (N, W), (N, 1, W) or (W,) for batch-1 exports
        if self.wave_rank == 1:
            x = x[0]
        elif self.wave_rank == 3:
            x = x[:, None, :]
        feed = {self.wave_in.name: x}
        if self.mask_in is not None:
            mshape = [d if isinstance(d, int) else s
                      for d, s in zip(self.mask_in.shape, (x.shape[0], WINDOW))]
            feed[self.mask_in.name] = np.zeros(mshape, dtype=bool)
        return feed

    def score_windows(self, windows: np.ndarray):
        """Return (P(bona fide), bona-fide log-prob) per window, each shape (N,).

        The model already emits log-softmax; index 1 = bona fide. The raw
        log-prob is the score the paper / Arena threshold on; the probability
        is the same information in a friendlier range.
        """
        out = np.asarray(self.sess.run([self.out_name], self._feed(windows))[0])
        out = out.reshape(-1, out.shape[-1])                  # (N, 2)
        logp = out - _logsumexp(out, axis=-1, keepdims=True)  # re-normalise (harmless if already log-softmax)
        return np.exp(logp[:, 1]), logp[:, 1]

    def score_file(self, path, long_audio: str = "truncate", agg: str = "mean",
                   overlap: float = 0.5, crop: str = "start") -> "Result":
        t0 = time.perf_counter()
        audio = load_audio(path)
        dur = len(audio) / SAMPLE_RATE

        if long_audio == "window":
            wins = np.stack(list(sliding_windows(audio, WINDOW, overlap)))
        else:
            wins = crop_window(audio, WINDOW, crop)[None, :]

        probs, logprobs = self.score_windows(wins)
        reduce = {"mean": np.mean, "min": np.min, "median": np.median}[agg]
        p = float(reduce(probs))

        return Result(
            file=str(path),
            duration_s=round(dur, 3),
            n_windows=len(probs),
            p_bonafide=p,
            p_spoof=1.0 - p,
            score_logprob=float(reduce(logprobs)),
            window_probs=[round(float(x), 6) for x in probs],
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )


def _logsumexp(a, axis=None, keepdims=False):
    m = np.max(a, axis=axis, keepdims=True)
    out = m + np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True))
    return out if keepdims else np.squeeze(out, axis=axis)


@dataclass
class Result:
    file: str
    duration_s: float
    n_windows: int
    p_bonafide: float
    p_spoof: float
    score_logprob: float
    window_probs: list
    latency_ms: float
    label: str = ""

    def decide(self, threshold: float) -> "Result":
        self.label = "bona fide" if self.p_bonafide >= threshold else "spoof"
        return self


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", nargs="+", help="audio file(s): wav/flac/ogg/opus")
    ap.add_argument("--model", default="xlsr-sls.onnx", help="path to xlsr-sls.onnx")
    ap.add_argument("--provider", default="cpu", choices=list(PROVIDER_MAP),
                    help="execution provider (default: cpu)")
    ap.add_argument("--threads", type=int, default=None, help="intra-op threads (default: all cores)")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="P(bona fide) below which a clip is called spoof (default: 0.5)")
    ap.add_argument("--long-audio", default="truncate", choices=["truncate", "window"],
                    help="'truncate' scores one 4.04 s window (model card default); "
                         "'window' scores overlapping windows across the whole clip")
    ap.add_argument("--crop", default="start", choices=["start", "center", "loudest"],
                    help="which 4.04 s window to keep when --long-audio truncate "
                         "(loudest = highest-energy window, skips silence)")
    ap.add_argument("--agg", default="mean", choices=["mean", "min", "median"],
                    help="how to combine window scores when --long-audio window (min = most suspicious)")
    ap.add_argument("--overlap", type=float, default=0.5, help="window overlap fraction (default: 0.5)")
    ap.add_argument("--json", metavar="PATH", help="also write results as JSON to PATH")
    ap.add_argument("--quiet", action="store_true", help="only print the verdict line per file")
    args = ap.parse_args(argv)

    det = Detector(args.model, provider=args.provider, threads=args.threads)
    if not args.quiet:
        print(f"model    : {args.model}")
        print(f"provider : {det.provider}")
        print(f"input    : {det.wave_in.name} {det.wave_in.shape} {det.wave_in.type}"
              + (f"  + mask '{det.mask_in.name}'" if det.mask_in is not None else ""))
        print(f"threshold: P(bona fide) >= {args.threshold}\n")

    results = []
    for path in args.audio:
        try:
            r = det.score_file(path, long_audio=args.long_audio, agg=args.agg,
                               overlap=args.overlap, crop=args.crop).decide(args.threshold)
        except Exception as e:  # noqa: BLE001
            print(f"{path}\tERROR\t{e}", file=sys.stderr)
            continue
        results.append(r)
        mark = "REAL " if r.label == "bona fide" else "FAKE "
        if args.quiet:
            print(f"{mark}  {r.p_bonafide:6.4f}  {path}")
        else:
            print(f"{mark} {Path(path).name}")
            print(f"     P(bona fide) = {r.p_bonafide:.4f}   P(spoof) = {r.p_spoof:.4f}")
            print(f"     {r.duration_s:.2f} s | {r.n_windows} window(s) | {r.latency_ms:.0f} ms")
            if r.n_windows > 1:
                print(f"     per-window: {', '.join(f'{x:.3f}' for x in r.window_probs)}")
            print()

    if args.json and results:
        Path(args.json).write_text(json.dumps([asdict(r) for r in results], indent=2))
        if not args.quiet:
            print(f"wrote {args.json}")

    # exit code: 0 all real, 1 any spoof, 2 nothing scored
    if not results:
        return 2
    return 1 if any(r.label == "spoof" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
