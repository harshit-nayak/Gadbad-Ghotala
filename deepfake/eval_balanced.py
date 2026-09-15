"""
Balanced evaluation of XLSR-SLS on an ASVspoof-style folder.

Picks a class-balanced random sample (half genuine / half fake) from a folder of
clips, runs each through the preprocessing pipeline + the ONNX model, and stores
per-file predictions plus an aggregate report (confusion matrix, accuracy, EER).

    python eval_balanced.py --folder flac_D_ac/flac_D \
                            --keys ASVspoof5.dev.track_1.tsv \
                            --n 1500 --out results

Outputs (under --out):
    predictions.tsv   filename  true_label  p_genuine  score_logprob  verdict  correct
    summary.json      counts, confusion matrix, accuracy, EER, timing, config

Re-running resumes: files already in predictions.tsv are skipped.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

from preprocess import SAMPLE_RATE, WINDOW, preprocess_file
from xlsr_sls_infer import Detector

AUDIO_EXT = {".flac", ".wav", ".mp3", ".ogg", ".opus", ".m4a"}
_UTT_RE = re.compile(r"^[A-Z]_[A-Za-z0-9]*\d{4,}$")   # D_0000000001, LA_E_1234567, ...
VG = {"bonafide": "genuine", "spoof": "fake"}


# --------------------------------------------------------------------------- #
# protocol / metrics helpers
# --------------------------------------------------------------------------- #
def read_keys(path: Path) -> dict[str, str]:
    """ASVspoof protocol (2019/2021/5) -> {utt_id: 'bonafide'|'spoof'}."""
    keys: dict[str, str] = {}
    for line in path.read_text().splitlines():
        toks = line.replace(",", " ").replace("\t", " ").split()
        lab = next((t.lower() for t in toks if t.lower() in ("bonafide", "spoof")), None)
        if lab is None:
            continue
        cand = [t for t in toks if _UTT_RE.match(t)]
        if cand:
            keys[max(cand, key=len)] = lab   # longest id-like token = utterance id
    return keys


def eer(genuine_scores: np.ndarray, fake_scores: np.ndarray) -> tuple[float, float]:
    """Equal error rate (%) and its threshold, scores are P(genuine) (higher = genuine)."""
    s = np.concatenate([genuine_scores, fake_scores])
    y = np.concatenate([np.ones(len(genuine_scores)), np.zeros(len(fake_scores))])
    order = np.argsort(s)
    s, y = s[order], y[order]
    n_gen, n_fake = len(genuine_scores), len(fake_scores)
    fn = np.cumsum(y)                                   # genuine below thr -> miss
    fp = n_fake - (np.arange(len(y)) + 1 - fn)          # fake at/above thr -> false alarm
    frr = fn / max(n_gen, 1)
    far = fp / max(n_fake, 1)
    i = int(np.nanargmin(np.abs(frr - far)))
    return float((frr[i] + far[i]) / 2 * 100), float(s[i])


# --------------------------------------------------------------------------- #
# sampling
# --------------------------------------------------------------------------- #
def build_sample(folder: Path, keys: dict[str, str], n: int, seed: int):
    by_stem = {}
    for p in folder.rglob("*"):
        if p.suffix.lower() in AUDIO_EXT and p.is_file():
            by_stem.setdefault(p.stem, p)

    pools: dict[str, list[Path]] = {"genuine": [], "fake": []}
    for stem, path in by_stem.items():
        lab = VG.get(keys.get(stem, ""))
        if lab:
            pools[lab].append(path)
    for v in pools.values():
        v.sort()

    per_class = n // 2
    rng = random.Random(seed)
    chosen: list[tuple[Path, str]] = []
    for cls, pool in pools.items():
        if len(pool) < per_class:
            raise SystemExit(
                f"only {len(pool)} '{cls}' files available in {folder} "
                f"(need {per_class}); lower --n or point at more data"
            )
        chosen += [(p, cls) for p in rng.sample(pool, per_class)]
    rng.shuffle(chosen)
    print(f"folder has {len(pools['genuine'])} genuine + {len(pools['fake'])} fake labelled clips; "
          f"sampling {per_class} of each")
    return chosen


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", type=Path, default=Path("flac_D_ac/flac_D"))
    ap.add_argument("--keys", type=Path, default=Path("ASVspoof5.dev.track_1.tsv"))
    ap.add_argument("--n", type=int, default=1500, help="total clips (split 50/50); default 1500")
    ap.add_argument("--out", type=Path, default=Path("results"))
    ap.add_argument("--model", default="xlsr-sls.onnx")
    ap.add_argument("--provider", default="cpu")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--crop", default="start", choices=["start", "center", "loudest"],
                    help="which 4.04 s window to score (default: start, matches ASVspoof protocol)")
    ap.add_argument("--normalize", action="store_true", help="peak-normalize each clip")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="P(genuine) below this => 'fake' (default 0.5)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if not args.folder.is_dir():
        raise SystemExit(f"{args.folder} is not a directory")
    if not args.keys.is_file():
        raise SystemExit(f"labels file {args.keys} not found")

    args.out.mkdir(parents=True, exist_ok=True)
    pred_path = args.out / "predictions.tsv"

    keys = read_keys(args.keys)
    print(f"loaded {len(keys)} labels from {args.keys.name}")
    sample = build_sample(args.folder, keys, args.n, args.seed)

    done: set[str] = set()
    if pred_path.exists():
        for ln in pred_path.read_text().splitlines()[1:]:
            if ln:
                done.add(ln.split("\t", 1)[0])
        print(f"resuming: {len(done)} already in {pred_path.name}")

    todo = [(p, c) for p, c in sample if p.stem not in done]
    fh = pred_path.open("a")
    if not done:
        fh.write("filename\ttrue_label\tp_genuine\tscore_logprob\tverdict\tcorrect\n")

    if todo:
        det = Detector(args.model, provider=args.provider)
        print(f"model: {args.model} | provider: {det.provider} | batch {args.batch} | "
              f"crop={args.crop} normalize={args.normalize}\n")
        t0 = time.perf_counter()
        n_done = 0
        buf_x: list[np.ndarray] = []
        buf_meta: list[tuple[str, str]] = []

        def flush():
            nonlocal n_done
            if not buf_x:
                return
            probs, logp = det.score_windows(np.stack(buf_x))
            for (stem, cls), pg, lp in zip(buf_meta, probs, logp):
                verdict = "fake" if pg < args.threshold else "genuine"
                ok = "yes" if verdict == cls else "NO"
                fh.write(f"{stem}\t{cls}\t{pg:.6f}\t{lp:.4f}\t{verdict}\t{ok}\n")
            fh.flush()
            n_done += len(buf_meta)
            rate = n_done / (time.perf_counter() - t0)
            print(f"  {n_done}/{len(todo)}  {rate:.1f} clips/s  "
                  f"ETA {(len(todo)-n_done)/rate/60:.1f} min", end="\r")
            buf_x.clear()
            buf_meta.clear()

        for path, cls in todo:
            try:
                buf_x.append(preprocess_file(path, crop=args.crop, normalize=args.normalize))
                buf_meta.append((path.stem, cls))
            except Exception as e:  # noqa: BLE001
                print(f"\n  skip {path.name}: {e}", file=sys.stderr)
                continue
            if len(buf_x) >= args.batch:
                flush()
        flush()
        fh.close()
        print(f"\n\nscored {n_done} clips in {(time.perf_counter()-t0)/60:.1f} min")
    else:
        fh.close()
        print("all sampled clips already scored")

    report(pred_path, args)
    return 0


def report(pred_path: Path, args):
    rows = [ln.split("\t") for ln in pred_path.read_text().splitlines()[1:] if ln]
    truth = np.array([r[1] for r in rows])
    pg = np.array([float(r[2]) for r in rows])
    verdict = np.array([r[4] for r in rows])

    gen, fake = pg[truth == "genuine"], pg[truth == "fake"]
    tp = int(np.sum((truth == "fake") & (verdict == "fake")))       # fake caught
    fn = int(np.sum((truth == "fake") & (verdict == "genuine")))    # fake missed
    tn = int(np.sum((truth == "genuine") & (verdict == "genuine")))
    fp = int(np.sum((truth == "genuine") & (verdict == "fake")))    # false alarm
    total = len(rows)
    acc = (tp + tn) / total if total else 0.0
    eer_pct, eer_thr = (eer(gen, fake) if len(gen) and len(fake) else (float("nan"), float("nan")))

    summary = {
        "model": args.model,
        "folder": str(args.folder),
        "n_scored": total,
        "class_counts": {"genuine": int((truth == "genuine").sum()),
                         "fake": int((truth == "fake").sum())},
        "threshold": args.threshold,
        "crop": args.crop,
        "normalize": args.normalize,
        "confusion": {"fake_caught": tp, "fake_missed": fn,
                      "genuine_ok": tn, "genuine_flagged_fake": fp},
        "accuracy": round(acc, 4),
        "eer_percent": round(eer_pct, 3),
        "eer_threshold_p_genuine": round(eer_thr, 4),
        "mean_p_genuine": {"genuine_clips": round(float(gen.mean()), 4) if len(gen) else None,
                           "fake_clips": round(float(fake.mean()), 4) if len(fake) else None},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 48)
    print(f"scored           : {total}   ({summary['class_counts']['genuine']} genuine, "
          f"{summary['class_counts']['fake']} fake)")
    print(f"mean P(genuine)   : genuine clips {summary['mean_p_genuine']['genuine_clips']}  "
          f"| fake clips {summary['mean_p_genuine']['fake_clips']}")
    print(f"\nconfusion @ P(genuine) >= {args.threshold}")
    print(f"                     predicted")
    print(f"                   fake   genuine")
    print(f"  actual fake     {tp:6d}  {fn:6d}")
    print(f"  actual genuine  {fp:6d}  {tn:6d}")
    print(f"\naccuracy          : {acc*100:.2f}%")
    print(f"EER               : {eer_pct:.2f}%   (at P(genuine) = {eer_thr:.3f})")
    print(f"\nwrote {pred_path}")
    print(f"wrote {args.out / 'summary.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
