# XLSR-Mamba — Multilingual Voice Deepfake Detection

A benchmark and multilingual fine-tune of **XLSR-Mamba** — a dual-column bidirectional
Mamba state-space model on a frozen wav2vec 2.0 (XLSR) backbone — for detecting voice
deepfakes. Starts from the model's published ASVspoof5 performance, then extends it to
catch Hindi, Bengali, and Tamil TTS/voice-conversion deepfakes that survive
WhatsApp-grade Opus compression.

Full narrative report with every chart and confusion matrix:
**[`results_indic/XLSR-Mamba-Field-Report.pdf`](results_indic/XLSR-Mamba-Field-Report.pdf)**
(or the interactive [`field_report.html`](results_indic/field_report.html)).

## Results

| | Metric | Before | After Indic fine-tune |
|---|---|---:|---:|
| ASVspoof5 (English-centric benchmark) | EER | **2.77%** | 21.28% |
| Indic deepfakes (Hindi/Bengali/Tamil, held-out test) | EER | 46.9% | **0.31%** |
| — clean audio | accuracy | — | 99.69% |
| — WhatsApp-compressed audio | accuracy | — | 99.69% |

The fine-tune is a **~151× reduction** in error rate on the task it targets — and a
**~7.7× regression** on the original benchmark (catastrophic forgetting from retraining
only the classification head). Both numbers are real; see "Two models, two jobs" below
before picking a checkpoint.

## Architecture

```
waveform (16kHz) -> XLSR-2.0 (317.5M, frozen) -> Linear+BN+SELU -> dual-column
Mamba conformer (1.79M, trainable) -> bonafide / spoof
```

Only the classifier head — six bidirectional Mamba layers with learned-attention
pooling, 1.79M of 319.3M total params — is trained. The backbone's output for a given
clip is therefore a fixed function of the waveform, so features are cached once and
training runs on the cache in minutes rather than hours.

Reference: Xiao & Das, *"XLSR-Mamba: A Dual-Column Bidirectional State Space Model for
Spoofing Attack Detection"*, [arXiv:2411.10027](https://arxiv.org/abs/2411.10027).

## Two models, two jobs

| Checkpoint | Use it for |
|---|---|
| `model.safetensors` (base, not included — see Weights) | General ASVspoof-style spoofing detection |
| `model_indic_ft.safetensors` (fine-tuned, not included — see Weights) | Hindi/Bengali/Tamil deepfake screening, including WhatsApp-compressed audio |

They share the same frozen backbone and differ in exactly 129 of 565 tensors (the
head). Neither is a strict upgrade of the other — pick by traffic.

## Repo layout

```
scripts/                   all code
  evaluate_model.py           ASVspoof5 eval (+ the "forgetting check" reuses this)
  build_indic_dataset.py      streams IndicVoices-R (real) + IndicSynth (fake), bakes
                               in WhatsApp-Opus compression, writes indic_df/manifest.tsv
  cache_features.py           precomputes frozen-backbone features -> indic_df/feat/
  finetune_indic.py           trains the conformer head on cached features
  evaluate_indic.py           EER by language / by codec on cached features
  confusion_indic.py          confusion matrices at the EER threshold (CPU-only, cheap)
  confusion_matrix.py         EER-threshold confusion matrix for ASVspoof scores
  threshold_sweep.py          full FAR/FRR/accuracy/F1 sweep across thresholds
  plot_results.py             score distributions / ROC / DET / metrics-vs-threshold
  run_indic_pipeline.sh       chains cache -> baseline -> finetune -> eval -> forgetting check
  fairseq_src/fairseq/        vendored wav2vec2 modules (trimmed to what's imported)
results/                   ASVspoof5 baseline: metrics, confusion matrix, threshold
                            sweep, plots (results/RESULTS.md is the write-up)
results_indic/              Indic fine-tune: metrics, confusion matrices, training
                            log, the full PDF/HTML field report
release/
  xlsr-mamba-indic-ft-lite.zip   shareable package: fine-tuned head only (7.2MB) +
                                 model card + loader + trimmed fairseq_src
  WEIGHTS_README.md              what's in the (not-included) full checkpoints
```

## Weights

The two full checkpoints (1.27GB each) and the ASVspoof5 protocol files / audio
(tens of GB) are **not committed here** — see `results/RESULTS.md` and
`results_indic/README.md` for exactly how to regenerate them, or grab
`release/xlsr-mamba-indic-ft-lite.zip` for the fine-tuned head alone (7.2MB; merges
onto a base checkpoint you provide — see the model card inside).

## Setup

```bash
cd scripts
pip install torch --index-url https://download.pytorch.org/whl/cu128  # or the CPU wheel
pip install safetensors soundfile scipy numpy tqdm datasets huggingface_hub av
```

`fairseq_src/fairseq` is vendored here (trimmed to only the `Wav2Vec2Model` /
`Wav2Vec2Config` code path actually imported); no separate fairseq install needed.

## Usage

```bash
cd scripts
# ASVspoof5 baseline (needs model.safetensors + the ASVspoof5 dataset alongside)
python evaluate_model.py --max_samples 9000 --seed 1234 --device cuda

# Build the Indic corpus, then run the full fine-tuning pipeline
python build_indic_dataset.py --target_gb 6      # resumable; network-bound
bash run_indic_pipeline.sh

# Confusion matrix for a trained checkpoint
python confusion_indic.py --model_path model_indic_ft.safetensors --split test
```

## Data & licensing

| Role | Source | License |
|---|---|---|
| ASVspoof5 benchmark | [ASVspoof5 Challenge](https://www.asvspoof.org/) | Challenge terms |
| Indic real speech | `SPRINGLab/IndicVoices-R_{Hindi,Bengali,Tamil}` | CC-BY-4.0 |
| Indic fake speech | `vdivyasharma/IndicSynth` | **CC-BY-NC-4.0** |

Base model and code: MIT. `IndicSynth` is non-commercial — whether that restricts
redistributing *weights* trained on it is genuinely unsettled; get your own legal read
before commercial use. Full discussion in the field report and
`release/xlsr-mamba-indic-ft-lite.zip`'s model card.

## Limitations

Small per-language dev/test sets, only the TTS/VC systems present in IndicSynth are
covered, unmitigated catastrophic forgetting on the original task, and the Indic
corpus was scaled down from a 6GB target to ~2.9GB after HuggingFace's streaming API
made repeated resume too expensive. Full detail, including the honest failure modes,
is in the field report — it's not swept under the rug.

## Citation

```bibtex
@article{xiao2024xlsr,
  title={{XLSR-Mamba}: A Dual-Column Bidirectional State Space Model for Spoofing Attack Detection},
  author={Xiao, Yang and Das, Rohan Kumar},
  journal={arXiv preprint arXiv:2411.10027},
  year={2024}
}
```
