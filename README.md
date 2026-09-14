# XLSR-Mamba — Multilingual Voice Deepfake Detection

A benchmark and multilingual fine-tune of **XLSR-Mamba** — a dual-column bidirectional
Mamba state-space model on a frozen wav2vec 2.0 (XLSR) backbone — for detecting voice
deepfakes. Starts from the model's published ASVspoof5 performance, extends it to
Hindi/Bengali/Tamil, then to Malayalam/Gujarati, diagnoses and fixes a Malayalam-specific
failure, and finally tests zero-shot generalization to 6 more Indic languages the model
has never trained on at all.

Full narrative report with every chart, diagram, and confusion matrix:
**[`results_indic/XLSR-Mamba-Field-Report.pdf`](results_indic/XLSR-Mamba-Field-Report.pdf)**
(or the interactive [`field_report.html`](results_indic/field_report.html)) — 14 sections,
§1–§14, telling the whole story including the dead ends.

## The short version

| Stage | Result |
|---|---:|
| ASVspoof5 baseline (English-centric benchmark) | 2.77% EER |
| + fine-tune on Hindi/Bengali/Tamil | 0.31% EER on Indic test, but 21.28% EER on ASVspoof5 (forgetting) |
| + domain-adversarial training (chasing cross-lingual robustness) | in-domain slightly better (0.52%), cross-lingual: statistical wash |
| + fold Malayalam & Gujarati into training directly | **99.85% accuracy / 0.16% EER across all 5 languages**, Malayalam 31.64%→0.00% EER |
| Zero-shot test on 6 more languages never trained on | **98.44% mean accuracy** (Kannada, Marathi, Punjabi, Telugu); Sanskrit the one outlier at 4.80% EER |

The headline finding: the frozen backbone's features were *already* separable for
Malayalam (98.67% linear-probe accuracy) — the failure was a missing-training-data
problem, not an architecture or backbone-coverage problem (verified by testing a
backbone pretrained on 1000+ languages, which did no better). Once that was fixed with
data instead of a bigger model, the fix generalized to 4 of 5 completely fresh
languages almost for free.

## Architecture

```
waveform (16kHz) -> XLSR-2.0 (317.5M, frozen) -> Linear+BN+SELU -> dual-column
Mamba conformer (1.79M, trainable) -> bonafide / spoof
```

Only the classifier head — six bidirectional Mamba layers with learned-attention
pooling, 1.79M of 319.3M total params — is ever trained. The backbone's output for a
given clip is a fixed function of the waveform, so features are cached once and
training runs on the cache in minutes rather than hours.

Reference: Xiao & Das, *"XLSR-Mamba: A Dual-Column Bidirectional State Space Model for
Spoofing Attack Detection"*, [arXiv:2411.10027](https://arxiv.org/abs/2411.10027).

## Checkpoints (full weights not committed here — see Weights)

| Checkpoint | Trained on | Use it for |
|---|---|---|
| `model.safetensors` (base) | ASVspoof5 | General ASVspoof-style spoofing detection |
| `model_indic_ft.safetensors` | hi/bn/ta | First Indic fine-tune — superseded by the 5-lang checkpoint below for those languages |
| `model_indic_ft_agnostic.safetensors` | hi/bn/ta + domain-adversarial training | Studying the DANN/gradient-reversal technique itself; not a clear upgrade in practice |
| `model_indic_ft_5lang.safetensors` | **hi/bn/ta/ml/gu, jointly** | **Recommended.** Best in-domain numbers, and the checkpoint that generalized zero-shot to 6 more languages |

## Repo layout

```
scripts/                        all code
  evaluate_model.py                ASVspoof5 eval + shared Model/SSLModel/MixerModel classes
  build_indic_dataset.py           streams real+fake speech for 5 Indic languages, bakes in
                                    WhatsApp-Opus compression, shard-level resumable
  cache_features.py                precomputes frozen-backbone features -> indic_df/feat/
  finetune_indic.py                trains the conformer head on cached features (plain)
  finetune_language_agnostic.py    same, + gradient-reversal language discriminator (DANN)
  evaluate_indic.py / confusion_indic.py   per-language / per-codec EER & confusion matrices
  confusion_all_languages.py       fixed-threshold confusion matrices across every corpus language
  evaluate_cross_lingual.py        scores a checkpoint on languages excluded from training
  probe_mms_vs_xlsr.py             backbone-coverage diagnostic: linear-probe separability, XLSR vs MMS-300m
  test_new_language.py             zero-shot probe: pulls fresh real+fake audio for ANY language,
                                    scores it against any checkpoint - no retraining
  test_6th_language.py             the original single-language (Kannada) version of the above
  extract_head_diff.py             extracts + verifies the fine-tuned-head-only delta from a full checkpoint
  plot_first_finetune.py           reconstructs training-curve plots from a run's console log
  confusion_matrix.py / threshold_sweep.py / plot_results.py   ASVspoof5-side analysis/plots
  run_indic_pipeline.sh            chains cache -> baseline -> finetune -> eval -> forgetting check
  fairseq_src/fairseq/             vendored wav2vec2 modules (trimmed to what's imported)
results/                        ASVspoof5 baseline: metrics, confusion matrix, threshold
                                 sweep, plots (results/RESULTS.md is the write-up)
results_indic/                  every Indic-side result: training logs (3-lang, agnostic,
                                 5-lang), confusion-matrix CSVs, cross-lingual and zero-shot
                                 eval CSVs, training-curve PNG, and the full PDF/HTML field report
release/
  xlsr-mamba-indic-ft-lite.zip          fine-tuned head only for model_indic_ft.safetensors (7.2MB)
  xlsr-mamba-indic-ft-agnostic-lite.zip same, for the domain-adversarial checkpoint (37MB, includes
                                        the updated field report + fairseq_src)
  xlsr-mamba-indic-ft-5lang-lite.zip    same, for the 5-language (best) checkpoint (37MB)
  WEIGHTS_README.md / WEIGHTS_README_v2.md   what's in the (not-included) full checkpoints
```

