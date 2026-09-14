# XLSR-Mamba weights v2 — domain-adversarial + 5-language checkpoints

Companion to `WEIGHTS_README.md` (base + 3-language plain fine-tune) — that file and
its checkpoints are untouched. This describes the two checkpoints trained afterward,
same architecture (`Model(emb_size=144, num_encoders=12)` in `scripts/evaluate_model.py`),
319.3M params / 1.27GB each. **Full checkpoints are not committed here** (over
GitHub's file-size limit) — only the head-only lite bundles below are.

| Checkpoint | What it is | Lite bundle |
|---|---|---|
| `model_indic_ft_agnostic.safetensors` | hi/bn/ta head, trained with domain-adversarial (gradient-reversal) language discrimination. In-domain dev EER 0.52%, but cross-lingual generalization to Malayalam/Gujarati was a statistical wash vs. the plain fine-tune (12.50% vs 12.38% EER). | `xlsr-mamba-indic-ft-agnostic-lite.zip` |
| `model_indic_ft_5lang.safetensors` | **Current best checkpoint.** Head trained directly on hi/bn/ta/ml/gu jointly. 99.85% accuracy / 0.16% EER across all 5 languages' held-out test data, plus 98.44% mean accuracy on 5 more languages it never trained on at all (Kannada, Marathi, Punjabi, Telugu, Sanskrit). | `xlsr-mamba-indic-ft-5lang-lite.zip` |

Both differ from the original base checkpoint in exactly 109 of 565 tensors (the
classifier head only) — each lite zip's `conformer_head_only_*.safetensors` is ~6MB
and was verified byte-identical on reconstruction (`scripts/extract_head_diff.py`)
before packaging.

## Load either one

```python
from evaluate_model import Model
from safetensors.torch import load_file

model = Model(emb_size=144, num_encoders=12)
model.load_state_dict(load_file("model_indic_ft_5lang.safetensors"), strict=False)   # or model_indic_ft_agnostic.safetensors
model.eval()
```

Or reconstruct from a lite zip's head-only file + your own base checkpoint — see
`load_model.py` and the `MODEL_CARD.md` inside each lite zip.

## Which checkpoint should I use?

- **Best overall for Hindi/Bengali/Tamil/Malayalam/Gujarati, and decent odds on other
  Indic languages**: `model_indic_ft_5lang.safetensors`.
- **Studying domain-adversarial training itself**: `model_indic_ft_agnostic.safetensors`.
- **Original ASVspoof5 benchmark task**: the base checkpoint (see `WEIGHTS_README.md`)
  — every fine-tune in this series trades that task away (catastrophic forgetting,
  documented in the field report).

Full write-up, all numbers, and the zero-shot test on 5 additional never-before-seen
languages: `results_indic/XLSR-Mamba-Field-Report.pdf` §9–§14.
