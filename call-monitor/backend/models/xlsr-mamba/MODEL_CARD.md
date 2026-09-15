---
base_model: AustinXiao/XLSR-Mamba-LA
tags:
  - audio-classification
  - anti-spoofing
  - deepfake-detection
  - audio-deepfake-detection
  - mamba
  - wav2vec2
  - multilingual
  - hindi
  - bengali
  - tamil
license: mit
license_note: see "Licensing" section — training data carries an additional NC restriction
datasets:
  - SPRINGLab/IndicVoices-R_Hindi
  - SPRINGLab/IndicVoices-R_Bengali
  - SPRINGLab/IndicVoices-R_Tamil
  - vdivyasharma/IndicSynth
language:
  - hi
  - bn
  - ta
---

# XLSR-Mamba — Indic Multilingual Fine-tune

A fine-tune of [XLSR-Mamba](https://arxiv.org/abs/2411.10027) (dual-column bidirectional
Mamba state-space model on a frozen wav2vec 2.0 / XLSR backbone) for **audio deepfake
detection in Hindi, Bengali, and Tamil**, trained to stay accurate after WhatsApp-style
Opus compression.

Full write-up, confusion matrices, and every number below: see `field_report.pdf` /
`field_report.html` in this release, or the companion repo's `results_indic/README.md`.

## Files

| File | Size | What it is |
|---|---:|---|
| `model_indic_ft.safetensors` | 1.27 GB | **Full checkpoint** — frozen XLSR-2.0 backbone + front-end + the fine-tuned head. Self-contained: load this alone. |
| `conformer_head_only.safetensors` | 7.2 MB | **Just the fine-tuned head** (129 tensors, 1.79M params). Requires the original base checkpoint's backbone weights alongside it — see loading code below. Share this when bandwidth matters. |
| `load_model.py` | — | Minimal loader for either file, using the architecture in the companion repo's `evaluate_model.py`. |

## What changed vs. the base model

Only `model.conformer` — the dual-column Mamba classification head — was retrained.
The wav2vec 2.0 / XLSR backbone (317.5M params) and the `LL` + `first_bn` front-end
are **byte-identical** to the base checkpoint. That means:

- `model_indic_ft.safetensors` and the base `model.safetensors` differ in exactly 129
  of 565 tensors.
- You can reconstruct the full fine-tuned model from the base checkpoint plus
  `conformer_head_only.safetensors` (see below) instead of downloading the full 1.27GB
  file again if you already have the base weights.

## Metrics

| | Base model | This fine-tune |
|---|---:|---:|
| ASVspoof5 (English-centric benchmark, dev subset) | **2.77%** EER | 21.28% EER |
| Indic deepfakes — Hindi/Bengali/Tamil, held-out test | 46.9% EER | **0.31%** EER |
| — clean audio | 48.3% EER | 99.69% accuracy |
| — WhatsApp-compressed audio | 46.1% EER | 99.69% accuracy |

**Read this both ways.** This checkpoint is dramatically better at Hindi/Bengali/Tamil
deepfake detection and is robust to WhatsApp-grade Opus compression by construction.
It is also dramatically *worse* than the base model at the original ASVspoof task —
a textbook case of catastrophic forgetting from fine-tuning a small head on a narrow
new distribution. **Pick the checkpoint that matches your traffic**, don't assume this
one is a strict upgrade.

## Intended use

Screening Hindi, Bengali, or Tamil speech for TTS/voice-conversion deepfakes, including
audio that has passed through a lossy messaging-app codec (Opus/WhatsApp-style, 16kHz
mono ~24kbps). Binary output: `bonafide` (real) vs. `spoof` (fake); score = the
bonafide-class logit, `out[:, 1]`.

**Not** validated for: languages outside hi/bn/ta, attack types beyond the TTS/VC
systems in IndicSynth (notably FreeVC24 and related voice-conversion models), or as a
drop-in replacement for the base model on ASVspoof-style benchmarks (see Metrics).

## How to load

```python
from evaluate_model import Model          # from the companion repo
from safetensors.torch import load_file

model = Model(emb_size=144, num_encoders=12)
model.load_state_dict(load_file("model_indic_ft.safetensors"), strict=False)
model.eval()
```

To reconstruct from the lightweight head-only file instead of the full checkpoint:

```python
from safetensors import safe_open
from safetensors.torch import load_file

sd = load_file("model.safetensors")               # base checkpoint (backbone + front-end)
with safe_open("conformer_head_only.safetensors", "pt") as f:
    for k in f.keys():
        sd[k] = f.get_tensor(k)                    # overwrite the 129 conformer.* tensors
model.load_state_dict(sd, strict=False)
```

## Training data

| Role | Source | License |
|---|---|---|
| bonafide (real) | `SPRINGLab/IndicVoices-R_{Hindi,Bengali,Tamil}` | CC-BY-4.0 |
| spoof (fake) | `vdivyasharma/IndicSynth` | **CC-BY-NC-4.0** |

17,236 clips (~2.9GB), 16kHz mono, ≤6s, speaker-disjoint 80/10/10 split. Half of every
training clip (and both variants of every dev/test clip) passed through Opus
compression at WhatsApp-typical settings before use.

## Licensing

The base model and this repo's code are **MIT**. `IndicSynth`, one of the two training
datasets, is licensed **CC-BY-NC-4.0** (non-commercial). Whether a model's *weights*
inherit a training dataset's NC restriction is genuinely unsettled and jurisdiction-
dependent — this is disclosed so you can make that call yourself rather than have it
made silently. **If you plan to use or redistribute this checkpoint commercially,
get your own legal read on that question first**; for non-commercial and research use
it's not a concern.

## Limitations

- Small held-out sets per language (Bengali dev: 454 clips, Tamil dev: 258) — treat
  per-language numbers as indicative, not tight statistical estimates.
- Only the TTS/voice-conversion systems represented in IndicSynth are covered; novel
  attack types are unvalidated.
- Catastrophic forgetting on the original ASVspoof task (above) is real and
  unmitigated in this checkpoint — no joint training, replay buffer, or EWC penalty
  was used.
- Trained on a 2.9GB corpus (scaled down from a 6GB target — see the field report for
  why); more data would likely help.

## Citation

```bibtex
@article{xiao2024xlsr,
  title={{XLSR-Mamba}: A Dual-Column Bidirectional State Space Model for Spoofing Attack Detection},
  author={Xiao, Yang and Das, Rohan Kumar},
  journal={arXiv preprint arXiv:2411.10027},
  year={2024}
}
```