## Weights

Full checkpoints (1.27GB each) and the ASVspoof5 protocol audio (tens of GB) are **not
committed here** — they're well over GitHub's file-size limits. Instead:

- Each `release/*-lite.zip` ships the fine-tuned head only (6–7MB) plus a model card,
  loader script, and everything needed to reconstruct the full model from a base
  checkpoint you provide.
- `results/RESULTS.md` and `results_indic/README.md` document exactly how to
  regenerate every full checkpoint from scratch.

## Setup

```bash
cd scripts
pip install torch --index-url https://download.pytorch.org/whl/cu128  # or the CPU wheel
pip install safetensors soundfile scipy numpy tqdm datasets huggingface_hub av scikit-learn transformers matplotlib
```

`fairseq_src/fairseq` is vendored here (trimmed to only the `Wav2Vec2Model` /
`Wav2Vec2Config` code path actually imported); no separate fairseq install needed.
`transformers` and `scikit-learn` are only needed for `probe_mms_vs_xlsr.py`.

## Usage

```bash
cd scripts

# ASVspoof5 baseline (needs model.safetensors + the ASVspoof5 dataset alongside)
python evaluate_model.py --max_samples 9000 --seed 1234 --device cuda

# Build the Indic corpus (5 languages), then run the full fine-tuning pipeline
python build_indic_dataset.py --target_gb 6      # resumable; network-bound
bash run_indic_pipeline.sh

# Domain-adversarial variant instead of the plain fine-tune
python finetune_language_agnostic.py --epochs 12 --patience 4 --batch_size 64 --train_crop 100

# Confusion matrix across every language currently in the corpus, one fixed threshold
python confusion_all_languages.py --model_path model_indic_ft_5lang.safetensors \
    --train_langs hi,bn,ta,ml,gu --csv_out results_indic/confusion_all_languages_5lang.csv

# Zero-shot test on a language that's never been in the corpus at all
python test_new_language.py --lcode te --lname Telugu \
    --real_repo eswardivi/Telugu_ASR_corpus --real_field audio --n_per_class 250
```

## Data & licensing

| Role | Source | License |
|---|---|---|
| ASVspoof5 benchmark | [ASVspoof5 Challenge](https://www.asvspoof.org/) | Challenge terms |
| Indic real speech, hi/bn/ta | `SPRINGLab/IndicVoices-R_{Hindi,Bengali,Tamil}` | CC-BY-4.0 |
| Indic real speech, ml/gu | `asr-malayalam/indicvoices-v1a`, `PharynxAI/IndicVoices-gujarati-10000` | see source repos |
| Indic fake speech (all 5) | `vdivyasharma/IndicSynth` | **CC-BY-NC-4.0** |
| Zero-shot test languages | PharynxAI (kn/mr), `eswardivi/Telugu_ASR_corpus`, `aaparajit02/punjabi-asr`, `surajp/shrutilipi_sanskrit`, + `vdivyasharma/IndicSynth` for fakes | see source repos |

Base model and code: MIT. `IndicSynth` is non-commercial — whether that restricts
redistributing *weights* trained on it is genuinely unsettled; get your own legal read
before commercial use. Full discussion in the field report and each lite zip's model card.

## Limitations

Small per-language dev/test sets, only the TTS/VC systems present in IndicSynth are
covered, unmitigated catastrophic forgetting on the original ASVspoof task, domain-
adversarial training didn't deliver a clear cross-lingual win, and Sanskrit is a
genuine outlier among the zero-shot languages (likely a corpus-register mismatch —
liturgical/recited speech vs. the conversational speech used everywhere else — rather
than a confirmed language-specific weakness). Full detail, including every honest
failure mode, is in the field report (§14) — it's not swept under the rug.

## Citation

```bibtex
@article{xiao2024xlsr,
  title={{XLSR-Mamba}: A Dual-Column Bidirectional State Space Model for Spoofing Attack Detection},
  author={Xiao, Yang and Das, Rohan Kumar},
  journal={arXiv preprint arXiv:2411.10027},
  year={2024}
}
@article{ganin2016dann,
  title={Domain-Adversarial Training of Neural Networks},
  author={Ganin, Yaroslav and Lempitsky, Victor},
  journal={JMLR},
  year={2016}
}
```
