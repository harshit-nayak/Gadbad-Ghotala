# XLSR-SLS deepfake-audio inference

Runs the **XLS-R 300M + SLS** speech anti-spoofing model
([Zhang, Wen & Hu, ACM MM 2024](https://doi.org/10.1145/3664647.3681345);
weights from [SpeechAntiSpoofingBenchmarks/XLSR-SLS](https://huggingface.co/SpeechAntiSpoofingBenchmarks/XLSR-SLS))
locally via ONNX Runtime — no `fairseq`, no PyTorch, no `xlsr2_300m.pt`.

## Files

| File | What |
|---|---|
| `xlsr-sls.onnx` | the model (1.36 GB). input `wav [batch, 64600]` f32 → output `logits [batch, 2]` (log-softmax; **index 1 = genuine**) |
| `preprocess.py` | audio preprocessing pipeline — any clip → 16 kHz / mono / exactly 64,600 samples |
| `xlsr_sls_infer.py` | model wrapper (`Detector`) + single-clip CLI |
| `eval_balanced.py` | balanced dataset evaluation: sample N clips 50/50, score, write predictions + report |
| `ASVspoof5.dev.track_1.tsv` | ground-truth labels for the ASVspoof5 dev set (from `ASVspoof5_protocols.tar`) |
| `flac_D_ac/flac_D/` | 47,334 dev clips (ASVspoof5 dev, part 3 of 3) |
| `MMpaper_model.pth` | original PyTorch state_dict — **unused** by this ONNX pipeline; safe to delete |
| `flac_D_ac.tar` | the archive `flac_D_ac/` was extracted from — **redundant**; safe to delete |

## Setup

```bash
pip install -r requirements.txt
# (re-)download the model:
python -c "from huggingface_hub import hf_hub_download as d; d('SpeechAntiSpoofingBenchmarks/XLSR-SLS','xlsr-sls.onnx',local_dir='.')"
```

## 1. Preprocessing pipeline (`preprocess.py`)

The model takes exactly one shape: **16 kHz, mono, float32, 64,600 samples (~4.04 s)** —
`fc1` needs a 22,847-d flatten, so the length is fixed. The pipeline:

```
load (wav/flac/mp3/ogg/opus) → downmix mono → resample 16 kHz
  → limit length to 64,600 samples → [optional] peak-normalize
```

Length limiting (`--crop`):

| mode | kept |
|---|---|
| `start` (default) | first 4.04 s — matches the ASVspoof / paper scoring protocol |
| `center` | middle 4.04 s |
| `loudest` | highest-energy 4.04 s window (skips leading/trailing silence) |

Clips shorter than 4.04 s are tile-repeated.

```bash
python preprocess.py clip.mp3                       # -> clip_16k_64600.wav
python preprocess.py *.flac --outdir prepared/ --crop loudest
```
```python
from preprocess import preprocess_file
x = preprocess_file("clip.mp3", crop="loudest")    # float32 (64600,)
```

## 2. Single-clip detection (`xlsr_sls_infer.py`)

```bash
python xlsr_sls_infer.py clip.wav
python xlsr_sls_infer.py *.flac --quiet --json out.json
python xlsr_sls_infer.py long.wav --long-audio window --agg min   # sweep a long clip
```
```python
from xlsr_sls_infer import Detector
r = Detector("xlsr-sls.onnx").score_file("clip.wav").decide(threshold=0.5)
print(r.label, r.p_bonafide)      # 'bona fide' | 'spoof'
```
`p_bonafide` = P(real); `score_logprob` = raw genuine log-prob (what the paper thresholds on).

## 3. Balanced evaluation (`eval_balanced.py`)

Picks a class-balanced random sample from a labelled folder, runs the full
pipeline + model, stores per-file predictions and an aggregate report.

```bash
python eval_balanced.py --folder flac_D_ac/flac_D \
                        --keys ASVspoof5.dev.track_1.tsv \
                        --n 1500 --out results
```

Outputs under `--out/`:

- `predictions.tsv` — `filename  true_label  p_genuine  score_logprob  verdict  correct`
- `summary.json` — class counts, confusion matrix, accuracy, EER, config

Options: `--crop {start,center,loudest}`, `--normalize`, `--threshold`,
`--seed`, `--batch`, `--provider {cpu,openvino,cuda,dml}`. Re-running resumes
(skips files already in `predictions.tsv`). ~3 clips/s on CPU → `--n 1500` ≈ 8 min.

## Performance / notes

- CPU (`--provider cpu`): ~2–3 clips/s on a Core Ultra 7 255H. Clips are batched.
- Intel Arc iGPU: `pip install onnxruntime-openvino` then `--provider openvino`
  (fp16 — re-check your threshold, scores shift slightly vs CPU fp32).
- Speech only; non-speech audio gives meaningless scores.
- Trained on ASVspoof 2019 LA. Strong spoof recall, some genuine clips get
  false-flagged — expect out-of-domain EER from ~4 % up to 20–30 %.
- Not for training/fine-tuning on this machine.
