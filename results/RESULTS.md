# XLSR-Mamba — ASVspoof5 dev track 1 evaluation

**Date:** 2026-09-10
**Model:** `model.safetensors` (XLSR-Mamba, dual-column bidirectional SSM, 319.3 M params)
**Eval script:** `evaluate_model.py` (pure-PyTorch)
**Hardware:** NVIDIA GeForce RTX 5060 Laptop GPU (8 GB, `sm_120`), PyTorch 2.10.0+cu128

## Test set

| | |
|---|---|
| Source TSV | `ASVspoof5.dev.track_1.tsv` (140,950 rows) |
| FLAC available locally | 46,150 of 140,950 (`flac_D/`) |
| Utterances scored | two runs: **9,000** (primary) and **4,000**, uniform random subsets, seed 1234 |
| Class balance | 9k run: 1,912 bonafide / 7,088 spoof · 4k run: 836 / 3,164 |
| Inference | GPU (RTX 5060), batch size 32, ~0.07 s/utterance (9k run 11.5 min, 4k run 4.5 min) |

Score convention: higher = more bonafide (`out[:, 1]`, the bonafide logit). No threshold
is applied by the model — scores are raw.

## Headline metrics

Primary result is the 9,000-utterance run; the 4,000 run is consistent with it.

| Metric | 9,000 utts | 4,000 utts |
|---|---|---|
| **EER** | **2.77%** (95% CI 2.39–3.17%) | 2.87% (95% CI 2.32–3.48%) |
| ROC AUC | 0.9907 | 0.9895 |
| EER threshold | −2.3629 | −2.2779 |
| Accuracy @ EER threshold | 97.23% | 97.12% |
| Balanced accuracy @ EER threshold | 97.23% | 97.13% |
| F1 (bonafide) @ EER threshold | 93.72 | 93.39 |
| Argmax accuracy (`p_genuine ≥ 0.5`) | 86.14% | 86.15% |

**Argmax vs EER threshold.** Deciding by the raw softmax (`p_genuine ≥ 0.5`) gives only
~86% accuracy: nearly all spoof is caught but only ~37% of bonafide — the score
distribution is shifted negative on this out-of-domain set, so most genuine speech falls
below `p = 0.5`. The EER threshold (≈ −2.36, i.e. `p_genuine ≈ 0.09`) is the correct
operating point and gives 97.2% accuracy. The `verdict`/`correct` columns in the
predictions TSV use the naive argmax rule, matching the requested format.

Reference (paper, different/easier benchmarks): ASVspoof 2021 LA 0.93%, DF 1.88%, In-the-Wild 6.71%.
ASVspoof5 is newer and harder and the model was not trained on it, so a higher EER is expected.

## Confusion matrix @ EER threshold — 9,000-utterance run (score ≥ −2.3629 → bonafide)

| actual \ predicted | bonafide | spoof | total |
|---|---:|---:|---:|
| **bonafide** | 1,859 (TP) | 53 (FN) | 1,912 |
| **spoof** | 196 (FP) | 6,892 (TN) | 7,088 |
| **total** | 2,055 | 6,945 | 9,000 |

- Spoof false-accept rate (FAR): 2.77%
- Bonafide false-reject rate (FRR): 2.77%
- Accuracy 97.23% · Precision 90.46% · Recall 97.23% · F1 93.72

(4,000-run matrix: TP 812 / FN 24 / FP 91 / TN 3,073 at threshold −2.2779.)

## Threshold behaviour

See `threshold_sweep_9000.csv` for the full sweep. Key points (9,000-utterance run):

| threshold | FAR % | FRR % | accuracy % | F1 | note |
|---:|---:|---:|---:|---:|---|
| −3.55 | 14.43 | 0.16 | 88.60 | 78.82 | catch almost all spoof, many false alarms |
| −2.73 | 4.36 | 1.41 | 96.27 | 91.82 | high-recall region |
| **−2.36** | **2.75** | **2.77** | **97.24** | **93.75** | **EER** |
| −1.92 | 1.81 | 5.54 | 97.40 | 93.92 | F1 / accuracy peak, precision-leaning |
| −1.51 | 1.28 | 12.03 | 96.43 | 91.29 | low-FAR gate |
| 0.00 | 0.62 | 62.55 | 86.22 | 53.59 | raw logit — degraded, scores offset negative |

Choose by cost:
- **Anti-spoof gate** (minimise spoof acceptance): threshold ≥ −1.5, FAR ≈ 1.3%, but rejects ~12% of genuine users.
- **Screening** (don't miss real speech): threshold ≤ −3.5, FRR ≈ 0.16%.
- **Default / balanced:** EER threshold ≈ −2.36 (or −1.92 for peak accuracy 97.4%).

Thresholds must be recalibrated on a dev set for any new score file — the −2.36 value is
specific to this run.

## Files

Primary run has the `_9000` suffix; the earlier 4,000-utterance run keeps the plain names.

| File | Description |
|---|---|
| `scores_dev_track1_sub9000.txt` | Raw per-utterance scores (`<utt_id> <score>`, 9,000 lines) |
| `scores_dev_track1_sub9000_predictions.tsv` | Per-utterance table: `name, true_label, p_genuine, score_logprob, verdict, correct` |
| `confusion_matrix_9000.csv` | 2×2 confusion matrix at the EER threshold |
| `threshold_sweep_9000.csv` | FAR/FRR/accuracy/precision/recall/F1 across 23 thresholds |
| `results_9000.png` | 4-panel figure: score distributions, ROC, DET, metrics-vs-threshold |
| `eval_sub9000.log` | Full run log (model build, weight loading, inference) |
| `scores_dev_track1_sub4000*`, `*_9000`-less files | Earlier 4,000-utterance run (same seed, consistent) |

## Reproduce

```bash
python evaluate_model.py --max_samples 9000 --seed 1234 --batch_size 32 --device cuda \
    --scores_out results/scores_dev_track1_sub9000.txt
python confusion_matrix.py --scores results/scores_dev_track1_sub9000.txt
python threshold_sweep.py  --scores results/scores_dev_track1_sub9000.txt
python plot_results.py     --scores results/scores_dev_track1_sub9000.txt --out results/results_9000.png
```

Full local dev set (46,150 files, ~55 min on the RTX 5060):
`python evaluate_model.py --batch_size 32 --device cuda`

GPU setup: `pip install --force-reinstall "torch==2.10.0" "torchvision==0.25.0"
--index-url https://download.pytorch.org/whl/cu128` (cu128 wheel required for the
RTX 5060's Blackwell `sm_120`; the default PyPI wheel is CPU-only).

## Fixes applied to `evaluate_model.py`

The script as originally written would have scored a half-initialised model:

| Bug | Impact | Fix |
|---|---|---|
| `num_encoders=6` hardcoded | Built 3 Mamba layers/direction vs. 6 in checkpoint; 60 weight tensors silently dropped while printing "Loaded 565/565 OK" | Set to 12 (matches `main.py`); 0 missing/unexpected |
| Zero-padding short clips | ~3% of files preprocessed unlike training | Repeat-tile, matching `XLSR_Mamba_repo/utils.py:pad` |
| Load check ignored unexpected tensors | Mismatch hidden | Hard-fail on any missing/unexpected tensor |
| `--max_samples` took first N rows | TSV grouped by speaker/attack → biased subset | Added `--seed` for uniform random sampling |
| `scores_out` dir not created | Crash on nested output path | `os.makedirs` before write |

Not replicated: the reference calls `.train()` on wav2vec2 during feature extraction
(`layerdrop=0.05` active → nondeterministic). Running in `eval()` is correct.
