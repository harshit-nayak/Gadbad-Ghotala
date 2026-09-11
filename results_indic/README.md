# Multilingual audio deepfake detection — Indic fine-tune

Fine-tuning XLSR-Mamba (the ASVspoof5 spoof detector, EER 2.77% on ASVspoof5 dev)
for **Hindi / Bengali / Tamil** deepfake detection, robust to messaging-app
compression.

## Data (`build_indic_dataset.py` -> `indic_df/`)

| class | source | notes |
|---|---|---|
| real (bonafide, label 1) | `SPRINGLab/IndicVoices-R_{Hindi,Bengali,Tamil}` | IndicVoices restored to studio quality, 48 kHz; ungated mirror of AI4Bharat IndicVoices |
| fake (spoof, label 0) | `vdivyasharma/IndicSynth` (Hindi/Bengali/Tamil configs) | TTS + voice-conversion deepfakes (freevc24, TTS models, ...), 24 kHz |

- All audio decoded to **16 kHz mono**, centre-cropped to ≤ 6 s.
- **Speaker-disjoint** train/dev/test ≈ 80/10/10 (speaker id hashed; real and fake
  speaker spaces kept separate).
- **WhatsApp-style lossy compression** baked in via PyAV / libopus:
  Opus, 16 kHz, mono, ~24 kbps, VoIP mode, then decoded back (Opus decodes at
  48 kHz → resampled to 16 kHz), i.e. the exact degradation path of a WhatsApp
  voice note.
  - train: each clip stored **either** `clean` **or** `whatsapp` (p = 0.5)
  - dev/test: each clip stored **both** ways → EER reported per condition
- Target size ≈ 6 GB of stored WAV (~50 h; 1 GB per language×class), filled
  round-robin so the corpus stays balanced at any stopping point. Resumable to a
  larger target later.
- Stored at `C:\Users\ATHARV\SIH_data\indic_df` (outside the OneDrive-synced
  project folder). Override with the `INDIC_DF` env var.
- `manifest.tsv`: `id lang label split codec speaker gender genmodel dur_s path`

## Model / fine-tuning

- `cache_features.py` — the XLSR-2.0 backbone **and** the `LL` / `first_bn`
  front-end are frozen, so the conformer input `SELU(first_bn(LL(xlsr)))` is a
  static function of the waveform. Computed once and memmapped to
  `indic_df/feat/<split>.dat` (float16 `[N, 208, 144]`).
- `finetune_indic.py` — trains **only** `model.conformer` (the dual-column Mamba
  head + classifier, ~1 M params) on the cached features. AdamW, class-balanced
  CE, cosine LR, light feature-space augmentation (frame mask + noise),
  dev-EER early stopping. Best checkpoint → `model_indic_ft.safetensors`.

## Evaluation

- `evaluate_indic.py` — EER overall / per-language / per-codec (clean vs
  whatsapp) / per-language×codec on the held-out test split.
- Forgetting check: the fine-tuned model re-run on ASVspoof5 dev (9 000-clip
  subset) — compare to the pre-fine-tune 2.77 % EER.

## Reproduce

```bash
python build_indic_dataset.py --target_gb 6       # resumable; ~2 h (network-bound)
bash run_indic_pipeline.sh                        # cache -> baseline -> finetune -> eval
```

## Corpus (final, as built)

Streaming resume turned out to be expensive (HF `datasets` streaming has no cheap
seek; resuming re-streams-and-discards every already-seen row, which got costly
as cursors grew past tens of thousands). Rather than pay repeated multi-hour
re-skips after transient stalls/interruptions, the corpus was finalized at
**~2.9 GB / 17,236 clips** instead of the original 6 GB target:

| lang | real (bonafide) | fake (spoof) |
|---|---:|---:|
| hi | 3,889 | 4,263 |
| bn | 3,178 | 1,967 |
| ta | 2,019 | 1,920 |

Each row is a `clean` or `whatsapp`-compressed clip; dev/test carry both variants
per source clip. Train/dev/test present for all 6 buckets.

## Results

_pending — populated after the pipeline run._
